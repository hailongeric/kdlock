"""Deep-chain evidence validation, plus the actual workload wait predicate."""

import copy
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from itertools import product
from pathlib import Path

from source_text import read_source

from test_spin_gate import without_includes
from test_spin_shadow import definition

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from readmission_protocol import readmission_chain
from remote_depth_protocol import validate, validate_placement


def placement(n, cross=False):
    cpus = list(range(2 + 4 * n))
    if cross:
        pools = [iter(range(19)), iter(range(21, 40))]
        cpus = [20, 19]
        for i in range(n):
            cpus.extend(next(pools[i % 2]) for _ in range(4))
    return {
        "depth": n,
        "role_cpus": cpus,
        "role_nodes": [int(c >= 20) for c in cpus],
        "online_cpus": list(range(40)),
        "allowed_cpus": list(range(40)),
        "require_cross_numa": cross,
    }


def readmit_placement(layer, count, cross=True):
    """Pinned closed queue; middle local acquisition changes the next hop."""
    groups, previous = [], 1
    for i in range(4):
        if i == layer:
            groups.append(previous)
            if count == 1:
                previous ^= 1
        else:
            previous ^= 1
            groups.append(previous)
    nodes = [1, 1]
    for node in groups:
        nodes.extend((1 - node, node, node, 1 - node))
    nodes.extend((groups[layer - 1], 1 - groups[layer - 1]))
    pools = [iter(range(20)), iter(range(20, 40))]
    p = placement(4, cross)
    p.update(
        role_cpus=[next(pools[node]) for node in nodes], role_nodes=nodes, readmit=count
    )
    if layer != 3:
        p["readmit_layer"] = layer
    return p


def fixture(
    n,
    stage,
    owner=False,
    renamed=False,
    reverse=False,
    cross=False,
    refusal=0,
    readmit=0,
    readmit_layer=3,
    late_observer=False,
    waiter_exit=False,
):
    p = placement(n, cross)
    if readmit:
        assert n == 4 and stage == 1 and not refusal
        p = readmit_placement(readmit_layer, readmit, cross)
    cpus = p["role_cpus"]
    selected = readmit_layer if readmit else n - 1
    head = 3 + 4 * selected
    locks = [f"{0x1000 + i * 8:x}" for i in range(n + 1)]
    executors = [cpus[3 + 4 * i] for i in range(n)]
    owners = [f"{0x9000 + i:x}" for i in range(n)]
    rejected_cpu, rejected_owner = executors[selected], owners[selected]
    local = bool(refusal) or readmit == 2
    if readmit:
        executors[selected], owners[selected] = cpus[19], "9004"
    if local:
        executors[selected], owners[selected] = (
            executors[selected - 1],
            owners[selected - 1],
        )
    frames = [i for i in range(n) if not (local and i == selected)]
    lines = []

    def event(tag, **fields):
        lines.append(tag + ": " + " ".join(f"{k}={v}" for k, v in fields.items()))

    def begin():
        for i in reversed(range(n)):
            released = i in order[:translated]
            event(
                "kd_native begin",
                task=10,
                outer=locks[i],
                entry="2000",
                ip="3000" if stage == 5 else "4000",
                sp="5000",
                mutex=0,
                cpu=executors[i],
                outer_released=int(released),
                remaining=int(not released),
            )
        if waiter_exit:
            event(
                "kd_relay_exit arm",
                **exit_identity,
                remaining=0,
                alive=1,
                valid=1,
            )
        event("kd_deep native probe", task=10, cpu=cpus[0], record=2, valid=1)
        if renamed:
            event(
                "kd_resume rename",
                task=10,
                cpu=cpus[0],
                old="klock_test",
                new="kd_renamed",
                preempt_before=1,
                preempt_after=1,
                irq_before=0,
                irq_after=0,
                valid=1,
            )

    def release(i, jit):
        if i in frames:
            event(
                "kd_spin outer release",
                task=10,
                outer=locks[i],
                remaining=int(
                    local and i == selected - 1 and (selected == n - 1 or not reverse)
                ),
                remote=int(not (local and selected == n - 1 and i == selected - 1)),
                cpu=executors[i],
                owner_task=owners[i],
            )
        if jit:
            first = selected - 1 if local and i == selected else i
            for j in frames:
                if j < first or j == frames[-1]:
                    continue
                event(
                    "kd_remote unlock",
                    task=10,
                    outer=locks[j],
                    lock=locks[i],
                    cpu=executors[j],
                    result=0,
                )
        else:
            event("kd_native ack", task=10, lock=locks[i], mutex=0, last_spin=0)

    exit_identity = {
        "task": 10,
        "cpu": executors[0],
        "owner": owners[0],
        "outer": locks[0],
        "entry": "2000",
        "ip": "4000",
        "sp": "5000",
    }
    for i, lock in enumerate(locks):
        event("kd_deep lock", index=i, addr=lock)
    event(
        "kd_deep request",
        task=9,
        cpu=0,
        record=1,
        before=0,
        called=0,
        after=0,
        valid=1,
        armed=0,
    )
    for i in range(1, n):
        if readmit and i == selected:
            previous, previous_task, previous_cpu = "6000", 40, cpus[head]
            for node, task, cpu in (
                ("6001", 50, cpus[18]),
                ("6002", 60, cpus[19]),
                ("6003", 10, cpus[head - 4]),
                ("6004", 70, cpus[head + 2]),
            ):
                event(
                    "kd_defer link",
                    lock=locks[selected],
                    node=node,
                    task=task,
                    cpu=cpu,
                    previous=previous,
                    previous_task=previous_task,
                    previous_cpu=previous_cpu,
                )
                previous, previous_task, previous_cpu = node, task, cpu
            event(
                "kd_defer append",
                lock=locks[selected],
                owner=40,
                cpu=cpus[head],
                socket=p["role_nodes"][head],
                request="6001",
                request_task=50,
                request_cpu=cpus[18],
                node="6002",
                task=60,
                node_cpu=cpus[19],
                node_socket=p["role_nodes"][19],
                head="6002",
                tail="6002",
            )
            event(
                "kd_remote start",
                task=10,
                outer=locks[selected],
                parent_outer=locks[selected - 1],
                cpu=cpus[head],
                owner_task=rejected_owner,
                entry="2000",
                ip=f"{0x2100 + selected * 8:x}",
            )
            event(
                "kd_defer splice",
                lock=locks[selected],
                owner=40,
                cpu=cpus[head],
                outer=0,
                head="6002",
                head_task=60,
                head_cpu=cpus[19],
                tail="6002",
                next="6003",
                next_task=10,
                next_cpu=cpus[head - 4],
                linked=1,
            )
        event(
            "kd_remote start",
            task=10,
            outer=locks[i],
            parent_outer=locks[i - 2 if local and i == selected + 1 else i - 1],
            cpu=cpus[19]
            if readmit and i == selected
            else rejected_cpu
            if refusal and i == n - 1
            else executors[i],
            owner_task="9004"
            if readmit and i == selected
            else rejected_owner
            if refusal and i == n - 1
            else owners[i],
            entry="2000",
            ip=f"{0x2100 + i * 8:x}",
        )
    order = list(reversed(range(n - 1))) if reverse else list(range(n - 1))
    translated = 0 if stage == 2 else 1 if stage == 4 else n - 1
    for i in order[:translated]:
        release(i, True)
    if late_observer:
        assert readmit and selected < 3 and not owner
        event(
            "kd_defer link",
            lock=locks[selected],
            node="6005",
            task=20,
            cpu=cpus[1],
            previous="6004",
            previous_task=70,
            previous_cpu=cpus[head + 2],
        )
    if stage != 1:
        if stage == 5:
            lines.append(
                "[KD_JIT] reason=PENDING_LOCK_NATIVE entry=0x2000 target=0x3000 "
                "sp=0x5000 return=0x6000 staged_ip=0x3000 staged_sp=0x5000 mutex=0 error=-7"
            )
        begin()
    for i in order[translated:]:
        release(i, False)
    for i, lock in enumerate(locks):
        observed_owner = owners[i] if i == n - 1 else "0" if owner else "a000"
        event(
            "kd_deep observe lock",
            index=i,
            addr=lock,
            word=1,
            owner=observed_owner,
            valid=1,
        )
    event(
        "kd_deep observe",
        task=20,
        cpu=cpus[1],
        owner="a000",
        waiter="b000",
        waiter_pid=10,
        origin_cpu=cpus[0],
        depth=n,
        prefix=1,
        suffix=0,
        preempt=n,
        irq=0,
        valid=1,
        comm="kd_native" if owner else "klock_test",
    )
    if stage != 1:
        for i in range(n):
            if waiter_exit and i == 0:
                continue
            event("kd_native complete", task=10, outer=locks[i], mutex=0)
        event("kd_native ack", task=10, lock=locks[n - 1], mutex=0, last_spin=1)
        if renamed:
            event(
                "kd_resume rename",
                task=10,
                cpu=cpus[0],
                old="kd_renamed",
                new="klock_test",
                preempt_before=0,
                preempt_after=0,
                irq_before=0,
                irq_after=0,
                valid=1,
            )
    native = int(stage != 1)
    event(
        "kd_deep request",
        task=10,
        cpu=cpus[0],
        record=2,
        before=native,
        called=native,
        after=native,
        valid=1,
        armed=1,
    )
    if waiter_exit:
        event(
            "kd_relay_exit release",
            **exit_identity,
            detached=1,
            packet=1,
            context=1,
            valid=1,
        )
        event("kd_native complete", task=10, outer=locks[0], mutex=0)
    for i in range(n):
        event(
            "kd_deep state",
            index=i,
            operations=(12009 if i == n - 1 else 12008)
            + (2 if readmit and i == selected else 0),
            valid=1,
        )
        event(
            "kd_spin lock stats",
            lock=locks[i],
            jit_success=3 - readmit
            if readmit and i == selected
            else int(stage == 1 and (not local or i != selected)),
            jit_disabled=int(refusal == 2 and i == n - 1),
        )
    for i in range(n + 1):
        event("kd_deep drain", index=i, inside=0, word=0, owner=0, queued=0, valid=1)
    event(
        "kd_deep summary",
        depth=n,
        stage=stage,
        reverse=int(reverse),
        requests=2,
        checked=2,
        prefix=1,
        suffix=1,
        observed=1,
        failures=0,
        abort=0,
    )
    event(
        "kd_native stats",
        started=n * native,
        completed=n * native,
        unlocks=(n - translated) * native,
    )
    if refusal:
        event(
            "kd_refusal summary",
            kind=refusal,
            claimed=1,
            task=10,
            entry="2000",
            ip=f"{0x2100 + (n - 1) * 8:x}",
            sp="5000",
            lock=locks[-2],
            outer=locks[-3],
            reject_cpu=rejected_cpu,
            reject_owner=rejected_owner,
            acquired_cpu=executors[-2],
            acquired_owner=owners[-2],
            injected=1 + refusal,
            cancelled=1,
            acquired=1,
            returned=2,
            finished=1,
            end=4,
            initial=1,
            cancel_valid=1,
            acquire_valid=1,
            end_valid=1,
            valid=1,
        )
    if readmit:
        event("kd_deep readmit", ready=1, valid=1)
        for i in range(2):
            declined = i < readmit
            event(
                "kd_readmit attempt",
                index=i,
                cpu=cpus[head] if i == 0 else cpus[19],
                owner=rejected_owner if i == 0 else "9004",
                head="6002" if i == 0 else "0",
                tail="6002" if i == 0 else "0",
                initial=1,
                cancelled=int(declined),
                ended=1,
                executed=int(not declined),
                ret=2 if declined else 4,
            )
        if local and selected < 3:
            event(
                "kd_readmit follow",
                count=1,
                outer=locks[selected + 1],
                ip=f"{0x2100 + (selected + 1) * 8:x}",
                sp="5010",
                cpu=executors[selected + 1],
                owner=owners[selected + 1],
                depth=selected + 1,
                valid=1,
            )
        event(
            "kd_readmit summary",
            refusals=readmit,
            attempts=2,
            task=10,
            entry="2000",
            ip=f"{0x2100 + selected * 8:x}",
            sp="5000",
            lock=locks[selected],
            outer=locks[selected - 1],
            node="6003",
            cancelled=readmit,
            returned=1,
            ret=2 if local else 3,
            cpu=executors[selected - 1],
            owner=owners[selected - 1],
            finished=1,
            end=4,
            return_valid=1,
            end_valid=1,
            unexpected=0,
            valid=1,
        )
    return "\n".join(lines), p


class DepthOracleTests(unittest.TestCase):
    def test_root_relay_outlives_the_actual_waiter_tid(self):
        # Extend the existing late remote case, preserving its six RPCs and
        # last-lock ACK. Invalid identities/packets/order must not pass just
        # because the native frame counters balance.
        options = {
            "native_owner": True,
            "renamed": True,
            "reverse": True,
            "waiter_exit": True,
        }
        text, p = fixture(
            4, 3, owner=True, renamed=True, reverse=True, cross=True, waiter_exit=True
        )
        result = validate(text, p, 3, **options)
        self.assertEqual(
            (result["native_frames"], result["acks"], result["rpc"]), (4, 1, 6)
        )
        self.assertEqual(result["waiter_exit"]["detached"], "1")
        for line in text.splitlines():
            if not line.startswith("kd_relay_exit "):
                continue
            malformed = [text.replace(line, ""), text.replace(line, line + "\n" + line)]
            for match in re.finditer(r"(\w+)=([\w-]+)", line):
                value = "1" if match[2] == "0" else "0"
                changed = line[: match.start(2)] + value + line[match.end(2) :]
                malformed.append(text.replace(line, changed))
            for damaged in malformed:
                with (
                    self.subTest(line=line, damaged=damaged),
                    self.assertRaises(AssertionError),
                ):
                    validate(damaged, p, 3, **options)
        for tag, before in (
            ("kd_relay_exit arm:", "kd_deep native probe:"),
            ("kd_relay_exit release:", "kd_native ack:"),
            ("kd_native complete: task=10 outer=1000", "kd_relay_exit release:"),
        ):
            lines = text.splitlines()
            line = next(item for item in lines if item.startswith(tag))
            lines.remove(line)
            index = next(i for i, item in enumerate(lines) if item.startswith(before))
            # Arming after the native probe is too late; the other mutations
            # complete/release before the event they are required to follow.
            lines.insert(index + int(tag.endswith("arm:")), line)
            with self.subTest(order=tag), self.assertRaises(AssertionError):
                validate("\n".join(lines), p, 3, **options)
        with self.assertRaises(AssertionError):
            validate(text, p, 3, **{**options, "waiter_exit": False})
        with self.assertRaises(AssertionError):
            validate(text, p, 2, **options)

    def test_middle_late_observer_link(self):
        for layer, count, reverse in product((1, 2), (1, 2), (False, True)):
            text, p = fixture(
                4,
                1,
                cross=True,
                readmit=count,
                readmit_layer=layer,
                reverse=reverse,
                late_observer=True,
            )
            validate(text, p, 1, reverse=reverse)
            line = next(
                line
                for line in text.splitlines()
                if line.startswith("kd_defer link:") and "task=20 " in line
            )
            for match in re.finditer(r"(\w+)=([\w-]+)", line):
                damaged = line[: match.start(2)] + "0" + line[match.end(2) :]
                with (
                    self.subTest(layer=layer, count=count, field=match[1]),
                    self.assertRaises(AssertionError),
                ):
                    validate(text.replace(line, damaged), p, 1, reverse=reverse)
            with self.assertRaises(AssertionError):
                validate(text + "\n" + line, p, 1, reverse=reverse)
            moved = text.replace(line + "\n", "")
            with self.assertRaises(AssertionError):
                validate(line + "\n" + moved, p, 1, reverse=reverse)
            with self.assertRaises(AssertionError):
                validate(moved + "\n" + line, p, 1, reverse=reverse)

    def test_middle_readmission_histories(self):
        for layer, count, owner, reverse in product(
            (1, 2), (1, 2), (False, True), (False, True)
        ):
            with self.subTest(layer=layer, count=count, owner=owner, reverse=reverse):
                text, p = fixture(
                    4,
                    1,
                    owner=owner,
                    reverse=reverse,
                    cross=True,
                    readmit=count,
                    readmit_layer=layer,
                )
                result = validate(text, p, 1, native_owner=owner, reverse=reverse)
                self.assertEqual(result["rpc"], 6 if count == 1 else 6 - layer)
                self.assertEqual(len(result["cpus"]), 5 if count == 1 else 4)
                self.assertEqual(result["native_frames"], 0)
                self.assertEqual(text.count("kd_readmit follow:"), int(count == 2))
                if count != 2:
                    continue
                selected = f"{0x1000 + layer * 8:x}"
                parent = f"{0x1000 + (layer - 1) * 8:x}"
                lines = text.splitlines()
                local_rpc = next(
                    line
                    for line in lines
                    if line.startswith("kd_remote unlock:")
                    and f"lock={selected} " in line
                )
                parent_release = next(
                    line
                    for line in lines
                    if line.startswith(
                        f"kd_spin outer release: task=10 outer={parent} "
                    )
                )
                next_start = next(
                    line
                    for line in lines
                    if line.startswith(
                        f"kd_remote start: task=10 outer={0x1000 + (layer + 1) * 8:x} "
                    )
                )
                corruptions = [
                    text.replace(local_rpc, ""),
                    text.replace(local_rpc, local_rpc + "\n" + local_rpc),
                    text.replace(
                        local_rpc,
                        local_rpc.replace(f"outer={parent}", f"outer={selected}"),
                    ),
                    text.replace(
                        next_start,
                        next_start.replace(
                            f"parent_outer={parent}", f"parent_outer={selected}"
                        ),
                    ),
                    text
                    + "\n"
                    + parent_release.replace(f"outer={parent}", f"outer={selected}"),
                    text.replace(
                        parent_release,
                        re.sub(
                            r"remaining=\d", f"remaining={int(reverse)}", parent_release
                        ),
                    ),
                    text.replace(
                        parent_release, parent_release.replace("remote=1", "remote=0")
                    ),
                ]
                for damaged in corruptions:
                    self.assertNotEqual(damaged, text)
                    with self.assertRaises(AssertionError):
                        validate(damaged, p, 1, native_owner=owner, reverse=reverse)

    def test_middle_readmission_placement(self):
        for layer in (1, 2):
            for count in (1, 2):
                with self.subTest(layer=layer, count=count):
                    p = readmit_placement(layer, count)
                    self.assertIs(validate_placement(p, 4), p)

    def test_readmission_histories(self):
        for count in (1, 2):
            for owner in (False, True):
                for reverse in (False, True):
                    text, p = fixture(
                        4, 1, owner=owner, reverse=reverse, cross=True, readmit=count
                    )
                    result = validate(text, p, 1, native_owner=owner, reverse=reverse)
                    self.assertEqual(result["rpc"], 6 if count == 1 else 3)
                    self.assertEqual(
                        result["readmit"]["ret"], "3" if count == 1 else "2"
                    )
                    links = [
                        dict(re.findall(r"(\w+)=([\w-]+)", line))
                        for line in text.splitlines()
                        if line.startswith("kd_defer link:")
                    ]
                    for length in range(4):
                        self.assertIsNone(readmission_chain(links[:length], p, "1018"))
                    self.assertEqual(
                        readmission_chain(list(reversed(links)), p, "1018")["request"][
                            "task"
                        ],
                        "10",
                    )

    def test_readmission_corruptions(self):
        for layer, count in product((1, 2, 3), (1, 2)):
            text, p = fixture(4, 1, cross=True, readmit=count, readmit_layer=layer)
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if not line.startswith(
                    ("kd_defer ", "kd_readmit ", "kd_deep readmit:")
                ):
                    continue
                with (
                    self.subTest(layer=layer, count=count, removed=line),
                    self.assertRaises((AssertionError, KeyError)),
                ):
                    validate("\n".join(lines[:i] + lines[i + 1 :]), p, 1)
                with (
                    self.subTest(layer=layer, count=count, duplicate=line),
                    self.assertRaises((AssertionError, KeyError)),
                ):
                    validate(text + "\n" + line, p, 1)
                for match in re.finditer(r"(\w+)=([\w-]+)", line):
                    damaged = (
                        line[: match.start(2)]
                        + ("0" if match[2] != "0" else "1")
                        + line[match.end(2) :]
                    )
                    with (
                        self.subTest(
                            layer=layer,
                            count=count,
                            tag=line.split(":")[0],
                            field=match[1],
                        ),
                        self.assertRaises((AssertionError, KeyError)),
                    ):
                        validate(text.replace(line, damaged), p, 1)
            head = 3 + 4 * layer
            for role in (head - 4, head - 3, head, head + 1, 18, 19):
                damaged = copy.deepcopy(p)
                damaged["role_nodes"][role] ^= 1
                with self.assertRaises(AssertionError):
                    validate_placement(damaged, 4)
            line = next(
                line
                for line in lines
                if line.startswith(f"kd_spin lock stats: lock={0x1000 + layer * 8:x} ")
            )
            for changed in (0, 3, 1 if count == 1 else 2):
                with self.assertRaises(AssertionError):
                    validate(
                        text.replace(
                            line,
                            re.sub(r"jit_success=\d+", f"jit_success={changed}", line),
                        ),
                        p,
                        1,
                    )

    def test_extracted_refusal_observer(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            (dest / "refusal_observer.h").write_text(
                without_includes(
                    (root / "tests/kernel/spin/spin_readmission_trace.c").read_text()
                )
                + "\n"
                + without_includes(
                    (root / "tests/kernel/spin/spin_refusal_trace.c").read_text()
                )
            )
            command = shlex.split(os.environ.get("CC", "cc"))
            subprocess.run(
                command
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(dest),
                    str(root / "tests/unit/spin/spin_refusal_trace_fixture.c"),
                    "-o",
                    str(dest / "observer"),
                ],
                check=True,
                timeout=30,
            )
            subprocess.run([str(dest / "observer")], check=True, timeout=10)

    def test_virtual_refusal_histories(self):
        for kind in (1, 2):
            for owner in (False, True):
                for reverse in (False, True):
                    for cross in (False, True):
                        text, p = fixture(
                            4,
                            1,
                            owner=owner,
                            reverse=reverse,
                            cross=cross,
                            refusal=kind,
                        )
                        result = validate(
                            text,
                            p,
                            1,
                            native_owner=owner,
                            reverse=reverse,
                            refusal=kind,
                        )
                        self.assertEqual(len(result["cpus"]), 4)
                        self.assertEqual(result["rpc"], 3)
                        self.assertEqual(result["native_frames"], 0)
                        with self.assertRaises(AssertionError):
                            validate(text, p, 1, native_owner=owner, reverse=reverse)

    def test_virtual_refusal_corruptions(self):
        for kind in (1, 2):
            text, p = fixture(4, 1, refusal=kind)
            line = next(
                x for x in text.splitlines() if x.startswith("kd_refusal summary:")
            )
            corruptions = ["", line + "\n" + line]
            for before, after in (
                ("returned=2", "returned=4"),
                ("returned=2", "returned=-5"),
                ("cancelled=1", "cancelled=0"),
                ("acquired=1", "acquired=2"),
                ("finished=1", "finished=0"),
                ("end=4", "end=3"),
                ("initial=1", "initial=0"),
                ("cancel_valid=1", "cancel_valid=0"),
                ("acquire_valid=1", "acquire_valid=0"),
                ("end_valid=1", "end_valid=0"),
                ("acquired_cpu=11", "acquired_cpu=15"),
                ("acquired_owner=9002", "acquired_owner=9003"),
                ("lock=1018", "lock=1010"),
                ("outer=1010", "outer=1008"),
                ("sp=5000", "sp=0"),
            ):
                self.assertIn(before, line)
                corruptions.append(line.replace(before, after))
            for damaged in corruptions:
                with (
                    self.subTest(kind=kind, damaged=damaged),
                    self.assertRaises(AssertionError),
                ):
                    validate(text.replace(line, damaged), p, 1, refusal=kind)
            for before, after in (
                ("remaining=1", "remaining=0"),
                ("remote=0", "remote=1"),
                ("operations=12009", "operations=12010"),
                ("suffix=1", "suffix=2"),
                ("prefix=1", "prefix=2"),
                ("started=0", "started=1"),
                ("lock=1018 jit_success=0", "lock=1018 jit_success=1"),
            ):
                self.assertIn(before, text)
                with self.assertRaises(AssertionError):
                    validate(text.replace(before, after), p, 1, refusal=kind)
            for changed in (
                text.replace("jit_disabled=0", "jit_disabled=1", 1),
                text.replace("jit_disabled=0", "jit_disabled=2", 1),
                text.replace(
                    f"lock=1018 jit_success=0 jit_disabled={int(kind == 2)}",
                    f"lock=1018 jit_success=0 jit_disabled={int(kind != 2)}",
                ),
            ):
                self.assertNotEqual(text, changed)
                with self.assertRaises(AssertionError):
                    validate(changed, p, 1, refusal=kind)

    def test_all_bounded_histories(self):
        count = 0
        for n in range(4, 9):
            for stage in (2, 3, 4, 5) if n == 8 else (1, 2, 3, 4):
                for owner in (False, True):
                    for reverse in (False, True):
                        for renamed in (False,) if stage == 1 else (False, True):
                            for cross in (False, True):
                                with self.subTest(
                                    n=n,
                                    stage=stage,
                                    owner=owner,
                                    reverse=reverse,
                                    renamed=renamed,
                                    cross=cross,
                                ):
                                    text, p = fixture(
                                        n, stage, owner, renamed, reverse, cross
                                    )
                                    result = validate(
                                        text, p, stage, owner, renamed, reverse, "3000"
                                    )
                                    self.assertEqual(
                                        result["native_frames"], 0 if stage == 1 else n
                                    )
                                    self.assertEqual(
                                        result["acks"],
                                        {1: 0, 2: n, 3: 1, 4: n - 1, 5: 1}[stage],
                                    )
                                    expected_rpc = (
                                        0
                                        if stage == 2
                                        else (1 if reverse else n - 1)
                                        if stage == 4
                                        else n * (n - 1) // 2
                                    )
                                    self.assertEqual(result["rpc"], expected_rpc)
                                    count += 1
        self.assertEqual(count, 288)

    def test_observer_can_precede_last_rpc_reply(self):
        for n in range(4, 9):
            for stage in (5,) if n == 8 else (1, 3):
                for reverse in (False, True):
                    with self.subTest(n=n, stage=stage, reverse=reverse):
                        text, p = fixture(n, stage, reverse=reverse)
                        lines = text.splitlines()
                        observations = [
                            line for line in lines if line.startswith("kd_deep observe")
                        ]
                        lines = [
                            line
                            for line in lines
                            if not line.startswith("kd_deep observe")
                        ]
                        last = max(
                            i
                            for i, line in enumerate(lines)
                            if line.startswith("kd_remote unlock:")
                        )
                        lines[last:last] = observations
                        validate(
                            "\n".join(lines), p, stage, reverse=reverse, lock_ip="3000"
                        )

    def test_rpc_must_follow_release_and_precede_continuation(self):
        for stage, boundary in ((3, "release"), (3, "native"), (1, "request")):
            with self.subTest(stage=stage, boundary=boundary):
                text, p = fixture(4, stage)
                lines = text.splitlines()
                indices = [
                    i
                    for i, line in enumerate(lines)
                    if line.startswith("kd_remote unlock:")
                ]
                reply = lines.pop(indices[0] if boundary == "release" else indices[-1])
                if boundary == "release":
                    at = next(
                        i
                        for i, line in enumerate(lines)
                        if line.startswith("kd_spin outer release:")
                    )
                elif boundary == "native":
                    at = (
                        next(
                            i
                            for i, line in enumerate(lines)
                            if line.startswith("kd_native begin:")
                        )
                        + 1
                    )
                else:
                    at = (
                        next(
                            i
                            for i, line in enumerate(lines)
                            if line.startswith("kd_deep request:") and "armed=1" in line
                        )
                        + 1
                    )
                lines.insert(at, reply)
                with self.assertRaises(AssertionError):
                    validate("\n".join(lines), p, stage)

    def test_required_witnesses(self):
        text, p = fixture(4, 4, renamed=True, cross=True)
        for tag in (
            "kd_deep lock:",
            "kd_deep observe:",
            "kd_deep observe lock:",
            "kd_remote start:",
            "kd_spin outer release:",
            "kd_remote unlock:",
            "kd_native begin:",
            "kd_native complete:",
            "kd_native ack:",
            "kd_deep native probe:",
            "kd_resume rename:",
            "kd_deep request:",
            "kd_deep state:",
            "kd_deep drain:",
            "kd_deep summary:",
        ):
            line = next(line for line in text.splitlines() if line.startswith(tag))
            for changed in (text.replace(line, "", 1), text + "\n" + line):
                with (
                    self.subTest(tag=tag),
                    self.assertRaises((AssertionError, KeyError)),
                ):
                    validate(changed, p, 4, renamed=True)

    def test_corrupt_identity_scope_state_and_last_ack(self):
        text, p = fixture(4, 4, renamed=True, cross=True)
        for old, new in (
            ("origin_cpu=20", "origin_cpu=0"),
            ("parent_outer=1000", "parent_outer=1008"),
            ("owner_task=9001", "owner_task=9000"),
            ("entry=2000", "entry=2001"),
            ("last_spin=1", "last_spin=0"),
            ("remaining=0", "remaining=1"),
            ("operations=12008", "operations=12007"),
            ("prefix=1", "prefix=0"),
            ("queued=0", "queued=1"),
            ("checked=2", "checked=1"),
            ("preempt_after=0", "preempt_after=1"),
            ("result=0", "result=-1"),
        ):
            with self.subTest(old=old), self.assertRaises((AssertionError, KeyError)):
                validate(text.replace(old, new, 1), p, 4, renamed=True)

    def test_capacity_requires_real_pending_packet(self):
        text, p = fixture(8, 5, cross=True)
        validate(text, p, 5, lock_ip="3000")
        for old, new in (
            ("error=-7", "error=-12"),
            ("staged_sp=0x5000", "staged_sp=0x5008"),
            ("target=0x3000", "target=0x4000"),
            ("reason=PENDING_LOCK_NATIVE", "reason=CALL_MISS"),
        ):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate(text.replace(old, new), p, 5, lock_ip="3000")
        with self.assertRaises(AssertionError):
            validate(text, p, 1)

    def test_invalid_layout(self):
        p = placement(8, True)
        for key, value in (
            ("depth", 8.0),
            ("role_cpus", [0] * 34),
            ("role_nodes", [0] * 34),
            ("online_cpus", [0]),
            ("allowed_cpus", [0]),
            ("require_cross_numa", 1),
        ):
            bad = copy.deepcopy(p)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_placement(bad, 8)

    def test_workload_wait_negative_count_and_publication(self):
        root = Path(__file__).resolve().parents[3]
        source = read_source(root / "workload_modules/lock_scenarios/fragments/remote_depth_workload.c")
        code = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
static bool deep_abort, deep_holder[4], deep_published[4];
static int deep_direct[4], deep_failures, count;
static unsigned int remote_chain_readmit_layer;
static unsigned long jiffies;
static struct { int rlock; } deep_locks[4];
#define HZ 1
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define smp_load_acquire(p) (*(p))
#define atomic_read(p) (*(p))
#define atomic_inc(p) (++*(p))
#define time_after_eq(a,b) ((a)>=(b))
#define pr_err(...) ((void)0)
#define raw_smp_processor_id() 0
static int kd_spin_debug_waiter_count(int *p) { (void)p; return count; }
static void cpu_relax(void) { ++jiffies; }
"""
        code += definition(
            source, "static bool kd_deep_wait(unsigned int id, unsigned int queued)"
        )
        code += definition(
            source, "static bool kd_deep_readmit_wait(unsigned int queued)"
        )
        code += r"""
int main(void) {
    unsigned int checks = 0;
    for (int holder=0; holder<2; holder++)
    for (int published=0; published<2; published++)
    for (int direct=0; direct<3; direct++)
    for (int c=-28; c<=3; c++)
    for (int queued=0; queued<4; queued++) {
        count=c; deep_holder[0]=holder; deep_published[0]=published;
        deep_direct[0]=direct; deep_abort=false; deep_failures=0; jiffies=0;
        bool expected=holder && (!queued || (c>=queued && direct==2 && (queued<2 || published)));
        assert(kd_deep_wait(0, queued)==expected);
        assert(deep_failures==!expected && deep_abort==!expected);
        checks++;
    }
    printf("deep workload wait: %u conditions PASS\n", checks);
    checks=0;
    for (remote_chain_readmit_layer=1; remote_chain_readmit_layer<=3; remote_chain_readmit_layer++)
    for (int holder=0; holder<2; holder++)
    for (int published=0; published<2; published++)
    for (int direct=0; direct<5; direct++)
    for (int c=-28; c<=5; c++)
    for (unsigned int queued=1; queued<=3; queued++) {
        unsigned int id=remote_chain_readmit_layer;
        count=c; deep_holder[id]=holder; deep_published[id]=published;
        deep_direct[id]=direct; deep_abort=false; deep_failures=0; jiffies=0;
        bool expected=holder && c >= (int)queued && direct >= (int)queued+1;
        assert(kd_deep_readmit_wait(queued)==expected);
        assert(deep_failures==!expected && deep_abort==!expected);
        checks++;
    }
    remote_chain_readmit_layer=3; deep_abort=true; deep_failures=0;
    assert(!kd_deep_readmit_wait(1) && !deep_failures);
    printf("readmission pre-publication wait: %u conditions and prior abort PASS\n", checks);
}
"""
        with tempfile.TemporaryDirectory(prefix="kd-deep-wait-") as directory:
            path = Path(directory)
            (path / "wait.c").write_text(code)
            subprocess.run(
                shlex.split(os.environ.get("CC", "cc"))
                + [
                    "-std=gnu11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(path / "wait.c"),
                    "-o",
                    str(path / "wait"),
                ],
                check=True,
                timeout=30,
            )
            subprocess.run([str(path / "wait")], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
