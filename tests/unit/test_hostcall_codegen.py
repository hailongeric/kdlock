import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "disassem"))

import hostcall

try:
    import indirect_jump
except ModuleNotFoundError as error:
    if error.name != "miasm":
        raise
    print("[SKIP] test_hostcall_codegen: miasm is unavailable")
    raise SystemExit(0) from error


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def stub_for(assembly, address, next_address=None):
    start = assembly.index(f"loc_{address:x}:")
    if next_address is None:
        return assembly[start:]
    end = assembly.index(f"loc_{next_address:x}:")
    return assembly[start:end]


def main():
    specs = hostcall.load_hostcall_specs()
    by_symbol = {spec.symbol: spec for spec in specs}
    require("ktime_get" in by_symbol, "ktime_get is absent from manifest")
    require("ktime_get_ns" in by_symbol, "ktime_get_ns is absent from manifest")

    with open(
        os.path.join(ROOT, "include", "exe_info.h"), "r", encoding="utf-8"
    ) as header:
        match = re.search(
            r"^#define\s+KD_EXE_HOSTCALL\s+([0-9]+)", header.read(), re.MULTILINE
        )
    require(match is not None, "KD_EXE_HOSTCALL is not defined")
    hostcall_exit = int(match.group(1))

    service_address = 0x1000
    unknown_address = 0x2000
    services = {service_address: by_symbol["ktime_get"]}
    assembly = indirect_jump.make_callee_table(
        [unknown_address, service_address], {service_address}, services
    )
    service_stub = stub_for(assembly, service_address, unknown_address)
    unknown_stub = stub_for(assembly, unknown_address)

    require("KD_HOSTCALL" in assembly, "hostcall marker is absent")
    require(
        f"0x{hostcall_exit:x}" in service_stub,
        "hostcall stub uses the wrong exit reason",
    )
    require(
        "R13 + 0x8" not in service_stub, "hostcall stub pops the virtual return address"
    )
    require("0x1" in unknown_stub, "unknown call does not use KD_EXE_CALL_MISS")
    require(
        "R13 + 0x8" in unknown_stub,
        "unknown call does not unwind its virtual CALL frame",
    )

    print("[PASS] test_hostcall_codegen")


if __name__ == "__main__":
    main()
