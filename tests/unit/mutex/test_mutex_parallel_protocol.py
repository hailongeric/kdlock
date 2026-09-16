"""Mutate multi-frame evidence so aggregate counters cannot hide misrouting."""

import copy
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mutex_parallel_protocol import (
    signal_native_peers,
    signal_original_waiters,
    validate,
    validate_peer_signals,
    validate_waiter_signals,
)

PUBLISHED = [{"entry": 0x100 + i, "code": 0x200 + i, "kind": 2} for i in range(2)]


def reloaded_fixture(first):
    original = fixture(first)
    lines = [f"kd_parallel native queued: lane={i} waiters=3" for i in (0, 1)]
    for line in original.splitlines():
        if not line.startswith("kd_parallel "):
            continue
        line = line.replace("owner=20", "owner=10").replace("owner=21", "owner=11")
        if line.startswith("kd_parallel lane:"):
            lane = int(line.split("lane=")[1][0])
            line = f"kd_parallel lane: lane={lane} sequence=3 digest=486 claimed=15 a=0 b=0"
        lines.append(line)
    for lane in (0, 1):
        for role in (1, 2, 3):
            task = lane + 20 if role == 2 else 100 + lane * 8 + role
            owner = f"1{lane}" if role == 2 else f"ff{task:x}"
            lines.append(
                f"kd_parallel retired record: lane={lane} role={role} task={task} waiter={owner} owner={owner} before=1 held=1 called=1 after=1 value={((lane * 8 + role + 1) * 3 + 17) ^ 0x5A5A:x}"
            )
    symbols = {
        "kd_parallel_cs0": 0x10,
        "kd_parallel_cs1": 0x20,
        "kd_parallel_native": 0xFF,
        "parallel_lanes": 0xA0,
    }
    metadata = {
        "before": symbols,
        "after": dict(symbols),
        "first": first,
        "sites": {str(0x100 + i): f"kd_parallel_cs{i}" for i in (0, 1)},
        "module_sha256": "a" * 64,
        "completed": True,
        "registry": [dict(p, status=-3) for p in PUBLISHED],
        "state": {"state": 2, "modules": 0, "frames": 0, "writers": 0},
    }
    text = original + "\nkd_source reload: phase=begin\n"
    text += "\n".join(lines) + "\nkd_source reload: phase=end\n"
    return text, metadata


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


def fixture(first):
    lines = []
    for lane in (0, 1):
        lines += [
            f"JIT body witness: entry={0x100 + lane:x} lock=a{lane} body=1",
            f"kd_native begin: task={lane + 20} outer=a{lane} entry={0x100 + lane:x} ip=ff sp=f{lane} held=2 mutex=1 cpu={lane * 4 + 1} outer_released=0 remaining=2",
            f"kd_parallel arrive: lane={lane} task={lane + 20} waiter=1{lane} owner=2{lane} outer=a{lane} inner=b{lane} record=c{lane} before=1 held=1 called=0 after=0 value={(lane * 8 + 3) * 3 + 17:x} cpu={lane * 4 + 2} valid=1",
        ]
    for lane in (first, 1 - first):
        lines += [
            f"kd_parallel resume: lane={lane} task={lane + 20} owner=2{lane} arrived=3 done={0 if lane == first else 1 << first} valid=1",
            f"kd_native ack: task={lane + 20} lock=b{lane} mutex=1 last_spin=0",
            f"kd_native complete: task={lane + 20} outer=a{lane} mutex=1",
            f"kd_native ack: task={lane + 20} lock=a{lane} mutex=1 last_spin=0",
            f"kd_parallel done: lane={lane} task={lane + 20} waiter=1{lane} owner=2{lane} record=c{lane} before=1 held=1 called=1 after=1 value={((lane * 8 + 3) * 3 + 17) ^ 0x5A5A:x} valid=1",
        ]
    digest = 0
    for sequence in range(1, 12005):
        digest = (digest * 33 + sequence) & ((1 << 64) - 1)
    for lane in (0, 1):
        lines.append(
            f"kd_parallel lane: lane={lane} sequence=12004 digest={digest:x} claimed=15 a=0 b=0"
        )
    lines += [
        f"kd_parallel stats: first={first} shared_cpu=0 pressure=0 pressure_done=0 arrived=3 done=3 failures=0",
        "kd_native stats: started=2 completed=2 unlocks=4",
        "kd_mutex stats: context_busy=0 multi_slot=0 node_overflow=0",
        "kd_mutex tasks: active_tasks=0 task_alloc_failure=0 task_reroutes=0",
        "kd_exec invariant_failures=0",
    ]
    return "\n".join(lines)


def shared_fixture():
    # Lane 1 executes its own original CS while lane 0 still borrows A/B.
    # There must be no second generated body, frame registration or owner ACK.
    lines = []
    for line in fixture(1).splitlines():
        if line.startswith("kd_native ") and "task=21" in line:
            continue
        if line.startswith("JIT body witness: entry=101"):
            continue
        if line.startswith("kd_parallel arrive: lane=1"):
            lines += [
                "mutex JIT context busy: task=31 waiter=21 entry=101 lock=a1 cpu=1",
                "kd_parallel contender: task=31 owner=31 cpu=1 valid=1",
            ]
        lines.append(line.replace("owner=21", "owner=11"))
    return (
        "\n".join(lines)
        .replace("shared_cpu=0", "shared_cpu=1")
        .replace("started=2 completed=2 unlocks=4", "started=1 completed=1 unlocks=2")
        .replace("context_busy=0 multi_slot=0", "context_busy=1 multi_slot=1")
    )


def after_publication(shared=False):
    return [
        dict(
            item,
            status=int(not shared or lane == 0),
            target=0xFF if not shared or lane == 0 else 0,
        )
        for lane, item in enumerate(PUBLISHED)
    ]


def pressure_fixture(early=False):
    # The no-node task may win A1 before or after the queued waiter. Both
    # orders are legal; its full-mask refusal and final own-owner unlock must
    # still be contained within the first waiter's retained native frame.
    text = shared_fixture().replace("cpu=6 valid=1", "cpu=1 valid=1")
    text = text.replace(
        "mutex JIT context busy:",
        "mutex node fallback: task=41 entry=101 lock=a1 cpu=1 slots=f\n"
        "mutex task fallback: task=42 entry=101 lock=a1 cpu=1\n"
        "mutex JIT context busy:",
        1,
    )
    before = "kd_parallel contender:" if early else "kd_parallel resume: lane=0"
    text = text.replace(
        before,
        "kd_parallel pressure done: role=5 task=41 waiter=41 owner=41 outer=a1 inner=b1 record=c5 before=1 held=1 called=1 after=1 value=5a61 cpu=1 valid=1\n"
        "kd_parallel pressure done: role=6 task=42 waiter=42 owner=42 outer=a1 inner=b1 record=c6 before=1 held=1 called=1 after=1 value=5a64 cpu=1 valid=1\n"
        + before,
        1,
    )
    digest = 0
    for sequence in range(1, 12007):
        digest = (digest * 33 + sequence) & ((1 << 64) - 1)
    old = next(line for line in text.splitlines() if "lane: lane=1" in line)
    return (
        text.replace(
            old,
            f"kd_parallel lane: lane=1 sequence=12006 digest={digest:x} claimed=111 a=0 b=0",
        )
        .replace("pressure=0 pressure_done=0", "pressure=1 pressure_done=3")
        .replace("node_overflow=0", "node_overflow=1")
        .replace("task_alloc_failure=0", "task_alloc_failure=1")
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


def code_pool_fixture(first=0):
    # Synthetic evidence exercises the observer's rejection contract only.
    # Live tests must separately derive these CALL sites from the loaded ELF.
    sites = {
        str(i): {"function": 0x1000 + i * 32, "entry": 0x1010 + i * 32}
        for i in range(64)
    }
    before = [dict(p, pid=0, tgid=42, status=0) for p in PUBLISHED]
    before.append(
        {
            "entry": sites["0"]["entry"],
            "code": 0x5000,
            "pid": 0,
            "tgid": 43,
            "kind": 2,
            "status": -1,
        }
    )
    held = copy.deepcopy(before)
    for row in held[:2]:
        row["status"] = 1
    held.append(
        {"entry": 0x9000, "code": 0x6000, "pid": 0, "tgid": 44, "kind": 2, "status": -1}
    )
    full = held + [
        {
            "entry": sites[str(i)]["entry"],
            "code": 0x6000 + i * 4096,
            "pid": 0,
            "tgid": 45,
            "kind": 2,
            "status": -1,
        }
        for i in range(1, 61)
    ]
    evidence = {
        "sites": sites,
        "lock": 0xC00,
        "module_sha256": "a" * 64,
        "snapshots": {
            phase: {
                "source": {
                    "state": 0,
                    "modules": 1,
                    "frames": 0 if phase == "prepare" else 2,
                    "writers": 0,
                },
                "registry": copy.deepcopy(registry),
            }
            for phase, registry in (
                ("prepare", before),
                ("held", held),
                ("filled", full),
                ("drained", full),
            )
        },
    }
    lines = []
    for i in range(64):
        if i >= 61:
            lines.append(
                f"kd_exe_add: code block pool exhausted entry={sites[str(i)]['entry']:x} task=100 kind=2"
            )
        lines.append(
            f"kd_parallel code record: role=1 site={i} fn={sites[str(i)]['function']:x} task=100 waiter=ee00 owner=ee00 lock=c00 updates=1 value={(i + 7) * 33 + i + 1:x} valid=1"
        )
    lines.append("kd_parallel code queued: lock=c00 task=102 waiters=3")
    lines.append(
        f"mutex JIT not ready: task=103 waiter=104 entry={sites['63']['entry']:x} lock=c00 cpu=9"
    )
    for role in (3, 4, 5):
        lines.append(
            f"kd_parallel code record: role={role} site=63 fn={sites['63']['function']:x} task={100 + role} waiter=ee0{role} owner=ee0{role} lock=c00 updates=1 value={(role + 7) * 33 + 64:x} valid=1"
        )
    text = fixture(first)
    point = text.index("kd_parallel resume:")
    text = (
        "JIT code block pool ready: 64/64\n"
        + text[:point]
        + "\n".join(lines)
        + "\n"
        + text[point:]
    )
    text += (
        "\nkd_parallel code stats: warm=12000 filled=64 claimed=63 updates=12067 lock=0"
    )
    return text, evidence


class CodePoolTests(unittest.TestCase):
    def test_capacity_then_retirement_does_not_count_reloaded_arrivals(self):
        for first in (0, 1):
            text, evidence = code_pool_fixture(first)
            reloaded, metadata = reloaded_fixture(first)
            interval = reloaded[reloaded.index("kd_source reload: phase=begin") :]
            result = validate(
                text + "\n" + interval,
                PUBLISHED,
                0xFF,
                first,
                reload=metadata,
                code_pool=evidence,
            )
            self.assertEqual(result["code_pool"]["native_queue_records"], 3)
            self.assertEqual(result["reloaded_native_records"], 6)
            # A replacement interval cannot hide an extra capacity record.
            bad = interval.replace(
                "kd_source reload: phase=end",
                "kd_parallel code record: role=4\nkd_source reload: phase=end",
            )
            with self.assertRaises(AssertionError):
                validate(
                    text + "\n" + bad,
                    PUBLISHED,
                    0xFF,
                    first,
                    reload=metadata,
                    code_pool=evidence,
                )

    def test_capacity_and_queue_preserve_both_original_ack_orders(self):
        for first in (0, 1):
            text, evidence = code_pool_fixture(first)
            result = validate(text, PUBLISHED, 0xFF, first, code_pool=evidence)
            self.assertEqual(result["jit_bodies"], 2)
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(
                result["code_pool"],
                {
                    "allocated_blocks": 64,
                    "cold_sites": 64,
                    "missing_sites": 3,
                    "native_queue_records": 3,
                    "pre_wrapper_refusals": 1,
                },
            )

    def test_pool_count_does_not_replace_identity_or_live_frame_evidence(self):
        text, evidence = code_pool_fixture()
        for variant in range(11):
            bad = copy.deepcopy(evidence)
            full = bad["snapshots"]["filled"]["registry"]
            if variant == 0:
                full.pop()
            elif variant == 1:
                full[-1]["code"] = full[0]["code"]
            elif variant == 2:
                full[0]["code"] += 1
            elif variant == 3:
                full[-1]["status"] = 0
            elif variant == 4:
                full[-1]["entry"] = bad["sites"]["63"]["entry"]
            elif variant == 5:
                bad["snapshots"]["drained"]["source"]["frames"] = 0
            elif variant == 6:
                bad["snapshots"]["held"]["source"]["state"] = 1
            elif variant == 7:
                bad["snapshots"]["filled"]["source"]["writers"] = 1
            elif variant == 8:
                bad["sites"]["63"] = bad["sites"]["62"]
            elif variant == 9:
                bad["lock"] += 1
            else:
                bad["module_sha256"] = ""
            with self.subTest(variant=variant), self.assertRaises(AssertionError):
                validate(text, PUBLISHED, 0xFF, 0, code_pool=bad)

    def test_fallback_records_and_loaded_sites_are_required(self):
        text, evidence = code_pool_fixture()
        for old, new in (
            ("ready: 64/64", "ready: 32/64"),
            ("pool exhausted entry=17b0", "pool exhausted entry=0000"),
            ("fn=17e0", "fn=17c0"),
            ("waiters=3", "waiters=0"),
            ("task=103 waiter=104", "task=103 waiter=105"),
            ("cpu=9", "cpu=1"),
            ("owner=ee03", "owner=20"),
            ("updates=1", "updates=2"),
            ("value=18a", "value=18b"),
            ("filled=64", "filled=63"),
            ("updates=12067", "updates=12068"),
        ):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(
                    text.replace(old, new, 1), PUBLISHED, 0xFF, 0, code_pool=evidence
                )
        for label in (
            "kd_parallel code queued:",
            "mutex JIT not ready:",
            "kd_parallel code record: role=4",
            "kd_native ack:",
        ):
            line = next(line for line in text.splitlines() if line.startswith(label))
            for bad in (text.replace(line, "", 1), text + "\n" + line):
                with (
                    self.subTest(label=label),
                    self.assertRaises((AssertionError, ValueError)),
                ):
                    validate(bad, PUBLISHED, 0xFF, 0, code_pool=evidence)

    def test_completed_old_frames_cannot_fake_concurrent_pressure(self):
        text, evidence = code_pool_fixture()
        line = next(
            line
            for line in text.splitlines()
            if line.startswith("kd_parallel code record: role=5")
        )
        with self.assertRaises(AssertionError):
            validate(
                text.replace(line, "", 1) + "\n" + line,
                PUBLISHED,
                0xFF,
                0,
                code_pool=evidence,
            )
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 0)
        with self.assertRaises(AssertionError):
            validate(
                text + "\nJIT body witness: entry=17f0 lock=c00 body=1",
                PUBLISHED,
                0xFF,
                0,
                code_pool=evidence,
            )


def with_native_peers(text, first):
    """Compose renamed borrowers and peer cancellation around the frame contract.

    Synthetic log records test the oracle, not Linux waiting or live signals.
    """
    routed, arrived = [], 0
    controls = [
        f"kd_parallel routed native: lane={lane} task={20 + lane} waiter=1{lane} owner=2{lane} outer=a{lane} inner=b{lane} local=e{lane} local_owner=1{lane} after_owner=0 acquired=1 released=1 comm=kd_renamed valid=1"
        for lane in (0, 1)
    ]
    for line in text.splitlines():
        if line.startswith(
            ("kd_parallel arrive:", "kd_parallel resume:", "kd_parallel done:")
        ):
            lane = int(re.search(r"lane=(\d+)", line)[1])
            if line.startswith("kd_parallel arrive:"):
                routed.append(
                    f"kd_resume rename: task={20 + lane} old=klock_test new=kd_renamed cpu={4 * lane + 2} preempt_before=0 preempt_after=0 irq_before=0 irq_after=0 valid=1"
                )
            routed.append(line + " comm=kd_renamed")
            if line.startswith("kd_parallel arrive:"):
                arrived += 1
                if arrived == 2:
                    routed.extend(controls)
            if line.startswith("kd_parallel done:"):
                routed.append(
                    f"kd_resume rename: task={20 + lane} old=kd_renamed new=klock_test cpu={4 * lane + 2} preempt_before=0 preempt_after=0 irq_before=0 irq_after=0 valid=1"
                )
        else:
            routed.append(line)
    text = "\n".join(routed)
    queued = []
    for attempt in (1, 2):
        for lane in (0, 1):
            if attempt == 2:
                queued.append(
                    f"kd_parallel peer cancelled: lane={lane} task={100 + lane} waiter=d{lane} lock=b{lane} owner=2{lane} other_owner=2{1 - lane} error=4 pending=1 fatal=0 queued=0 matched=0 cancelled=1 acquired=0 released=0 valid=1"
                )
            queued += [
                f"kd_parallel peer try: lane={lane} attempt={attempt} task={100 + lane} waiter=d{lane} lock=b{lane} owner=2{lane} result=0 comm=kd_native valid=1",
                f"kd_parallel peer queued: lane={lane} attempt={attempt} task={100 + lane} waiter=d{lane} lock=b{lane} owner=2{lane} queued=1 matched=1 valid=1",
            ]
    marker = f"kd_parallel resume: lane={first} "
    text = text.replace(marker, "\n".join(queued) + "\n" + marker)
    for lane in (first, 1 - first):
        value = ((0x700 + lane) * 33 + 17) ^ 0x5A5A
        lines = [
            f"kd_parallel peer acquired: lane={lane} task={100 + lane} waiter=d{lane} lock=b{lane} owner=d{lane} other=b{1 - lane} other_owner=2{1 - lane} cross_try={0 if lane == first else 2} value={value:x} valid=1",
            f"kd_parallel peer released: lane={lane} task={100 + lane} acquired=1 released=1 value={value:x} valid=1",
        ]
        marker = f"kd_native ack: task={20 + lane} lock=b{lane} mutex=1 last_spin=0"
        text = text.replace(marker, marker + "\n" + "\n".join(lines))
    return (
        text
        + "\nkd_parallel peer stats: completed=3 acquired=2 released=2 cancelled=2 valid=1"
    )


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


class PeerSignalTests(unittest.TestCase):
    def client_logs(self):
        return [
            "\n".join(
                (
                    f"parallel peer client enter: lane={lane} pid={100 + lane}",
                    f"parallel peer client cancelled: lane={lane} pid={100 + lane} ret=-1 errno=4 signals=1",
                    f"parallel peer client return: lane={lane} pid={100 + lane} ret=0 errno=0 signals=1",
                )
            )
            + "\n"
            for lane in (0, 1)
        ]

    def control(self, phase, out, *, corrupt=""):
        # Proc, pidfd, source and signal APIs are all substitutes here. Live
        # tests must independently verify real wait lists and the same clients.
        from source_retirement import source

        client = out.parent / "mutex-signal-client"
        original_text, original_bytes, original_resolve = (
            Path.read_text,
            Path.read_bytes,
            Path.resolve,
        )

        def read_text(path, *args, **kwargs):
            if str(path).startswith("/proc/"):
                if path.name == "comm":
                    return "wrong\n" if corrupt == "comm" else "kd_native\n"
                if path.name == "status":
                    pid = int(path.parent.name)
                    return (
                        f"Tgid:\t{pid}\nThreads:\t{2 if corrupt == 'threads' else 1}\n"
                    )
            return original_text(path, *args, **kwargs)

        def read_bytes(path, *args, **kwargs):
            if str(path).startswith("/proc/") and path.name == "cmdline":
                lane = int(path.parent.name) - 100
                values = [str(client), str(lane), "kd_native", "parallel-peer"]
                if corrupt == "argv":
                    values[-1] = "pending-int"
                return b"\0".join(os.fsencode(v) for v in values) + b"\0"
            return original_bytes(path, *args, **kwargs)

        def resolve(path, *args, **kwargs):
            if str(path).startswith("/proc/") and path.name == "exe":
                return out / "wrong" if corrupt == "exe" else client
            return original_resolve(path, *args, **kwargs)

        state = {
            "state": 0,
            "modules": 1,
            "frames": 1 if corrupt == "frames" else 2,
            "writers": 0,
        }
        text = with_native_peers(fixture(0), 0)
        if corrupt == "queue":
            text = text.replace(
                "queued: lane=1 attempt=1 task=101", "queued: lane=1 attempt=1 task=102"
            )
        with (
            patch("mutex_parallel_protocol.os.open", return_value=90),
            patch("mutex_parallel_protocol.os.close") as close,
            patch.object(source, "info", return_value=state),
            patch("mutex_parallel_protocol.subprocess.check_output", return_value=text),
            patch(
                "mutex_parallel_protocol.os.pidfd_open", side_effect=[77, 78]
            ) as opened,
            patch(
                "mutex_parallel_protocol.select.select",
                return_value=([77] if corrupt == "exited" else [], [], []),
            ),
            patch("mutex_parallel_protocol.signal.pidfd_send_signal") as send,
            patch.object(Path, "read_text", read_text),
            patch.object(Path, "read_bytes", read_bytes),
            patch.object(Path, "resolve", resolve),
        ):
            if corrupt:
                with self.assertRaises(AssertionError):
                    signal_native_peers(phase, out)
                send.assert_not_called()
            else:
                signal_native_peers(phase, out)
                self.assertEqual(send.call_count, 2 if phase == "signal" else 0)
                if phase == "signal":
                    self.assertEqual(
                        [c.args for c in send.call_args_list],
                        [(77, 10, None, 0), (78, 10, None, 0)],
                    )
            self.assertEqual(close.call_count, 1 + opened.call_count)

    def test_verified_pidfds_and_userspace_retry_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "native-peers"
            out.mkdir()
            (root / "mutex-signal-client").write_bytes(b"fixture client")
            clients = self.client_logs()
            for lane, log in enumerate(clients):
                (out / f"role-{lane}.log").write_text(log)
            self.control("signal", out)
            self.control("requeued", out)
            evidence = json.loads((out / "signal.json").read_text())
            text = with_native_peers(fixture(0), 0)
            self.assertEqual(
                validate_peer_signals(text, evidence, clients),
                {
                    "pidfd_signals": 2,
                    "userspace_cancellations": 2,
                    "explicit_retries": 2,
                },
            )
            for key, value in (
                ("pid", 999),
                ("pidfd", False),
                ("signum", 9),
                ("before_ns", 0),
                ("lane", 1),
            ):
                bad = copy.deepcopy(evidence)
                bad["peers"][0][key] = value
                with self.subTest(key=key), self.assertRaises(AssertionError):
                    validate_peer_signals(text, bad, clients)
            bad = copy.deepcopy(evidence)
            bad["source"]["requeued"]["frames"] = 1
            with self.assertRaises(AssertionError):
                validate_peer_signals(text, bad, clients)
            for old, new in (
                ("errno=4", "errno=0"),
                ("ret=-1", "ret=0"),
                ("signals=1", "signals=2"),
            ):
                with self.subTest(field=old), self.assertRaises(AssertionError):
                    validate_peer_signals(
                        text, evidence, [clients[0].replace(old, new), clients[1]]
                    )

    def test_wrong_client_or_missing_retained_frames_is_never_signalled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "native-peers"
            out.mkdir()
            (root / "mutex-signal-client").write_bytes(b"fixture client")
            for lane, log in enumerate(self.client_logs()):
                (out / f"role-{lane}.log").write_text(log)
            for corrupt in (
                "comm",
                "threads",
                "argv",
                "exe",
                "frames",
                "queue",
                "exited",
            ):
                with self.subTest(corrupt=corrupt):
                    self.control("signal", out, corrupt=corrupt)

    def test_delivered_client_has_no_automatic_eintr_retry(self):
        source = Path(__file__).with_name("mutex_parallel_client_fixture.c")
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "client-fixture"
            subprocess.run(
                [
                    *shlex.split(os.environ.get("CC", "cc")),
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(source),
                    "-o",
                    str(executable),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(executable)], check=True, text=True, capture_output=True, timeout=5
            )
            self.assertIn(
                "24 valid/error rounds and invalid target pass", result.stdout
            )


def waiter_signal_fixture(first):
    """Compose task-exit evidence with the existing full two-frame oracle."""
    text = with_native_peers(fixture(first), first)
    text = "\n".join(
        line + f" pending=1 fatal={int(f'lane={first} ' in line)}"
        if line.startswith("kd_parallel resume:") else line
        for line in text.splitlines()
    )
    prefix = text[:text.index(f"kd_parallel resume: lane={1 - first} ")]
    evidence = {
        "first": first, "complete": True, "client_sha256": "a" * 64,
        "source": {
            "before": {"state": 0, "modules": 1, "frames": 2, "writers": 0},
            "after_exit": {"state": 1, "modules": 1, "frames": 1, "writers": 1},
        },
        "waiters": [
            {"lane": lane, "pid": 20 + lane, "pidfd": True,
             "signum": 9 if lane == first else 10, "before_ns": 100, "after_ns": 101}
            for lane in (0, 1)
        ],
        "after_exit": {
            "pidfd_exited": True, "survivor_alive": True, "observed_ns": 200,
            "log_bytes": len(prefix.encode()),
            "log_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        },
    }
    clients = [
        f"parallel waiter client enter: lane={lane} pid={20 + lane}\n"
        + ("" if lane == first else
           f"parallel waiter client return: lane={lane} pid={20 + lane} ret=0 errno=0 signals=1\n")
        for lane in (0, 1)
    ]
    statuses = "\n".join(f"{i}\t{137 if i == 4 + first else 0}" for i in range(8))
    return text, evidence, clients, statuses


class OriginalWaiterSignalTests(unittest.TestCase):
    def test_both_orders_keep_a_live_frame_after_verified_fatal_exit(self):
        for first in (0, 1):
            text, evidence, clients, statuses = waiter_signal_fixture(first)
            result = validate(text, PUBLISHED, 0xFF, first, native_peers=True)
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(result["jit_bodies"], 2)
            self.assertEqual(
                validate_waiter_signals(text, evidence, clients, statuses, first),
                {"pidfd_signals": 2, "fatal_exits": 1, "surviving_native_frames": 1,
                 "nonfatal_returns": 1},
            )

    def test_exit_status_cannot_replace_identity_ack_or_pending_signal(self):
        text, evidence, clients, statuses = waiter_signal_fixture(0)
        for path, value in (
            (("complete",), False),
            (("first",), 1),
            (("source", "after_exit", "frames"), 0),
            (("source", "after_exit", "writers"), 0),
            (("after_exit", "pidfd_exited"), False),
            (("after_exit", "survivor_alive"), False),
            (("after_exit", "observed_ns"), 99),
            (("after_exit", "log_sha256"), "a" * 64),
            (("waiters", 0, "pid"), 99),
            (("waiters", 0, "signum"), 10),
            (("waiters", 1, "pidfd"), False),
        ):
            bad = copy.deepcopy(evidence)
            item = bad
            for key in path[:-1]:
                item = item[key]
            item[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(AssertionError):
                validate_waiter_signals(text, bad, clients, statuses, 0)
        for old, new in (
            ("kd_native ack: task=20 lock=a0", "kd_native ack: task=21 lock=a0"),
            ("kd_parallel done: lane=0 task=20", "kd_parallel done: lane=1 task=20"),
            ("pending=1 fatal=1", "pending=0 fatal=1"),
            ("comm=kd_renamed pending=1 fatal=0", "comm=kd_renamed pending=1 fatal=1"),
        ):
            # Recompute the prefix identity so semantic checks, not merely
            # the archive hash mismatch, reject the altered history.
            bad_text = text.replace(old, new, 1)
            prefix = bad_text[:bad_text.index("kd_parallel resume: lane=1 ")]
            bad = copy.deepcopy(evidence)
            bad["after_exit"].update(log_bytes=len(prefix.encode()),
                                     log_sha256=hashlib.sha256(prefix.encode()).hexdigest())
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate_waiter_signals(bad_text, bad, clients, statuses, 0)
        for bad_clients, bad_status in (
            ([clients[0] + "parallel waiter client return\n", clients[1]], statuses),
            ([clients[0], clients[1].replace("signals=1", "signals=0")], statuses),
            (clients, statuses.replace("137", "0")),
            (clients, statuses.replace("137", "124")),
            (clients, statuses + "\n4\t137"),
        ):
            with self.subTest(clients=bad_clients, status=bad_status), self.assertRaises(AssertionError):
                validate_waiter_signals(text, evidence, bad_clients, bad_status, 0)

    def test_controller_checks_real_client_contract_before_sending(self):
        # Only proc/device/pidfd/signal primitives are substituted. Exercise
        # the delivered controller, including both handle lifetimes and gate
        # release on pre-send identity failure or missing post-send exit.
        from source_retirement import source

        for first, corrupt in [(0, ""), (1, "")] + [
            (0, name) for name in ("comm", "argv", "threads", "exe", "frames", "exited", "no-exit")
        ]:
            with self.subTest(first=first, corrupt=corrupt), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                client = out / "mutex-signal-client"
                client.write_bytes(b"test client")
                text, expected, clients, statuses = waiter_signal_fixture(first)
                for lane, log in enumerate(clients):
                    (out / f"role-{lane}-2.log").write_text(log.splitlines()[0] + "\n")
                original_text, original_bytes, original_resolve, original_write = (
                    Path.read_text, Path.read_bytes, Path.resolve, Path.write_text
                )
                released = []

                def read_text(path, *args, **kwargs):
                    if str(path).startswith("/sys/"):
                        return "Y\n"
                    if str(path).startswith("/proc/"):
                        if path.name == "comm":
                            return "klock_test\n" if corrupt == "comm" else "kd_renamed\n"
                        if path.name == "status":
                            return f"Tgid:\t{path.parent.name}\nThreads:\t{2 if corrupt == 'threads' else 1}\n"
                    return original_text(path, *args, **kwargs)

                def read_bytes(path, *args, **kwargs):
                    if str(path).startswith("/proc/") and path.name == "cmdline":
                        lane = int(path.parent.name) - 20
                        args = [str(client), str(lane), "klock_test",
                                "parallel-peer" if corrupt == "argv" else "parallel-waiter"]
                        return b"\0".join(os.fsencode(a) for a in args) + b"\0"
                    return original_bytes(path, *args, **kwargs)

                def resolve(path, *args, **kwargs):
                    if str(path).startswith("/proc/") and path.name == "exe":
                        return out / "wrong" if corrupt == "exe" else client
                    return original_resolve(path, *args, **kwargs)

                def write_text(path, value, *args, **kwargs):
                    if str(path).startswith("/sys/"):
                        released.append((path.name, value))
                        return len(value)
                    return original_write(path, value, *args, **kwargs)

                def selected(handles, writes, errors, timeout):
                    ready = handles if (
                        corrupt == "exited" or (timeout == 10 and corrupt != "no-exit")
                    ) else []
                    return ready, [], []

                before = dict(expected["source"]["before"])
                if corrupt == "frames":
                    before["frames"] = 1
                initial = text[:text.index(f"kd_parallel resume: lane={first} ")]
                after = text.encode()[:expected["after_exit"]["log_bytes"]].decode()
                with (
                    patch("mutex_parallel_protocol.os.open", return_value=90),
                    patch("mutex_parallel_protocol.os.close") as close,
                    patch.object(source, "info", side_effect=[before, before, expected["source"]["after_exit"]]),
                    patch("mutex_parallel_protocol.subprocess.check_output", side_effect=[initial, after]),
                    patch("mutex_parallel_protocol.os.pidfd_open", side_effect=[77, 78]) as opened,
                    patch("mutex_parallel_protocol.select.select", side_effect=selected),
                    patch("mutex_parallel_protocol.signal.pidfd_send_signal") as send,
                    patch.object(Path, "read_text", read_text),
                    patch.object(Path, "read_bytes", read_bytes),
                    patch.object(Path, "resolve", resolve),
                    patch.object(Path, "write_text", write_text),
                    # Path.touch also uses os.open/close. Substitute this
                    # separate readiness file so it cannot alias the mocked
                    # source descriptor, and assert the handshake explicitly.
                    patch.object(Path, "touch", autospec=True) as ready,
                ):
                    if corrupt:
                        with self.assertRaises(AssertionError):
                            signal_original_waiters(out, first)
                        self.assertEqual(send.call_count, 2 if corrupt == "no-exit" else 0)
                    else:
                        signal_original_waiters(out, first)
                        self.assertEqual(
                            [c.args for c in send.call_args_list],
                            [(77, 9 if first == 0 else 10, None, 0),
                             (78, 9 if first == 1 else 10, None, 0)],
                        )
                        saved = json.loads((out / "waiter-signals.json").read_text())
                        validate_waiter_signals(text, saved, clients, statuses, first)
                    self.assertEqual(close.call_count, 1 + opened.call_count)
                    self.assertEqual(released, [("mutex_parallel_exit_hold", "0\n")])
                    if not corrupt or corrupt == "no-exit":
                        ready.assert_called_once_with(out / "waiter-signals.ready")
                    else:
                        ready.assert_not_called()


def shadow_fixture(first=0):
    """Compose a real-capacity contract into the existing peer/pool fixture.

    This is an oracle fixture, not proof of kernel allocation or Linux waiting;
    the same complex live scripts must independently produce these observations.
    """
    text, code = code_pool_fixture(first)
    text = with_native_peers(text, first)
    base, stride, entry = 0x100000, 32, 0x8888
    evidence = {
        "base": base,
        "stride": stride,
        "entry": entry,
        "count": 1025,
        "module_sha256": "b" * 64,
        "snapshots": {
            phase: {
                "allocated": allocated,
                "source": {
                    "state": 0,
                    "modules": 1,
                    "frames": 0 if phase == "prepare" else 2,
                    "writers": 0,
                },
            }
            for phase, allocated in (
                ("prepare", 3),
                ("held", 5),
                ("filled", 1024),
                ("drained", 1024),
            )
        },
    }
    declarations = [
        f"kd_parallel shadow layout: base={base:x} stride={stride} count=1025"
    ]
    declarations += [
        f"kd_hotlock selftest promote: lock={base + i * stride:x}" for i in range(1025)
    ]
    lines = []
    value = 0
    for role, indexes in ((0, range(1025)), (1, [1024]), (2, [1024]), (3, [1024])):
        for i in indexes:
            lock = base + i * stride
            if (role == 0 and i >= 1019) or role >= 2:
                lines.append(
                    f"mutex shadow fallback: task={200 + role} entry={entry:x} lock={lock:x} cpu=9"
                )
            if role == 1:
                lines.append(
                    f"kd_parallel shadow queued: task=201 owner=ff201 lock={lock:x} count=2 matched=3"
                )
            value = (i + 7 if not role else value) * 33 + i + 1
            lines.append(
                f"kd_parallel shadow record: role={role} index={i} task={200 + role} waiter=ff{200 + role} owner=ff{200 + role} lock={lock:x} registered={int(not role and i < 1019)} updates={role + 1} value={value:x} valid=1"
            )
    marker = "kd_parallel peer try: lane=0 "
    text = text.replace(marker, "\n".join(lines) + "\n" + marker, 1)
    return "\n".join(declarations) + "\n" + text, code, evidence


class ShadowPoolTests(unittest.TestCase):
    def check(self, text, code, evidence, first=0, **kwargs):
        return validate(
            text,
            PUBLISHED,
            0xFF,
            first,
            code_pool=code,
            native_peers=True,
            shadow_pool=evidence,
            **kwargs,
        )

    def rejects(self, text, code, evidence, **kwargs):
        with self.assertRaises((AssertionError, ValueError, KeyError)):
            self.check(text, code, evidence, **kwargs)

    def test_shadow_full_preserves_both_frame_peer_retirement_orders(self):
        for first in (0, 1):
            text, code, evidence = shadow_fixture(first)
            native, metadata = reloaded_fixture(first)
            native = native[native.index("kd_source reload: phase=begin") :]
            result = self.check(
                text + "\n" + native, code, evidence, first, reload=metadata
            )
            self.assertEqual(
                result["shadow_pool"],
                {
                    "allocated_shadows": 1024,
                    "previous_shadows": 5,
                    "new_shadows": 1019,
                    "filler_records": 1025,
                    "native_queue_records": 3,
                    "target_refusals": 8,
                },
            )
            self.assertEqual(result["jit_bodies"], 2)
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(result["reloaded_native_records"], 6)
            self.assertEqual(result["native_peers"]["queued"], 4)
            self.assertEqual(result["code_pool"]["allocated_blocks"], 64)

    def test_counts_require_real_membership_identity_and_live_frames(self):
        text, code, evidence = shadow_fixture()
        for phase in evidence["snapshots"]:
            for key, value in (
                ("allocated", 0),
                ("allocated", 1023),
                ("frames", 1),
                ("state", 2),
            ):
                bad = copy.deepcopy(evidence)
                if key == "allocated":
                    bad["snapshots"][phase][key] = value
                else:
                    bad["snapshots"][phase]["source"][key] = value
                # Prepare can be any observed positive count no greater than
                # the held snapshot; the exact allocation delta is checked later.
                with self.subTest(phase=phase, key=key, value=value):
                    self.rejects(text, code, bad)
        for key, value in (
            ("base", 1),
            ("stride", 1),
            ("count", 1024),
            ("entry", 1),
            ("module_sha256", ""),
        ):
            self.rejects(text, code, {**evidence, key: value})

    def test_owner_packets_queue_and_each_refusal_are_not_optional(self):
        text, code, evidence = shadow_fixture()
        for label in (
            "kd_parallel shadow layout:",
            "kd_hotlock selftest promote:",
            "kd_parallel shadow record: role=0",
            "kd_parallel shadow record: role=2",
            "mutex shadow fallback:",
            "kd_parallel shadow queued:",
        ):
            row = next(line for line in text.splitlines() if line.startswith(label))
            self.rejects(text.replace(row, "", 1), code, evidence)
            self.rejects(text + "\n" + row, code, evidence)
        prefix = "kd_parallel shadow record: role=2"
        row = next(line for line in text.splitlines() if line.startswith(prefix))
        for key, value in (
            ("role", "1"),
            ("index", "0"),
            ("task", "20"),
            ("owner", "20"),
            ("lock", "a0"),
            ("registered", "1"),
            ("updates", "2"),
            ("value", "0"),
            ("valid", "0"),
        ):
            replacement = re.sub(rf"\b{key}=\w+", f"{key}={value}", row)
            self.rejects(text.replace(row, replacement), code, evidence)
        for old, new in (
            ("count=2 matched=3", "count=2 matched=1"),
            ("entry=8888", "entry=8889"),
            ("registered=0 updates=1", "registered=1 updates=1"),
        ):
            self.rejects(text.replace(old, new, 1), code, evidence)

    def test_pressure_must_not_be_after_old_frames_or_hidden_in_reload(self):
        text, code, evidence = shadow_fixture()
        row = next(
            line
            for line in text.splitlines()
            if line.startswith("kd_parallel shadow record: role=3")
        )
        self.rejects(text.replace(row, "", 1) + "\n" + row, code, evidence)
        with self.assertRaises(AssertionError):
            validate(text, PUBLISHED, 0xFF, 0, code_pool=code, native_peers=True)
        native, metadata = reloaded_fixture(0)
        interval = native[native.index("kd_source reload: phase=begin") :]
        for label in ("layout", "record", "queued"):
            bad = interval.replace(
                "kd_source reload: phase=end",
                f"kd_parallel shadow {label}: role=0\nkd_source reload: phase=end",
            )
            self.rejects(text + "\n" + bad, code, evidence, reload=metadata)


if __name__ == "__main__":
    unittest.main()
