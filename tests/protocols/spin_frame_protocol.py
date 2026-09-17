"""Physical frame nesting: current task stacks and archived shadow-stack logs."""

import argparse
import itertools
import json
import re
import subprocess
import time
from pathlib import Path

from cpu_placement import capture_topology, validate_topology

STACK_SIZE = 8192  # Archived private-stack evidence.
TASK_STACK_SIZE = 16384  # Captured x86_64 guest kernel.
ENTRY_RESERVE = 1024
WRITE_GUARD = 256


def worker_cpus(depth):
    assert type(depth) is int and 1 <= depth <= 8
    return [0, 19, *range(1, depth + 1), *range(10, 10 + depth), *range(20, 20 + depth)]


def deferred_roles(placement):
    return [
        (level, extra, 30 + 3 * level + extra)
        for level in placement.get("defer_levels", [])
        for extra in range(placement.get("defer_count", 1))
    ]


def follower_cpus(placement, level):
    cpus = placement["role_cpus"][len(worker_cpus(placement["depth"])) :]
    return [
        cpu
        for (index, _, _), cpu in zip(deferred_roles(placement), cpus)
        if index == level
    ]


def parse_levels(text, depth):
    levels = [int(item) for item in text.split(",")] if text else []
    assert levels == sorted(set(levels)), "defer levels must be sorted and unique"
    assert all(0 <= level < depth for level in levels)
    return levels


def validate_placement(placement, depth, numa):
    assert type(numa) is int and numa in (0, 1)
    cpus = worker_cpus(depth)
    keys = {
        "depth",
        "numa",
        "role_cpus",
        "role_nodes",
        "online_cpus",
        "allowed_cpus",
    }
    if "buffered" in placement:
        assert placement["buffered"] is True and numa == 1
        keys.add("buffered")
    if "probe_frames" in placement:
        assert placement["probe_frames"] is True
        keys.add("probe_frames")
    if "defer_levels" in placement:
        assert placement.get("buffered") is True
        levels, count = placement["defer_levels"], placement["defer_count"]
        assert (
            isinstance(levels, list) and levels and all(type(i) is int for i in levels)
        )
        assert levels == sorted(set(levels)) and all(0 <= i < depth for i in levels)
        assert type(count) is int and 1 <= count <= 3
        keys |= {"defer_levels", "defer_count"}
        cpus += placement["role_cpus"][len(cpus) :]
        assert len(cpus) == len(worker_cpus(depth)) + len(levels) * count
    assert set(placement) == keys
    assert type(placement["depth"]) is int and placement["depth"] == depth
    assert type(placement["numa"]) is int and placement["numa"] == numa
    validate_topology(placement, len(cpus))
    assert placement["role_cpus"] == cpus
    if "defer_levels" in placement:
        nodes = dict(zip(cpus, placement["role_nodes"]))
        assert all(
            nodes[cpu] == nodes[0]
            for cpu in [*range(1, depth + 1), *range(10, 10 + depth)]
        )
        remotes = cpus[len(worker_cpus(depth)) :]
        assert all(nodes[cpu] != nodes[0] for cpu in remotes)
    spare = set(placement["online_cpus"]) & set(placement["allowed_cpus"]) - set(cpus)
    assert spare, "one online/allowed non-worker CPU is required"
    return min(spare)


def capture_placement(depth, numa, buffered=False, levels=None, count=1, probe=False):
    cpus = worker_cpus(depth)
    placement = {**capture_topology(cpus), "depth": depth, "numa": numa}
    if buffered:
        placement["buffered"] = True
    if probe:
        placement["probe_frames"] = True
    if levels:
        assert buffered and numa == 1 and type(count) is int and 1 <= count <= 3
        available = sorted(
            set(placement["online_cpus"]) & set(placement["allowed_cpus"]) - set(cpus)
        )
        candidates = capture_topology(available)
        remote = [
            cpu
            for cpu, node in zip(available, candidates["role_nodes"])
            if node != placement["role_nodes"][0]
        ]
        needed = len(levels) * count
        assert len(remote) >= needed and len(available) > needed, (
            "insufficient remote/spare controller CPUs"
        )
        placement.update(capture_topology(cpus + remote[:needed]))
        placement.update(defer_levels=levels, defer_count=count)
    else:
        assert count == 1
    validate_placement(placement, depth, numa)
    return placement


def records(log, prefix):
    rows = []
    for line in log.splitlines():
        if prefix not in line:
            continue
        fields = re.findall(r"(\w+)=(-?[0-9a-f]+)(?=\s|$)", line.split(prefix, 1)[1])
        assert len(dict(fields)) == len(fields), "duplicate evidence key"
        rows.append(dict(fields))
    return rows


def validate_controller(placement, controller):
    cpu = validate_placement(placement, placement["depth"], placement["numa"])
    assert type(controller["cpu"]) is int and controller["cpu"] == cpu
    assert controller["affinity"] == [cpu]
    assert type(controller["pid"]) is int and controller["pid"] > 0


def linked_chain(log, placement, level, lock):
    """Recover published pointer order, independent of inter-CPU printk order."""
    links = [row for row in records(log, "kd_defer link:") if row["lock"] == lock]
    expected = [level + 1, *follower_cpus(placement, level), level + 10]
    assert len(links) <= len(expected)
    assert all(int(row["cpu"]) in expected for row in links)
    result = []
    for cpu in expected:
        found = [row for row in links if row["cpu"] == str(cpu)]
        assert len(found) <= 1
        if not found:
            return None
        result.append(found[0])
    first = result[0]
    assert first["previous_cpu"] == "0"
    for previous, following in itertools.pairwise(result):
        assert following["previous"] == previous["node"]
        assert following["previous_cpu"] == previous["cpu"]
        assert following["previous_task"] == previous["task"]
    nodes = {first["previous"], *(row["node"] for row in result)}
    tasks = {first["previous_task"], *(row["task"] for row in result)}
    assert len(nodes) == len(tasks) == len(result) + 1
    assert all(int(node, 16) for node in nodes) and all(int(task) > 0 for task in tasks)
    return result


def wait_linked_chain(placement, level, timeout=10):
    assert level in placement["defer_levels"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        log = subprocess.check_output(["dmesg"], text=True, timeout=3)
        locks = {
            int(row["index"]): row["addr"] for row in records(log, "kd_chain lock:")
        }
        if level in locks:
            chain = linked_chain(log, placement, level, locks[level])
            if chain:
                return chain
        time.sleep(0.01)
    raise TimeoutError(
        f"level {level}: request/follower/trailer links not all published"
    )


def validate_buffered(log, placement, locks, frames):
    """Empty-list observer bring-up, not a live remote-follower experiment.

    Buffered records use their own reservation sequence, never dmesg ordering
    relative to runtime lines. Here every producer is the same pinned CPU 0 task.
    """
    events = records(log, "kd_defer buffered:")
    summaries = records(log, "kd_defer buffer summary:")
    if not placement.get("buffered"):
        assert not events and not summaries
        return None
    if placement.get("defer_levels"):
        return validate_combined(log, placement, locks, frames)
    n = placement["depth"]
    assert len(events) == 2 * n
    (summary,) = summaries
    assert summary == {
        "events": str(2 * n),
        "capacity": "256",
        "overflow": "0",
        "incomplete": "0",
    }
    (root,) = records(log, "kd_chain root:")
    assert root["cpu"] == "0" and int(root["task"]) > 0
    assert root["task"] not in {frame["task"] for frame in frames}
    expected = [(4, i) for i in range(n)] + [(5, i) for i in reversed(range(n))]
    for sequence, (event, (kind, level)) in enumerate(zip(events, expected)):
        empty_fields = [
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
        ]
        assert set(event) == set(empty_fields) | {
            "event",
            "kind",
            "lock",
            "owner",
            "cpu",
            "depth",
            "socket",
            "parent",
        }
        assert int(event["event"]) == sequence and int(event["kind"]) == kind
        assert event["cpu"] == "0" and event["owner"] == root["task"]
        assert int(event["socket"]) == placement["role_nodes"][0]
        assert int(event["depth"]) == level and event["lock"] == locks[level]
        assert event["parent"] == (locks[level - 1] if level else "0")
        assert all(event[key] == "0" for key in empty_fields)
    for tag in ("append", "splice", "restore"):
        assert not records(log, f"kd_defer {tag}:")
    # Link logs remain live and retain captured predecessor identity even when
    # the CPU-0 head node is reused by a later child combiner.
    links = records(log, "kd_defer link:")
    assert len(links) == 2 * n
    for i, frame in enumerate(frames):
        linked = [row for row in links if row["lock"] == locks[i]]
        assert len(linked) == 2
        (request,) = [row for row in linked if row["cpu"] == str(i + 1)]
        (trailer,) = [row for row in linked if row["cpu"] == str(i + 10)]
        assert request["task"] == frame["task"]
        assert request["previous_cpu"] == "0"
        assert request["previous_task"] == (
            frames[i - 1]["task"] if i else root["task"]
        )
        assert trailer["previous"] == request["node"]
        assert trailer["previous_task"] == request["task"]
        assert trailer["previous_cpu"] == request["cpu"]
        assert trailer["task"] not in {root["task"], request["task"]}
        nodes = {request["previous"], request["node"], trailer["node"]}
        assert len(nodes) == 3 and all(int(node, 16) for node in nodes)
    return {"events": len(events), "links": len(links), "live_prefixes": 0}


def validate_combined(log, placement, locks, frames):
    """Replay each physical owner's list stack using only buffered records.

    Scalar identities may outlive the nodes they name. Cross-CPU dmesg positions
    are not timestamps; live publication chains are checked separately.
    """
    n, levels = placement["depth"], placement["defer_levels"]
    (root,) = records(log, "kd_chain root:")
    assert root["cpu"] == "0" and int(root["task"]) > 0
    assert root["task"] not in {frame["task"] for frame in frames}
    nodes = dict(zip(placement["role_cpus"], placement["role_nodes"]))
    chains = {}
    for level in range(n):
        chain = linked_chain(log, placement, level, locks[level])
        assert chain is not None
        assert chain[0]["task"] == frames[level]["task"]
        assert chain[0]["previous_task"] == (
            frames[level - 1]["task"] if level else root["task"]
        )
        chains[locks[level]] = chain
    links = records(log, "kd_defer link:")
    assert len(links) == 2 * n + len(deferred_roles(placement))
    for tag in ("append", "splice", "restore"):
        assert not records(log, f"kd_defer {tag}:")
    events = records(log, "kd_defer buffered:")
    (summary,) = records(log, "kd_defer buffer summary:")
    assert summary == {
        "events": str(len(events)),
        "capacity": "256",
        "overflow": "0",
        "incomplete": "0",
    }
    assert 0 < len(events) <= 256
    fields = {
        "event",
        "kind",
        "lock",
        "owner",
        "cpu",
        "depth",
        "socket",
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
        "parent",
        "result",
        "outer",
        "linked",
    }
    common = {"event", "kind", "lock", "owner", "cpu", "depth", "socket"}
    used = {
        1: {
            "request",
            "request_task",
            "request_cpu",
            "node",
            "task",
            "node_cpu",
            "node_socket",
            "head",
            "tail",
        },
        2: {
            "head",
            "head_task",
            "head_cpu",
            "tail",
            "next",
            "next_task",
            "next_cpu",
            "outer",
            "linked",
        },
        3: {
            "request",
            "request_task",
            "request_cpu",
            "first",
            "last",
            "head",
            "tail",
            "next",
            "result",
        },
        4: {"head", "tail", "parent"},
        5: {"head", "tail", "parent"},
    }
    stacks, owner_tasks = {}, {0: root["task"]}
    root_saves, root_resumes, primary, splices, restores = [], [], [], [], 0
    live_prefixes, simultaneous = set(), set()
    for sequence, row in enumerate(events):
        assert set(row) == fields
        kind, cpu, depth = (int(row[key]) for key in ("kind", "cpu", "depth"))
        assert kind in used and int(row["event"]) == sequence
        assert (
            row["lock"] in chains and cpu in nodes and int(row["socket"]) == nodes[cpu]
        )
        chain = chains[row["lock"]]
        followers = chain[1:-1]
        if cpu:
            (owner,) = [item for item in followers if item["cpu"] == str(cpu)]
            owner_tasks[cpu] = owner["task"]
        assert row["owner"] == owner_tasks[cpu]
        assert all(row[key] == "0" for key in fields - common - used[kind])
        stack = stacks.setdefault(cpu, [])
        if kind in (4, 5):
            if kind == 5:
                assert stack and stack[-1]["lock"] == row["lock"]
                assert not stack.pop()["list"]
            assert depth == len(stack)
            parent = stack[-1] if stack else None
            prefix = parent["list"] if parent else []
            assert row["parent"] == (parent["lock"] if parent else "0")
            assert row["head"] == (prefix[0]["node"] if prefix else "0")
            assert row["tail"] == (prefix[-1]["node"] if prefix else "0")
            if cpu == 0:
                (root_saves if kind == 4 else root_resumes).append(row["lock"])
                assert depth == next(i for i in range(n) if locks[i] == row["lock"])
                if prefix:
                    live_prefixes.add(row["lock"])
            else:
                assert depth == 0
            if kind == 4:
                stack.append({"lock": row["lock"], "list": []})
            continue
        assert stack and stack[-1]["lock"] == row["lock"] and depth == len(stack)
        staged = stack[-1]["list"]
        by_node = {item["node"]: item for item in chain}
        if kind == 1:
            selected, appended = by_node[row["request"]], by_node[row["node"]]
            assert appended in followers
            assert (
                row["request_task"] == selected["task"]
                and row["request_cpu"] == selected["cpu"]
            )
            assert (
                row["task"] == appended["task"] and row["node_cpu"] == appended["cpu"]
            )
            assert int(row["node_socket"]) == nodes[int(appended["cpu"])] != nodes[cpu]
            assert appended["previous"] == (
                staged[-1]["node"] if staged else selected["node"]
            )
            assert not staged or row["request"] == staged[0]["request"]
            staged.append(row)
            assert row["head"] == staged[0]["node"] and row["tail"] == row["node"]
            if cpu == 0:
                assert selected == chain[0]
                primary.append(row)
                if len(stack) > 1 and stack[-2]["list"]:
                    simultaneous.add((stack[-2]["lock"], row["lock"]))
            else:
                assert selected in followers
        elif kind == 2:
            assert cpu == 0 and staged
            assert [item["node"] for item in staged] == [
                item["node"] for item in followers
            ]
            for key, value in {
                "head": followers[0]["node"],
                "head_task": followers[0]["task"],
                "head_cpu": followers[0]["cpu"],
                "tail": followers[-1]["node"],
                "next": chain[-1]["node"],
                "next_task": chain[-1]["task"],
                "next_cpu": chain[-1]["cpu"],
                "outer": "0",
                "linked": "1",
            }.items():
                assert row[key] == value
            splices.append(row["lock"])
            staged.clear()
        else:
            assert cpu != 0 and staged and row["result"] == "2"
            assert row["request"] == staged[0]["request"]
            assert row["request_task"] == staged[0]["request_task"]
            assert row["request_cpu"] == staged[0]["request_cpu"]
            assert row["first"] == row["next"] == staged[0]["node"]
            assert (
                row["last"] == staged[-1]["node"] and row["head"] == row["tail"] == "0"
            )
            staged.clear()
            restores += 1
    assert not any(stacks.values())
    assert root_saves == [locks[i] for i in range(n)]
    assert root_resumes == list(reversed(root_saves))
    assert splices == [locks[i] for i in reversed(levels)]
    assert len(primary) == len(deferred_roles(placement))
    assert live_prefixes == {locks[i + 1] for i in levels if i + 1 < n}
    expected_pairs = {(locks[i], locks[i + 1]) for i in levels if i + 1 in levels}
    assert simultaneous == expected_pairs
    follower_rows = records(log, "kd_chain follower:")
    assert len(follower_rows) == 2 * len(primary)
    for level, extra, _ in deferred_roles(placement):
        link = chains[locks[level]][extra + 1]
        rows = [
            row
            for row in follower_rows
            if int(row["lock"]) == level and int(row["extra"]) == extra
        ]
        assert len(rows) == 2 and [row["acquired"] for row in rows] == ["1", "0"]
        assert rows[0]["origin"] == rows[1]["origin"] and int(rows[0]["origin"], 16)
        for row in rows:
            assert row["task"] == link["task"] and row["cpu"] == link["cpu"]
            assert (
                row["preempt"] == row["acquired"]
                and row["irq"] == "0"
                and row["valid"] == "1"
            )
            if row["acquired"] == "1":
                assert row["owner"] == row["origin"] and int(
                    row["word"], 16
                ) & 0xFF in (1, 3)
    (deferred,) = records(log, "kd_chain deferred:")
    assert deferred == {
        "mask": str(sum(1 << i for i in levels)),
        "count": str(placement["defer_count"]),
        "acquired": str(len(primary)),
        "returned": str(len(primary)),
        "valid": "1",
    }
    return {
        "events": len(events),
        "links": len(links),
        "live_prefixes": len(live_prefixes),
        "simultaneous": len(simultaneous),
        "followers": len(primary),
        "restores": restores,
    }


def validate(log, placement, depth, numa, lock_ip):
    validate_placement(placement, depth, numa)
    n = depth
    lock_rows = records(log, "kd_chain lock:")
    locks = {int(row["index"]): row["addr"] for row in lock_rows}
    assert len(lock_rows) == len(locks) == n + 1
    assert set(locks) == set(range(n + 1)) and len(set(locks.values())) == n + 1
    assert all(int(address, 16) for address in locks.values())
    (summary,) = records(log, "kd_frame summary:")
    stack_kind = int(summary.get("stack_kind", "0"))
    assert stack_kind in (0, 1)
    stack_size = TASK_STACK_SIZE if stack_kind else STACK_SIZE
    frames = records(log, "kd_frame trace:")
    assert len(frames) == n
    assert len({row["task"] for row in frames}) == n
    assert len({row["entry"] for row in frames}) == 1
    request_rows = records(log, "kd_chain request:")
    requests = {int(row["lock"]): row for row in request_rows}
    assert len(request_rows) == len(requests) == n
    stats_rows = records(log, "kd_spin lock stats:")
    stats = {row["lock"]: row for row in stats_rows}
    assert len(stats_rows) == len(stats)
    last_used = 0
    for i, frame in enumerate(frames):
        assert int(frame["event"]) == i and int(frame["depth"]) == i + 1
        assert frame["cpu"] == "0" and int(frame["local"]) == i + 1
        assert frame["outer"] == locks[i]
        assert frame["parent"] == (locks[i - 1] if i else "0")
        assert frame["valid"] == frame["executed"] == frame["returned"] == "1"
        assert int(frame["ret"]) == (6 if n == 8 and i == 7 else 4)
        assert int(frame["used"]) > last_used and int(frame["left"]) >= ENTRY_RESERVE
        assert int(frame["used"]) + int(frame["left"]) == stack_size
        last_used = int(frame["used"])
        request = requests[i]
        assert request["task"] == frame["task"] and int(request["cpu"]) == i + 1
        assert (
            request["before"]
            == request["called"]
            == request["after"]
            == request["valid"]
            == "1"
        )
        lock_stats = stats[locks[i]]
        assert int(lock_stats["jit_success"]) == (0 if n == 8 and i == 7 else 1)
        remote = follower_cpus(placement, i)
        assert int(lock_stats["jit_not_ready"]) == max(0, len(remote) - 1)
        assert lock_stats["waiters"] == "0"
    (summary,) = records(log, "kd_frame summary:")
    assert summary["failures"] == "0" and int(summary["max_depth"]) == n
    assert int(summary["events"]) == n and int(summary["numa"]) == numa
    assert int(summary["stack_size"]) == stack_size
    min_left = min(int(row["left"]) for row in frames)
    assert int(summary["sampled_min_left"]) == min_left
    watermark_rows = records(log, "kd_stack watermark:")
    if stack_kind:
        # Live task stacks cannot be repainted or read after task exit. This
        # is a sampled RSP bound, explicitly not the former write watermark.
        assert not watermark_rows
        written_left = None
    else:
        watermarks = {int(row["cpu"]): row for row in watermark_rows}
        assert len(watermarks) == len(watermark_rows)
        assert set(placement["online_cpus"]) <= set(watermarks)
        for cpu, row in watermarks.items():
            assert cpu >= 0 and row["valid"] == "1" and int(row["size"]) == STACK_SIZE
            untouched, written = int(row["untouched"]), int(row["written"])
            assert WRITE_GUARD <= untouched <= STACK_SIZE and 0 <= written <= STACK_SIZE
            assert untouched + written == STACK_SIZE
        written_left = int(watermarks[0]["untouched"])
        assert written_left <= min_left, (
            "watermark must include observed frame stack writes"
        )
    state_rows = records(log, "kd_chain state:")
    states = {int(row["lock"]): row for row in state_rows}
    assert len(states) == len(state_rows) == n and set(states) == set(range(n))
    for index, state in states.items():
        assert int(state["operations"]) == (12006 if index == 0 else 12004) + len(
            follower_cpus(placement, index)
        )
        assert state["valid"] == "1"
    (summary,) = records(log, "kd_chain summary:")
    assert int(summary["operations"]) == n * 12004 + 2 + len(deferred_roles(placement))
    assert int(summary["states"]) == int(summary["depth"]) == n
    assert int(summary["requests"]) == int(summary["checked"]) == n * 12002
    assert summary["failures"] == "0"
    (native,) = records(log, "kd_native stats:")
    assert (
        int(native["started"])
        == int(native["completed"])
        == int(native["unlocks"])
        == (1 if n == 8 else 0)
    )
    assert log.count("reason=PENDING_LOCK_NATIVE") == (1 if n == 8 else 0)
    pending_return = None
    entry = frames[0]["entry"]
    if n == 8:
        (begin,) = records(log, "kd_native begin:")
        assert begin["task"] == frames[-1]["task"] and begin["outer"] == locks[7]
        assert begin["held"] == "1" and begin["ip"] == lock_ip
        assert begin["mutex"] == begin["cpu"] == "0"
        pending = re.search(
            r"reason=PENDING_LOCK_NATIVE entry=0x([0-9a-f]+) target=0x([0-9a-f]+) "
            r"sp=0x([0-9a-f]+) return=0x([0-9a-f]+) staged_ip=0x([0-9a-f]+) "
            r"staged_sp=0x([0-9a-f]+) mutex=0 error=-7",
            log,
        )
        assert pending, "expected actual pre-advance capacity failure"
        entry_ip, target, sp, pending_return, staged_ip, staged_sp = pending.groups()
        assert entry_ip == entry and target == staged_ip == begin["ip"]
        assert sp == staged_sp == begin["sp"]
    else:
        assert not records(log, "kd_native begin:")
    held = validate_held_refusal(log, frames, locks, pending_return, lock_ip)
    buffered = validate_buffered(log, placement, locks, frames)
    capacity = validate_capacity(log, placement, frames)
    return {
        "depth": n,
        "numa": numa,
        "entry": entry,
        "stack_size": stack_size,
        "stack_kind": stack_kind,
        "sampled_left": min_left,
        "written_left": written_left,
        "pending_return": pending_return,
        **({"held": held} if held is not None else {}),
        **({"buffered": buffered} if buffered is not None else {}),
        **({"capacity": capacity} if capacity is not None else {}),
    }


def validate_held_refusal(log, frames, locks, return_ip, lock_ip):
    """Check the full inherited ledger, not the later local-shadow branch.

    A returned body and a final count alone cannot prove that the refusal kept
    every GPR, the CALL word, physical owners and the untouched B packet.
    """
    rows = records(log, "kd_frame held refusal:")
    if len(frames) < 8:
        assert not rows, "a shorter physical chain cannot prove held-lock exhaustion"
        return None
    (row,) = rows
    (begin,) = records(log, "kd_native begin:")
    expected = dict.fromkeys(
        (
            "ready",
            "valid_before",
            "packet",
            "frame",
            "combiner",
            "physical",
            "pending",
            "context",
        ),
        "1",
    )
    expected.update(
        cpu="0",
        task=frames[-1]["task"],
        entry=frames[-1]["entry"],
        outer=locks[7],
        lock=locks[8],
        target=lock_ip,
        sp=begin["sp"],
        return_ip=return_ip,
        depth="8",
        recorded="8",
        local="8",
        error="-7",
    )
    expected["return"] = expected.pop("return_ip")
    assert row == expected, "incomplete or changed natural held-lock refusal packet"
    return {"depth": 8, "recorded": 8, "local": 8, "packet_unchanged": True}


def validate_capacity(log, placement, frames):
    rows = records(log, "kd_frame capacity:")
    if not placement.get("probe_frames"):
        assert not rows, "capacity probe must be absent in the default profile"
        return None
    (row,) = rows
    assert set(row) == {
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
        "snapshot",
    }
    assert row["snapshot"] == "5264"
    if placement["depth"] < 8:
        assert all(value == "0" for key, value in row.items() if key != "snapshot")
    else:
        for key in (
            "claimed",
            "ready",
            "attempted",
            "rejected",
            "unchanged",
            "valid_before",
            "valid_after",
        ):
            assert row[key] == "1", f"invalid full-context probe: {key}={row[key]}"
        assert row["depth"] == "8" and row["cpu"] == "0"
        (summary,) = records(log, "kd_frame summary:")
        assert row["irq"] == ("1" if summary.get("stack_kind") == "1" else "0")
        assert int(row["preempt"]) > 0
        for key in ("task", "entry", "outer"):
            assert row[key] == frames[-1][key]
        (root,) = records(log, "kd_chain root:")
        assert root["cpu"] == "0" and int(root["task"]) > 0
        assert row["owner"] == root["task"]
    return {
        "attempted": int(row["attempted"]),
        "depth": int(row["depth"]),
        "snapshot": int(row["snapshot"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("depth", type=int)
    capture.add_argument("numa", type=int, choices=(0, 1))
    capture.add_argument("--buffered", action="store_true")
    capture.add_argument("--probe-frames", action="store_true")
    capture.add_argument("--defer-levels", default="")
    capture.add_argument("--defer-count", type=int, default=1)
    control = commands.add_parser("control")
    control.add_argument("placement", type=Path)
    followers = commands.add_parser("followers")
    followers.add_argument("placement", type=Path)
    gate = commands.add_parser("gate")
    gate.add_argument("placement", type=Path)
    gate.add_argument("level", type=int)
    check = commands.add_parser("validate")
    check.add_argument("evidence", type=Path)
    check.add_argument("daemon", type=Path)
    check.add_argument("lock_ip")
    args = parser.parse_args()
    if args.command == "capture":
        placement = capture_placement(
            args.depth,
            args.numa,
            args.buffered,
            parse_levels(args.defer_levels, args.depth),
            args.defer_count,
            args.probe_frames,
        )
        print(json.dumps(placement, sort_keys=True, indent=2))
        return
    placement_path = (
        args.placement
        if args.command in ("control", "followers", "gate")
        else args.evidence / "placement.json"
    )
    placement = json.loads(placement_path.read_text())
    cpu = validate_placement(placement, placement["depth"], placement["numa"])
    if args.command == "control":
        print(cpu)
        return
    if args.command == "followers":
        cpus = placement["role_cpus"][len(worker_cpus(placement["depth"])) :]
        for (_, _, role), cpu in zip(deferred_roles(placement), cpus):
            print(role, cpu)
        return
    if args.command == "gate":
        print(json.dumps(wait_linked_chain(placement, args.level)))
        return
    controller = json.loads((args.evidence / "controller.json").read_text())
    validate_controller(placement, controller)
    result = validate(
        (args.evidence / "dmesg.log").read_text(),
        placement,
        placement["depth"],
        placement["numa"],
        args.lock_ip,
    )
    for level in placement.get("defer_levels", []):
        log = (args.evidence / "dmesg.log").read_text()
        locks = {
            int(row["index"]): row["addr"] for row in records(log, "kd_chain lock:")
        }
        saved = json.loads((args.evidence / f"linked-{level}.json").read_text())
        assert saved == linked_chain(log, placement, level, locks[level])
    for entry in (result["entry"], result["pending_return"]):
        if entry is not None:
            assert list((args.daemon / ("0x" + entry)).glob("*/asm/jit.bin")), entry
    print("physical frame protocol: " + json.dumps(result, sort_keys=True) + " PASS")
    print(
        f"actual nested frames={result['depth']}; same CPU, distinct waiters; "
        f"sampled remaining stack={result['sampled_left']}; "
        f"untouched write watermark={result['written_left']}; records exact"
    )


if __name__ == "__main__":
    main()
