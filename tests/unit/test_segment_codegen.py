#!/usr/bin/env python3
import os
import re
import sys


ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "disassem"))

try:
    from miasm.arch.x86.arch import mn_x86
    from miasm.core.bin_stream import bin_stream_str
    from miasm.core.locationdb import LocationDB
except ModuleNotFoundError:
    print("[SKIP] test_segment_codegen: miasm is unavailable")
    raise SystemExit(0)

import conflict
import disassem as translator
import normal


CURRENT_TASK_OFFSET = 0x20B80
GENERIC_GS_OFFSET = 0x23000


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def instruction(source):
    return mn_x86.fromstring(source, loc_db=LocationDB(), mode=64)


def translate_normal(source):
    line = instruction(source)
    normal.check_mem_base_block_init()
    return normal.process_normal(
        line.name, line.args, 0x1000, conflict.block_init()
    )


def require_virtual_gs(source):
    line = instruction(source)
    require(normal.segment_policy_error(line) is None,
            "%s was rejected" % source)
    assembly = translate_normal(source)
    require("Stack_RGS" in assembly,
            "%s did not load waiter GS" % source)
    require("GS:[" not in assembly,
            "%s retained a hardware GS operand" % source)


def main():
    normal.set_current_task_offset(CURRENT_TASK_OFFSET)

    require_virtual_gs(
        "MOV RAX, QWORD PTR GS:[0x%x]" % GENERIC_GS_OFFSET)
    require_virtual_gs(
        "MOV QWORD PTR GS:[0x%x], RAX" % GENERIC_GS_OFFSET)
    require_virtual_gs(
        "INC QWORD PTR GS:[0x%x]" % (GENERIC_GS_OFFSET + 8))

    current = instruction(
        "MOV RAX, QWORD PTR GS:[0x%x]" % CURRENT_TASK_OFFSET)
    require(normal.segment_policy_error(current) is None,
            "current_task MOV was rejected")
    current_assembly = translate_normal(
        "MOV RAX, QWORD PTR GS:[0x%x]" % CURRENT_TASK_OFFSET)
    require("Stack_RCT" in current_assembly,
            "current_task did not load the logical waiter task")
    require("Stack_RGS" not in current_assembly,
            "current_task incorrectly dereferenced waiter GS")

    fs_line = instruction("MOV RAX, QWORD PTR FS:[0x28]")
    require("FS-prefixed" in normal.segment_policy_error(fs_line),
            "FS memory access was not rejected")
    swapgs_line = mn_x86.dis(bin_stream_str(bytes.fromhex("0f01f8")), 64, 0)
    require("FS/GS base" in normal.segment_policy_error(swapgs_line),
            "binary SWAPGS was not rejected despite miasm's misdecode")
    for raw in ("f30faec0", "f30faec8", "f30faed0", "f30faed8",
                "f3480faec0", "f3480faec8", "f3480faed0", "f3480faed8"):
        require("FS/GS base" in normal.segment_encoding_policy_error(
                    bytes.fromhex(raw)),
                "FSGSBASE encoding %s was not rejected" % raw)
    misdecoded_wrgsbase = mn_x86.dis(
        bin_stream_str(bytes.fromhex("f3480faed8")), 64, 0)
    require("FS/GS base" in normal.segment_policy_error(misdecoded_wrgsbase),
            "misdecoded WRGSBASE instruction bypassed policy")
    empty_error = translator.find_segment_policy_error(
        {0x1000: type("EmptyBlock", (), {"lines": []})()})
    require(empty_error == (0x1000, "undecodable or empty basic block"),
            "undecodable reachable block did not fail closed")
    external_error = translator.find_segment_policy_error(
        {0x1000: type("ExternalBadBlock", (), {"lines": []})()},
        [(0x2000, 0x2100)])
    require(external_error is None,
            "out-of-range CALL-miss placeholder was rejected")
    current_write = instruction(
        "MOV QWORD PTR GS:[0x%x], RAX" % CURRENT_TASK_OFFSET)
    require("current_task" in normal.segment_policy_error(current_write),
            "current_task write was not rejected")
    alignment_nop = instruction("NOP WORD PTR CS:[RAX + RAX]")
    require(normal.segment_policy_error(alignment_nop) is None,
            "CS-prefixed alignment NOP was rejected")
    require(translate_normal("NOP WORD PTR CS:[RAX + RAX]").strip() ==
            "NOP", "alignment NOP retained its pseudo memory operand")

    with open(os.path.join(ROOT, "include", "asm_head.h"),
              "r", encoding="utf-8") as header_file:
        header = header_file.read()
    require("#define Stack_RGS QWORD PTR [RBP - 8*15]" in header,
            "GS stack slot moved")
    require("#define Stack_TASK QWORD PTR [RBP - 8*16]" in header,
            "task did not reuse the old second segment slot")
    require("#define PT_GS QWORD PTR [ARG_REG]" in header,
            "args[0] is not waiter GS")
    require("#define PT_TASK QWORD PTR [ARG_REG + 8]" in header,
            "args[1] is not logical task")
    require("Stack_RFS" not in header and "PT_FS" not in header,
            "obsolete FS ABI remains in asm_head.h")

    with open(os.path.join(ROOT, "include", "wrapper.S"),
              "r", encoding="utf-8") as wrapper_file:
        wrapper = wrapper_file.read()
    gs_push = re.search(r"\bpush\s+PT_GS\b", wrapper)
    task_push = re.search(r"\bpush\s+PT_TASK\b", wrapper)
    require(gs_push is not None and task_push is not None,
            "wrapper does not save both two-word context inputs")
    require(gs_push.start() < task_push.start(),
            "wrapper input order does not match Stack_RGS/Stack_TASK")
    require("PT_FS" not in wrapper,
            "wrapper still consumes an obsolete FS input")

    print("[PASS] test_segment_codegen")


if __name__ == "__main__":
    main()
