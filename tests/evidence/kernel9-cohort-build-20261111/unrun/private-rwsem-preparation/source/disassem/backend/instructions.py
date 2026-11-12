"""Original source-stack/control lowering with the selected KD register map.

The original UB-derived CALL/RET/stack pattern is retained. Code is constructed
privately before any instruction is emitted, so a representation/register-pool
failure can end that path before the source instruction. No native helper is
called and no source-name model, borrowed stack or admission analyzer is used.
"""

from copy import deepcopy

from miasm.expression.expression import ExprId, ExprInt, ExprMem, ExprOp

from .assist import get_inst_name, im64_abs, make_inst, make_mem_dict
from .conflict import (
    conflict_resolve,
    recover_stable,
    release_conflict,
    release_tmp_conflict,
    reverse_reg,
)
from .errors import LoweringInvariant, LoweringUnsupported
from .normal import NormalLowering


LEGACY_PREFIXES = frozenset({
    0x26, 0x2E, 0x36, 0x3E, 0x64, 0x65, 0x66, 0x67, 0xF0, 0xF2, 0xF3,
})
SEGMENT_PREFIXES = frozenset({0x26, 0x2E, 0x36, 0x3E, 0x64, 0x65})
IMPLICIT_MEMORY_OPCODES = frozenset({
    0x6C, 0x6D, 0x6E, 0x6F,
    0xA4, 0xA5, 0xA6, 0xA7, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xD7,
})
FLAGS_STACK = frozenset({
    "PUSHF", "PUSHFW", "PUSHFD", "PUSHFQ", "POPF", "POPFW", "POPFD", "POPFQ",
})


def opcode_bytes(raw):
    index = 0
    while index < len(raw) and (
        raw[index] in LEGACY_PREFIXES or 0x40 <= raw[index] <= 0x4F
    ):
        index += 1
    return raw[:index], raw[index:]


def implicit_memory(opcode):
    # INS/OUTS, strings, XLAT and MASKMOV retain an EA outside explicit args.
    return bool(opcode and (opcode[0] in IMPLICIT_MEMORY_OPCODES
                            or opcode.startswith(b"\x0f\xf7")))


def lowering_instruction(record):
    """Retain the source record; mutate only this build's instruction copy."""

    line = deepcopy(record.backend_instruction)
    if (line.offset != record.site or line.l != record.length
            or bytes(line.b) != record.raw or line.name != record.name
            or tuple(line.args) != record.operands):
        raise LoweringInvariant("backend instruction disagrees with retained source identity")
    line.args = list(line.args)
    # Rebuild the original duplicate-base/index LEA case from complete source
    # bytes. Legacy prefixes may precede REX; only the final prefix can be an
    # effective REX. No-index/no-base SIB encodings are distinct cases.
    prefixes, opcode = opcode_bytes(record.raw)
    rex = prefixes[-1] if prefixes and 0x40 <= prefixes[-1] <= 0x4F else 0
    if (line.name == "LEA" and len(line.args) == 2 and len(opcode) >= 3
            and opcode[0] == 0x8D and opcode[1] & 7 == 4
            and opcode[1] >> 6 != 3):
        mod, sib = opcode[1] >> 6, opcode[2]
        index, base = (sib >> 3) & 7, sib & 7
        same_register = index == base and bool(rex & 2) == bool(rex & 1)
        no_index = index == 4 and not rex & 2
        no_base = mod == 0 and base == 5
        if same_register and not no_index and not no_base:
            displacement_bytes = 1 if mod == 1 else 4 if mod == 2 else 0
            if len(opcode) != 3 + displacement_bytes or not isinstance(line.args[1], ExprMem):
                raise LoweringUnsupported("duplicate-register LEA has no exact retained byte form")
            bits = 32 if 0x67 in prefixes else 64
            names = (("EAX", "ECX", "EDX", "EBX", "ESP", "EBP", "ESI", "EDI")
                     if bits == 32 else
                     ("RAX", "RCX", "RDX", "RBX", "RSP", "RBP", "RSI", "RDI"))
            register = (f"R{base + 8}D" if bits == 32 else f"R{base + 8}") if rex & 1 else names[base]
            source = ExprId(register, bits)
            terms = [ExprOp("*", source, ExprInt((1 << (sib >> 6)) + 1, bits))]
            if displacement_bytes:
                displacement = int.from_bytes(opcode[3:], "little", signed=True)
                terms.append(ExprInt(displacement & ((1 << bits) - 1), bits))
            # LEA ignores the segment base; this new tree changes no retained
            # decoder leaf and preserves each encoded source EA contribution.
            pointer = terms[0] if len(terms) == 1 else ExprOp("+", *terms)
            line.args[1] = ExprMem(pointer, line.args[1].size)
    return line


def validate_representation(line):
    """Reject known decoder aliases as construction gaps, not source policy."""

    prefixes, opcode = opcode_bytes(bytes(line.b))
    if implicit_memory(opcode) and SEGMENT_PREFIXES.intersection(prefixes):
        # Miasm stores these implicit EAs only in prefix metadata, not args.
        # Per-iteration origin-segment/address-width effects are not rewritten.
        raise LoweringUnsupported("segment-overridden implicit source memory has no origin lowering")
    if (line.breakflow() or line.dstflow() or line.is_subcall()) and (
        {0xF0, 0xF2, 0xF3}.intersection(prefixes)
        or line.name in {"CALL", "JMP"} and 0x3E in prefixes
    ):
        raise LoweringUnsupported("source control prefix has no equivalent lowered transfer")
    if opcode.startswith(b"\x0f\x01\xf8") or (
        0xF3 in prefixes and opcode.startswith(b"\x0f\xae")
        and len(opcode) >= 3 and opcode[2] & 0xE0 == 0xC0
    ):
        raise LoweringUnsupported("decoder aliases a direct FS/GS-base instruction")


class InstructionLowering:
    def __init__(self, current_task_offset):
        self.normal = NormalLowering(current_task_offset)

    def flush(self, reg_map):
        # A new source label always imports this canonical block-local map.
        release_tmp_conflict(reg_map)
        return release_conflict(reg_map) + recover_stable(reg_map, set())

    def push(self, arg, offset, reg_map, width=8):
        bits = width * 8
        code = conflict_resolve(reg_map, {"T1"}, offset)
        if isinstance(arg, ExprInt):
            value = int(arg)
            if arg.size < bits and value & (1 << (arg.size - 1)):
                value |= ((1 << bits) - 1) ^ ((1 << arg.size) - 1)
            arg = ExprInt(value & ((1 << bits) - 1), bits)
        # Evaluate PUSH RSP and stack-relative memory against pre-push SP.
        # The source value is retained before the one source-stack write.
        code += self.normal.process_normal(
            "MOV" + im64_abs(arg), [ExprId("RT1", bits), arg], offset, reg_map
        )
        code += self.normal.process_normal(
            "LEA", [ExprId("RSP", 64), make_mem_dict(64, ["RSP"], -width)],
            offset, reg_map,
        )
        code += self.normal.process_normal(
            "MOV", [make_mem_dict(bits, ["RSP"]), ExprId("RT1", bits)],
            offset, reg_map,
        )
        return code

    def pop(self, arg, offset, reg_map, width=8):
        bits = width * 8
        temporary = "T2" if str(arg).startswith("RT2") else "T1"
        code = conflict_resolve(reg_map, {temporary}, offset)
        value = ExprId("R" + temporary, bits)
        code += self.normal.process_normal(
            "MOV", [value, make_mem_dict(bits, ["RSP"])], offset, reg_map
        )
        code += self.normal.process_normal(
            "LEA", [ExprId("RSP", 64), make_mem_dict(64, ["RSP"], width)],
            offset, reg_map,
        )
        # POP RSP assigns the loaded value after the stack increment. A memory
        # destination likewise computes any source-SP address after increment.
        code += self.normal.process_normal("MOV", [arg, value], offset, reg_map)
        return code

    def resolve_target(self, arg, offset, reg_map):
        # Evaluate using the unchanged source SP/registers. A memory target may
        # need both mapped scratch registers, so preserve physical RAX briefly.
        code = make_inst("PUSH", ["RAX"])
        code += self.normal.process_normal("MOV", [ExprId("RAX", 64), arg], offset, reg_map)
        code += make_inst("MOV", ["Stack_TARGET", "RAX"])
        code += make_inst("POP", ["RAX"])
        return code

    def require_call_form(self, line):
        validate_representation(line)
        prefixes, _ = opcode_bytes(bytes(line.b))
        rex_w = bool(prefixes and 0x48 <= prefixes[-1] <= 0x4F)
        if (line.name != "CALL" or len(line.args) != 1
                or line.args[0].size != 64 or 0x66 in prefixes and not rex_w):
            raise LoweringUnsupported("only the eight-byte near source CALL is implemented")

    def require_jump_form(self, line):
        validate_representation(line)
        prefixes, _ = opcode_bytes(bytes(line.b))
        rex_w = bool(prefixes and 0x48 <= prefixes[-1] <= 0x4F)
        if (line.name != "JMP" or len(line.args) != 1
                or line.args[0].size != 64 or 0x66 in prefixes and not rex_w):
            raise LoweringUnsupported("only the eight-byte near source JMP target is implemented")

    def stage_call(self, continuation, reg_map):
        """Stage the actual source return word without evaluating a target."""
        code = conflict_resolve(reg_map, {"T1"}, continuation)
        code += self.normal.process_normal(
            "MOVABS", [ExprId("RT1", 64), ExprInt(continuation, 64)],
            continuation, reg_map,
        )
        code += self.push(ExprId("RT1", 64), continuation, reg_map)
        return code + self.flush(reg_map)

    def call(self, line, continuation, target, reg_map):
        self.require_call_form(line)
        code = ""
        if target is None:
            code += self.resolve_target(line.args[0], continuation, reg_map)
        code += self.stage_call(continuation, reg_map)
        if target is None:
            code += make_inst("MOV", ["R14", "Stack_TARGET"])
        else:
            code += make_inst("MOVABS", ["R14", hex(target)])
        return code

    def ret(self, line, offset, reg_map):
        validate_representation(line)
        prefixes, opcode = opcode_bytes(bytes(line.b))
        rex_w = bool(prefixes and 0x48 <= prefixes[-1] <= 0x4F)
        if (not opcode or opcode[0] not in {0xC2, 0xC3}
                or 0x66 in prefixes and not rex_w):
            raise LoweringUnsupported("only the eight-byte near source return is implemented")
        code = conflict_resolve(reg_map, {"T2"}, offset)
        code += self.pop(ExprId("RT2", 64), offset, reg_map)
        if line.args:
            if len(line.args) != 1 or not isinstance(line.args[0], ExprInt):
                raise LoweringUnsupported("RET adjustment has no immediate representation")
            code += self.normal.process_normal(
                "LEA", [ExprId("RSP", 64), make_mem_dict(64, ["RSP"], int(line.args[0]))],
                offset, reg_map,
            )
        physical = reverse_reg(reg_map, "RT2")
        if physical == " ":
            raise LoweringUnsupported("RET target is not retained in its mapped temporary")
        code += make_inst("MOV", ["Stack_TARGET", "R" + physical])
        code += self.flush(reg_map)
        code += make_inst("MOV", ["R14", "Stack_TARGET"])
        return code

    def flags_stack(self, line, offset, reg_map):
        prefixes, opcode = opcode_bytes(bytes(line.b))
        rex_w = bool(prefixes and 0x48 <= prefixes[-1] <= 0x4F)
        if (line.args or not opcode or opcode[0] not in {0x9C, 0x9D}
                or 0x66 in prefixes and not rex_w):
            raise LoweringUnsupported("only the eight-byte flags-stack form is implemented")
        code = conflict_resolve(reg_map, {"T1"}, offset)
        if opcode[0] == 0x9C:
            physical = reverse_reg(reg_map, "RT1")
            code += "PUSHFQ\n" + make_inst("POP", ["R" + physical])
            code += self.push(ExprId("RT1", 64), offset, reg_map)
        else:
            code += self.pop(ExprId("RT1", 64), offset, reg_map)
            physical = reverse_reg(reg_map, "RT1")
            code += make_inst("PUSH", ["R" + physical]) + "POPFQ\n"
        # Only the lowered source push/pop changes virtual SP. Physical flag
        # temporaries are balanced, and the mapped source values remain valid.
        return code + self.flush(reg_map)

    def ordinary(self, line, offset, reg_map):
        validate_representation(line)
        if line.breakflow() or line.dstflow() or line.is_subcall():
            raise LoweringInvariant("source control transfer bypassed its typed lowering")
        if line.name == "ENTER":
            raise LoweringUnsupported("implicit source ENTER frame construction is not implemented")
        name = get_inst_name(line)
        if line.name == "NOP":
            code = "PAUSE\n" if bytes(line.b) == b"\xf3\x90" else "NOP\n"
        elif line.name == "ENDBR64":
            code = "ENDBR64\n"
        elif line.name in FLAGS_STACK:
            return self.flags_stack(line, offset, reg_map)
        elif line.name in {"PUSH", "POP"}:
            prefixes, _ = opcode_bytes(bytes(line.b))
            rex_w = bool(prefixes and 0x48 <= prefixes[-1] <= 0x4F)
            width = 2 if 0x66 in prefixes and not rex_w else 8
            method = self.push if line.name == "PUSH" else self.pop
            code = method(line.args[0], offset, reg_map, width)
        elif line.name == "LEAVE":
            prefixes, _ = opcode_bytes(bytes(line.b))
            rex_w = bool(prefixes and 0x48 <= prefixes[-1] <= 0x4F)
            if 0x66 in prefixes and not rex_w:
                raise LoweringUnsupported("only the eight-byte source LEAVE is implemented")
            code = self.normal.process_normal(
                "MOV", [ExprId("RSP", 64), ExprId("RBP", 64)], offset, reg_map
            )
            code += self.pop(ExprId("RBP", 64), offset, reg_map)
        else:
            code = self.normal.process_normal(name, line.args, offset, reg_map)
            prefixes, opcode = opcode_bytes(bytes(line.b))
            if implicit_memory(opcode) and 0x67 in prefixes:
                # The implicit SI/DI/BX and repeat-count width has no operand
                # spelling. Keep address-size on the actual source instruction.
                code = ".byte 0x67\n" + code
        return code + self.flush(reg_map)
