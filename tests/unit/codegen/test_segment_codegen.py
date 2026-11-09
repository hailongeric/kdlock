# Execute GS lowering against owned userspace storage through the real wrapper.
# No hardware segment base or kernel memory is accessed by these guest tests.
import ctypes
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "disassem"))

try:
    from miasm.arch.x86.arch import mn_x86
    from miasm.core.bin_stream import bin_stream_str
    from miasm.core.locationdb import LocationDB
except ModuleNotFoundError:
    print("[SKIP] test_segment_codegen: miasm is unavailable")
    raise SystemExit(0)

import conflict
import normal

import disassem as translator
from test_jit_body_witness import render, run_image
from test_instruction_policy import SYMBOLS

CURRENT_TASK_OFFSET = 0x20B80
GENERIC_GS_OFFSET = 0x23000


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def macro_value(header, name):
    match = re.search(rf"^#define\s+{re.escape(name)}\s+(.+)$", header, re.MULTILINE)
    require(match is not None, f"missing {name} macro")
    return re.sub(r"\s+", "", match.group(1))


def instruction(source):
    return mn_x86.fromstring(source, loc_db=LocationDB(), mode=64)


def translate_normal(source):
    line = instruction(source)
    return normal.process_normal(line.name, line.args, 0x1000, conflict.block_init())


def require_virtual_gs(source):
    line = instruction(source)
    require(normal.segment_policy_error(line) is None, f"{source} was rejected")
    assembly = translate_normal(source)
    require("Stack_RGS" in assembly, f"{source} did not load waiter GS")
    require("GS:[" not in assembly, f"{source} retained a hardware GS operand")


def check_execution():
    # Distinct base/task packets catch accidental executor-GS use, stale input
    # caching across wrapper calls, and using the per-CPU current slot as task.
    raw = "65488b0425280000006548890425300000006548ff042538000000"
    raw += "65488b142520000000c3"
    for kind in ("spin", "mutex"):
        assembly, log, status = render(
            raw, lock_kind=kind, kernel_symbols={"current_task": 0x20},
            symbols={0x20: "current_task"}, return_status=True,
        )
        require(status == 0, log)
        require(b"GS:[" not in re.sub(rb"/\*.*?\*/", b"", assembly, flags=re.S),
                "hardware GS survived lowering")
        for seed in (0x123456789ABC, 0xABCDEF012345):
            origin = (ctypes.c_ulong * 8)(*[seed + i for i in range(8)])
            before = list(origin)
            logical_task = seed ^ 0x5555
            regs, args = run_image(
                assembly, [0x1000], context=(ctypes.addressof(origin), logical_task)
            )[0]
            require(regs[12] == before[5], "GS read did not use origin storage")
            require(regs[14] == logical_task, "current did not use logical waiter")
            require(list(origin) == before[:6] + [before[5], before[7] + 1],
                    "GS write/RMW changed the wrong storage")
            require(args[1] == 1, "wrapper did not report an executed body")

    # Logical current needs no origin-CPU storage and remains usable by both
    # backends. A zero GS base catches accidental dependence on that input.
    for kind in ("spin", "mutex"):
        assembly, log, status = render(
            "65488b142520000000c3", lock_kind=kind,
            kernel_symbols={"current_task": 0x20}, symbols={0x20: "current_task"},
            return_status=True,
        )
        require(status == 0, log)
        for task in (0x12345678, 0xABCDEF00):
            regs, args = run_image(assembly, [0x1000], context=(0, task))[0]
            require(regs[14] == task, "current did not use the logical waiter")
            require(args[1] == 1, "logical-current body did not execute")


def check_rip_gs_execution():
    # Destination + GS + IP exhaust both idle slots and temporarily borrow
    # physical R13. Releasing IP must leave saved logical SP intact.
    for entry in (0x1000, 0xffffffff817f7110):
        for kind, abi in (("spin", 0), ("mutex", 2)):
            for destination, packet in ((12, 6), (13, 5), (14, 4), (15, 3)):
                raw = bytes((0x65, 0x4c, 0x8b, 0x25 + 8 * (destination - 12)))
                raw += (0x28).to_bytes(4, "little") + b"\xc3"
                options = {}
                assembly, log, status = render(
                    raw.hex(), entry=entry, lock_kind=kind, abi=abi,
                    kernel_symbols=SYMBOLS, trusted_source=True,
                    return_status=True, build_options=options)
                require(status == 0, log)
                require(re.search(rb"\bStack_R\b", assembly) is None,
                        "released IP emitted an unnamed spill")
                for seed in (0x123456789ABC, 0xABCDEF012345):
                    origin = (ctypes.c_ulong * 2)(seed, seed + 1)
                    initial = []

                    def initialize(regs, stack):
                        regs[2] = seed + 7
                        initial.append(regs[1])

                    gs = (ctypes.addressof(origin) - entry - 8 - 0x28) % (1 << 64)
                    regs, args = run_image(
                        assembly, [entry], initialize=initialize, context=(gs, seed),
                        abi=abi, requirements=options["requirements"])[0]
                    require(regs[packet] == seed, "GS/RIP loaded the wrong value")
                    require(regs[1] == initial[0] + 8, "logical SP was not restored")
                    require(regs[2] == seed + 7, "logical BP changed")
                    require(regs[0] == 0x4444, "RET used the wrong logical stack")
                    require(list(origin) == [seed, seed + 1], "GS read changed storage")
                    require(args[1] == 1, "GS/RIP body did not execute")


def main():
    normal.set_current_task_offset(CURRENT_TASK_OFFSET)

    reg_map = conflict.block_init()
    ip_assembly = conflict.conflict_resolve(reg_map, {"IP"}, 0x123456789)
    require("0x123456789" in ip_assembly, "virtual RIP lost its source offset")
    require("IP" in reg_map.values(), "virtual RIP was not assigned a register")
    require(reg_map["15"] == "IP", "virtual register allocation is not deterministic")

    require_virtual_gs(f"MOV RAX, QWORD PTR GS:[0x{GENERIC_GS_OFFSET:x}]")
    require_virtual_gs(f"MOV QWORD PTR GS:[0x{GENERIC_GS_OFFSET:x}], RAX")
    require_virtual_gs("INC QWORD PTR GS:[0x%x]" % (GENERIC_GS_OFFSET + 8))

    current = instruction(f"MOV RAX, QWORD PTR GS:[0x{CURRENT_TASK_OFFSET:x}]")
    require(
        normal.segment_policy_error(current) is None, "current_task MOV was rejected"
    )
    current_assembly = translate_normal(
        f"MOV RAX, QWORD PTR GS:[0x{CURRENT_TASK_OFFSET:x}]"
    )
    require(
        "Stack_RCT" in current_assembly,
        "current_task did not load the logical waiter task",
    )
    require(
        "Stack_RGS" not in current_assembly,
        "current_task incorrectly dereferenced waiter GS",
    )

    fs_line = instruction("MOV RAX, QWORD PTR FS:[0x28]")
    require(
        "FS-prefixed" in normal.segment_policy_error(fs_line),
        "FS memory access was not rejected",
    )
    swapgs_line = mn_x86.dis(bin_stream_str(bytes.fromhex("0f01f8")), 64, 0)
    require(
        "FS/GS base" in normal.segment_policy_error(swapgs_line),
        "binary SWAPGS was not rejected despite miasm's misdecode",
    )
    for raw in (
        "f30faec0",
        "f30faec8",
        "f30faed0",
        "f30faed8",
        "f3480faec0",
        "f3480faec8",
        "f3480faed0",
        "f3480faed8",
    ):
        require(
            "FS/GS base" in normal.segment_encoding_policy_error(bytes.fromhex(raw)),
            f"FSGSBASE encoding {raw} was not rejected",
        )
    misdecoded_wrgsbase = mn_x86.dis(bin_stream_str(bytes.fromhex("f3480faed8")), 64, 0)
    require(
        "FS/GS base" in normal.segment_policy_error(misdecoded_wrgsbase),
        "misdecoded WRGSBASE instruction bypassed policy",
    )
    empty_error = translator.find_segment_policy_error(
        {0x1000: type("EmptyBlock", (), {"lines": []})()}
    )
    require(
        empty_error == (0x1000, "undecodable or empty basic block"),
        "undecodable reachable block did not fail closed",
    )
    external_error = translator.find_segment_policy_error(
        {0x1000: type("ExternalBadBlock", (), {"lines": []})()}, [(0x2000, 0x2100)]
    )
    require(external_error is None, "missing text was rejected before CFG expansion")
    current_write = instruction(f"MOV QWORD PTR GS:[0x{CURRENT_TASK_OFFSET:x}], RAX")
    require(
        "current_task" in normal.segment_policy_error(current_write),
        "current_task write was not rejected",
    )
    alignment_nop = instruction("NOP WORD PTR CS:[RAX + RAX]")
    require(
        normal.segment_policy_error(alignment_nop) is None,
        "CS-prefixed alignment NOP was rejected",
    )
    require(
        translate_normal("NOP WORD PTR CS:[RAX + RAX]").strip() == "NOP",
        "alignment NOP retained its pseudo memory operand",
    )

    with open(
        os.path.join(ROOT, "include", "asm_head.h"), "r", encoding="utf-8"
    ) as header_file:
        header = header_file.read()
    require(
        macro_value(header, "Stack_RGS") == "QWORDPTR[RBP-8*15]", "GS stack slot moved"
    )
    require(
        macro_value(header, "Stack_TASK") == "QWORDPTR[RBP-8*16]",
        "task did not reuse the old second segment slot",
    )
    require(
        macro_value(header, "PT_GS") == "QWORDPTR[ARG_REG]", "args[0] is not waiter GS"
    )
    require(
        macro_value(header, "PT_TASK") == "QWORDPTR[ARG_REG+8]",
        "args[1] is not logical task",
    )
    require(
        "Stack_RFS" not in header and "PT_FS" not in header,
        "obsolete FS ABI remains in asm_head.h",
    )

    with open(
        os.path.join(ROOT, "include", "wrapper.S"), "r", encoding="utf-8"
    ) as wrapper_file:
        wrapper = wrapper_file.read()
    gs_push = re.search(r"\bmov\s+rax,\s*PT_GS\b", wrapper)
    task_push = re.search(r"\bmov\s+rax,\s*PT_TASK\b", wrapper)
    require(
        gs_push is not None and task_push is not None,
        "wrapper does not save both two-word context inputs",
    )
    require(
        gs_push.start() < task_push.start(),
        "wrapper input order does not match Stack_RGS/Stack_TASK",
    )
    require("PT_FS" not in wrapper, "wrapper still consumes an obsolete FS input")
    require(
        re.search(r"\bmov\s+Stack_JIT_WITNESS\s*,\s*0\b", wrapper) is not None,
        "wrapper does not initialize its second output",
    )

    check_execution()
    check_rip_gs_execution()
    print("[PASS] test_segment_codegen")


if __name__ == "__main__":
    main()
