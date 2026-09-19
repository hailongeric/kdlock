"""Select multi-frame protocol checks without weakening per-role oracles."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mutex_parallel_protocol import validate

from parallel_fixtures import PUBLISHED, reloaded_fixture, fixture, shared_fixture, after_publication, pressure_fixture, code_pool_fixture, with_native_peers

from parallel_signals_cases import PeerSignalTests, OriginalWaiterSignalTests
from parallel_pools_cases import CodePoolTests, ShadowPoolTests

class RetiredReloadTests(unittest.TestCase):
    def test_both_native_orders_preserve_original_jit_oracle(self):
        for first in (0, 1):
            text, metadata = reloaded_fixture(first)
            result = validate(text, PUBLISHED, 0xFF, first, reload=metadata)
            self.assertEqual(result["jit_bodies"], 2)
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(result["reloaded_native_records"], 6)

    def test_native_interval_cannot_hide_execution_or_record_errors(self):
        text, metadata = reloaded_fixture(0)
        before, native = text.split("kd_source reload: phase=begin\n")
        for old, new in (
            ("waiters=3", "waiters=0"),
            ("owner=10", "owner=20"),
            ("before=1", "before=2"),
            ("called=1", "called=0"),
            ("outer=a0", "outer=a1"),
            ("sequence=3", "sequence=4"),
            ("digest=486", "digest=0"),
            ("claimed=15", "claimed=7"),
            ("a=0 b=0", "a=1 b=0"),
            ("failures=0", "failures=1"),
            ("kd_parallel retired record:", "lost record:"),
            ("role=1", "role=2"),
            ("kd_source reload: phase=end", "no end"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(
                    before
                    + "kd_source reload: phase=begin\n"
                    + native.replace(old, new, 1),
                    PUBLISHED,
                    0xFF,
                    0,
                    reload=metadata,
                )
        for extra in (
            "JIT body witness: body=1",
            "kd_native ack: task=1",
            "kd_parallel error: x=1",
            "BUG: bad",
        ):
            with self.subTest(extra=extra), self.assertRaises(AssertionError):
                validate(
                    before + "kd_source reload: phase=begin\n" + extra + "\n" + native,
                    PUBLISHED,
                    0xFF,
                    0,
                    reload=metadata,
                )

    def test_source_identity_and_terminal_registry_are_required(self):
        text, metadata = reloaded_fixture(0)
        for variant in range(7):
            bad = copy.deepcopy(metadata)
            if variant == 0:
                bad["after"]["kd_parallel_cs0"] += 1
            elif variant == 1:
                bad["completed"] = False
            elif variant == 2:
                bad["state"]["writers"] = 1
            elif variant == 3:
                bad["registry"][0]["status"] = 0
            elif variant == 4:
                bad["registry"][0]["code"] += 1
            elif variant == 5:
                bad["sites"].pop(str(0x100))
            else:
                bad["module_sha256"] = ""
            with self.subTest(variant=variant), self.assertRaises(AssertionError):
                validate(text, PUBLISHED, 0xFF, 0, reload=bad)
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 0)

    def test_old_jit_failures_are_not_hidden_by_native_replacement(self):
        text, metadata = reloaded_fixture(0)
        with self.assertRaises(AssertionError):
            validate(
                text.replace("kd_native ack:", "lost ack:", 1),
                PUBLISHED,
                0xFF,
                0,
                reload=metadata,
            )


class ParallelProtocolTests(unittest.TestCase):
    def test_real_node_pressure_covers_shared_refusal_without_assuming_fairness(self):
        for early in (False, True):
            result = validate(
                pressure_fixture(early),
                PUBLISHED,
                0xFF,
                1,
                True,
                after_publication(True),
                True,
            )
            self.assertEqual(result["jit_bodies"], 1)
            self.assertEqual(result["native_node_fallbacks"], 1)
            self.assertEqual(result["native_task_fallbacks"], 1)
            self.assertEqual(result["context_refusals"], 1)
            self.assertEqual(result["owner_acks"], 2)
            self.assertEqual(result["records"], 8)
            self.assertEqual(result["transitions"], 24010)

    def test_task_refusal_cannot_duplicate_a_request_or_hide_missing_completion(self):
        # The allocation failure is an independent, unstarted request. Check
        # its identity/effects as strictly as node exhaustion, not only the
        # shared task_alloc_failure counter at module unload.
        text = pressure_fixture()
        for old, new in (
            ("task=42 entry=101", "task=41 entry=101"),
            ("task=42 entry=101", "task=42 entry=100"),
            ("owner=42", "owner=41"),
            ("record=c6", "record=c5"),
            ("role=6", "role=5"),
            ("value=5a64", "value=5a65"),
            ("task_alloc_failure=1", "task_alloc_failure=0"),
            ("task_alloc_failure=1", "task_alloc_failure=2"),
            ("pressure_done=3", "pressure_done=1"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(
                    text.replace(old, new, 1), PUBLISHED, 0xFF, 1, True, pressure=True
                )
        for label in ("mutex task fallback", "kd_parallel pressure done: role=6"):
            line = next(line for line in text.splitlines() if line.startswith(label))
            for bad in (
                text.replace(line, "", 1),
                text + "\n" + line,
                line + "\n" + text.replace(line, "", 1),
                text.replace(line, "", 1) + "\n" + line,
            ):
                with self.assertRaises((AssertionError, ValueError)):
                    validate(bad, PUBLISHED, 0xFF, 1, True, pressure=True)

    def test_node_pressure_requires_real_mask_identity_owners_and_exact_effects(self):
        text = pressure_fixture()
        for old, new in (
            ("slots=f", "slots=7"),
            ("slots=f", "slots=0"),
            ("task=41 entry=101", "task=40 entry=101"),
            ("task=41 entry=101", "task=41 entry=100"),
            ("lock=a1 cpu=1 slots=f", "lock=a0 cpu=1 slots=f"),
            ("lock=a1 cpu=1 slots=f", "lock=a1 cpu=5 slots=f"),
            ("owner=41", "owner=31"),
            ("waiter=41 owner=41", "waiter=11 owner=11"),
            ("inner=b1 record=c5", "inner=b0 record=c5"),
            ("record=c5", "record=c1"),
            ("value=5a61", "value=5a62"),
            (
                "before=1 held=1 called=1 after=1 value=5a61",
                "before=2 held=1 called=1 after=1 value=5a61",
            ),
            ("sequence=12006", "sequence=12004"),
            ("claimed=111", "claimed=15"),
            ("node_overflow=1", "node_overflow=2"),
            ("pressure_done=3", "pressure_done=0"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(
                    text.replace(old, new, 1), PUBLISHED, 0xFF, 1, True, pressure=True
                )
        for label in ("mutex node fallback", "kd_parallel pressure done"):
            line = next(line for line in text.splitlines() if line.startswith(label))
            for bad in (text.replace(line, "", 1), text + "\n" + line):
                with self.assertRaises((AssertionError, ValueError)):
                    validate(bad, PUBLISHED, 0xFF, 1, True, pressure=True)

    def test_pressure_must_overlap_live_frame_not_inject_or_mislabel_results(self):
        text = pressure_fixture()
        for label in ("mutex node fallback", "kd_parallel pressure done"):
            line = next(line for line in text.splitlines() if line.startswith(label))
            for bad in (
                line + "\n" + text.replace(line, "", 1),
                text.replace(line, "", 1) + "\n" + line,
            ):
                with self.assertRaises(AssertionError):
                    validate(bad, PUBLISHED, 0xFF, 1, True, pressure=True)
        for bad in (
            text + "\nJIT body witness: entry=101 lock=a1 body=1",
            text + "\nkd_native ack: task=41 lock=a1 mutex=1 last_spin=0",
            text + "\nreason=PENDING_LOCK_NATIVE",
        ):
            with self.assertRaises(AssertionError):
                validate(bad, PUBLISHED, 0xFF, 1, True, pressure=True)
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 1, True)
        with self.assertRaises(AssertionError):
            validate(shared_fixture(), PUBLISHED, 0xFF, 1, True, pressure=True)
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 1, pressure=True)

    def test_both_release_orders(self):
        for first in (0, 1):
            self.assertEqual(
                validate(
                    fixture(first), PUBLISHED, 0xFF, first, after=after_publication()
                )["jit_bodies"],
                2,
            )

    def test_shared_cpu_refuses_unexecuted_request_without_losing_live_frame(self):
        result = validate(
            shared_fixture(), PUBLISHED, 0xFF, 1, True, after_publication(True)
        )
        self.assertEqual(result["jit_bodies"], 1)
        self.assertEqual(result["native_frames"], 1)
        self.assertEqual(result["overlapping_native_frames"], 0)
        self.assertEqual(result["context_refusals"], 1)
        self.assertEqual(result["owner_acks"], 2)

    def test_shared_refusal_must_match_cpu_entry_waiter_owner_and_lifetime(self):
        text = shared_fixture()
        for old, new in (
            ("task=31 waiter=21", "task=30 waiter=21"),
            ("waiter=21 entry=101", "waiter=20 entry=101"),
            ("entry=101 lock=a1", "entry=100 lock=a1"),
            ("lock=a1 cpu=1", "lock=a0 cpu=1"),
            ("lock=a1 cpu=1", "lock=a1 cpu=5"),
            ("owner=31", "owner=20"),
            ("owner=11", "owner=21"),
            ("context_busy=1", "context_busy=0"),
            ("multi_slot=1", "multi_slot=0"),
            ("started=1", "started=2"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(text.replace(old, new, 1), PUBLISHED, 0xFF, 1, True)
        for label in ("mutex JIT context busy", "kd_parallel contender"):
            line = next(line for line in text.splitlines() if line.startswith(label))
            for bad in (text.replace(line, "", 1), text + "\n" + line):
                with self.assertRaises((AssertionError, ValueError)):
                    validate(bad, PUBLISHED, 0xFF, 1, True)
        refusal = next(
            line
            for line in text.splitlines()
            if line.startswith("mutex JIT context busy")
        )
        with self.assertRaises(AssertionError):
            validate(
                text.replace(refusal, "") + "\n" + refusal, PUBLISHED, 0xFF, 1, True
            )
        with self.assertRaises(AssertionError):
            validate(
                text + "\nJIT body witness: entry=101 lock=a1 body=1",
                PUBLISHED,
                0xFF,
                1,
                True,
            )
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 0, True)

    def test_after_publication_matches_executed_not_just_entry_counts(self):
        for field, value in (("entry", 0x100), ("status", 1), ("code", 0x222)):
            after = after_publication(True)
            after[1][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                validate(shared_fixture(), PUBLISHED, 0xFF, 1, True, after)
        after = after_publication(True)
        after[0]["status"], after[1]["status"] = 0, 1
        with self.assertRaises(AssertionError):
            validate(shared_fixture(), PUBLISHED, 0xFF, 1, True, after)
        after = after_publication()
        after[0]["target"] = 0xFE
        with self.assertRaises(AssertionError):
            validate(fixture(0), PUBLISHED, 0xFF, 0, after=after)

    def test_wrong_identity_packet_owner_and_exactly_once_fields(self):
        for old, new in (
            ("body=1", "body=0"),
            ("entry=100", "entry=102"),
            ("ip=ff", "ip=fe"),
            ("sp=f0", "sp=0"),
            ("held=2", "held=1"),
            ("mutex=1", "mutex=0"),
            ("cpu=1", "cpu=0"),
            ("remaining=2", "remaining=1"),
            ("outer_released=0", "outer_released=1"),
            ("owner=20", "owner=10"),
            ("owner=21", "owner=20"),
            ("record=c1", "record=c0"),
            ("before=1", "before=2"),
            ("held=1 called=0", "held=0 called=0"),
            ("called=0", "called=1"),
            ("value=1a", "value=1b"),
            ("arrived=3 done=0", "arrived=1 done=0"),
            ("arrived=3 done=1", "arrived=3 done=0"),
            ("lock=b0", "lock=b1"),
            ("last_spin=0", "last_spin=1"),
            ("called=1 after=1", "called=2 after=1"),
            ("sequence=12004", "sequence=12003"),
            ("claimed=15", "claimed=7"),
            ("a=0 b=0", "a=0 b=20"),
            ("active_tasks=0", "active_tasks=1"),
            ("task_alloc_failure=0", "task_alloc_failure=1"),
            ("completed=2", "completed=1"),
            ("invariant_failures=0", "invariant_failures=1"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(fixture(0).replace(old, new, 1), PUBLISHED, 0xFF, 0)

    def test_missing_or_duplicate_protocol_events(self):
        text = fixture(0)
        for label in (
            "kd_parallel arrive",
            "kd_parallel resume",
            "kd_parallel done",
            "kd_native begin",
            "kd_native ack",
            "kd_native complete",
            "JIT body witness",
            "kd_parallel lane",
            "kd_parallel stats",
        ):
            line = next(
                line for line in text.splitlines() if line.startswith(label + ":")
            )
            for bad in (text.replace(line, "", 1), text + "\n" + line):
                # Unpacking also rejects missing/duplicate task-keyed events.
                with (
                    self.subTest(label=label),
                    self.assertRaises((AssertionError, ValueError)),
                ):
                    validate(bad, PUBLISHED, 0xFF, 0)

    def test_serial_execution_or_early_completion_is_not_overlap(self):
        text = fixture(0)
        arrival = next(line for line in text.splitlines() if "arrive: lane=1" in line)
        for bad in (
            text.replace(arrival, "") + "\n" + arrival,
            text.replace("kd_native ack: task=20 lock=a0 mutex=1 last_spin=0", "")
            + "\nkd_native ack: task=20 lock=a0 mutex=1 last_spin=0",
            text.replace("kd_parallel resume: lane=1", "kd_parallel resume: lane=0"),
        ):
            with self.assertRaises(AssertionError):
                validate(bad, PUBLISHED, 0xFF, 0)

    def test_publication_refusal_and_wrong_completion_order(self):
        for published in (
            PUBLISHED[:1],
            PUBLISHED * 2,
            [PUBLISHED[0], {"entry": 0x102, "code": 0x201, "kind": 2}],
            [PUBLISHED[0], {"entry": 0x101, "code": 0, "kind": 2}],
            [PUBLISHED[0], {"entry": 0x101, "code": 0x201, "kind": 1}],
        ):
            with self.assertRaises(AssertionError):
                validate(fixture(0), published, 0xFF, 0)
        with self.assertRaises(AssertionError):
            validate(fixture(0), PUBLISHED, 0xFF, 1)
        with self.assertRaises(AssertionError):
            validate(fixture(0) + "\nreason=PENDING_LOCK_NATIVE", PUBLISHED, 0xFF, 0)


class NativePeerTests(unittest.TestCase):
    def test_both_orders_with_capacity_retirement_and_reloaded_source(self):
        for first in (0, 1):
            text, evidence = code_pool_fixture(first)
            text = with_native_peers(text, first)
            reloaded, metadata = reloaded_fixture(first)
            interval = reloaded[reloaded.index("kd_source reload: phase=begin") :]
            result = validate(
                text + "\n" + interval,
                PUBLISHED,
                0xFF,
                first,
                code_pool=evidence,
                reload=metadata,
                native_peers=True,
            )
            self.assertEqual(
                result["native_peers"],
                {
                    "failed_tries": 5,
                    "queued": 4,
                    "cancelled": 2,
                    "acquired": 2,
                    "released": 2,
                },
            )
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(result["reloaded_native_records"], 6)
            self.assertEqual(result["code_pool"]["allocated_blocks"], 64)
            self.assertEqual(
                result["native_routing"],
                {
                    "renamed_waiters": 2,
                    "native_acquisitions": 2,
                    "native_unlocks": 2,
                    "restored_after_acks": 2,
                },
            )

    def test_renamed_borrower_keeps_identity_and_owns_only_its_native_c(self):
        text = with_native_peers(fixture(0), 0)
        for label, old, new in (
            ("kd_resume rename:", "task=20", "task=100"),
            ("kd_resume rename:", "old=klock_test", "old=kd_native"),
            ("kd_resume rename:", "new=kd_renamed", "new=klock_test"),
            ("kd_resume rename:", "cpu=2", "cpu=1"),
            ("kd_resume rename:", "preempt_after=0", "preempt_after=1"),
            ("kd_resume rename:", "irq_before=0", "irq_before=1"),
            ("kd_parallel routed native:", "waiter=10", "waiter=20"),
            ("kd_parallel routed native:", "owner=20", "owner=21"),
            ("kd_parallel routed native:", "outer=a0", "outer=a1"),
            ("kd_parallel routed native:", "inner=b0", "inner=b1"),
            ("kd_parallel routed native:", "local=e0", "local=b0"),
            ("kd_parallel routed native:", "local=e0", "local=e1"),
            ("kd_parallel routed native:", "local_owner=10", "local_owner=20"),
            ("kd_parallel routed native:", "after_owner=0", "after_owner=10"),
            ("kd_parallel routed native:", "acquired=1", "acquired=2"),
            ("kd_parallel routed native:", "released=1", "released=0"),
            ("kd_parallel routed native:", "comm=kd_renamed", "comm=klock_test"),
            ("kd_parallel done:", "comm=kd_renamed", "comm=klock_test"),
            ("kd_parallel resume:", "comm=kd_renamed", "comm=klock_test"),
        ):
            line = next(s for s in text.splitlines() if s.startswith(label))
            self.assertIn(old, line)
            with self.subTest(label=label, old=old), self.assertRaises(AssertionError):
                validate(
                    text.replace(line, line.replace(old, new, 1), 1),
                    PUBLISHED,
                    0xFF,
                    0,
                    native_peers=True,
                )

    def test_routing_events_cannot_be_missing_or_restored_before_final_ack(self):
        text = with_native_peers(fixture(0), 0)
        for label in ("kd_resume rename:", "kd_parallel routed native:"):
            line = next(s for s in text.splitlines() if s.startswith(label))
            for bad in (
                text.replace(line, "", 1),
                text + "\n" + line,
                text.replace(line, "", 1) + "\n" + line,
            ):
                with (
                    self.subTest(label=label),
                    self.assertRaises((AssertionError, ValueError)),
                ):
                    validate(bad, PUBLISHED, 0xFF, 0, native_peers=True)
        restore = next(
            s
            for s in text.splitlines()
            if s.startswith("kd_resume rename: task=20 old=kd_renamed")
        )
        ack = "kd_native ack: task=20 lock=a0 mutex=1 last_spin=0"
        with self.assertRaises(AssertionError):
            validate(
                text.replace(restore, "").replace(ack, restore + "\n" + ack),
                PUBLISHED,
                0xFF,
                0,
                native_peers=True,
            )
        for extra in (
            "JIT body witness: entry=333 lock=e0 body=1",
            "kd_native ack: task=20 lock=e0 mutex=1 last_spin=0",
        ):
            with self.assertRaises(AssertionError):
                validate(text + "\n" + extra, PUBLISHED, 0xFF, 0, native_peers=True)

    def test_reload_or_unselected_flow_cannot_hide_a_renamed_borrower(self):
        text = with_native_peers(fixture(0), 0)
        reloaded, metadata = reloaded_fixture(0)
        interval = reloaded[reloaded.index("kd_source reload: phase=begin") :]
        for label in ("kd_resume rename:", "kd_parallel routed native:"):
            line = next(s for s in text.splitlines() if s.startswith(label))
            bad = interval.replace(
                "kd_source reload: phase=end", line + "\nkd_source reload: phase=end"
            )
            with self.assertRaises(AssertionError):
                validate(
                    text + "\n" + bad,
                    PUBLISHED,
                    0xFF,
                    0,
                    reload=metadata,
                    native_peers=True,
                )
            with self.assertRaises(AssertionError):
                validate(fixture(0) + "\n" + line, PUBLISHED, 0xFF, 0)

    def test_real_queue_ownership_trylock_and_exact_records_are_required(self):
        text = with_native_peers(fixture(0), 0)
        for old, new in (
            ("task=100", "task=20"),
            ("waiter=d0", "waiter=20"),
            ("owner=d0", "owner=20"),
            ("comm=kd_native", "comm=klock_test"),
            ("result=0", "result=1"),
            ("queued=1", "queued=0"),
            ("matched=1", "matched=0"),
            ("other_owner=21", "other_owner=0"),
            ("cross_try=0", "cross_try=1"),
            ("acquired=1", "acquired=2"),
            ("released=1", "released=0"),
            ("completed=3", "completed=1"),
            ("value=bd4b", "value=bd4a"),
            ("attempt=2", "attempt=1"),
            ("error=4", "error=0"),
            ("pending=1", "pending=0"),
            ("fatal=0", "fatal=1"),
            ("queued=0", "queued=1"),
            ("matched=0", "matched=1"),
            ("cancelled=1", "cancelled=2"),
            ("cancelled=1 acquired=0", "cancelled=1 acquired=1"),
        ):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(
                    text.replace(old, new, 1), PUBLISHED, 0xFF, 0, native_peers=True
                )

    def test_missing_duplicate_or_late_peer_cannot_pass_as_concurrent(self):
        text = with_native_peers(fixture(0), 0)
        for label in ("try", "queued", "cancelled", "acquired", "released", "stats"):
            line = next(
                s
                for s in text.splitlines()
                if s.startswith("kd_parallel peer " + label + ":")
            )
            for bad in (text.replace(line, "", 1), text + "\n" + line):
                with (
                    self.subTest(label=label),
                    self.assertRaises((AssertionError, ValueError)),
                ):
                    validate(bad, PUBLISHED, 0xFF, 0, native_peers=True)
        for label in ("try", "queued", "cancelled", "acquired", "released"):
            line = next(
                s
                for s in text.splitlines()
                if s.startswith("kd_parallel peer " + label + ": lane=0")
            )
            with self.subTest(late=label), self.assertRaises(AssertionError):
                validate(
                    text.replace(line, "", 1) + "\n" + line,
                    PUBLISHED,
                    0xFF,
                    0,
                    native_peers=True,
                )

    def test_native_peers_are_explicit_and_cannot_hide_in_source_reload(self):
        text = with_native_peers(fixture(0), 0)
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 0)
        with self.assertRaises(AssertionError):
            validate(fixture(0), PUBLISHED, 0xFF, 0, native_peers=True)
        with self.assertRaises(AssertionError):
            validate(
                shared_fixture(), PUBLISHED, 0xFF, 1, shared_cpu=True, native_peers=True
            )
        reloaded, metadata = reloaded_fixture(0)
        interval = reloaded[reloaded.index("kd_source reload: phase=begin") :]
        for label in ("try", "queued", "cancelled", "acquired", "released", "stats"):
            bad = interval.replace(
                "kd_source reload: phase=end",
                f"kd_parallel peer {label}: lane=0\nkd_source reload: phase=end",
            )
            with self.subTest(label=label), self.assertRaises(AssertionError):
                validate(
                    text + "\n" + bad,
                    PUBLISHED,
                    0xFF,
                    0,
                    reload=metadata,
                    native_peers=True,
                )


if __name__ == "__main__":
    unittest.main()
