"""Guest-only physical-frame oracle and extracted stack-watermark checks."""

import copy
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from spin_frame_protocol import (
    STACK_SIZE,
    deferred_roles,
    follower_cpus,
    linked_chain,
    parse_levels,
    records,
    validate,
    validate_controller,
    validate_placement,
    worker_cpus,
)
from test_spin_shadow import definition


def event(prefix, **fields):
    return prefix + ": " + " ".join(f"{key}={value}" for key, value in fields.items())


def fixture(depth=2, numa=0):
    cpus = worker_cpus(depth)
    placement = {
        "depth": depth,
        "numa": numa,
        "role_cpus": cpus,
        "role_nodes": [int(cpu >= 20) for cpu in cpus],
        "online_cpus": list(range(40)),
        "allowed_cpus": list(range(40)),
    }
    locks = [f"{0x1000 + 4 * i:x}" for i in range(depth + 1)]
    lines = [event("kd_chain lock", index=i, addr=lock) for i, lock in enumerate(locks)]
    if depth == 8:
        lines += [
            (
                "[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE entry=0x3000 target=0x4000 "
                "sp=0x5000 return=0x3010 staged_ip=0x4000 staged_sp=0x5000 mutex=0 error=-7"
            ),
            event(
                "kd_native begin",
                task=107,
                outer=locks[7],
                entry="3000",
                ip="4000",
                sp="5000",
                held=1,
                mutex=0,
                cpu=0,
            ),
            event(
                "kd_frame held refusal",
                ready=1,
                valid_before=1,
                cpu=0,
                task=107,
                entry="3000",
                outer=locks[7],
                lock=locks[8],
                target="4000",
                sp="5000",
                depth=8,
                recorded=8,
                local=8,
                error=-7,
                packet=1,
                frame=1,
                combiner=1,
                physical=1,
                pending=1,
                context=1,
                **{"return": "3010"},
            ),
        ]
    for i in range(depth):
        used = 680 + i * 700
        lines += [
            event(
                "kd_frame trace",
                event=i,
                cpu=0,
                task=100 + i,
                depth=i + 1,
                local=i + 1,
                entry="3000",
                outer=locks[i],
                parent=locks[i - 1] if i else 0,
                used=used,
                left=STACK_SIZE - used,
                valid=1,
                executed=1,
                returned=1,
                ret=6 if depth == 8 and i == 7 else 4,
            ),
            event(
                "kd_chain request",
                lock=i,
                task=100 + i,
                cpu=i + 1,
                before=1,
                called=1,
                after=1,
                valid=1,
            ),
            event(
                "kd_spin lock stats",
                lock=locks[i],
                jit_success=0 if depth == 8 and i == 7 else 1,
                jit_not_ready=0,
                waiters=0,
            ),
            event("kd_chain state", lock=i, operations=12004 if i else 12006, valid=1),
        ]
    left = STACK_SIZE - 680 - (depth - 1) * 700
    lines.append(
        event(
            "kd_frame summary",
            events=depth,
            max_depth=depth,
            sampled_min_left=left,
            failures=0,
            numa=numa,
            stack_size=STACK_SIZE,
        )
    )
    for cpu in range(40):
        untouched = left - 512 if cpu == 0 else STACK_SIZE
        lines.append(
            event(
                "kd_stack watermark",
                cpu=cpu,
                size=STACK_SIZE,
                untouched=untouched,
                written=STACK_SIZE - untouched,
                valid=1,
            )
        )
    lines += [
        event(
            "kd_chain summary",
            depth=depth,
            operations=depth * 12004 + 2,
            states=depth,
            requests=depth * 12002,
            checked=depth * 12002,
            failures=0,
        ),
        event(
            "kd_native stats",
            started=int(depth == 8),
            completed=int(depth == 8),
            unlocks=int(depth == 8),
        ),
    ]
    return "\n".join(lines), placement


def change(log, prefix, key, value):
    lines = log.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(prefix))
    lines[index], count = re.subn(rf"\b{key}=[^ ]+", f"{key}={value}", lines[index])
    assert count == 1
    return "\n".join(lines)


def buffered_fixture(depth):
    log, placement = fixture(depth, 1)
    placement["buffered"] = True
    lines = [event("kd_chain root", task=900, cpu=0)]
    for i in range(depth):
        request = f"{0xC000 + i * 0x100:x}"
        lines.extend(
            [
                event(
                    "kd_defer link",
                    lock=f"{0x1000 + i * 4:x}",
                    node=request,
                    task=100 + i,
                    cpu=i + 1,
                    previous="b000",
                    previous_task=900 if not i else 99 + i,
                    previous_cpu=0,
                ),
                event(
                    "kd_defer link",
                    lock=f"{0x1000 + i * 4:x}",
                    node=f"{0xD000 + i * 0x100:x}",
                    task=200 + i,
                    cpu=i + 10,
                    previous=request,
                    previous_task=100 + i,
                    previous_cpu=i + 1,
                ),
            ]
        )
    lines.append(log)
    order = [(4, i) for i in range(depth)] + [(5, i) for i in reversed(range(depth))]
    for sequence, (kind, level) in enumerate(order):
        fields = dict.fromkeys(
            [
                "request",
                "request_task",
                "request_cpu",
                "node",
                "task",
                "node_cpu",
                "node_socket",
                "head",
                "head_task",
                "head_cpu",
                "tail",
                "next",
                "next_task",
                "next_cpu",
                "first",
                "last",
                "result",
                "outer",
                "linked",
            ],
            0,
        )
        fields.update(
            event=sequence,
            kind=kind,
            lock=f"{0x1000 + level * 4:x}",
            owner=900,
            cpu=0,
            depth=level,
            socket=0,
            parent=f"{0x1000 + (level - 1) * 4:x}" if level else 0,
        )
        lines.append(event("kd_defer buffered", **fields))
    lines.append(
        event(
            "kd_defer buffer summary",
            events=2 * depth,
            capacity=256,
            overflow=0,
            incomplete=0,
        )
    )
    return "\n".join(lines), placement


def combined_fixture(depth, levels, count, cross_remote=False):
    log, placement = buffered_fixture(depth)
    placement.update(defer_levels=levels, defer_count=count)
    used = set(placement["role_cpus"])
    remote = [cpu for cpu in range(20, 40) if cpu not in used][: len(levels) * count]
    assert len(remote) == len(levels) * count
    placement["role_cpus"] += remote
    placement["role_nodes"] += [
        2 if cross_remote and i % count == 2 else 1 for i in range(len(remote))
    ]
    nodes = dict(zip(placement["role_cpus"], placement["role_nodes"]))
    for level in levels:
        log = change(
            log,
            f"kd_chain state: lock={level} ",
            "operations",
            (12004 if level else 12006) + count,
        )
        log = change(
            log,
            f"kd_spin lock stats: lock={0x1000 + level * 4:x} ",
            "jit_not_ready",
            count - 1,
        )
    log = change(
        log, "kd_chain summary:", "operations", depth * 12004 + 2 + len(remote)
    )
    fields = {key: 0 for key in records(log, "kd_defer buffered:")[0]}
    lines = [line for line in log.splitlines() if "kd_defer " not in line]
    links = {}
    for level in range(depth):
        previous, previous_cpu, previous_task = "b000", 0, 99 + level if level else 900
        chain = []
        for index, cpu in enumerate(
            [level + 1, *follower_cpus(placement, level), level + 10]
        ):
            task = 100 + level if not index else 200 + cpu
            node = f"{0xC000 + level * 0x100 + index * 8:x}"
            row = {
                "lock": f"{0x1000 + level * 4:x}",
                "node": node,
                "task": str(task),
                "cpu": str(cpu),
                "previous": previous,
                "previous_cpu": str(previous_cpu),
                "previous_task": str(previous_task),
            }
            lines.append(event("kd_defer link", **row))
            chain.append(row)
            previous, previous_cpu, previous_task = node, cpu, task
        links[level] = chain
    sequence = 0

    def buffered(kind, level, **values):
        nonlocal sequence
        row = {
            **fields,
            "event": sequence,
            "kind": kind,
            "lock": f"{0x1000 + level * 4:x}",
            "owner": 900,
            "cpu": 0,
            "depth": level + 1,
            "socket": 0,
            **values,
        }
        lines.append(event("kd_defer buffered", **row))
        sequence += 1

    def context(kind, level):
        parent = links[level - 1][1:-1] if level else []
        buffered(
            kind,
            level,
            depth=level,
            parent=f"{0x1000 + (level - 1) * 4:x}" if level else 0,
            head=parent[0]["node"] if parent else 0,
            tail=parent[-1]["node"] if parent else 0,
        )

    for level in range(depth):
        context(4, level)
        request, *followers, _ = links[level]
        for follower in followers:
            buffered(
                1,
                level,
                request=request["node"],
                request_task=request["task"],
                request_cpu=request["cpu"],
                node=follower["node"],
                task=follower["task"],
                node_cpu=follower["cpu"],
                node_socket=nodes[int(follower["cpu"])],
                head=followers[0]["node"],
                tail=follower["node"],
            )
    for level in reversed(range(depth)):
        _, *followers, trailer = links[level]
        if followers:
            buffered(
                2,
                level,
                head=followers[0]["node"],
                head_task=followers[0]["task"],
                head_cpu=followers[0]["cpu"],
                tail=followers[-1]["node"],
                next=trailer["node"],
                next_task=trailer["task"],
                next_cpu=trailer["cpu"],
                linked=1,
            )
        context(5, level)
    for level, extra, _ in deferred_roles(placement):
        follower = links[level][extra + 1]
        for kind in (4, 5):
            buffered(
                kind,
                level,
                depth=0,
                cpu=follower["cpu"],
                owner=follower["task"],
                socket=nodes[int(follower["cpu"])],
            )
            if kind == 4 and cross_remote and extra == 0:
                selected, appended = links[level][2:4]
                buffered(
                    1,
                    level,
                    depth=1,
                    cpu=follower["cpu"],
                    owner=follower["task"],
                    socket=1,
                    request=selected["node"],
                    request_task=selected["task"],
                    request_cpu=selected["cpu"],
                    node=appended["node"],
                    task=appended["task"],
                    node_cpu=appended["cpu"],
                    node_socket=2,
                    head=appended["node"],
                    tail=appended["node"],
                )
                buffered(
                    3,
                    level,
                    depth=1,
                    cpu=follower["cpu"],
                    owner=follower["task"],
                    socket=1,
                    request=selected["node"],
                    request_task=selected["task"],
                    request_cpu=selected["cpu"],
                    first=appended["node"],
                    last=appended["node"],
                    next=appended["node"],
                    result=2,
                )
        for acquired in (1, 0):
            lines.append(
                event(
                    "kd_chain follower",
                    lock=level,
                    extra=extra,
                    acquired=acquired,
                    task=follower["task"],
                    cpu=follower["cpu"],
                    origin=f"e{follower['cpu']}",
                    owner=f"e{follower['cpu']}" if acquired else 0,
                    word=1 if acquired else 0,
                    preempt=acquired,
                    irq=0,
                    valid=1,
                )
            )
    lines.extend(
        [
            event(
                "kd_defer buffer summary",
                events=sequence,
                capacity=256,
                overflow=0,
                incomplete=0,
            ),
            event(
                "kd_chain deferred",
                mask=sum(1 << i for i in levels),
                count=count,
                acquired=len(remote),
                returned=len(remote),
                valid=1,
            ),
        ]
    )
    return "\n".join(lines), placement


def capacity_fixture(log, placement):
    placement = {**placement, "probe_frames": True}
    fields = dict.fromkeys(
        (
            "claimed",
            "ready",
            "attempted",
            "rejected",
            "unchanged",
            "valid_before",
            "valid_after",
            "depth",
            "cpu",
            "task",
            "owner",
            "entry",
            "outer",
            "preempt",
            "irq",
        ),
        0,
    )
    fields["snapshot"] = 5264
    if placement["depth"] == 8:
        for key in (
            "claimed",
            "ready",
            "attempted",
            "rejected",
            "unchanged",
            "valid_before",
            "valid_after",
        ):
            fields[key] = 1
        frame = records(log, "kd_frame trace:")[-1]
        fields.update(depth=8, owner=900, preempt=1)
        for key in ("task", "entry", "outer"):
            fields[key] = frame[key]
        if not records(log, "kd_chain root:"):
            log += "\n" + event("kd_chain root", task=900, cpu=0)
    return log + "\n" + event("kd_frame capacity", **fields), placement


class FrameTests(unittest.TestCase):
    def rejects(self, log, placement):
        with self.assertRaises((AssertionError, KeyError, ValueError)):
            validate(log, placement, placement["depth"], placement["numa"], "4000")

    def test_depths_and_profiles(self):
        for depth in range(1, 9):
            for numa in (0, 1):
                log, placement = fixture(depth, numa)
                with self.subTest(depth=depth, numa=numa):
                    result = validate(log, placement, depth, numa, "4000")
                    self.assertEqual(result["depth"], depth)
                    self.assertEqual(result["numa"], numa)
                    self.assertEqual(
                        result["pending_return"], "3010" if depth == 8 else None
                    )
                    self.assertLess(result["written_left"], result["sampled_left"])

    def test_capacity_probe(self):
        for depth in range(1, 9):
            for numa in (0, 1):
                log, p = capacity_fixture(*fixture(depth, numa))
                result = validate(log, p, depth, numa, "4000")
                self.assertEqual(
                    result["capacity"],
                    {
                        "attempted": int(depth == 8),
                        "depth": 8 if depth == 8 else 0,
                        "snapshot": 5264,
                    },
                )
                row = next(
                    line
                    for line in log.splitlines()
                    if line.startswith("kd_frame capacity:")
                )
                self.rejects(log.replace(row, ""), p)
                self.rejects(log + "\n" + row, p)
                disabled = {
                    key: value for key, value in p.items() if key != "probe_frames"
                }
                self.rejects(log, disabled)
                for key, value in records(log, "kd_frame capacity:")[0].items():
                    replacement = "0" if value != "0" else "1"
                    with self.subTest(depth=depth, numa=numa, field=key):
                        self.rejects(
                            change(log, "kd_frame capacity:", key, replacement), p
                        )
                for value in (False, 1, "1"):
                    self.rejects(log, {**p, "probe_frames": value})

    def test_natural_held_refusal_preserves_the_whole_contract(self):
        for numa in (0, 1):
            log, p = fixture(8, numa)
            result = validate(log, p, 8, numa, "4000")
            self.assertEqual(
                result["held"],
                {
                    "depth": 8,
                    "recorded": 8,
                    "local": 8,
                    "packet_unchanged": True,
                },
            )
            row = next(
                line
                for line in log.splitlines()
                if line.startswith("kd_frame held refusal:")
            )
            self.rejects(log.replace(row, ""), p)
            self.rejects(log + "\n" + row, p)
            self.rejects(log.replace(row, row + " unexpected=1"), p)
            short_log, short_p = fixture(2, numa)
            self.rejects(short_log + "\n" + row, short_p)
            for key, value in records(log, "kd_frame held refusal:")[0].items():
                with self.subTest(numa=numa, field=key):
                    self.rejects(
                        change(
                            log,
                            "kd_frame held refusal:",
                            key,
                            "0" if value != "0" else "1",
                        ),
                        p,
                    )

    def test_capacity_with_deferred_lists(self):
        for depth, levels, count in (
            (4, [0, 1, 2, 3], 3),
            (8, list(range(8)), 1),
            (8, [0, 2, 4, 6], 3),
        ):
            log, p = capacity_fixture(*combined_fixture(depth, levels, count))
            result = validate(log, p, depth, 1, "4000")
            self.assertEqual(result["capacity"]["attempted"], int(depth == 8))
            self.assertEqual(result["buffered"]["followers"], len(levels) * count)

    def test_buffered_empty_parent_records(self):
        for depth in range(1, 9):
            log, p = buffered_fixture(depth)
            with self.subTest(depth=depth):
                result = validate(log, p, depth, 1, "4000")
                self.assertEqual(
                    result["buffered"],
                    {"events": 2 * depth, "links": 2 * depth, "live_prefixes": 0},
                )
                # Reporting later is not a license to infer runtime ordering.
                lines = log.splitlines()
                buffered = [
                    row for row in lines if row.startswith("kd_defer buffered:")
                ]
                rest = [
                    row for row in lines if not row.startswith("kd_defer buffered:")
                ]
                validate("\n".join(buffered + rest), p, depth, 1, "4000")

    def test_combined_live_parent_child_prefixes(self):
        cases = 0
        for depth in range(1, 9):
            selections = {
                (0,),
                (depth - 1,),
                tuple(sorted({0, depth - 1})),
                tuple(range(depth)),
            }
            selections.update((i, i + 1) for i in range(depth - 1))
            for selected in sorted(selections):
                levels = list(selected)
                for count in range(1, 4):
                    if len(levels) * count > 20 - depth:
                        continue
                    with self.subTest(depth=depth, levels=levels, count=count):
                        log, placement = combined_fixture(depth, levels, count)
                        result = validate(log, placement, depth, 1, "4000")["buffered"]
                        self.assertEqual(result["followers"], len(levels) * count)
                        self.assertEqual(
                            result["simultaneous"], sum(i + 1 in levels for i in levels)
                        )
                        for level in levels:
                            chain = linked_chain(
                                log, placement, level, f"{0x1000 + level * 4:x}"
                            )
                            self.assertEqual(len(chain), count + 2)
                            for row in chain:
                                reduced = log.replace(event("kd_defer link", **row), "")
                                self.assertIsNone(
                                    linked_chain(reduced, placement, level, row["lock"])
                                )
                        cases += 1
        self.assertGreaterEqual(cases, 80)
        print(f"combined frame oracle: {cases} distinct histories PASS")

    def test_combined_cancelled_native_selection(self):
        log, placement = combined_fixture(2, [0, 1], 3, cross_remote=True)
        self.assertEqual(
            validate(log, placement, 2, 1, "4000")["buffered"]["restores"], 2
        )
        restore = next(
            line
            for line in log.splitlines()
            if line.startswith("kd_defer buffered:") and " kind=3 " in line
        )
        for key, value in (
            ("first", 0),
            ("last", 0),
            ("next", 0),
            ("head", "c000"),
            ("result", 1),
            ("request", 0),
        ):
            self.rejects(change(log, restore, key, value), placement)

    def test_combined_corruption_refused(self):
        log, placement = combined_fixture(2, [0, 1], 2)
        parent_save = next(
            line
            for line in log.splitlines()
            if line.startswith("kd_defer buffered:") and " event=3 " in line
        )
        for prefix, fields in (
            (
                parent_save,
                {"head": 0, "tail": 0, "parent": 0, "owner": 999},
            ),
            (
                "kd_chain follower:",
                {
                    "task": 999,
                    "cpu": 0,
                    "owner": 0,
                    "origin": 0,
                    "preempt": 0,
                    "irq": 1,
                    "valid": 0,
                },
            ),
            (
                "kd_chain deferred:",
                {"mask": 1, "count": 1, "acquired": 3, "returned": 0, "valid": 0},
            ),
            ("kd_defer buffer summary:", {"events": 0, "overflow": 1, "incomplete": 1}),
        ):
            for key, value in fields.items():
                with self.subTest(prefix=prefix, key=key):
                    self.rejects(change(log, prefix, key, value), placement)
        for prefix in (
            "kd_defer buffered:",
            "kd_chain follower:",
            "kd_chain deferred:",
            "kd_defer link:",
        ):
            row = next(line for line in log.splitlines() if line.startswith(prefix))
            self.rejects(log + "\n" + row, placement)
            self.rejects(log.replace(row, ""), placement)
        for key, value in (
            ("defer_levels", [1, 0]),
            ("defer_levels", [0, 0]),
            ("defer_levels", [2]),
            ("defer_count", 0),
            ("defer_count", 4),
            ("buffered", False),
        ):
            broken = {**placement, key: value}
            self.rejects(log, broken)
        for text in ("1,0", "0,0", "2", "-1"):
            with self.assertRaises(AssertionError):
                parse_levels(text, 2)
        p = copy.deepcopy(placement)
        p["role_nodes"][-1] = 0
        self.rejects(log, p)

    def test_buffered_loss_corruption_and_mode_mismatch(self):
        log, p = buffered_fixture(2)
        for prefix, fields in (
            (
                "kd_defer buffer summary:",
                {"events": 3, "capacity": 255, "overflow": 1, "incomplete": 1},
            ),
            (
                "kd_defer buffered:",
                {
                    "event": 1,
                    "kind": 5,
                    "owner": 901,
                    "cpu": 1,
                    "depth": 1,
                    "parent": "1000",
                    "head": "b000",
                    "result": 2,
                    "socket": 1,
                },
            ),
            (
                "kd_defer link:",
                {
                    "previous_task": 999,
                    "previous_cpu": 1,
                    "task": 999,
                    "cpu": 9,
                    "node": "b000",
                },
            ),
        ):
            for key, value in fields.items():
                with self.subTest(prefix=prefix, key=key):
                    self.rejects(change(log, prefix, key, value), p)
        for prefix in (
            "kd_chain root:",
            "kd_defer buffered:",
            "kd_defer buffer summary:",
            "kd_defer link:",
        ):
            row = next(row for row in log.splitlines() if row.startswith(prefix))
            self.rejects(log.replace(row, "", 1), p)
            self.rejects(log + "\n" + row, p)
        self.rejects(log, {k: v for k, v in p.items() if k != "buffered"})
        for value in (False, 1, "1"):
            self.rejects(log, {**p, "buffered": value})
        self.rejects(log, {**p, "numa": 0})
        lines = log.splitlines()
        indexes = [
            i for i, line in enumerate(lines) if line.startswith("kd_defer buffered:")
        ]
        lines[indexes[0]], lines[indexes[1]] = lines[indexes[1]], lines[indexes[0]]
        self.rejects("\n".join(lines), p)

    def test_topology_and_profile(self):
        log, p = fixture(8, 1)
        for key, value in (
            ("depth", True),
            ("numa", True),
            ("numa", 0),
            ("role_cpus", list(reversed(p["role_cpus"]))),
            ("online_cpus", p["role_cpus"]),
            ("allowed_cpus", p["role_cpus"]),
            ("online_cpus", list(range(20))),
            ("role_nodes", []),
        ):
            with self.subTest(key=key, value=value):
                self.rejects(log, {**p, key: value})
        for depth in (0, 9, True):
            with self.assertRaises(AssertionError):
                worker_cpus(depth)

    def test_controller(self):
        for depth in range(1, 9):
            _, p = fixture(depth)
            cpu = validate_placement(p, depth, 0)
            controller = {"cpu": cpu, "affinity": [cpu], "pid": 777}
            before = copy.deepcopy(p)
            validate_controller(p, controller)
            self.assertEqual(p, before)
            for key, value in (
                ("cpu", 0),
                ("affinity", [cpu, 0]),
                ("pid", 0),
                ("pid", True),
            ):
                with self.assertRaises(AssertionError):
                    validate_controller(p, {**controller, key: value})

    def test_frame_corruption(self):
        for depth in (2, 8):
            log, p = fixture(depth)
            for key, value in (
                ("event", 1),
                ("cpu", 1),
                ("task", 999),
                ("depth", 2),
                ("local", 2),
                ("entry", "3001"),
                ("outer", "1004"),
                ("parent", "1004"),
                ("used", 1),
                ("left", 1023),
                ("valid", 0),
                ("executed", 0),
                ("returned", 0),
                ("ret", 6),
            ):
                with self.subTest(depth=depth, key=key):
                    self.rejects(change(log, "kd_frame trace:", key, value), p)
            for key, value in (
                ("events", 1),
                ("max_depth", 1),
                ("failures", 1),
                ("sampled_min_left", STACK_SIZE),
                ("numa", 1),
                ("stack_size", 1),
            ):
                self.rejects(change(log, "kd_frame summary:", key, value), p)

    def test_watermark_corruption(self):
        log, p = fixture(8)
        for key, value in (
            ("cpu", 1),
            ("size", 1),
            ("untouched", 255),
            ("untouched", STACK_SIZE),
            ("written", 0),
            ("valid", 0),
        ):
            with self.subTest(key=key):
                self.rejects(change(log, "kd_stack watermark:", key, value), p)
        for cpu in (0, 39):
            lines = [
                line
                for line in log.splitlines()
                if not line.startswith(f"kd_stack watermark: cpu={cpu} ")
            ]
            self.rejects("\n".join(lines), p)
        row = next(
            line for line in log.splitlines() if line.startswith("kd_stack watermark:")
        )
        self.rejects(log + "\n" + row, p)
        self.rejects(log.replace(row, row + " valid=1"), p)

    def test_request_and_state_corruption(self):
        log, p = fixture(2)
        for prefix, fields in (
            (
                "kd_chain request:",
                {
                    "task": 900,
                    "cpu": 9,
                    "before": 0,
                    "called": 0,
                    "after": 0,
                    "valid": 0,
                },
            ),
            (
                "kd_spin lock stats:",
                {"jit_success": 0, "jit_not_ready": 1, "waiters": 1},
            ),
            ("kd_chain state:", {"operations": 12004, "valid": 0}),
            (
                "kd_chain summary:",
                {
                    "depth": 1,
                    "operations": 0,
                    "states": 1,
                    "requests": 0,
                    "checked": 0,
                    "failures": 1,
                },
            ),
        ):
            for key, value in fields.items():
                with self.subTest(prefix=prefix, key=key):
                    self.rejects(change(log, prefix, key, value), p)
        for prefix in (
            "kd_chain lock:",
            "kd_frame trace:",
            "kd_chain request:",
            "kd_chain state:",
            "kd_spin lock stats:",
            "kd_frame summary:",
        ):
            row = next(line for line in log.splitlines() if line.startswith(prefix))
            self.rejects(log + "\n" + row, p)
            self.rejects(log.replace(row, ""), p)

    def test_pending_call_corruption(self):
        log, p = fixture(8)
        for old, new in (
            ("target=0x4000", "target=0x4001"),
            ("error=-7", "error=-12"),
            ("staged_sp=0x5000", "staged_sp=0x5008"),
            ("staged_ip=0x4000", "staged_ip=0x4001"),
            ("entry=0x3000", "entry=0x3001"),
        ):
            self.rejects(log.replace(old, new), p)
        for key, value in (
            ("task", 100),
            ("held", 2),
            ("ip", "4001"),
            ("sp", "5008"),
            ("mutex", 1),
            ("cpu", 1),
        ):
            self.rejects(change(log, "kd_native begin:", key, value), p)
        for key in ("started", "completed", "unlocks"):
            self.rejects(change(log, "kd_native stats:", key, 0), p)

    def test_old_entry_only_evidence_is_insufficient(self):
        log, p = fixture(2)
        without = "\n".join(
            line for line in log.splitlines() if "kd_stack watermark:" not in line
        )
        self.rejects(without, p)
        self.rejects(re.sub(r" numa=0 stack_size=\d+", "", log), p)

    def test_invalid_driver_flag(self):
        for value in ("2", "-1", "bad"):
            result = subprocess.run(
                ["bash", str(ROOT / "tests/test_14_spin_frame_depth.sh"), "2"],
                env={**os.environ, "KD_CHAIN_PROBE_FRAMES": value},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("KD_CHAIN_PROBE_FRAMES must be 0 or 1", result.stdout)
        for value in ("2", "-1", "bad"):
            result = subprocess.run(
                ["bash", str(ROOT / "tests/test_14_spin_frame_depth.sh"), "2"],
                env={**os.environ, "KD_CHAIN_NUMA": value},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("KD_CHAIN_NUMA must be 0 or 1", result.stdout)
        for buffered, numa in (("1", "0"), ("2", "1"), ("bad", "1")):
            result = subprocess.run(
                ["bash", str(ROOT / "tests/test_14_spin_frame_depth.sh"), "2"],
                env={
                    **os.environ,
                    "KD_CHAIN_NUMA": numa,
                    "KD_CHAIN_TRACE_BUFFERED": buffered,
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("buffering requires NUMA=1", result.stdout)

    def test_production_watermark_primitives(self):
        source = (ROOT / "tests/kernel/spin_frame_trace.c").read_text()
        spin = (ROOT / "kernel_module/kd_spinlock.c").read_text()
        (size,) = re.findall(
            r"^#define SIZE_OF_SHADOW_STACK (\d+)L$", spin, re.MULTILINE
        )
        (byte,) = re.findall(
            r"^#define KD_STACK_WATERMARK_BYTE (0x[0-9a-f]+)$", source, re.MULTILINE
        )
        code = "#include <stdbool.h>\n#include <stdio.h>\n#include <string.h>\n"
        code += f"#define SIZE_OF_SHADOW_STACK {size}L\n#define KD_STACK_WATERMARK_BYTE {byte}\n"
        code += "static bool kd_frame_trace;\n"
        for marker in (
            "static void kd_spin_selftest_stack_init(void *base)",
            "static unsigned long kd_spin_selftest_stack_untouched(const void *base)",
        ):
            code += definition(source, marker) + "\n"
        code += r"""
static unsigned int checks;
#define CHECK(condition) do { checks++; if (!(condition)) return 1; } while (0)
int main(void)
{
    unsigned char storage[SIZE_OF_SHADOW_STACK + 2] = {0};
    unsigned char *base = storage + 1;
    unsigned long offsets[] = {0, 1, 255, 256, 1023, 1024, SIZE_OF_SHADOW_STACK - 1};
    unsigned int i;
    storage[0] = 0x31;
    storage[SIZE_OF_SHADOW_STACK + 1] = 0x32;
    kd_spin_selftest_stack_init(base);
    CHECK(base[0] == 0 && base[SIZE_OF_SHADOW_STACK - 1] == 0);
    kd_frame_trace = true;
    kd_spin_selftest_stack_init(base);
    CHECK(kd_spin_selftest_stack_untouched(base) == SIZE_OF_SHADOW_STACK);
    CHECK(storage[0] == 0x31 && storage[SIZE_OF_SHADOW_STACK + 1] == 0x32);
    for (i = 0; i < sizeof(offsets) / sizeof(offsets[0]); i++) {
        base[offsets[i]] = 0;
        CHECK(kd_spin_selftest_stack_untouched(base) == offsets[i]);
        base[offsets[i]] = KD_STACK_WATERMARK_BYTE;
        CHECK(kd_spin_selftest_stack_untouched(base) == SIZE_OF_SHADOW_STACK);
    }
    base[1024] = 0;
    base[256] = 0;
    CHECK(kd_spin_selftest_stack_untouched(base) == 256);
    kd_frame_trace = false;
    kd_spin_selftest_stack_init(base);
    CHECK(base[256] == 0 && base[1024] == 0);
    CHECK(storage[0] == 0x31 && storage[SIZE_OF_SHADOW_STACK + 1] == 0x32);
    printf("production watermark checks=%u PASS\n", checks);
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="kdlock-frame-watermark-unit-") as tmp:
            path = Path(tmp)
            (path / "watermark.c").write_text(code)
            command = shlex.split(os.environ.get("CC", "cc"))
            subprocess.run(
                command
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(path / "watermark.c"),
                    "-o",
                    str(path / "watermark"),
                ],
                check=True,
                timeout=30,
            )
            subprocess.run([str(path / "watermark")], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
