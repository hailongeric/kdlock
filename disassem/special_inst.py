# Lower virtual CALL/RET/stack/control operations that cannot use plain copying.
# CALL pushes the source return address; POP/PUSH use virtual SP, not physical
# wrapper RSP. Processor-state instructions never execute in generated code;
# separately admitted native markers stop before their original source bytes.
import diagnostics
import instruction_policy
import native_escape
from assist import (conditional_branch, get_inst_name, im64_abs, make_inst,
                    make_mem_dict, unconditional_branch)
from conflict import (
    conflict_resolve,
    release_conflict,
    release_tmp_conflict,
    reverse_reg,
)
from miasm.expression.expression import ExprId, ExprInt, ExprLoc, ExprMem
from normal import process_normal

special_instruction = [
    "NOP",
    "CALL",
    "RET",
    "POP",
    "PUSH",
    "LEAVE",
    "ENDBR64",
]


def native_escape_marker(line, reg_map):
    """Stop before the reviewed source instruction, with no replay or CALL."""
    if not native_escape.descriptor(line):
        raise ValueError("unreviewed native escape instruction")
    code = release_conflict(reg_map)
    # MOV-only spill stores above retain the source arithmetic flags. Use the
    # executor's allocated stack for this temporary word, never the waiter SP.
    code += "PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]\n"
    code += make_inst("MOVABS", ["R14", hex(line.offset)])
    code += make_inst("MOV", ["Stack_IJ", str(native_escape.EXIT)])
    code += make_inst("JMP", ["full_exit"])
    return code


def terminal_clobber_unlock(target, continuation, reg_map):
    """Check the original CALL's metadata without touching the waiter stack.

    R13 is still the pre-CALL SP. Compare the static return PC instead of
    writing it and immediately reading it back. Only translator scratch
    registers change before the fallback, so every logical GPR remains exact.
    """
    fallback = f'kd_terminal_full_{continuation:x}'
    code = release_conflict(reg_map)
    code += make_inst('MOV', ['R15', 'Stack_CLOBBER'])
    code += make_inst('TEST', ['R15', 'R15'])
    code += make_inst('JZ', [fallback])
    code += make_inst('CMP', ['QWORD PTR[R15 + 88]', '0'])
    code += make_inst('JE', [fallback])
    code += make_inst('MOVABS', ['R14', hex(target)])
    for left, right in [('R14', 'QWORD PTR[R15 + 40]'),
                        ('RDI', 'QWORD PTR[R15 + 32]'), ('RSI', 'R13'),
                        ('RCX', 'R12')]:
        code += make_inst('CMP', [left, right])
        code += make_inst('JNE', [fallback])
    code += make_inst('MOVABS', ['R14', hex(continuation)])
    code += make_inst('CMP', ['RDX', 'R14'])
    code += make_inst('JNE', [fallback])
    code += make_inst('JMP', ['clobber_complete'])
    code += fallback + ':\n'
    code += make_inst('MOVABS', ['R15', hex(continuation)])
    code += make_inst('LEA', ['R13', '[R13 - 8]'])
    code += make_inst('MOV', ['QWORD PTR[R13]', 'R15'])
    code += make_inst('MOVABS', ['R14', hex(target)])
    code += make_inst('MOV', ['Stack_IJ', '1'])
    code += make_inst('JMP', ['full_exit'])
    return code


def process_jump(name, line, arg, offset, db, reg_map):
    ret_str = ""
    if isinstance(arg, ExprLoc):
        ret_str += release_conflict(reg_map)
        ret_str += make_inst(name, line.arg2str(arg, 0, db))
    elif isinstance(arg, ExprMem):
        ret_str = conflict_resolve(reg_map, {"T2"})
        ret_str += process_normal("MOV", [ExprId("RT2", 64), arg], offset, reg_map)
        ret_str += process_jump(name, line, ExprId("RT2", 64), offset, db, reg_map)
    elif isinstance(arg, ExprId):
        ret_str += release_conflict(reg_map)
        tmp = reverse_reg(reg_map, arg)
        if tmp != " ":
            dst_tgt = "R" + tmp
        else:
            dst_tgt = "Stack_R" + str(arg)[1:3]

        if dst_tgt != "R14":
            ret_str += make_inst("MOV", ["R14", dst_tgt])
        ret_str += make_inst(name, ["ij_" + hex(offset)[2:]])
    else:
        diagnostics.warn("UNRESOLVED_JUMP", "omit_jump", f"{name}: {arg}")
    return ret_str


def special_inst_dispatch(line, args, offset, db, reg_map, block_end):
    ret_str = ""
    name = get_inst_name(line)
    if name == "ENDBR64" or line.name == "NOP":
        # The pinned x86 decoder represents F3 90 as the prefixed NOP alias.
        # Retain its physical spin hint without introducing a runtime exit.
        # Do not reinterpret other NOP encodings or redundant prefixes.
        pause = (line.name == "NOP" and line.l == 2 and
                 bytes(getattr(line, "b", b"")) == b"\xf3\x90")
        ret_str += "PAUSE\n" if pause else "NOP\n"
        ret_str += release_conflict(reg_map, block_end)
    elif name == "CALL":
        ret_str += conflict_resolve(reg_map, {"T2"})
        ret_str += process_normal(
            "MOVABS", [ExprId("RT2", 64), ExprInt(offset, 64)], offset, reg_map
        )
        ret_str += process_push(ExprId("RT2", 64), offset, reg_map)
        ret_str += process_jump("JMP", line, args[0], offset, db, reg_map)
    elif name == "PUSH":
        ret_str += process_push(args[0], offset, reg_map)
        ret_str += release_conflict(reg_map, block_end)
    elif name == "POP":
        ret_str += process_pop(args[0], offset, reg_map)
        ret_str += release_conflict(reg_map, block_end)
    elif name == "RET":
        ret_str += conflict_resolve(reg_map, {"T2"})
        ret_str += process_pop(ExprId("RT2", 64), offset, reg_map)
        ret_str += process_jump("JMP", line, ExprId("RT2", 64), offset, db, reg_map)
    elif name == "LEAVE":
        ret_str += process_normal(
            "MOV", [ExprId("RSP", 64), ExprId("RBP", 64)], offset, reg_map
        )
        ret_str += process_pop(ExprId("RBP", 64), offset, reg_map)
        ret_str += release_conflict(reg_map, block_end)
    else:
        raise ValueError(f"unsupported special instruction: {name}")
    return ret_str


def process_push(arg, offset, reg_map):
    ret_str = ""
    ret_str += process_normal(
        "LEA",
        [ExprId("RSP", 64), make_mem_dict(64, ["RSP"], -1 * arg.size / 8)],
        offset,
        reg_map,
    )
    if not isinstance(arg, ExprMem):
        if isinstance(arg, ExprInt):
            arg = ExprInt(int(str(arg), 16), 32)
        ret_str += process_normal(
            "MOV" + im64_abs(arg),
            [make_mem_dict(arg.size, ["RSP"]), arg],
            offset,
            reg_map,
        )
    else:
        ret_str += conflict_resolve(reg_map, {"T1"})
        ret_str += process_normal("MOV", [ExprId("RT1", 64), arg], offset, reg_map)
        ret_str += process_normal(
            "MOV", [make_mem_dict(64, ["RSP"]), ExprId("RT1", 64)], offset, reg_map
        )
        release_tmp_conflict(reg_map)
    return ret_str


def process_pop(arg, offset, reg_map):
    ret_str = ""
    if not isinstance(arg, ExprMem):
        ret_str += process_normal(
            "MOV", [arg, make_mem_dict(64, ["RSP"])], offset, reg_map
        )
    else:
        ret_str += conflict_resolve(reg_map, {"T1"})
        ret_str += process_normal(
            "MOV", [ExprId("RT1", 64), make_mem_dict(64, ["RSP"])], offset, reg_map
        )
        ret_str += process_normal("MOV", [arg, ExprId("RT1", 64)], offset, reg_map)
        release_tmp_conflict(reg_map)

    ret_str += process_normal(
        "LEA",
        [ExprId("RSP", 64), make_mem_dict(64, ["RSP"], arg.size / 8)],
        offset,
        reg_map,
    )
    return ret_str


def translate(line, offset, db, reg_map, block_end, *, trusted_source=False):
    # Trusted translation skips source-safety admission. A known decoder alias
    # still cannot be reassembled as another instruction: that is a lowering
    # representation error, independent of whether the source is trusted.
    if trusted_source:
        error = instruction_policy.segment_encoding_policy_error(
            getattr(line, "b", b""))
        if error:
            raise ValueError("decoder cannot faithfully lower source encoding: " + error)
    # Checked-mode utility callers retain their historical instruction policy.
    if not trusted_source:
        reason = instruction_policy.rejection(line)
        if reason:
            raise ValueError(reason)
    args = line.args
    name = get_inst_name(line)
    if line.name in special_instruction:
        return special_inst_dispatch(line, args, offset, db, reg_map, block_end)
    elif line.name in conditional_branch or line.name in unconditional_branch:
        return process_jump(line.name, line, args[0], offset, db, reg_map)
    else:
        return process_normal(name, args, offset, reg_map) + release_conflict(
            reg_map, block_end
        )
