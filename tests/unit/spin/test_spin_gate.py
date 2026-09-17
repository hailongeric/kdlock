"""Compile the production gate map/owner helpers with deterministic primitives.

Run in the guest. This checks state transitions, not native queue concurrency.
"""

import copy
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
import spin_gate_protocol as protocol


class GateProtocolTests(unittest.TestCase):
    def fixture(self):
        # A bounded synthetic log tests the oracle, not Linux scheduling/JIT.
        # Use all real capacity indices so loss/duplication cannot hide in sums.
        count, capacity, before = protocol.COUNT, protocol.CAPACITY, 64
        base, stride = 0x100000, 4
        evidence = {
            "base": base,
            "stride": stride,
            "entry": 0x88888,
            "count": count,
            "module_sha256": "a" * 64,
            "snapshots": {},
            "progress": {
                "outer": 0x110000, "entry": 0x90000,
                "target": 0xf0000, "return": 0x90050,
                "publication": dict(entry=0x90000, code=0x99000, status=0,
                                    kind=1, pid=40, tgid=40),
                "artifacts": [dict(path=name, sha256="b" * 64)
                              for name in ("jit.S", "jit.bin", "bin.txt")],
            },
        }
        for phase in ("prepare", "held", "filled", "progress", "drained"):
            evidence["snapshots"][phase] = {
                "allocated": 2
                if phase == "prepare"
                else before
                if phase == "held"
                else capacity,
                "phase": int(phase != "prepare"),
                "progress_phase": 1 if phase == "progress" else 2 if phase == "drained" else 0,
                "publication": dict(evidence["progress"]["publication"]),
                "source": {
                    "state": 0,
                    "modules": 1,
                    "frames": 2 if phase == "progress" else int(phase != "prepare"),
                    "writers": 0,
                },
            }
        log = [f"kd_gate layout: base={base:x} stride={stride} count={count}"]
        for index in range(count):
            log.append(f"kd_hotlock selftest promote: lock={base + index * stride:x}")
        log += [
            "reason=PENDING_LOCK_NATIVE task=100 error=-7",
            "kd_native begin: task=100 mutex=0 held=1",
            "kd_pending spin blocked: task=100",
            "kd_gate hold: task=200 cpu=1 a=a000 b=b000 valid=1",
        ]

        def record(index, role):
            present = not role and index < capacity - before
            value = index + 7
            for _ in range(role + 1):
                value = value * 33 + index + 1
            return (
                f"kd_gate record: role={role} index={index} task={300 + role} "
                f"cpu={9 + role} lock={base + index * stride:x} registered={int(present)} "
                f"updates={role + 1} value={value:x} pins=0 valid=1"
            )

        for index in range(count):
            if index >= capacity - before:
                log.append(
                    f"kd_gate refusal: task=300 cpu=9 lock={base + index * stride:x}"
                )
            log.append(record(index, 0))
        log += [
            f"kd_gate refusal: task=302 cpu=11 lock={base + (count - 1) * stride:x}",
            f"kd_gate queued: task=301 cpu=10 lock={base + (count - 1) * stride:x} value=101",
            record(count - 1, 1),
            record(count - 1, 2),
        ]
        prefix = (7 * 33 + 0x12340001 + 17) * 33 + 0x12340001
        inner = base + (count - 1) * stride

        def caller(role):
            return (f"kd_gate progress caller: role={role} task={400 + role} "
                    f"self=c00{role} cpu={role + 10} pins=0 valid=1")

        log += [
            caller(3), caller(4),
            "JIT body witness: entry=90000 lock=110000 body=1",
            f"kd_gate refusal: task=405 cpu=15 lock={inner:x}",
            "reason=PENDING_LOCK_NATIVE entry=0x90000 target=0xf0000 sp=0xa000 "
            "return=0x90050 staged_ip=0x90050 staged_sp=0xa008 mutex=0 error=-12 outer_released=0 task=406",
            "kd_native begin: task=406 outer=110000 entry=90000 ip=f0000 sp=a000 "
            "held=1 mutex=0 cpu=15 outer_released=0 remaining=1",
            f"kd_gate progress blocked: task=408 self=c008 cpu=18 outer=110000 lock={inner:x} "
            f"owner=c005 waiter=c006 word=101 before=2 inner=0 after=1 value={prefix:x} pins=1 valid=1",
            f"kd_gate progress acquired: task=406 self=c006 cpu=16 outer=110000 lock={inner:x} "
            f"owner=c005 before=2 inner=0 after=1 value={prefix:x} pins=2 valid=1",
            "kd_native ack: task=406 lock=110000 mutex=0 last_spin=1",
            "kd_native complete: task=406 outer=110000 mutex=0",
            *(caller(role) for role in range(5, 9)),
            "kd_gate resume: task=200 cpu=1 a=a000 b=b000 valid=1",
            "kd_pending spin acquired: task=100",
            "kd_native ack: task=100 lock=1000 mutex=0 last_spin=1",
            "kd_native complete: task=100 outer=1000 mutex=0",
            "kd_gate stats: locks=1025 roles=1ff phase=2 valid=1",
            f"kd_gate progress stats: before=2 inner=1 after=2 value={(prefix ^ 0x24680002) + 17:x} "
            "direct=3 observed=1 phase=2 valid=1",
            "kd_native stats: started=2 completed=2 unlocks=2",
        ]
        return "\n".join(log), evidence, "".join(f"{role}\t0\n" for role in range(9))

    def test_real_capacity_records_and_native_interval_oracle(self):
        result = protocol.validate_gate_pool(*self.fixture())
        self.assertEqual(result["new_gates"], 960)
        self.assertEqual(result["filler_records"], 1025)
        self.assertEqual(result["target_refusals"], 67)
        self.assertEqual(result["progressed_gate_refusals"], 1)
        self.assertEqual(result["overlapping_frames"], 2)

    def test_missing_pressure_or_frame_snapshot_is_rejected(self):
        text, original, statuses = self.fixture()
        for phase, key, value in (
            ("filled", "allocated", 1023),
            ("drained", "allocated", 1),
            ("held", "phase", 2),
            ("progress", "source", dict(state=0, modules=1, frames=1, writers=0)),
            ("progress", "progress_phase", 0),
            ("drained", "publication", dict(original["progress"]["publication"], code=0x99001)),
            (
                "drained",
                "source",
                {"state": 0, "modules": 1, "frames": 0, "writers": 0},
            ),
        ):
            evidence = copy.deepcopy(original)
            evidence["snapshots"][phase][key] = value
            with self.subTest(phase=phase, key=key), self.assertRaises(AssertionError):
                protocol.validate_gate_pool(text, evidence, statuses)

    def test_owner_queue_effect_and_identity_corruption_are_rejected(self):
        text, evidence, statuses = self.fixture()
        mutations = [
            text.replace(
                "kd_gate resume: task=200 cpu=1 a=a000",
                "kd_gate resume: task=200 cpu=1 a=c000",
            ),
            text.replace("role=0 index=1 ", "role=0 index=0 "),
            text.replace("updates=3", "updates=2"),
            text.replace("pins=0", "pins=1", 1),
            text.replace("cpu=11", "cpu=10"),
            text.replace("task=302", "task=301"),
            text.replace("value=101\n", "value=1\n"),
            text.replace("kd_gate refusal: task=302", "ignored refusal: task=302"),
            text.replace("kd_gate queued:", "ignored queue:"),
            text + "\nJIT body witness: entry=88888 body=1\n",
            text.replace("JIT body witness: entry=90000", "ignored witness: entry=90000"),
            text.replace("error=-12", "error=-7"),
            text.replace("staged_sp=0xa008", "staged_sp=0xa000"),
            text.replace("return=0x90050", "return=0x90000"),
            text.replace("owner=c005", "owner=c006"),
            text.replace("before=2", "before=3", 1),
            text.replace("inner=1 after=2", "inner=2 after=2"),
            text.replace("pins=2 valid=1", "pins=3 valid=1"),
            text.replace("kd_native ack: task=406", "ignored ack: task=406"),
            text.replace("kd_gate refusal: task=405", "ignored refusal: task=405"),
            text.replace("started=2 completed=2 unlocks=2", "started=1 completed=1 unlocks=1"),
        ]
        for index, mutated in enumerate(mutations):
            with (
                self.subTest(mutation=index),
                self.assertRaises((AssertionError, ValueError)),
            ):
                protocol.validate_gate_pool(mutated, evidence, statuses)
        with self.assertRaises(AssertionError):
            protocol.validate_gate_pool(
                text, evidence, statuses.replace("2\t0", "2\t124")
            )


def without_includes(source):
    return re.sub(r'^#include [<"].*$', "", source, flags=re.MULTILINE)


def main():
    types = (
        definition(
            (ROOT / "include/qspinlock_i.h").read_text(), "struct orig_qspinlock {"
        ).rstrip()
        + ";\n"
    )
    header = without_includes((ROOT / "include/kd_spin_gate.h").read_text())
    source = without_includes((ROOT / "kernel_module/kd_spin_gate.c").read_text())
    with tempfile.TemporaryDirectory(prefix="kdlock-spin-gate-unit-") as directory:
        path = Path(directory)
        (path / "gate_production.h").write_text(types + header + source)
        binary = path / "spin-gate"
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + [
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(path),
                str(ROOT / "tests/unit/spin/spin_gate_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)
        # The second fixture drives concurrent creators through one collision
        # chain and observes initialization at the actual release publication.
        binary = path / "spin-gate-publish"
        command = shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
            "-I", str(path),
            str(ROOT / "tests/unit/spin/spin_gate_publish_fixture.c"),
            "-o", str(binary),
        ]
        subprocess.run(command, check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    main()
    unittest.main()
