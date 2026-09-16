"""Audit memory-forwarded context addresses; run only in the configured guest.

Exit 0 means this bounded corpus meets admission expectations, 1 reports gaps,
and 2 reports an invalid fixture/tool failure. Requires the guest's miasm setup.
The translator emits assembly with mocked kernel text/symbols and binary build;
no native or JIT machine code is run.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unit import configure_paths

configure_paths()

from miasm.analysis.machine import Machine
from miasm.core.bin_stream import bin_stream_str
from miasm.core.locationdb import LocationDB
from miasm.expression.expression import ExprId, ExprInt, ExprMem
from miasm.ir.symbexec import SymbolicExecutionEngine
from test_jit_diagnostics import render, translator

ENTRY = 0x1000
CONTEXT_START, CONTEXT_END = 0x3000, 0x3100
SEED = "48b8f82f000000000000"
STORE = "488945f8"
LOAD = "488b75f8"
ACCESS = "4883c61048adc3"


@dataclass(frozen=True)
class Case:
    name: str
    raw: str
    sensitive: bool = True
    registers: dict = field(default_factory=dict)
    targets: tuple = ()


def call_return_fixture(clear=False):
    # CALL writes 0x1005, the local RET consumes it, then the caller reloads it.
    caller = "e83b000000488b4424f8" + ("4831c0" if clear else "")
    caller += "4805fb1f0000488b38c3"
    return caller + "90" * (0x40 - len(bytes.fromhex(caller))) + "c3"


def identity_store_fixture(sensitive=False):
    # OR [RDI],0 cannot move the unrelated 0x1005 into the pointer at 0x8400.
    pointer = "00300000" if sensitive else "00200000"
    return (
        "48c704250083000005100000"
        + "48c7042500840000"
        + pointer
        + "48830f00488b042500840000488b18c3"
    )


def rmw_store_fixture(sensitive=False):
    # A nonidentity RMW may change the pointer, but cannot import distant bytes.
    # Unlike 0x2000, none of 0x2200's shifted increments matches a mock lock API.
    pointer = "f02f0000" if sensitive else "00220000"
    update = "48830710" if sensitive else "48830701"
    return (
        "48c704250083000005100000"
        + "48c7042500840000"
        + pointer
        + update
        + "488b042500840000488b18c3"
    )


def direct_call_fixture(prefix, suffix, body):
    caller = bytes.fromhex(prefix)
    displacement = 0x40 - len(caller) - 5
    caller += b"\xe8" + displacement.to_bytes(4, "little", signed=True)
    caller += bytes.fromhex(suffix) + b"\xc3"
    if len(caller) > 0x40:
        raise ValueError("caller overlaps the fixture callee")
    return (caller.ljust(0x40, b"\x90") + bytes.fromhex(body)).hex()


CASES = (
    Case("frame-slot", SEED + STORE + LOAD + ACCESS),
    Case("push-pop", SEED + "505e" + ACCESS),
    Case(
        "stack-slot",
        "4883ec08" + SEED + "488904244831c0488b34244883c408" + ACCESS,
    ),
    Case("ordinary-pointer", SEED + "488907488b37" + ACCESS),
    Case("copied-base", SEED + STORE + "4889ea488b72f8" + ACCESS),
    Case("adjusted-base", SEED + STORE + "4889ea4883ea08488b32" + ACCESS),
    Case("cfg-edge", SEED + STORE + "eb00" + LOAD + ACCESS),
    Case(
        "conditional-overwrite",
        SEED + STORE + "4885d2750848c745f800000000" + LOAD + ACCESS,
        registers={"RDX": 1},
    ),
    Case(
        "may-alias-write-preserves-old",
        SEED + STORE + "48c70700000000" + LOAD + ACCESS,
        registers={"RDI": 0x8200},
    ),
    Case(
        "may-alias-partial-write-constructs-address",
        "b800200000" + STORE + "c60730" + LOAD + "48adc3",
        registers={"RDI": 0x80F9},
    ),
    Case(
        "partial-slot-write", SEED + STORE + "c645f808" + LOAD + "4881c60001000048adc3"
    ),
    Case(
        "base-register-reassigned",
        SEED + STORE + "4889ea4889fd48c745f8000000004889d5" + LOAD + ACCESS,
    ),
    Case("safe-value", "b8f81f0000" + STORE + LOAD + ACCESS, sensitive=False),
    Case(
        "exact-overwrite",
        SEED + STORE + "48c745f800000000" + LOAD + ACCESS,
        sensitive=False,
    ),
    Case(
        "equivalent-alias-overwrite",
        SEED + STORE + "4889ea4883ea0848c70200000000" + LOAD + ACCESS,
        sensitive=False,
    ),
    Case("call-return-slot", call_return_fixture(), targets=(0x1040,)),
    Case(
        "call-return-value-overwritten",
        call_return_fixture(clear=True),
        sensitive=False,
        targets=(0x1040,),
    ),
    Case(
        "identity-write-preserves-safe-pointer",
        identity_store_fixture(),
        sensitive=False,
    ),
    Case("identity-write-preserves-sensitive-pointer", identity_store_fixture(True)),
    Case("rmw-no-sensitive-range", rmw_store_fixture(), sensitive=False),
    Case(
        "rmw-constructs-sensitive-address",
        rmw_store_fixture(True),
        registers={"RDI": 0x8400},
    ),
    Case(
        "direct-call-argument",
        direct_call_fixture("bff82f0000", "", "4883c710488b07c3"),
        targets=(0x1040,),
    ),
    Case(
        "direct-call-return-register",
        direct_call_fixture("", "488d701048ad", "b8f82f0000c3"),
        targets=(0x1040,),
    ),
    Case(
        "direct-call-argument-cleared",
        direct_call_fixture("bff82f0000", "", "31ff4883c710488b07c3"),
        sensitive=False,
        targets=(0x1040,),
    ),
    Case(
        "direct-call-return-overwritten",
        direct_call_fixture("", "31c0488d701048ad", "b8f82f0000c3"),
        sensitive=False,
        targets=(0x1040,),
    ),
)


class AccessWitness(SymbolicExecutionEngine):
    """Concrete input addresses, abstract memory values, no policy-tracker reuse."""

    def __init__(self, lifter, values):
        super().__init__(lifter, values)
        self.accesses = []
        self.blocks = 0

    def eval_updt_irblock(self, irb, step=False):
        self.blocks += 1
        if self.blocks > 128:
            raise ValueError("witness exceeds 128 IR blocks")
        return super().eval_updt_irblock(irb, step)

    def eval_assignblk(self, assignblk):
        memories = set()
        for destination, source in assignblk.items():
            for expression in (destination, source):
                memories.update(
                    item
                    for item in expression.get_r(mem_read=True)
                    if isinstance(item, ExprMem)
                )
        for memory in sorted(memories, key=str):
            pointer = self.eval_expr(memory.ptr)
            if not isinstance(pointer, ExprInt):
                raise TypeError(f"witness has unresolved memory address: {pointer}")
            address, size = int(pointer), (memory.size + 7) // 8
            if address < CONTEXT_END and address + size > CONTEXT_START:
                self.accesses.append(
                    {
                        "rip": hex(assignblk.instr.offset),
                        "instruction": str(assignblk.instr).strip(),
                        "address": hex(address),
                        "bytes": size,
                    }
                )
        return super().eval_assignblk(assignblk)


def witness(case):
    database = LocationDB()
    machine = Machine("x86_64")
    raw = bytes.fromhex(case.raw)
    cfg = machine.dis_engine(
        bin_stream_str(raw, base_address=ENTRY),
        loc_db=database,
        follow_call=bool(case.targets),
    ).dis_multiblock(ENTRY)
    lifter = machine.lifter(database)
    ircfg = lifter.new_ircfg_from_asmcfg(cfg)
    inputs = {"RBP": 0x8100, "RSP": 0x8000, "RDI": 0x8200, "RDX": 0, **case.registers}
    values = {ExprId(reg, 64): ExprInt(value, 64) for reg, value in inputs.items()}
    values[ExprId("df", 1)] = ExprInt(0, 1)
    engine = AccessWitness(lifter, values)
    engine.run_at(ircfg, ENTRY)
    if bool(engine.accesses) != case.sensitive:
        raise ValueError(
            f"{case.name}: concrete witness disagrees with fixture expectation"
        )
    return inputs, engine.accesses


def audit(case, translate=render):
    inputs, accesses = witness(case)
    symbols = translator.context_policy.ContextSymbols(
        {CONTEXT_START: "__per_cpu_offset"}, {CONTEXT_START: CONTEXT_END}
    )
    options = {}
    if case.targets:
        options["regions"] = [(bytes.fromhex(case.raw), ENTRY, [ENTRY, *case.targets])]
    assembly, log, status = translate(
        case.raw, symbols=symbols, return_status=True, **options
    )
    expected = translator.context_policy.NATIVE_ONLY_EXIT if case.sensitive else 0
    valid = (
        status == expected
        and (not assembly if case.sensitive else bool(assembly))
        and (not case.sensitive or "CONTEXT_NATIVE_ONLY" in log)
    )
    return {
        "name": case.name,
        "raw": case.raw,
        "inputs": {name: hex(value) for name, value in inputs.items()},
        "witness_accesses": accesses,
        "expected_status": expected,
        "actual_status": status,
        "assembly_source_bytes": len(assembly),
        "ok": valid,
        "diagnostics": log,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", action="append", choices=[case.name for case in CASES]
    )
    args = parser.parse_args(argv)
    selected = [case for case in CASES if args.case is None or case.name in args.case]
    try:
        results = [audit(case) for case in selected]
    except (
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
        NotImplementedError,
    ) as error:
        print(json.dumps({"error": str(error), "ok": False}), file=sys.stderr)
        return 2
    failures = sum(not result["ok"] for result in results)
    print(
        json.dumps(
            {
                "cases": results,
                "failures": failures,
                "ok": failures == 0,
                "reference": "concrete-input miasm IR, not native execution or full alias proof",
                "translation": "mocked kernel text/symbols and binary build; assembly only",
            },
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
