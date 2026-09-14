# Compare generated service stubs with the shared hostcall manifest.
# Emitting a matching exit does not execute a Linux service or prove resumption.
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "disassem"))

import hostcall

# Missing miasm must fail this required code-generation gate, not count as PASS.
import indirect_jump


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
    require(by_symbol["int_sqrt"].service_id == 3, "scalar service ID drifted")

    with open(
        os.path.join(ROOT, "include", "exe_info.h"), "r", encoding="utf-8"
    ) as header:
        match = re.search(
            r"^#define\s+KD_EXE_HOSTCALL\s+([0-9]+)", header.read(), re.MULTILINE
        )
    require(match is not None, "KD_EXE_HOSTCALL is not defined")
    hostcall_exit = int(match.group(1))

    unknown_address = 0x2000
    addresses = {spec.symbol: 0x1000 + i * 0x100 for i, spec in enumerate(specs)}
    services = hostcall.resolve_hostcalls(lambda symbol, _: addresses.get(symbol))
    require(len(services) == len(specs), "a declared service was not resolved")
    assembly = indirect_jump.make_callee_table(
        [unknown_address, *services], services
    )
    unknown_stub = stub_for(assembly, unknown_address)

    ordered = sorted(services) + [unknown_address]
    for address, next_address in zip(ordered, ordered[1:]):
        service = services[address]
        service_stub = stub_for(assembly, address, next_address)
        require(
            f"KD_HOSTCALL id={service.service_id} symbol={service.symbol}" in assembly,
            "named service marker is absent",
        )
        require(f"0x{hostcall_exit:x}" in service_stub, "wrong service exit reason")
        require(f"0x{address:x}" in service_stub, "wrong native service target")
        require("R13 + 0x8" not in service_stub, "service popped its CALL word")
        require("RDI" not in service_stub, "stub overwrote the scalar argument")
    require("0x1" in unknown_stub, "unknown call does not use KD_EXE_CALL_MISS")
    require(
        "R13 + 0x8" not in unknown_stub,
        "unknown call discards its native continuation return address",
    )

    print("[PASS] test_hostcall_codegen")


if __name__ == "__main__":
    main()
