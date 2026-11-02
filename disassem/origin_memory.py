"""Returning original-CPU service for exact unlocked GS memory INC/DEC."""

from conflict import block_init, release_conflict, reverse_reg, spill_register
from assist import make_inst
from normal import process_normal, segment_operand
from miasm.expression.expression import ExprId, ExprMem

EXIT = 13
REQUIREMENT = 1 << 10
READ_REQUIREMENT = 1 << 11
READ = 1
MAX_SITES = 1024
OPERATIONS = {"INC": 1, "DEC": 2}
LOAD, TEST = 3, 4


def read_operands(line):
    if is_gs_mutation(line) or line.name.upper() in {
            "LEA", "NOP", "PREFETCHNTA", "PREFETCHT0", "PREFETCHT1", "PREFETCHT2",
            "PREFETCH0", "PREFETCH1", "PREFETCH2", "PREFETCHW", "PREFETCHWT1"}:
        return []
    return [arg for arg in line.args if segment_operand(arg)[0] == "GS"]


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
    raw = bytes(line.b)
    if not raw or len(raw) != line.l:
        return None
    cursor, gs, word = 0, False, False
    while cursor < len(raw) and raw[cursor] in (0x65, 0x66):
        if raw[cursor] == 0x65:
            if gs: return None
            gs = True
        else:
            if word: return None
            word = True
        cursor += 1
    rex = 0
    if cursor < len(raw) and 0x40 <= raw[cursor] <= 0x4f:
        rex, cursor = raw[cursor], cursor + 1
    if not gs or cursor + 2 > len(raw):
        return None
    opcode = raw[cursor]
    modrm = raw[cursor + 1]
    cursor += 2
    mod, extension, rm = modrm >> 6, (modrm >> 3) & 7, modrm & 7
    name = line.name.upper()
    width = 64 if rex & 8 else 16 if word else 32
    immediate = 0
    if opcode == 0xff and name in OPERATIONS and not word:
        operation = OPERATIONS[name]
        if extension != operation - 1 or len(line.args) != 1:
            return None
    elif opcode == 0x8b and name == "MOV" and not word:
        operation = LOAD
        if (len(line.args) != 2 or not isinstance(line.args[0], ExprId) or
                segment_operand(line.args[1])[0] != "GS" or
                (extension | ((rex & 4) << 1)) == 4):
            return None
    elif opcode == 0xf7 and name == "TEST" and extension == 0 and width in (16, 32):
        operation = TEST
        immediate = width // 8
        if len(line.args) != 2 or segment_operand(line.args[0])[0] != "GS":
            return None
    else:
        return None
    memory = line.args[1] if operation == LOAD else line.args[0]
    if mod == 3 or segment_operand(memory)[0] != "GS" or memory.size != width:
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
    if cursor + immediate != len(raw) or len(raw) > 15:
        return None
    return operation, width


def sites(blocks, *, reads=False):
    offsets = {line.offset for block in blocks.values() for line in block.lines}
    selected = {}
    for block in blocks.values():
        for line in block.lines:
            if not is_gs_mutation(line) and not (reads and read_operands(line)):
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
    if not is_gs_mutation(line) and not read_operands(line):
        raise ValueError("unsupported original-CPU memory instruction")
    code = release_conflict(reg_map)
    code += "PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]\n"
    code += make_inst("MOVABS", ["R14", hex(line.offset)])
    code += make_inst("MOV", ["Stack_IJ", str(EXIT)])
    return code + make_inst("JMP", ["full_exit"])


def read_guard(line, reg_map, preempt_symbol):
    """Preserve flags/GPRs while checking the actual decoded GS offset."""
    operands = read_operands(line)
    if not operands:
        return ""
    failed = f"kd_memory_read_service_{line.offset:x}"
    done = f"kd_memory_read_ordinary_{line.offset:x}"
    code = ""
    for physical, logical in reg_map.items():
        if logical and logical not in {"T1", "T2", "IP", "FS", "GS", "CT"}:
            code += spill_register(reg_map, physical)
    code += "MOV R12, Stack_RBP\nMOV R13, Stack_RSP\nPUSHFQ\n"
    reg_map.clear()
    reg_map.update(block_init())
    reg_map.dirty.clear()
    for operand in operands:
        _, address = segment_operand(operand)
        code += process_normal("LEA", [ExprId("RT1", address.size), ExprMem(address, 64)],
                               line.offset + line.l, reg_map)
        pointer = "R" + reverse_reg(reg_map, ExprId("RT1", 64))
        if pointer != "R14": code += f"MOV R14, {pointer}\n"
        reg_map.clear()
        reg_map.update(block_init())
        reg_map.dirty.clear()
        code += f"MOVABS R15, 0x{preempt_symbol:x}\nSUB R14, R15\n"
        code += f"CMP R14, 4\nJB {failed}\nNEG R14\n"
        code += f"CMP R14, {operand.size // 8}\nJB {failed}\n"
    code += f"POPFQ\nJMP {done}\n{failed}:\nPOPFQ\n"
    code += marker(line, reg_map)
    return code + done + ":\n"


def metadata(selected, preempt_symbol=None):
    output = ".balign 8\nkd_origin_memory_sites:\n"
    for ip, (line, operation, width) in sorted(selected.items()):
        output += f".quad 0x{ip:x}, 0x{ip + line.l:x}\n"
        output += (f".long loc_{ip + line.l:x} - main\n" if operation else ".long 0\n")
        flags = READ if read_operands(line) else 0
        output += f".byte {line.l}, {operation}, {width}, {flags}\n"
        output += ".byte " + ", ".join(str(b) for b in bytes(line.b).ljust(16, b"\0")) + "\n"
    return (output + f'.ascii "KDOM000{2 if preempt_symbol is not None else 1}"\n'
            + '.long kd_origin_memory_sites - main\n' + f".long {len(selected)}\n"
            + (f".quad 0x{preempt_symbol:x}\n" if preempt_symbol is not None else ""))
