import diagnostics
from assist import get_inst_name, im64_abs, make_inst, make_mem_dict
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
    "PUSHF",
    "POPF",
    "ENDBR64",
    "SYSCALL",
    "INVLPG",
    "INT",
]


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
    if name == "ENDBR64" or line.name == "NOP" or name == "INT":
        if name == "INT":
            diagnostics.warn(
                "INT_AS_NOP", "emit_nop", "original interrupt behavior is omitted"
            )
        ret_str += "NOP\n"
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
    elif name == "SYSCALL":
        ret_str += make_inst("MOVABS", ["R14", hex(offset - 2)])
        ret_str += make_inst("JMP", ["comp_syscall"])
    elif name == "INVLPG":
        ret_str += make_inst("MOVABS", ["R14", hex(offset - 2)])
        ret_str += make_inst("JMP", ["ill_inst"])
    else:
        diagnostics.warn("UNSUPPORTED_SPECIAL", "omit_instruction", name)
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
