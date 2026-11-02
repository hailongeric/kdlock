"""Returning original-CPU service for exact unlocked GS memory INC/DEC."""

from conflict import release_conflict
from assist import make_inst
from normal import segment_operand

EXIT = 13
REQUIREMENT = 1 << 10
MAX_SITES = 1024
OPERATIONS = {"INC": 1, "DEC": 2}


def is_gs_mutation(line):
    name = line.name.upper()
    # These memory operands are inputs even when printed as argument zero.
    read_only = {"CMP", "TEST", "BT", "PUSH", "CALL", "JMP", "MUL", "IMUL",
                 "DIV", "IDIV", "NOP", "PREFETCHNTA", "PREFETCHT0", "PREFETCHT1",
                 "PREFETCHT2", "PREFETCH0", "PREFETCH1", "PREFETCH2", "PREFETCHW",
                 "PREFETCHWT1"}
    exchange = {"XCHG", "XADD", "CMPXCHG", "CMPXCHG8B", "CMPXCHG16B"}
    return any(segment_operand(arg)[0] == "GS" and
               (name in exchange or (index == 0 and name not in read_only))
               for index, arg in enumerate(line.args))


def descriptor(line):
    if line.name.upper() not in OPERATIONS or len(line.args) != 1:
        return None
    segment, _ = segment_operand(line.args[0])
    if segment != "GS" or line.args[0].size not in (32, 64):
        return None
    raw = bytes(line.b)
    if not raw or len(raw) != line.l or raw[0] != 0x65:
        return None
    cursor = 1
    rex = 0
    if cursor < len(raw) and 0x40 <= raw[cursor] <= 0x4f:
        rex, cursor = raw[cursor], cursor + 1
    if cursor + 2 > len(raw) or raw[cursor] != 0xff:
        return None
    modrm = raw[cursor + 1]
    cursor += 2
    mod, extension, rm = modrm >> 6, (modrm >> 3) & 7, modrm & 7
    if mod == 3 or extension != OPERATIONS[line.name.upper()] - 1:
        return None
    if rm == 4:
        if cursor >= len(raw):
            return None
        base = raw[cursor] & 7
        cursor += 1
        if mod == 0 and base == 5:
            cursor += 4
    elif mod == 0 and rm == 5:
        cursor += 4
    cursor += 1 if mod == 1 else 4 if mod == 2 else 0
    width = 64 if rex & 8 else 32
    if cursor != len(raw) or len(raw) > 15 or width != line.args[0].size:
        return None
    return OPERATIONS[line.name.upper()], width


def sites(blocks):
    offsets = {line.offset for block in blocks.values() for line in block.lines}
    selected = {}
    for block in blocks.values():
        for line in block.lines:
            if not is_gs_mutation(line):
                continue
            parsed = descriptor(line)
            if parsed and line.offset + line.l in offsets:
                selected[line.offset] = (line, *parsed)
            else:
                # An unsupported reached form exits before effects. It must
                # not inherit ordinary remote memory-RMW lowering merely
                # because a different branch has supported instruction sites.
                selected[line.offset] = (line, 0, 0)
    if len(selected) > MAX_SITES:
        raise ValueError("original-CPU memory instruction directory exceeds its bound")
    return dict(sorted(selected.items()))


def marker(line, reg_map):
    if not is_gs_mutation(line):
        raise ValueError("unsupported original-CPU memory instruction")
    code = release_conflict(reg_map)
    code += "PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]\n"
    code += make_inst("MOVABS", ["R14", hex(line.offset)])
    code += make_inst("MOV", ["Stack_IJ", str(EXIT)])
    return code + make_inst("JMP", ["full_exit"])


def metadata(selected):
    output = ".balign 8\nkd_origin_memory_sites:\n"
    for ip, (line, operation, width) in sorted(selected.items()):
        output += f".quad 0x{ip:x}, 0x{ip + line.l:x}\n"
        output += (f".long loc_{ip + line.l:x} - main\n" if operation else ".long 0\n")
        output += f".byte {line.l}, {operation}, {width}, 0\n"
        output += ".byte " + ", ".join(str(b) for b in bytes(line.b).ljust(16, b"\0")) + "\n"
    return (output + '.ascii "KDOM0001"\n.long kd_origin_memory_sites - main\n'
            + f".long {len(selected)}\n")
