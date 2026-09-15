"""Deferred-list evidence and actual queue selection/trace code in guest only."""

import copy
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from source_text import read_source
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remote_depth_protocol import (
    deferred_roles,
    select_control_cpu,
    validate,
    validate_placement,
    wait_deferred_link,
)
from test_remote_depth_protocol import fixture
from test_spin_gate import without_includes
from test_spin_shadow import definition


def event(tag, **fields):
    return tag + ": " + " ".join(f"{key}={value}" for key, value in fields.items())


def deferred_fixture(
    n, stage, layer, owner=False, renamed=False, reverse=False, count=1
):
    text, p = fixture(n, stage, owner, renamed, reverse, True)
    cpus = p["role_cpus"]
    follower_role = 5 + 4 * layer
    local_cpu = cpus[follower_role]
    remote = [
        cpu for cpu in range(40) if cpu not in cpus and (cpu >= 20) != (local_cpu >= 20)
    ]
    if not 1 <= count <= min(8, len(remote)):
        raise ValueError("deferred count exceeds this topology's free remote CPUs")
    cpus[follower_role] = remote[0]
    cpus.extend(remote[1:count])
    cpus.append(local_cpu)
    p["role_nodes"] = [int(cpu >= 20) for cpu in cpus]
    p["defer_layer"] = layer
    p["defer_count"] = count
    lock = f"{0x1000 + layer * 8:x}"
    executor = cpus[3 + 4 * layer]
    request_cpu = cpus[0] if layer == 0 else cpus[3 + 4 * (layer - 1)]
    r_cpu, s_cpu = cpus[follower_role], cpus[-1]
    own_pid = 30 + layer
    participants = [
        (f"{0xC100 + i * 0x100:x}", 40 + i, cpu)
        for i, cpu in enumerate([cpus[follower_role], *cpus[2 + 4 * n :]])
    ]
    prefix = [
        event(
            "kd_defer link",
            lock=lock,
            node="c000",
            task=10,
            cpu=request_cpu,
            previous="b100",
            previous_task=own_pid,
            previous_cpu=executor,
        ),
    ]
    previous = ("c000", 10, request_cpu)
    for node, task, cpu in participants:
        prefix.append(
            event(
                "kd_defer link",
                lock=lock,
                node=node,
                task=task,
                cpu=cpu,
                previous=previous[0],
                previous_task=previous[1],
                previous_cpu=previous[2],
            )
        )
        previous = node, task, cpu
    prefix.extend(
        event(
            "kd_defer append",
            lock=lock,
            owner=own_pid,
            cpu=executor,
            socket=int(executor >= 20),
            request="c000",
            request_task=10,
            request_cpu=request_cpu,
            node=node,
            task=task,
            node_cpu=cpu,
            node_socket=int(cpu >= 20),
            head="c100",
            tail=node,
        )
        for node, task, cpu in participants[:-1]
    )
    splice = event(
        "kd_defer splice",
        lock=lock,
        owner=own_pid,
        cpu=executor,
        outer=int(layer < n - 1),
        head="c100",
        head_task=40,
        head_cpu=r_cpu,
        tail=participants[-2][0],
        next=participants[-1][0],
        next_task=participants[-1][1],
        next_cpu=s_cpu,
        linked=1,
    )
    followers = [
        event(
            "kd_deep follower",
            index=layer,
            extra=extra,
            acquired=acquired,
            task=task,
            cpu=cpu,
            owner="d000" if acquired else "0",
            word=int(acquired),
            preempt=int(acquired),
            irq=0,
            valid=1,
        )
        for extra, (_, task, cpu) in enumerate(participants)
        for acquired in (1, 0)
    ]
    lines = text.splitlines()
    at = next(
        i
        for i, line in enumerate(lines)
        if line.startswith("kd_remote start:")
        and (layer == 0 or f" outer={lock} " in line)
    )
    lines[at:at] = prefix
    if layer < n - 1:
        at = next(
            i
            for i, line in enumerate(lines)
            if line.startswith("kd_spin outer release:") and f"outer={lock} " in line
        )
        lines[at] += f" owner={own_pid} next_task=40 next_cpu={r_cpu}"
        lines[at:at] = [splice]
        lines[at + 2 : at + 2] = followers
    else:
        at = next(
            i
            for i, line in enumerate(lines)
            if line.startswith("kd_deep request:") and "armed=1" in line
        )
        lines[at:at] = [splice, *followers]
    at = next(
        i
        for i, line in enumerate(lines)
        if line.startswith(f"kd_deep state: index={layer} ")
    )
    operations = 12009 if layer == n - 1 else 12008
    lines[at] = lines[at].replace(
        f"operations={operations}", f"operations={operations + count}"
    )
    lines.append(
        event(
            "kd_deep deferred",
            layer=layer,
            ready=1,
            followers=count + 1,
            acquired=count + 1,
            returned=count + 1,
            valid=1,
        )
    )
    return "\n".join(lines), p


def cancelled_selection(text, placement):
    """A target observer follows S; the penultimate R rejects the last R."""
    count = placement["defer_count"]
    assert count >= 2 and placement["defer_layer"] == 0
    cpus = placement["role_cpus"]
    roles = deferred_roles(placement)
    owner_cpu, request_cpu = cpus[roles[-2]], cpus[roles[-1]]
    owner, request_task, task = 40 + count - 2, 40 + count - 1, 40 + count
    request = f"{0xC000 + count * 0x100:x}"
    node = f"{0xC100 + count * 0x100:x}"
    events = [
        event(
            "kd_defer link",
            lock="1000",
            node="cf00",
            task=20,
            cpu=cpus[1],
            previous=node,
            previous_task=task,
            previous_cpu=cpus[-1],
        ),
        event(
            "kd_defer append",
            lock="1000",
            owner=owner,
            cpu=owner_cpu,
            socket=int(owner_cpu >= 20),
            request=request,
            request_task=request_task,
            request_cpu=request_cpu,
            node=node,
            task=task,
            node_cpu=cpus[-1],
            node_socket=int(cpus[-1] >= 20),
            head=node,
            tail=node,
        ),
        event(
            "kd_defer restore",
            lock="1000",
            owner=owner,
            cpu=owner_cpu,
            request=request,
            request_task=request_task,
            request_cpu=request_cpu,
            first=node,
            last=node,
            head="0",
            tail="0",
            next=node,
            result=2,
        ),
    ]
    lines = text.splitlines()
    at = next(
        i
        for i, line in enumerate(lines)
        if line.startswith("kd_deep follower:") and f"extra={count - 2} " in line
    )
    lines[at:at] = events
    return "\n".join(lines)


class DeferredTests(unittest.TestCase):
    def test_controller_cpu_does_not_overlap_workers(self):
        for depth, counts in ((4, range(1, 9)), (8, range(1, 4))):
            for count in counts:
                for layer in range(depth):
                    _, p = deferred_fixture(depth, 2, layer, count=count)
                    before = copy.deepcopy(p)
                    spare = sorted(set(range(40)) - set(p["role_cpus"]))
                    self.assertEqual(select_control_cpu(p), spare[0])
                    self.assertEqual(p, before)
                    narrowed = {**p, "allowed_cpus": p["role_cpus"] + [spare[-1]]}
                    self.assertEqual(select_control_cpu(narrowed), spare[-1])
                    for key in ("allowed_cpus", "online_cpus"):
                        with (
                            self.subTest(
                                depth=depth, count=count, layer=layer, key=key
                            ),
                            self.assertRaises(AssertionError),
                        ):
                            select_control_cpu({**p, key: p["role_cpus"]})

    def test_multiple_followers(self):
        histories = 0
        for n, counts in ((4, range(2, 9)), (8, (2, 3))):
            for count in counts:
                for stage in (2, 3, 4, 5) if n == 8 else (1, 2, 3, 4):
                    for layer in range(n):
                        for owner in (False, True):
                            for reverse in (False, True):
                                text, p = deferred_fixture(
                                    n, stage, layer, owner, stage != 1, reverse, count
                                )
                                with self.subTest(
                                    n=n, count=count, stage=stage, layer=layer
                                ):
                                    result = validate(
                                        text,
                                        p,
                                        stage,
                                        owner,
                                        stage != 1,
                                        reverse,
                                        "3000",
                                    )
                                    self.assertEqual(
                                        result["deferred"],
                                        {
                                            "followers": count,
                                            "appends": count,
                                            "restores": 0,
                                        },
                                    )
                                    histories += 1
        self.assertEqual(histories, 704)

    def test_cancelled_secondary_selection(self):
        for count in range(2, 9):
            for stage in range(1, 5):
                for reverse in (False, True):
                    text, p = deferred_fixture(
                        4, stage, 0, reverse=reverse, count=count
                    )
                    text = cancelled_selection(text, p)
                    with self.subTest(count=count, stage=stage, reverse=reverse):
                        self.assertEqual(
                            validate(text, p, stage, reverse=reverse)["deferred"],
                            {"followers": count, "appends": count + 1, "restores": 1},
                        )
                        lines = text.splitlines()
                        at = next(
                            i for i, line in enumerate(lines) if "node=cf00 " in line
                        )
                        link = lines.pop(at)
                        # S->observer is published before the scan, but its producer
                        # may log only after the consumer's restore observation.
                        lines.insert(at + 2, link)
                        validate("\n".join(lines), p, stage, reverse=reverse)

    def test_reject_corrupt_secondary_selection(self):
        text, p = deferred_fixture(4, 2, 0, count=8)
        text = cancelled_selection(text, p)
        lines = text.splitlines()
        secondary = [
            line for line in lines if "owner=46 " in line and "kd_defer " in line
        ]
        observer = next(line for line in lines if "node=cf00 " in line)
        for line in [*secondary, observer]:
            for damaged in (text.replace(line, "", 1), text + "\n" + line):
                with (
                    self.subTest(line=line),
                    self.assertRaises((AssertionError, KeyError)),
                ):
                    validate(damaged, p, 2)
        restore = next(
            line for line in secondary if line.startswith("kd_defer restore:")
        )
        for old, new in (
            ("owner=46", "owner=45"),
            ("request=c800", "request=c700"),
            ("request_task=47", "request_task=46"),
            (f"request_cpu={p['role_cpus'][-2]}", "request_cpu=999"),
            ("first=c900", "first=c800"),
            ("last=c900", "last=c800"),
            ("head=0", "head=c900"),
            ("tail=0", "tail=c900"),
            ("next=c900", "next=c800"),
            ("result=2", "result=3"),
        ):
            self.assertIn(old, restore)
            with self.subTest(old=old), self.assertRaises((AssertionError, KeyError)):
                validate(text.replace(restore, restore.replace(old, new)), p, 2)
        append = secondary[0]
        ai, ri = lines.index(append), lines.index(restore)
        lines[ai], lines[ri] = lines[ri], lines[ai]
        with self.assertRaises((AssertionError, KeyError)):
            validate("\n".join(lines), p, 2)

    def test_multi_gate_and_follower_order(self):
        text, p = deferred_fixture(4, 1, 0, count=8)
        lines = text.splitlines()
        links = [line for line in lines if line.startswith("kd_defer link:")]
        rest = "\n".join(
            line for line in lines if not line.startswith("kd_defer link:")
        )
        snapshots = [
            rest + "\n" + "\n".join(reversed(links[-n:])) for n in range(1, 11)
        ]
        with (
            patch(
                "remote_depth_protocol.subprocess.check_output", side_effect=snapshots
            ) as read,
            patch("remote_depth_protocol.time.sleep"),
        ):
            self.assertEqual(len(wait_deferred_link(p)["followers"]), 8)
            self.assertEqual(read.call_count, 10)
        returned = [
            line
            for line in lines
            if line.startswith("kd_deep follower:") and "acquired=0 " in line
        ]
        late_returns = [line for line in lines if line not in returned] + returned
        validate("\n".join(late_returns), p, 1)
        first = next(i for i, line in enumerate(lines) if "extra=0 acquired=1 " in line)
        second = next(
            i for i, line in enumerate(lines) if "extra=1 acquired=1 " in line
        )
        lines[first], lines[second] = lines[second], lines[first]
        with self.assertRaises(AssertionError):
            validate("\n".join(lines), p, 1)

    def test_deferred_count_contract(self):
        _, p = deferred_fixture(4, 1, 0, count=8)
        for count in (0, 9, True, None, "8"):
            with self.subTest(count=count), self.assertRaises(AssertionError):
                validate_placement({**p, "defer_count": count}, 4)
        with self.assertRaises(AssertionError):
            validate_placement(
                {key: value for key, value in p.items() if key != "defer_layer"}, 4
            )
        with self.assertRaises(AssertionError):
            validate_placement({**p, "defer_count": 7}, 4)
        for role in deferred_roles(p):
            bad = copy.deepcopy(p)
            bad["role_nodes"][role] = bad["role_nodes"][-1]
            with self.subTest(role=role), self.assertRaises(AssertionError):
                validate_placement(bad, 4)
        with self.assertRaises(ValueError):
            deferred_fixture(8, 2, 0, count=4)

    def test_all_layers_and_boundaries(self):
        count = 0
        for n in range(4, 9):
            for stage in (2, 3, 4, 5) if n == 8 else (1, 2, 3, 4):
                for layer in range(n):
                    for owner in (False, True):
                        for reverse in (False, True):
                            for renamed in (False,) if stage == 1 else (False, True):
                                with self.subTest(
                                    n=n,
                                    stage=stage,
                                    layer=layer,
                                    owner=owner,
                                    reverse=reverse,
                                    renamed=renamed,
                                ):
                                    text, p = deferred_fixture(
                                        n, stage, layer, owner, renamed, reverse
                                    )
                                    validate(
                                        text, p, stage, owner, renamed, reverse, "3000"
                                    )
                                    count += 1
        self.assertEqual(count, 872)

    def test_missing_duplicate_and_corrupt_evidence(self):
        text, p = deferred_fixture(4, 3, 1)
        for tag in (
            "kd_defer link:",
            "kd_defer append:",
            "kd_defer splice:",
            "kd_deep follower:",
            "kd_deep deferred:",
        ):
            line = next(line for line in text.splitlines() if line.startswith(tag))
            for bad in (text.replace(line, "", 1), text + "\n" + line):
                with (
                    self.subTest(tag=tag),
                    self.assertRaises((AssertionError, KeyError)),
                ):
                    validate(bad, p, 3)
        for old, new in (
            ("head=c100", "head=c200"),
            ("tail=c100", "tail=c200"),
            ("previous_task=10", "previous_task=40"),
            ("linked=1", "linked=0"),
            ("returned=2", "returned=1"),
            ("outer=1 head", "outer=0 head"),
            ("request_cpu=1", "request_cpu=2"),
            ("next_task=40", "next_task=41"),
            ("operations=12009", "operations=12008"),
        ):
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises((AssertionError, KeyError)):
                validate(text.replace(old, new, 1), p, 3)

    def test_deferred_topology_requires_remote_follower_local_successor(self):
        _, p = deferred_fixture(4, 1, 0)
        for index in (3, 4, 5, len(p["role_nodes"]) - 1):
            bad = copy.deepcopy(p)
            bad["role_nodes"][index] ^= 1
            with self.subTest(index=index), self.assertRaises(AssertionError):
                validate_placement(bad, 4)
        for layer in (None, True, -1, 4):
            with self.subTest(layer=layer), self.assertRaises(AssertionError):
                validate_placement({**p, "defer_layer": layer}, 4)

    def test_real_link_wait_and_wrong_predecessor(self):
        text, p = deferred_fixture(4, 1, 0)
        before = "\n".join(
            line for line in text.splitlines() if "kd_defer link:" not in line
        )
        with (
            patch(
                "remote_depth_protocol.subprocess.check_output",
                side_effect=[before, text],
            ),
            patch("remote_depth_protocol.time.sleep"),
        ):
            self.assertEqual(
                wait_deferred_link(p)["successor"]["cpu"], str(p["role_cpus"][-1])
            )
        bad = text.replace(f"previous_cpu={p['role_cpus'][5]}", "previous_cpu=999")
        with (
            patch("remote_depth_protocol.subprocess.check_output", return_value=bad),
            self.assertRaises(AssertionError),
        ):
            wait_deferred_link(p)
        with self.assertRaises(TimeoutError):
            wait_deferred_link(p, timeout=0)

    def test_gate_waits_for_complete_chain_in_any_log_order(self):
        text, p = deferred_fixture(4, 1, 0)
        lines = text.splitlines()
        links = [line for line in lines if line.startswith("kd_defer link:")]
        rest = "\n".join(
            line for line in lines if not line.startswith("kd_defer link:")
        )
        snapshots = [rest + "\n" + "\n".join(links[-n:]) for n in (1, 2, 3)]
        with (
            patch(
                "remote_depth_protocol.subprocess.check_output", side_effect=snapshots
            ) as read,
            patch("remote_depth_protocol.time.sleep"),
        ):
            wait_deferred_link(p)
            self.assertEqual(read.call_count, 3)

    def test_link_log_order_is_not_pointer_order(self):
        text, p = deferred_fixture(4, 1, 0)
        lines = text.splitlines()
        links = [line for line in lines if line.startswith("kd_defer link:")]
        # Each producer logs after its own write, not after other producers log.
        at = next(
            i for i, line in enumerate(lines) if line.startswith("kd_defer link:")
        )
        changed = [line for line in lines if not line.startswith("kd_defer link:")]
        changed[at:at] = list(reversed(links))
        validate("\n".join(changed), p, 1)

    def test_production_queue_selection_and_trace_lifetimes(self):
        root = Path(__file__).resolve().parents[2]
        source = read_source(root / "kernel_module/kd_spinlock.c")
        code = without_includes(
            (root / "tests/kernel/spin_deferred_trace.c").read_text()
        )
        code += definition(
            source, "static inline bool check_irq_node(struct kd_spin_node *node)"
        )
        code += definition(
            source,
            "__always_inline static void add_to_local_queue(struct kd_spin_node *node)",
        )
        code += "static struct kd_spin_node *\n" + definition(
            source, "get_next_node(struct kd_spin_node *my_node)"
        )
        with tempfile.TemporaryDirectory(prefix="kd-deferred-unit-") as directory:
            path = Path(directory)
            (path / "deferred_trace_production.h").write_text(code)
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-pthread",
                    "-I",
                    str(path),
                    str(root / "tests/unit/deferred_trace_fixture.c"),
                    "-o",
                    str(path / "trace"),
                ],
                check=True,
                timeout=30,
            )
            subprocess.run([str(path / "trace")], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
