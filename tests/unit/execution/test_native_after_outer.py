"""Guest-only tests of real frame/known-call code with mocked lock primitives.

These tests do not model Linux ownership, concurrency, or assembly entry/exit.
The OOO kernel workloads separately exercise those paths with real JIT code.
"""

import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from source_text import read_source

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import spin_acquired_protocol as protocol
from source_text import ROOT, without_includes
from test_spin_shadow import definition


class AcquiredProtocolTests(unittest.TestCase):
    def fixture(self):
        # Synthetic records test rejection by the oracle, not kernel execution.
        lines = (
            "JIT body witness: entry=1234 lock=a000 body=1",
            "spin JIT injected failure after nested lock=b000 outer=a000 val=1 kind=1",
            "reason=SPIN_ACQUIRED_NATIVE entry=0x1234 target=0x100 lock=0xb000 ip=0x900 sp=0x2008 call_sp=0x2000 return=0x900 owner=0xc000 task=42",
            "kd_native begin: task=42 outer=a000 entry=1234 ip=900 sp=2008 held=2 mutex=0 cpu=4 outer_released=0 remaining=2",
            "kd_native ack: task=42 lock=b000 mutex=0 last_spin=0",
            "kd_native complete: task=42 outer=a000 mutex=0",
            "kd_native ack: task=42 lock=a000 mutex=0 last_spin=1",
            "kd_native stats: started=1 completed=1 unlocks=2",
        )
        return "\n".join(lines)

    def test_checked_post_packet_and_both_acks(self):
        result = protocol.validate(self.fixture(), 0xA000, 0xB000, 0x100)
        self.assertEqual(result["post_call_sp"], "0x2008")
        self.assertEqual(result["owner_acks"], 2)
        self.assertFalse(result["full_registers_checked"])

    def queue_fixture(self):
        text = self.fixture().replace("kind=1", "kind=2")
        text = text.replace(
            "spin JIT injected",
            "kd_acquired queued: task=42 holder=101 cpu=1 a_owner=c000 b_owner=d000 prefix=1 waiters=2 valid=1\nspin JIT injected",
        )
        text = text.replace(
            "kd_native ack: task=42 lock=b000",
            "kd_acquired resumed: task=42 cpu=0 waiter=f000 a_owner=c000 b_owner=c000 prefix=1 suffix=1 valid=1\nkd_native ack: task=42 lock=b000",
        )
        records = [
            "kd_acquired trailer: task=102 cpu=2 owner=e000 prefix=1 suffix=1 valid=1",
            "kd_acquired finish: task=42 prefix=1 suffix=1 completed=1",
            *(
                f"kd_acquired role: role={role} task={100 + role} cpu={role}"
                for role in (1, 2, 3, 4, 6, 8)
            ),
            "kd_acquired stats: prepared=1 prefix=1 suffix=1 completed=1 queued=1 trailer=1 failures=0",
        ]
        text = text.replace(
            "kd_native stats:", "\n".join(records) + "\nkd_native stats:"
        )
        return text, "\n".join(f"{role}\t0" for role in (1, 3, 4, 6, 0, 2, 8))

    def test_actual_queued_contract_requires_the_new_owner_and_follower(self):
        text, statuses = self.queue_fixture()
        result = protocol.validate(
            text, 0xA000, 0xB000, 0x100, queued=True, statuses=statuses
        )
        self.assertTrue(result["queue_owner_checked"])

    def test_fast_or_corrupt_queue_evidence_is_not_a_queued_pass(self):
        text, statuses = self.queue_fixture()
        mutations = (
            ("kind=2", "kind=1"),
            ("waiters=2", "waiters=1"),
            ("b_owner=d000", "b_owner=c000"),
            ("b_owner=c000", "b_owner=d000"),
            ("holder=101", "holder=102"),
            ("prefix=1", "prefix=2"),
            ("suffix=1", "suffix=0"),
            ("completed=1 queued=1", "completed=0 queued=1"),
            ("valid=1", "valid=0"),
            ("owner=e000", "owner=c000"),
            ("cpu=2 owner", "cpu=3 owner"),
            ("role=6", "role=4"),
            ("failures=0", "failures=1"),
            ("waiter=f000", "waiter=c000"),
        )
        for before, after in mutations:
            with self.subTest(field=before), self.assertRaises(AssertionError):
                protocol.validate(
                    text.replace(before, after),
                    0xA000,
                    0xB000,
                    0x100,
                    queued=True,
                    statuses=statuses,
                )
        for broken in ("", statuses.replace("2\t0", "2\t1"), statuses + "\n2\t0"):
            with self.subTest(status=broken), self.assertRaises(AssertionError):
                protocol.validate(
                    text, 0xA000, 0xB000, 0x100, queued=True, statuses=broken
                )

    def test_corrupt_or_missing_evidence_is_not_a_pass(self):
        text = self.fixture()
        corrupt = [
            text.replace(before, after)
            for before, after in (
                ("body=1", "body=0"),
                ("entry=1234 lock=a000", "entry=1235 lock=a000"),
                ("lock=b000 outer=a000", "lock=b004 outer=a000"),
                ("target=0x100", "target=0x101"),
                ("lock=0xb000", "lock=0xb004"),
                ("sp=0x2008", "sp=0x2000"),
                ("return=0x900", "return=0x901"),
                ("owner=0xc000", "owner=0x0"),
                ("sp=2008", "sp=2000"),
                ("ip=900 sp=2008", "ip=100 sp=2008"),
                ("remaining=2", "remaining=1"),
                ("held=2", "held=1"),
                ("outer_released=0", "outer_released=1"),
                ("lock=b000 mutex=0", "lock=a000 mutex=0"),
                ("lock=b000 mutex=0", "lock=b000 mutex=1"),
                ("last_spin=1", "last_spin=0"),
                ("completed=1", "completed=0"),
                ("kd_native begin: task=42", "kd_native begin: task=43"),
            )
        ]
        for line in text.splitlines():
            corrupt.append(text.replace(line, ""))
            # Several legitimate requests can return the same JIT prefix.
            if not line.startswith("JIT body witness:"):
                corrupt.append(text + "\n" + line)
        # A body witness or native publication appearing only after the
        # checkpoint/ACK is not evidence that this JIT suffix was handed off.
        lines = text.splitlines()
        corrupt.append("\n".join(lines[1:] + lines[:1]))
        corrupt.append("\n".join(lines[:3] + lines[4:7] + lines[3:4] + lines[7:]))
        for i, candidate in enumerate(corrupt):
            with (
                self.subTest(variant=i),
                self.assertRaises((AssertionError, KeyError, ValueError)),
            ):
                protocol.validate(candidate, 0xA000, 0xB000, 0x100)


def main():
    types = (
        definition(
            read_source((ROOT / "include/kd_spin_entry.h")), "struct kd_spin_ref {"
        ).rstrip()
        + ";\n"
    )
    for name in ("include/kd_call.h", "include/kd_exec.h"):
        types += without_includes(read_source((ROOT / name))) + "\n"
    executor = read_source((ROOT / "kernel_module/exe.c"))
    types += (
        next(
            line
            for line in executor.splitlines()
            if line.startswith("#define KD_MUTEX_CALL_STACK_BYTES")
        )
        + "\n"
    )
    types += definition(executor, "struct kd_mutex_call_stack {").rstrip() + ";\n"
    types += "\n".join(
        line
        for line in read_source((ROOT / "include/exe.h")).splitlines()
        if line.startswith("#define KD_EXE_")
    )
    code = ""
    functions = {
        "kernel_module/kd_exec.c": (
            "static int kd_exec_invariant_failure(void)",
            "static bool kd_exec_frame_state_is_active(int state)",
            "int kd_exec_frame_state(const struct kd_exec_frame *frame)",
            "static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)",
            "bool kd_exec_frame_validate(const struct kd_exec_frame *frame)",
            "void kd_exec_frame_save_continuation(struct kd_exec_frame *frame,",
            "int kd_exec_frame_lock_push(struct kd_exec_frame *frame,",
            "unsigned int kd_exec_frame_lock_depth(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_lock_contains(const struct kd_exec_frame *frame,",
            "int kd_exec_frame_lock_pop(struct kd_exec_frame *frame, unsigned long lock_addr)",
            "int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,",
            "kd_exec_frame_lock_kind(const struct kd_exec_frame *frame,",
            "void *kd_exec_frame_lock_node(const struct kd_exec_frame *frame,",
            "bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame)",
            "bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame)",
            "int kd_exec_frame_record_event(struct kd_exec_frame *frame,",
            "int kd_exec_frame_complete(struct kd_exec_frame *frame)",
            "bool kd_exec_frame_can_borrow_locks(const struct kd_exec_frame *frame)",
            "int kd_exec_native_begin(struct kd_exec_frame *frame, bool mutex)",
        ),
        "kernel_module/kd_lock.c": (
            "static int kd_jit_begin_call(struct kd_exec_frame *frame, struct pt_regs *regs)",
            "static int kd_jit_advance_call(struct kd_exec_frame *frame,",
            "int kd_mutex_jit_nested_lock_ctx(struct mutex *lock, struct pt_regs *regs,",
            "int kd_mutex_jit_nested_unlock_ctx(struct mutex *lock,",
        ),
        "kernel_module/exe.c": (
            "static int advance_after_known_call(struct pt_regs *regs)",
            "static int advance_and_save_continuation(struct kd_exec_frame *frame,",
            "static int finish_acquired_spin_call(struct kd_exec_frame *frame,",
            "static int finish_known_lock_call(struct kd_exec_frame *frame,",
            "static int kd_mutex_stack_prepare(struct kd_exec_frame *frame,",
            "static int kd_mutex_stack_finish(struct kd_exec_frame *frame,",
            "static int handle_known_mutex_call(struct kd_exec_frame *frame,",
            "static int handle_known_call(struct pt_regs *regs,",
        ),
    }
    for name, signatures in functions.items():
        source = read_source((ROOT / name))
        for signature in signatures:
            if signature.startswith("kd_exec_frame_lock_kind("):
                code += "enum kd_exec_lock_kind\n"
            code += definition(source, signature) + "\n"
    with tempfile.TemporaryDirectory(prefix="kdlock-after-outer-unit-") as directory:
        path = Path(directory)
        (path / "frame_types.h").write_text(types)
        (path / "frame_code.h").write_text(code)
        binary = path / "after-outer"
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
                "-I",
                str(ROOT / "include"),
                str(ROOT / "tests/unit/execution/native_after_outer_fixture.c"),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    main()
    unittest.main()
