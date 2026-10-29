"""Exact original-task instruction services with immutable JIT successors.

This directory authorizes a bounded instruction transaction, not a Native CALL
or arbitrary source continuation. The runtime retains its frame and owner.
"""
import native_escape
from conflict import release_conflict
from assist import make_inst

EXIT = 12
REQUIREMENT = 1 << 6
MAX_SITES = 64
KINDS = {"RDTSC": 1, "RDTSCP": 2, "CPUID": 3}


def sites(blocks):
    """Only a decoded exact instruction with an emitted successor can resume."""
    offsets = {line.offset for block in blocks.values() for line in block.lines}
    found = {}
    for block in blocks.values():
        for line in block.lines:
            if (line.name.upper() in KINDS and native_escape.descriptor(line)
                    and line.offset + line.l in offsets):
                found[line.offset] = (line, KINDS[line.name.upper()])
    # Excess sites keep their existing Native-suffix behavior, without refusing
    # another branch or expanding the bounded immutable directory.
    return dict(sorted(found.items())[:MAX_SITES])


def marker(line, reg_map):
    if line.name.upper() not in KINDS or not native_escape.descriptor(line):
        raise ValueError("unreviewed original-task instruction")
    code = release_conflict(reg_map)
    code += "PUSHFQ\nPOP QWORD PTR[REG_BANK + KD_REG_FLAGS]\n"
    code += make_inst("MOV", ["R15", "Stack_BUDGET"])
    code += make_inst("MOV", ["QWORD PTR[REG_BANK + KD_REG_SS]", "R15"])
    code += make_inst("MOVABS", ["R14", hex(line.offset)])
    code += make_inst("MOV", ["Stack_IJ", str(EXIT)])
    code += make_inst("JMP", ["full_exit"])
    return code


def entry_dispatch(f, selected):
    """Called after PUSHFQ; every route consumes exactly that saved word.

    MINIMAL/clobber packets have no orig_ax contract. Only FULL regular entry
    can import the runtime's tag, budget and arithmetic flags. All comparisons
    precede the final flag merge, and a bad tag/target never executes a body.
    """
    f.write("CMP     Stack_CLOBBER, 0\nJNE     kd_origin_regular_dispatch\n")
    f.write("MOVABS  R15, KD_REG_ORIGIN_REENTRY_TAG\n")
    f.write("CMP     QWORD PTR[REG_BANK + KD_REG_ORIG_AX], R15\n")
    f.write("JNE     kd_origin_regular_dispatch\n")
    f.write("MOV     QWORD PTR[REG_BANK + KD_REG_ORIG_AX], 0\n")
    f.write("MOV     R15, QWORD PTR[REG_BANK + KD_REG_SS]\n")
    f.write("CMP     R15, 0\nJE      kd_origin_dispatch_miss\n")
    f.write("CMP     R15, 0x1000000\nJA      kd_origin_dispatch_miss\n")
    f.write("MOV     Stack_BUDGET, R15\n")
    for next_ip in sorted({line.offset + line.l for line, _ in selected.values()}):
        f.write(f"CMP     R14, 0x{next_ip:x}\nJE      kd_origin_dispatch_{next_ip:x}\n")
    f.write("kd_origin_dispatch_miss:\nPOPFQ\n")
    f.write("MOV     Stack_IJ, 0x2\nMOV     R15, R14\nJMP     exit\n")
    f.write("kd_origin_regular_dispatch:\n")


def continuation_dispatch(f, selected):
    for next_ip in sorted({line.offset + line.l for line, _ in selected.values()}):
        f.write(f"kd_origin_dispatch_{next_ip:x}:\nPOPFQ\n")
        f.write("PUSHFQ\nPOP R15\n")
        f.write("AND R15, ~KD_REG_ARITHMETIC_FLAGS\n")
        f.write("MOV R14, QWORD PTR[REG_BANK + KD_REG_FLAGS]\n")
        f.write("AND R14, KD_REG_ARITHMETIC_FLAGS\nOR R15, R14\n")
        f.write("PUSH R15\nPOPFQ\n")
        # This cold receipt is part of the service contract, even when general
        # entry observations are off. It proves dispatch reached the successor.
        f.write(make_inst("MOV", ["Stack_JIT_WITNESS", "1"]))
        f.write(f"JMP     loc_{next_ip:x}\n")


def metadata(selected):
    result = ".balign 8\nkd_origin_sites:\n"
    for ip, (line, kind) in sorted(selected.items()):
        next_ip = ip + line.l
        result += f".quad 0x{ip:x}, 0x{next_ip:x}\n"
        result += f".long loc_{next_ip:x} - main\n.byte {kind}, {line.l}, 0, 0\n"
        result += ".byte " + ", ".join(str(b) for b in bytes(line.b).ljust(8, b"\0")) + "\n"
    return result + '.ascii "KDOS0001"\n.long kd_origin_sites - main\n' + f".long {len(selected)}\n"
