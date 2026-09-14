"""Reject lookalike native exits and stale values in the live stack oracle.

These log mutations test acceptance only. The real B owner and returned JIT
body in test_10 provide the concurrency evidence, never this fixture.
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mutex_stack_protocol import control_returns, validate

LOG = """
kd_stack publish: task=31 waiter=100 slot=8008 old=123456789abcdef0 record=12001
JIT body witness: entry=1000 lock=2000 body=1
kd_stack changed: task=31 waiter=100 slot=8008 old=123456789abcdef0 new=fedcba987654321 combiner=200 combiner_pid=32 holder=300 holder_pid=33 holder_comm=kd_native outer=2000 lock=3000 queued=1 valid=1
[KD_JIT][WARN] reason=MUTEX_STACK_CHANGED entry=0x1000 target=0x4000 ip=0x1010 sp=0x8000 task=31
kd_native begin: task=31 outer=2000 entry=1000 ip=1010 sp=8000 held=2 mutex=1 cpu=4 outer_released=0 remaining=2
kd_stack observed: task=31 waiter=100 value=fedcba987654321 a_owner=200 b_owner=200 reads=1 valid=1
kd_native ack: task=31 lock=3000 mutex=1 last_spin=0
kd_native ack: task=31 lock=2000 mutex=1 last_spin=0
kd_native complete: task=31 mutex=1
kd_stack complete: task=31 completed=1 valid=1
kd_native stats: started=1 completed=1 unlocks=2
kd_stack stats: writes=1 reads=1 completed=1
kd_mutex stack checks: bytes=256 equal=0 changed=1 unavailable=0
kd_resume records: requests=12002 failures=0
kd_pending mutex: observed=0 acquired=0
"""
REGISTRY = [
    {
        "entry": 0x1000,
        "target": 0,
        "code": 0x9000,
        "pid": 0,
        "tgid": 30,
        "kind": 2,
        "status": 0,
    }
]
SOURCE = {"mutex_lock": 0x4000, "observer": 0x5000, "returns": [0x1000, 0x1010]}
ASSEMBLY = "loc_1000:\nMOV Stack_JIT_WITNESS, 1\n"
STATUSES = dict.fromkeys(range(7), 0)


def check(
    text=LOG, before=None, after=None, source=None, assembly=ASSEMBLY, statuses=None
):
    return validate(
        text,
        REGISTRY if before is None else before,
        REGISTRY if after is None else after,
        SOURCE if source is None else source,
        assembly,
        STATUSES if statuses is None else statuses,
    )


class MutexStackTests(unittest.TestCase):
    def test_changed_stack_retains_owners_and_completes_once(self):
        result = check()
        self.assertEqual(result["owner_acks"], 2)
        self.assertEqual(result["post_call"], "0x1010")
        self.assertEqual(result["value"], "0xfedcba987654321")
        cold = REGISTRY[0] | {"entry": 0x6000, "status": -1, "tgid": 32}
        check(after=[*REGISTRY, cold])
        # The combiner's completion print may precede the final waiter ACK.
        early = LOG.replace("kd_native complete: task=31 mutex=1\n", "")
        early = early.replace(
            "kd_native ack: task=31 lock=2000",
            "kd_native complete: task=31 mutex=1\nkd_native ack: task=31 lock=2000",
        )
        check(early)

    def test_stale_value_outside_window_and_missing_real_waiter_fail(self):
        for old, new in (
            ("value=fedcba987654321", "value=123456789abcdef0"),
            ("slot=8008", "slot=8100"),
            ("slot=8008", "slot=8001"),
            ("queued=1", "queued=0"),
            ("holder_comm=kd_native", "holder_comm=klock_test"),
            ("old=123456789abcdef0", "old=0"),
        ):
            with self.subTest(new=new), self.assertRaises(AssertionError):
                check(LOG.replace(old, new))

    def test_control_packet_must_match_actual_call_successor(self):
        for old, new in (
            ("ip=0x1010", "ip=0x4000"),
            ("ip=0x1010", "ip=0x5000"),
            ("ip=0x1010", "ip=0x1020"),
            ("sp=8000 held", "sp=8008 held"),
            ("target=0x4000", "target=0x5000"),
            ("entry=0x1000", "entry=0x1010"),
        ):
            with self.subTest(new=new), self.assertRaises(AssertionError):
                check(LOG.replace(old, new))

    def test_owner_handoff_duplicate_effects_and_wrong_ack_fail(self):
        for old, new in (
            ("b_owner=200", "b_owner=100"),
            ("a_owner=200", "a_owner=300"),
            ("combiner_pid=32", "combiner_pid=31"),
            ("reads=1", "reads=2"),
            ("completed=1 valid=1", "completed=2 valid=1"),
            ("lock=3000 mutex=1", "lock=2000 mutex=1"),
            ("held=2", "held=1"),
            ("requests=12002 failures=0", "requests=12002 failures=1"),
        ):
            with self.subTest(new=new), self.assertRaises(AssertionError):
                check(LOG.replace(old, new))

    def test_missing_events_and_lookalike_call_miss_fail(self):
        for label in (
            "reason=MUTEX_STACK_CHANGED",
            "kd_stack changed:",
            "JIT body witness:",
            "kd_native ack:",
            "kd_stack complete:",
        ):
            changed = "\n".join(line for line in LOG.splitlines() if label not in line)
            with self.subTest(label=label), self.assertRaises(AssertionError):
                check(changed)
        for extra in (
            "reason=PENDING_LOCK_NATIVE",
            "reason=MUTEX_STACK_UNAVAILABLE",
            "kd_stack error:",
        ):
            with self.subTest(extra=extra), self.assertRaises(AssertionError):
                check(LOG + extra)

    def test_registry_cannot_change_status_target_or_generation(self):
        for key, value in (
            ("status", 1),
            ("target", 0x5000),
            ("code", 0x9008),
            ("kind", 1),
            ("entry", 0x1010),
            ("tgid", 0),
        ):
            after = copy.deepcopy(REGISTRY)
            after[0][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                check(after=after)
        with self.assertRaises(AssertionError):
            check(before=[], after=[])
        with self.assertRaises(AssertionError):
            check(after=REGISTRY * 2)
        for changes in ({"status": 0}, {"target": 0x5000}, {"kind": 1}):
            cold = REGISTRY[0] | {"entry": 0x6000, "status": -1} | changes
            with self.subTest(changes=changes), self.assertRaises(AssertionError):
                check(after=[*REGISTRY, cold])

    def test_wrong_image_or_failed_role_is_not_an_execution_pass(self):
        with self.assertRaises(AssertionError):
            check(assembly=ASSEMBLY.replace("1000", "1010"))
        with self.assertRaises(AssertionError):
            check(assembly="loc_1000:\n")
        for role in range(7):
            with self.subTest(role=role), self.assertRaises(AssertionError):
                check(statuses=STATUSES | {role: 124})

    def test_source_returns_require_e8_and_matching_relocations(self):
        source = """00000020 <run_nested_mutex_cs>:
  25: e8 00 00 00 00        call 2a <run_nested_mutex_cs+0xa>
      26: R_X86_64_PLT32 mutex_lock-0x4
  35: e8 00 00 00 00        call 3a <run_nested_mutex_cs+0x1a>
      36: R_X86_64_PLT32 mutex_lock-0x4
  45: e8 00 00 00 00        call 4a <run_nested_mutex_cs+0x2a>
      46: R_X86_64_PLT32 kd_stack_change_observe-0x4
"""
        self.assertEqual(control_returns(source, 0x1000), [0x100A, 0x101A])
        # Both constant-lane roots use the same relocation contract. An
        # explicit symbol must match; another function cannot supply its RIP.
        for name in ("kd_shared_cs0", "kd_shared_cs1"):
            named = source.replace("run_nested_mutex_cs", name)
            self.assertEqual(control_returns(named, 0x2000, name), [0x200A, 0x201A])
            with self.assertRaises(AssertionError):
                control_returns(named, 0x2000, "wrong_symbol")
        for old, new in (
            ("36: R_", "37: R_"),
            ("35: e8", "35: e9"),
            ("mutex_lock-0x4", "mutex_unlock-0x4"),
        ):
            with self.subTest(new=new), self.assertRaises(AssertionError):
                control_returns(source.replace(old, new), 0x1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
