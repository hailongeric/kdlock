"""Corrupted-log tests, not a kernel concurrency or JIT-execution model."""

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remote_outer_protocol import (
    capture_placement,
    validate,
    validate_chain,
    validate_multi_roots,
    validate_placement,
)


def fixture(stage, native=False, renamed=False):
    lines = []

    def event(label, **fields):
        lines.append(
            label + ": " + " ".join(f"{key}={value}" for key, value in fields.items())
        )

    event(
        "kd_remote start",
        task=10,
        cpu=2,
        entry="200",
        ip="210",
        outer="b",
        parent_outer="a",
        owner_task="bbb",
    )
    if stage != 1:
        event(
            "kd_native begin",
            task=10,
            cpu=2,
            entry="200",
            ip="500",
            sp="600",
            outer="b",
            outer_released=0,
            remaining=1,
            mutex=0,
        )
        event(
            "kd_native begin",
            task=10,
            cpu=4,
            entry="200",
            ip="500",
            sp="600",
            outer="a",
            outer_released=int(stage == 3),
            remaining=int(stage == 2),
            mutex=0,
        )
    event(
        "kd_spin outer release",
        task=10,
        cpu=4,
        outer="a",
        remaining=0,
        remote=1,
        owner_task="ddd",
    )
    if stage != 2:
        event("kd_remote unlock", task=10, cpu=4, outer="a", lock="a", result=0)
    event(
        "kd_remote observe",
        task=30,
        cpu=9 if native else 8,
        origin_cpu=0,
        waiter="aaa",
        waiter_pid=10,
        outer="a",
        inner="b",
        child="c",
        a_word=1,
        b_word=3,
        c_word=1,
        a_owner="ccc",
        b_owner="bbb",
        preempt=2,
        irq=0,
        prefix=1,
        suffix=0,
        valid=1,
        comm="kd_native" if native else "klock_test",
    )
    if stage != 1:
        if renamed:
            event(
                "kd_resume rename",
                task=10,
                new="kd_renamed",
                valid=1,
                preempt_before=1,
                preempt_after=1,
                irq_before=0,
                irq_after=0,
            )
        if stage == 2:
            event("kd_native ack", task=10, lock="a", mutex=0, last_spin=0)
        event("kd_native complete", task=10, outer="b", mutex=0)
        event("kd_native complete", task=10, outer="a", mutex=0)
        event("kd_native ack", task=10, lock="b", mutex=0, last_spin=1)
        if renamed:
            event(
                "kd_resume rename",
                task=10,
                new="klock_test",
                valid=1,
                preempt_before=0,
                preempt_after=0,
                irq_before=0,
                irq_after=0,
            )
    else:
        for lock in ("a", "b"):
            event("kd_spin lock stats", lock=lock, jit_success=1)
    event(
        "kd_native stats",
        started=0 if stage == 1 else 2,
        completed=0 if stage == 1 else 2,
        unlocks=0 if stage == 1 else 2 if stage == 2 else 1,
    )
    event(
        "kd_remote workload",
        stage=stage,
        native_owner=int(native),
        prefix=1,
        suffix=1,
        observed=1,
    )
    return "\n".join(lines)


class RemoteOracleTests(unittest.TestCase):
    def test_origin_and_native_executor_must_match_placement(self):
        text = fixture(2)
        for corrupted in (
            text.replace("origin_cpu=0", "origin_cpu=1"),
            text.replace("cpu=4", "cpu=6", 1),
        ):
            with self.subTest(log=corrupted), self.assertRaises(AssertionError):
                validate(corrupted, 2, False, False)

    def test_controlled_histories(self):
        for stage in (1, 2, 3):
            for native in (False, True):
                for renamed in (False,) if stage == 1 else (False, True):
                    with self.subTest(stage=stage, native=native, renamed=renamed):
                        validate(
                            fixture(stage, native, renamed), stage, native, renamed
                        )

    def test_missing_and_duplicate_witnesses(self):
        for stage in (1, 2, 3):
            text = fixture(stage)
            for line in text.splitlines():
                for broken in (text.replace(line, ""), text + "\n" + line):
                    with (
                        self.subTest(stage=stage, line=line, broken=broken),
                        self.assertRaises(AssertionError),
                    ):
                        validate(broken, stage, False, False)

    def test_owner_cpu_ledger_and_pin_corruption(self):
        for stage in (1, 2, 3):
            text = fixture(stage)
            for old, new in (
                ("cpu=2", "cpu=4"),
                ("owner_task=bbb", "owner_task=eee"),
                ("owner_task=ddd", "owner_task=aaa"),
                ("parent_outer=a", "parent_outer=b"),
                ("entry=200", "entry=210"),
                ("remote=1", "remote=0"),
                ("valid=1", "valid=0"),
                ("b_word=3", "b_word=0"),
                ("b_owner=bbb", "b_owner=aaa"),
                ("waiter_pid=10", "waiter_pid=20"),
                ("preempt=2", "preempt=1"),
                ("suffix=0", "suffix=1"),
                ("result=0", "result=-2"),
                ("completed=2", "completed=1"),
                ("last_spin=1", "last_spin=0"),
                ("outer_released=1", "outer_released=0"),
                (
                    "outer=a outer_released=1 remaining=0",
                    "outer=a outer_released=1 remaining=1",
                ),
            ):
                if old not in text:
                    continue
                with (
                    self.subTest(stage=stage, old=old),
                    self.assertRaises(AssertionError),
                ):
                    validate(text.replace(old, new), stage, False, False)

    def test_release_must_precede_independent_owner_progress(self):
        text = fixture(1)
        release = next(
            line
            for line in text.splitlines()
            if line.startswith("kd_spin outer release")
        )
        with self.assertRaises(AssertionError):
            validate(text.replace(release, "") + "\n" + release, 1, False, False)


def chain_fixture(stage, native=False, renamed=False, reverse=False):
    lines = []

    def event(label, **fields):
        lines.append(label + ": " + " ".join(f"{k}={v}" for k, v in fields.items()))

    cpus = {"a": 4, "b": 2, "c": 11}
    owners = {"a": "aaa", "b": "bbb", "c": "ccc"}
    order = ["b", "a"] if reverse else ["a", "b"]
    translated = 0 if stage == 2 else 1 if stage == 4 else 2
    for index, lock in enumerate(("b", "c")):
        event(
            "kd_remote start",
            task=10,
            cpu=cpus[lock],
            entry="200",
            ip="210" if index == 0 else "220",
            outer=lock,
            parent_outer="a" if index == 0 else "b",
            owner_task=owners[lock],
        )

    def release(lock, jit):
        event(
            "kd_spin outer release",
            task=10,
            cpu=cpus[lock],
            outer=lock,
            remaining=0,
            remote=1,
            owner_task=owners[lock],
        )
        if jit:
            if lock == "a":
                event("kd_remote unlock", task=10, cpu=4, outer="a", lock="a", result=0)
            event("kd_remote unlock", task=10, cpu=2, outer="b", lock=lock, result=0)
        else:
            event("kd_native ack", task=10, lock=lock, mutex=0, last_spin=0)

    for lock in order[:translated]:
        release(lock, True)
    if stage != 1:
        for lock in ("c", "b", "a"):
            is_released = lock in order[:translated]
            event(
                "kd_native begin",
                task=10,
                cpu=cpus[lock],
                outer=lock,
                entry="200",
                ip="500",
                sp="600",
                mutex=0,
                outer_released=int(is_released),
                remaining=int(not is_released),
            )
        if renamed:
            event(
                "kd_resume rename",
                task=10,
                new="kd_renamed",
                valid=1,
                preempt_before=1,
                preempt_after=1,
                irq_before=0,
                irq_after=0,
            )
        for lock in order[translated:]:
            release(lock, False)
    event(
        "kd_chain observe",
        task=30,
        cpu=9 if native else 8,
        origin_cpu=0,
        owner_task="ddd",
        waiter="eee",
        waiter_pid=10,
        a="a",
        b="b",
        c="c",
        d="d",
        a_word=1,
        b_word=1,
        c_word=3,
        d_word=1,
        a_owner="0" if native else "ddd",
        b_owner="0" if native else "ddd",
        c_owner="ccc",
        preempt=3,
        irq=0,
        prefix=1,
        suffix=0,
        valid=1,
        comm="kd_native" if native else "klock_test",
    )
    if stage == 1:
        for lock in ("a", "b", "c"):
            event("kd_spin lock stats", lock=lock, jit_success=1)
    else:
        for lock in ("c", "b", "a"):
            event("kd_native complete", task=10, outer=lock, mutex=0)
        event("kd_native ack", task=10, lock="c", mutex=0, last_spin=1)
        if renamed:
            event(
                "kd_resume rename",
                task=10,
                new="klock_test",
                valid=1,
                preempt_before=0,
                preempt_after=0,
                irq_before=0,
                irq_after=0,
            )
    event(
        "kd_native stats",
        started=0 if stage == 1 else 3,
        completed=0 if stage == 1 else 3,
        unlocks=0 if stage == 1 else 3 - translated,
    )
    event(
        "kd_chain workload",
        stage=stage,
        native_owner=int(native),
        reverse=int(reverse),
        depth=3,
        prefix=1,
        suffix=1,
        observed=1,
    )
    return "\n".join(lines)


class ChainOracleTests(unittest.TestCase):
    def test_three_executor_histories_and_native_boundaries(self):
        for stage in (1, 2, 3, 4):
            for native in (False, True):
                for reverse in (False, True):
                    for renamed in (False,) if stage == 1 else (False, True):
                        with self.subTest(
                            stage=stage, native=native, reverse=reverse, renamed=renamed
                        ):
                            validate_chain(
                                chain_fixture(stage, native, renamed, reverse),
                                stage,
                                native,
                                renamed,
                                reverse,
                            )

    def test_missing_duplicate_and_wrong_scope(self):
        for stage in (1, 2, 3, 4):
            for reverse in (False, True):
                text = chain_fixture(stage, reverse=reverse)
                for line in text.splitlines():
                    for bad in (text.replace(line, ""), text + "\n" + line):
                        with (
                            self.subTest(stage=stage, reverse=reverse, line=line),
                            self.assertRaises(AssertionError),
                        ):
                            validate_chain(bad, stage, False, False, reverse)

    def test_owner_cpu_rpc_ledger_and_last_pin_corruption(self):
        for stage in (1, 2, 3, 4):
            for reverse in (False, True):
                text = chain_fixture(stage, renamed=stage != 1, reverse=reverse)
                for old, new in (
                    ("cpu=11", "cpu=2"),
                    ("cpu=4", "cpu=2"),
                    ("owner_task=aaa", "owner_task=eee"),
                    ("owner_task=bbb", "owner_task=ccc"),
                    ("parent_outer=b", "parent_outer=a"),
                    ("ip=220", "ip=210"),
                    ("entry=200", "entry=210"),
                    ("c_owner=ccc", "c_owner=ddd"),
                    ("b_owner=ddd", "b_owner=bbb"),
                    ("preempt=3", "preempt=2"),
                    ("remote=1", "remote=0"),
                    ("result=0", "result=-2"),
                    ("outer=a lock=a", "outer=b lock=a"),
                    ("outer=b lock=a", "outer=a lock=a"),
                    ("outer_released=1 remaining=0", "outer_released=1 remaining=1"),
                    ("outer_released=0 remaining=1", "outer_released=0 remaining=0"),
                    ("last_spin=1", "last_spin=0"),
                    ("lock=c mutex=0", "lock=d mutex=0"),
                    ("completed=3", "completed=2"),
                    ("suffix=0", "suffix=1"),
                    (
                        "preempt_before=0 preempt_after=0",
                        "preempt_before=1 preempt_after=1",
                    ),
                ):
                    if old not in text:
                        continue
                    with (
                        self.subTest(stage=stage, reverse=reverse, old=old),
                        self.assertRaises(AssertionError),
                    ):
                        validate_chain(
                            text.replace(old, new), stage, False, stage != 1, reverse
                        )

    def test_reordered_observation_release_and_native_packet(self):
        for stage in (1, 2, 3, 4):
            text = chain_fixture(stage)
            for tag in ("kd_chain observe", "kd_spin outer release", "kd_native begin"):
                found = [line for line in text.splitlines() if line.startswith(tag)]
                if not found:
                    continue
                bad = text.replace(found[0], "") + "\n" + found[0]
                with (
                    self.subTest(stage=stage, tag=tag),
                    self.assertRaises(AssertionError),
                ):
                    validate_chain(bad, stage, False, False, False)


CROSS_LAYOUTS = (
    [20, 21, 22, 3, 4, 25, 6, 27, 8, 9, 10, 11, 12, 13],
    [0, 1, 2, 23, 24, 5, 26, 7, 28, 29, 30, 31, 32, 33],
)


def placement_fixture(depth, cpus):
    return {
        "depth": depth,
        "role_cpus": cpus,
        "role_nodes": [int(cpu >= 20) for cpu in cpus],
        "allowed_cpus": list(range(40)),
        "online_cpus": list(range(40)),
        "require_cross_numa": True,
    }


def remap_trace(text, cpus):
    return re.sub(
        r"\b(cpu|origin_cpu)=(\d+)",
        lambda match: f"{match[1]}={cpus[int(match[2])]}",
        text,
    )


class PlacementOracleTests(unittest.TestCase):
    def test_actual_cross_node_histories(self):
        for layout in CROSS_LAYOUTS:
            for depth in (2, 3):
                cpus = layout[:10] if depth == 2 else layout
                placement = placement_fixture(depth, cpus)
                for stage in range(1, 4 if depth == 2 else 5):
                    for native in (False, True):
                        for reverse in (False,) if depth == 2 else (False, True):
                            for renamed in (False,) if stage == 1 else (False, True):
                                with self.subTest(
                                    layout=layout,
                                    depth=depth,
                                    stage=stage,
                                    native=native,
                                    reverse=reverse,
                                    renamed=renamed,
                                ):
                                    if depth == 2:
                                        result = validate(
                                            remap_trace(
                                                fixture(stage, native, renamed), cpus
                                            ),
                                            stage,
                                            native,
                                            renamed,
                                            placement,
                                        )
                                    else:
                                        result = validate_chain(
                                            remap_trace(
                                                chain_fixture(
                                                    stage, native, renamed, reverse
                                                ),
                                                cpus,
                                            ),
                                            stage,
                                            native,
                                            renamed,
                                            reverse,
                                            placement,
                                        )
                                    expected = [cpus[0], cpus[4], cpus[2]]
                                    if depth == 3:
                                        expected.append(cpus[11])
                                    self.assertEqual(result["cpus"], expected)
                                    self.assertEqual(
                                        result["nodes"],
                                        [int(cpu >= 20) for cpu in expected],
                                    )
                                    self.assertTrue(result["require_cross_numa"])

    def test_default_checks_do_not_invent_node_evidence(self):
        self.assertIsNone(validate(fixture(1), 1, False, False)["nodes"])
        self.assertIsNone(
            validate_chain(chain_fixture(1), 1, False, False, False)["nodes"]
        )

    def test_invalid_cpu_and_topology_manifests(self):
        good = placement_fixture(3, CROSS_LAYOUTS[0])
        bad = []
        for key, value in (
            ("depth", 2),
            ("depth", 3.0),
            ("role_cpus", good["role_cpus"][:-1]),
            ("role_nodes", [0] * 14),
            ("allowed_cpus", list(range(20))),
            ("online_cpus", list(range(20))),
            ("require_cross_numa", 1),
        ):
            changed = copy.deepcopy(good)
            changed[key] = value
            bad.append(changed)
        for key, index, value in (
            ("role_cpus", 1, good["role_cpus"][0]),
            ("role_cpus", 1, -1),
            ("role_nodes", 1, True),
            ("role_nodes", 0, 0),
            ("role_nodes", 6, 1),
            ("role_nodes", 12, 1),
        ):
            changed = copy.deepcopy(good)
            changed[key][index] = value
            bad.append(changed)
        missing = copy.deepcopy(good)
        del missing["online_cpus"]
        bad.append(missing)
        for changed in bad:
            with self.subTest(manifest=changed), self.assertRaises(AssertionError):
                validate_placement(changed, 3)

    def test_wrong_observed_origin_executor_or_manifest(self):
        cpus = CROSS_LAYOUTS[0]
        placement = placement_fixture(3, cpus)
        text = remap_trace(chain_fixture(3, renamed=True), cpus)
        for changed in (
            text.replace("origin_cpu=20", "origin_cpu=0"),
            text.replace("origin_cpu=20", ""),
            text.replace("cpu=22", "cpu=2"),
            text.replace("cpu=11", "cpu=31"),
            text.replace("cpu=8", "cpu=28"),
        ):
            with (
                self.subTest(log=changed),
                self.assertRaises((AssertionError, KeyError)),
            ):
                validate_chain(changed, 3, False, True, False, placement)
        with self.assertRaises(AssertionError):
            validate_chain(
                text, 3, False, True, False, placement_fixture(3, CROSS_LAYOUTS[1])
            )

    def test_capture_uses_sysfs_and_current_allowed_cpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "online").write_text("0-19,20-39\n")
            for cpu in range(40):
                (root / f"cpu{cpu}" / f"node{int(cpu >= 20)}").mkdir(parents=True)
            cpus = CROSS_LAYOUTS[0]
            text = ",".join(map(str, cpus))
            captured = capture_placement(text, 3, True, root, set(range(40)))
            self.assertEqual(captured, placement_fixture(3, cpus))
            with self.assertRaises(AssertionError):
                capture_placement(text, 3, True, root, set(range(20)))
            (root / "online").write_text("0-19\n")
            with self.assertRaises(AssertionError):
                capture_placement(text, 3, True, root, set(range(40)))
            (root / "online").write_text("0-39\n")
            for malformed in ("x", "1,,2", "0-13", "-1", "0,0", "0,1"):
                with (
                    self.subTest(cpus=malformed),
                    self.assertRaises((AssertionError, ValueError)),
                ):
                    capture_placement(malformed, 3, True, root, set(range(40)))
            node = root / "cpu20" / "node1"
            node.rmdir()
            with self.assertRaises(AssertionError):
                capture_placement(text, 3, True, root, set(range(40)))
            node.mkdir()
            (root / "cpu20" / "node0").mkdir()
            with self.assertRaises(AssertionError):
                capture_placement(text, 3, True, root, set(range(40)))


def multi_fixture(reverse=False, quota=False):
    """Log-only oracle fixture; do not model lock execution with this trace."""
    lines = []
    roles = [
        f"role={r} task={100 + r} self={0xA00 + r:x} cpu={r} preempt=0 irq=0"
        for r in range(14)
    ]
    lines.extend("kd_multi start: " + row for row in roles)
    for lock in ("a", "c"):
        lines.append(f"JIT body witness: entry=200 lock={lock} body=1")
    lines.append(
        "kd_multi queued: a0=a a1=c b=b first=100 second=105 "
        "owner0=a03 owner1=a08 b_owner=a0a count=4 valid=1"
    )
    for lane in ((1, 0) if reverse else (0, 1)):
        parent = "a" if lane == 0 else "c"
        lines.append(
            f"kd_remote start: task={100 + 5 * lane} cpu=12 entry=200 "
            f"ip=210 outer=b parent_outer={parent} owner_task=a0c"
        )
        lines.append("JIT body witness: entry=200 lock=b body=1")
        if quota and lane == 0:
            lines.append(
                "[KD_JIT][WARN] reason=CALL_LIMIT_NATIVE entry=0x200 "
                "ip=0x500 sp=0x600 return=0x220 lock=0xb task=100 hostcall=1"
            )
            for lock, cpu in (("b", 12), ("a", 3)):
                lines.append(
                    f"kd_native begin: task=100 outer={lock} entry=200 "
                    f"ip=500 sp=600 held=1 mutex=0 cpu={cpu} "
                    "outer_released=0 remaining=1"
                )
                if lock == "b":
                    lines.append(
                        "kd_child_exit arm: task=100 cpu=12 owner=a0c outer=b "
                        "entry=200 ip=500 sp=600 remaining=1 alive=1 valid=1"
                    )
            for phase in (0, 1):
                lines.append(
                    f"kd_multi quota: phase={phase} task=100 self=a00 cpu=0 "
                    "a0=a03 a1=a08 b=a0c other_before=2 other_after=1 "
                    "other_shared=12003 sequence=12006 calls=34 preempt=1 irq=0 valid=1"
                )
            lines.extend((
                "kd_native complete: task=100 outer=b mutex=0",
                "kd_native ack: task=100 lock=b mutex=0 last_spin=0",
                "kd_native complete: task=100 outer=a mutex=0",
                "kd_native ack: task=100 lock=a mutex=0 last_spin=1",
                "kd_multi done: " + roles[0],
                "kd_child_exit release: task=100 cpu=12 owner=a0c outer=b "
                "entry=200 ip=500 sp=600 detached=1 packet=1 context=1 valid=1",
            ))
    lines.extend("kd_multi done: " + row for row in roles[int(quota):])
    for lane in (0, 1):
        token, value = 0x12340001 + lane * 0x101, 0
        for _ in range(2):
            value = (value + token) ^ (token << 1)
        sequence = 12006 + (1 - lane if reverse else lane)
        lines.append(
            f"kd_multi record: lane={lane} before=2 after=2 value={value:x} "
            f"expected={value:x} shared={sequence}"
        )
    lines.extend((
        "kd_multi stats: started=3fff finished=3fff failures=0 aborted=0",
        f"kd_native stats: started={2 * quota} completed={2 * quota} unlocks={2 * quota}",
        f"kd_multi services: quota={int(quota)} calls={34 * quota} observed={int(quota)}",
    ))
    if quota:
        lines.append(
            "kd_hostcall stats: exits=17 executed=16 resumed=16 rejected=0 failed=0 limit=1"
        )
    placement = {
        "role_cpus": list(range(14)),
        "role_nodes": [0] * 14,
        "allowed_cpus": list(range(40)),
        "online_cpus": list(range(40)),
    }
    publications = "\n".join(
        json.dumps({
            "entry": entry, "status": 0, "code": "1000",
            "tgid": 7, "pid": 0, "observed_ns": 10,
        })
        for entry in ("100", "200", "300")
    )
    statuses = "\n".join(f"{r}\t0" for r in range(14))
    base = ("\n".join(lines), placement, publications, statuses)
    if not quota:
        return base
    assembly = "/* KD_HOSTCALL id=1 symbol=ktime_get */\nloc_500:\nloc_220:\n"
    return base + (True, publications.replace('"observed_ns": 10', '"observed_ns": 20'),
                   {0x200: assembly})


class MultiRootOracleTests(unittest.TestCase):
    def test_both_orders_and_distinct_logical_packets(self):
        for reverse, quota in ((False, False), (True, False), (False, True)):
            with self.subTest(reverse=reverse, quota=quota):
                result = validate_multi_roots(*multi_fixture(reverse, quota))
                self.assertEqual(result["waiters"], [100, 105])
                self.assertEqual(result["jit_bodies"], 4)
                self.assertEqual(result["b_executor"], "a0c")
                self.assertEqual(result["quota_native"], int(quota))
                self.assertEqual(result["waiter_exit"], int(quota))

    def test_reject_missing_duplicate_or_corrupted_evidence(self):
        # Every witness is required. Mutations also distinguish successful
        # native completion, swapped root packets and a different B executor.
        text, placement, publications, statuses = multi_fixture()
        broken_logs = []
        for line in text.splitlines():
            broken_logs.extend((text.replace(line, "", 1), text + "\n" + line))
        for old, new in (
            ("task=105 cpu=12", "task=100 cpu=12"),
            ("parent_outer=c", "parent_outer=a"),
            ("owner_task=a0c", "owner_task=a0b"),
            ("owner0=a03", "owner0=a00"),
            ("owner1=a08", "owner1=a03"),
            ("b_owner=a0a", "b_owner=a0c"),
            ("entry=200", "entry=400"),
            ("cpu=12 entry", "cpu=11 entry"),
            ("preempt=0", "preempt=1"),
            ("irq=0", "irq=1"),
            ("body=1", "body=0"),
            ("shared=12007", "shared=12006"),
            ("before=2", "before=3"),
            ("after=2", "after=1"),
            ("value=", "value=1"),
            ("valid=1", "valid=0"),
            ("failures=0", "failures=1"),
            ("completed=0", "completed=1"),
        ):
            self.assertIn(old, text)
            broken_logs.append(text.replace(old, new, 1))
        for changed in broken_logs:
            with self.subTest(log=changed), self.assertRaises(AssertionError):
                validate_multi_roots(changed, placement, publications, statuses)
        for changed in (
            publications.replace('"status": 0', '"status": 1', 1),
            publications.replace('"entry": "200"', '"entry": "100"'),
            publications.replace('"code": "1000"', '"code": "0"', 1),
        ):
            with self.subTest(publications=changed), self.assertRaises(AssertionError):
                validate_multi_roots(text, placement, changed, statuses)
        for changed in (statuses.replace("0\t0", "0\t1", 1), statuses + "\n0\t0"):
            with self.subTest(statuses=changed), self.assertRaises(AssertionError):
                validate_multi_roots(text, placement, publications, changed)
        invalid = copy.deepcopy(placement)
        invalid["role_cpus"][12] = 11
        with self.assertRaises(AssertionError):
            validate_multi_roots(text, invalid, publications, statuses)

        # This selected schedule pauses at B pop, not its pre-ACK finish. The
        # first TID must detach before the same owner starts the next child;
        # log corruption is not a substitute for the actual PID/RCU observer.
        args = list(multi_fixture(quota=True))
        text = args[0]
        corruptions = []
        for line in text.splitlines():
            corruptions.extend((text.replace(line, "", 1), text + "\n" + line))
        for old, new in (
            ("phase=1", "phase=0"),
            ("other_shared=12003", "other_shared=12006"),
            ("b=a0c", "b=a0b"),
            ("remaining=1", "remaining=2"),
            ("hostcall=1", "hostcall=0"),
            ("ip=0x500", "ip=0x510"),
            ("resumed=16", "resumed=15"),
            ("calls=34", "calls=35"),
            ("preempt=1", "preempt=2"),
            ("last_spin=0", "last_spin=1"),
            ("alive=1", "alive=0"),
            ("detached=1", "detached=0"),
            ("packet=1", "packet=0"),
            ("context=1", "context=0"),
            ("owner=a0c", "owner=a0b"),
        ):
            self.assertIn(old, text)
            corruptions.append(text.replace(old, new, 1))
        completed = "kd_native complete: task=100 outer=b mutex=0"
        corruptions.append(text.replace(completed, "") + "\n" + completed)
        lines = text.splitlines()
        for earlier, later in (
            ("kd_child_exit arm:", "kd_native begin: task=100 outer=a"),
            ("kd_multi done: role=0 ", "kd_child_exit release:"),
            ("kd_child_exit release:", "kd_remote start: task=105 "),
        ):
            swapped = lines.copy()
            left = next(i for i, line in enumerate(lines) if line.startswith(earlier))
            right = next(i for i, line in enumerate(lines) if line.startswith(later))
            swapped[left], swapped[right] = swapped[right], swapped[left]
            corruptions.append("\n".join(swapped))
        for changed in corruptions:
            with self.subTest(quota_log=changed), self.assertRaises(AssertionError):
                validate_multi_roots(changed, *args[1:])
        after = args[5].replace('"code": "1000"', '"code": "2000"', 1)
        with self.assertRaises(AssertionError):
            validate_multi_roots(*args[:5], after, args[6])
        for assembly in (args[6][0x200].replace("ktime_get", "unknown"), "loc_220:"):
            with self.subTest(assembly=assembly), self.assertRaises(AssertionError):
                validate_multi_roots(*args[:6], {0x200: assembly})


if __name__ == "__main__":
    unittest.main()
