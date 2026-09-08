"""Evidence contract for real four-to-eight-executor mode-8 requests."""

import argparse
import json
import re
import subprocess
import time
from itertools import pairwise
from pathlib import Path

from cpu_placement import capture_topology, validate_topology
from readmission_protocol import readmission_chain, validate_readmission


def deferred_roles(placement):
    base = 2 + 4 * placement["depth"]
    return [5 + 4 * placement["defer_layer"]] + list(
        range(base, base + placement.get("defer_count", 1) - 1)
    )


def validate_placement(placement, depth):
    assert type(depth) is int and 4 <= depth <= 8
    expected = {
        "depth",
        "role_cpus",
        "role_nodes",
        "online_cpus",
        "allowed_cpus",
        "require_cross_numa",
    }
    deferred = placement.get("defer_layer")
    if "defer_layer" in placement:
        expected.add("defer_layer")
        assert type(deferred) is int and 0 <= deferred < depth
    count = placement.get("defer_count", 1)
    readmit = placement.get("readmit", 0)
    readmit_layer = placement.get("readmit_layer", 3)
    if "readmit_layer" in placement:
        expected.add("readmit_layer")
        assert readmit and type(readmit_layer) is int and 1 <= readmit_layer <= 3
    if "readmit" in placement:
        expected.add("readmit")
        assert type(readmit) is int and readmit in (1, 2)
        assert depth == 4 and deferred is None
    assert type(count) is int and 1 <= count <= 8
    if "defer_count" in placement:
        expected.add("defer_count")
        assert deferred is not None
    assert set(placement) == expected
    assert type(placement["depth"]) is int and placement["depth"] == depth
    validate_topology(
        placement,
        2 + 4 * depth + (2 if readmit else count if deferred is not None else 0),
    )
    assert type(placement["require_cross_numa"]) is bool
    if placement["require_cross_numa"]:
        groups = [(0,)] + [(3 + 4 * i, 4 + 4 * i) for i in range(depth)]
        if readmit:
            if readmit == 1:
                groups[readmit_layer + 1] = (19,)
            else:
                del groups[readmit_layer + 1]
        for left, right in pairwise(groups):
            assert not {placement["role_nodes"][i] for i in left} & {
                placement["role_nodes"][i] for i in right
            }, "every possible logical handoff must cross nodes"
    if readmit:
        nodes = placement["role_nodes"]
        head = 3 + 4 * readmit_layer
        assert len({nodes[i] for i in (head - 4, head - 3, head, head + 1, 18)}) == 1
        assert nodes[19] != nodes[18], "the real committed prefix must be remote"
    if deferred is not None:
        nodes = placement["role_nodes"]
        assert nodes[3 + 4 * deferred] == nodes[4 + 4 * deferred] == nodes[-1], (
            "both potential executors and the extra successor must be local"
        )
        assert all(nodes[role] != nodes[-1] for role in deferred_roles(placement)), (
            "every deferred follower must be remote"
        )
    return placement


def capture_placement(
    cpu_text,
    depth,
    cross_numa=False,
    defer_layer=None,
    defer_count=1,
    readmit=0,
    readmit_layer=3,
):
    assert type(defer_count) is int and 1 <= defer_count <= 8
    assert defer_layer is not None or defer_count == 1
    assert type(readmit_layer) is int and 1 <= readmit_layer <= 3
    assert readmit or readmit_layer == 3
    cpus = (
        [int(value) for value in cpu_text.split(",")]
        if cpu_text
        else list(
            range(
                2
                + 4 * depth
                + (2 if readmit else defer_count if defer_layer is not None else 0)
            )
        )
    )
    extra = (
        {}
        if defer_layer is None
        else {"defer_layer": defer_layer, "defer_count": defer_count}
    )
    if readmit:
        extra["readmit"] = readmit
        if readmit_layer != 3:
            extra["readmit_layer"] = readmit_layer
    return validate_placement(
        {
            **capture_topology(cpus),
            "depth": depth,
            "require_cross_numa": cross_numa,
            **extra,
        },
        depth,
    )


def select_control_cpu(placement):
    """Keep the userspace gate driver off CPUs occupied by pinned spinners."""
    validate_placement(placement, placement["depth"])
    spare = set(placement["online_cpus"]) & set(placement["allowed_cpus"]) - set(
        placement["role_cpus"]
    )
    assert spare, "one online/allowed CPU must remain for the test controller"
    return min(spare)


def deferred_chain(links, placement, lock):
    """Recover pointer order independently of cross-CPU log order."""
    cpus = placement["role_cpus"]
    layer = placement["defer_layer"]

    def find(**fields):
        found = [
            row
            for row in links
            if row["lock"] == lock
            and all(row[key] == value for key, value in fields.items())
        ]
        assert len(found) <= 1
        return found[0] if found else None

    successor = find(cpu=str(cpus[-1]))
    if successor is None:
        return None
    following = successor
    followers = []
    for role in reversed(deferred_roles(placement)):
        assert following["previous_cpu"] == str(cpus[role])
        follower = find(node=following["previous"])
        if follower is None:
            return None
        assert follower["cpu"] == following["previous_cpu"]
        assert follower["task"] == following["previous_task"]
        followers.append(follower)
        following = follower
    followers.reverse()
    request = find(node=followers[0]["previous"])
    if request is None:
        return None
    assert request["task"] == followers[0]["previous_task"]
    assert request["cpu"] == followers[0]["previous_cpu"]
    assert request["previous_cpu"] in {
        str(cpus[3 + 4 * layer]),
        str(cpus[4 + 4 * layer]),
    }
    chain = [request, *followers, successor]
    assert (
        len({request["previous_task"], *(row["task"] for row in chain)})
        == len(chain) + 1
    )
    nodes = {request["previous"], *(row["node"] for row in chain)}
    assert len(nodes) == len(chain) + 1 and all(int(node, 16) for node in nodes)
    return {"request": request, "followers": followers, "successor": successor}


def wait_deferred_link(placement, timeout=10):
    """Release the holder only after the complete published predecessor chain."""
    validate_placement(placement, placement["depth"])
    readmit = placement.get("readmit", 0)
    layer = placement.get("readmit_layer", 3) if readmit else placement["defer_layer"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = subprocess.check_output(["dmesg"], text=True, timeout=3)
        locks = re.findall(r"kd_deep lock: index=(\d+) addr=([0-9a-f]+)", text)
        selected = dict(locks).get(str(layer))
        links = [
            dict(re.findall(r"(\w+)=([\w-]+)", line))
            for line in text.splitlines()
            if "kd_defer link:" in line
        ]
        chain = (readmission_chain if readmit else deferred_chain)(
            links, placement, selected
        )
        if chain:
            return chain
        time.sleep(0.01)
    raise TimeoutError("head/request/follower/successor links were not all published")


def validate_deferred_events(rows, placement, chain, owner_cpu):
    """Account for every append, including scans cancelled by native followers."""
    request, followers, successor = (
        chain[key] for key in ("request", "followers", "successor")
    )
    lock, pid = request["lock"], request["task"]
    links = rows("kd_defer link")
    by_node = {row["node"]: row for _, row in links}
    assert len(by_node) == len(links) and all(row["lock"] == lock for _, row in links)
    cpus = placement["role_cpus"]
    node_by_cpu = dict(zip(cpus, placement["role_nodes"]))
    owner_by_cpu = {int(row["cpu"]): row["task"] for row in [*followers, successor]}
    owner_by_cpu[owner_cpu] = request["previous_task"]
    appended, spliced, restored = (
        rows("kd_defer " + tag) for tag in ("append", "splice", "restore")
    )
    assert len(spliced) == 1
    splice_at, splice = spliced[0]
    pending, primary = {}, []
    events = sorted(
        (at, tag, row)
        for tag, records in (
            ("append", appended),
            ("splice", spliced),
            ("restore", restored),
        )
        for at, row in records
    )
    for at, tag, row in events:
        assert row["lock"] == lock
        cpu = int(row["cpu"])
        assert row["owner"] == owner_by_cpu[cpu]
        key = (row["owner"], cpu)
        if tag == "append":
            selected = by_node[row["request"]]
            linked = by_node[row["node"]]
            assert any(
                other["previous"] == row["node"] for other in by_node.values()
            ), "a terminal node cannot have been deferred"
            assert row["request_task"] == selected["task"]
            assert row["request_cpu"] == selected["cpu"]
            assert row["task"] == linked["task"] and row["node_cpu"] == linked["cpu"]
            assert row["owner"] != row["request_task"]
            assert int(row["socket"]) == node_by_cpu[cpu]
            assert int(row["node_socket"]) == node_by_cpu[int(row["node_cpu"])]
            assert row["socket"] != row["node_socket"]
            staged = pending.setdefault(key, [])
            if staged:
                assert row["request"] == staged[0]["request"]
            previous = staged[-1]["node"] if staged else row["request"]
            assert linked["previous"] == previous
            assert row["head"] == (staged[0]["node"] if staged else row["node"])
            assert row["tail"] == row["node"]
            staged.append(row)
            if row["request_task"] == pid:
                assert cpu == owner_cpu and row["request"] == request["node"]
                primary.append((at, row))
            else:
                assert at > splice_at and selected in [*followers, successor]
        else:
            staged = pending.pop(key)
            assert staged
            if tag == "restore":
                assert row["request"] == staged[0]["request"]
                assert row["request_task"] == staged[0]["request_task"] != pid
                assert row["request_cpu"] == staged[0]["request_cpu"]
                assert row["first"] == row["next"] == staged[0]["node"]
                assert row["last"] == staged[-1]["node"]
                assert row["head"] == row["tail"] == "0" and row["result"] == "2"
            else:
                assert cpu == owner_cpu and staged[0]["request_task"] == pid
                assert [item["node"] for item in staged] == [
                    item["node"] for item in followers
                ]
                assert row["head"] == followers[0]["node"]
                assert row["tail"] == followers[-1]["node"]
                assert row["head_task"] == followers[0]["task"]
                assert row["head_cpu"] == followers[0]["cpu"]
                assert row["next"] == successor["node"]
                assert row["next_task"] == successor["task"]
                assert row["next_cpu"] == successor["cpu"] and row["linked"] == "1"
                assert row["outer"] == str(
                    int(placement["defer_layer"] < placement["depth"] - 1)
                )
    assert not pending
    assert len(primary) == len(followers)
    chain_links = [request, *followers, successor]
    assert (
        max(at for at, row in links if row in chain_links) < primary[0][0] < splice_at
    )
    return (
        splice_at,
        splice,
        {
            "followers": len(followers),
            "appends": len(appended),
            "restores": len(restored),
        },
    )


def validate_deferred(rows, placement, locks, releases, pid, executors):
    layer = placement.get("defer_layer")
    tags = (
        "kd_defer link",
        "kd_defer append",
        "kd_defer splice",
        "kd_defer restore",
        "kd_deep follower",
        "kd_deep deferred",
    )
    if layer is None:
        assert not any(rows(tag) for tag in tags)
        return None
    cpus = placement["role_cpus"]
    lock = locks[layer]
    links = rows("kd_defer link")
    chain = deferred_chain([row for _, row in links], placement, lock)
    assert chain is not None
    request_link = chain["request"]
    assert request_link["task"] == pid
    assert request_link["cpu"] == str(cpus[0] if layer == 0 else executors[layer - 1])
    assert request_link["previous_cpu"] == str(executors[layer])
    splice_at, splice, stats = validate_deferred_events(
        rows, placement, chain, executors[layer]
    )
    participants = [*chain["followers"], chain["successor"]]
    follower = rows("kd_deep follower")
    assert len(follower) == 2 * len(participants)
    assert [row["extra"] for _, row in follower if row["acquired"] == "1"] == list(
        map(str, range(len(participants)))
    )
    for extra, participant in enumerate(participants):
        records = [(t, r) for t, r in follower if r["extra"] == str(extra)]
        assert len(records) == 2 and splice_at < records[0][0] < records[1][0]
        for index, (_, row) in enumerate(records):
            assert (
                row["task"] == participant["task"] and row["cpu"] == participant["cpu"]
            )
            assert row["index"] == str(layer) and row["valid"] == "1"
            assert row["acquired"] == row["preempt"] == str(1 - index)
            assert row["irq"] == "0"
            if index == 0:
                assert int(row["owner"], 16) and int(row["word"], 16) & 0xFF in (1, 3)
        assert all(
            at < records[0][0]
            for at, row in rows("kd_defer restore")
            if row["request_task"] == participant["task"]
        )
    if layer < placement["depth"] - 1:
        release_at, release = next((t, r) for t, r in releases if r["outer"] == lock)
        assert splice_at < release_at < min(t for t, _ in follower)
        assert release["owner"] == splice["owner"]
        assert release["next_task"] == chain["followers"][0]["task"]
        assert release["next_cpu"] == chain["followers"][0]["cpu"]
    summary = rows("kd_deep deferred")
    assert len(summary) == 1 and summary[0][1] == {
        "layer": str(layer),
        "ready": "1",
        "followers": str(len(participants)),
        "acquired": str(len(participants)),
        "returned": str(len(participants)),
        "valid": "1",
    }
    return stats


def validate(
    text,
    placement,
    stage,
    native_owner=False,
    renamed=False,
    reverse=False,
    lock_ip=None,
    refusal=0,
):
    n = placement["depth"]
    validate_placement(placement, n)
    cpus = placement["role_cpus"]
    assert stage in (1, 2, 3, 4, 5)
    assert not (stage == 1 and (renamed or n == 8))
    assert stage != 5 or n == 8
    assert type(refusal) is int and refusal in (0, 1, 2)
    if refusal:
        assert n == 4 and stage == 1 and "defer_layer" not in placement
    readmit = placement.get("readmit", 0)
    if readmit:
        assert stage == 1 and not refusal
    local = bool(refusal) or readmit == 2
    readmit_layer = placement.get("readmit_layer", 3)
    local_layer = readmit_layer if readmit == 2 else n - 1
    physical = [i for i in range(n) if not (local and i == local_layer)]

    def frame_for(lock):
        return lock - 1 if local and lock == local_layer else lock

    def candidates(layer):
        return (
            (cpus[19],)
            if readmit and layer == readmit_layer
            else (cpus[3 + 4 * layer], cpus[4 + 4 * layer])
        )

    def rows(tag):
        return [
            (m.start(), dict(re.findall(r"(\w+)=([\w-]+)", m[1])))
            for m in re.finditer(re.escape(tag) + r": ([^\n]+)", text)
        ]

    def one(tag):
        found = rows(tag)
        assert len(found) == 1, (tag, found)
        return found[0]

    declared = rows("kd_deep lock")
    assert len(declared) == n + 1
    assert [r["index"] for _, r in declared] == list(map(str, range(n + 1)))
    locks = [r["addr"] for _, r in declared]
    assert len(set(locks)) == n + 1 and all(int(x, 16) for x in locks)
    observed_at, observed = one("kd_deep observe")
    assert observed["depth"] == observed["preempt"] == str(n)
    assert observed["valid"] == observed["prefix"] == "1"
    assert observed["suffix"] == observed["irq"] == "0"
    assert observed["origin_cpu"] == str(cpus[0]) and observed["cpu"] == str(cpus[1])
    assert observed["comm"] == ("kd_native" if native_owner else "klock_test")
    pid = observed["waiter_pid"]
    assert observed["task"] != pid
    assert observed["owner"] != observed["waiter"]
    inspections = rows("kd_deep observe lock")
    assert len(inspections) == n + 1
    for i, (at, row) in enumerate(inspections):
        assert row["index"] == str(i) and row["addr"] == locks[i]
        assert row["valid"] == "1" and int(row["word"], 16) & 0xFF in (1, 3)
        assert at < observed_at
        if i < n - 1 and not native_owner:
            assert row["owner"] == observed["owner"]

    starts = rows("kd_remote start")
    if readmit:
        starts, readmit_witness = validate_readmission(
            rows, placement, locks, pid, starts
        )
    else:
        assert not rows("kd_readmit attempt") and not rows("kd_readmit summary")
        assert not rows("kd_readmit follow")
        assert not rows("kd_deep readmit")
    assert len(starts) == n - 1
    assert [r["outer"] for _, r in starts] == locks[1:n]
    entry = starts[0][1]["entry"]
    continuation = set()
    releases = rows("kd_spin outer release")
    root = [row for _, row in releases if row["outer"] == locks[0]]
    assert len(root) == 1
    executors = {0: int(root[0]["cpu"])}
    owners = {0: root[0]["owner_task"]}
    for i, (at, row) in enumerate(starts, 1):
        assert row["task"] == pid and row["entry"] == entry and row["ip"] != entry
        assert row["parent_outer"] == locks[frame_for(i - 1)] and at < observed_at
        continuation.add(row["ip"])
        assert int(row["cpu"]) in candidates(i)
        executors[i], owners[i] = int(row["cpu"]), row["owner_task"]
    assert len(continuation) == n - 1
    refusal_rows = rows("kd_refusal summary")
    if refusal:
        assert len(refusal_rows) == 1
        rejected = starts[-1][1]
        witness = refusal_rows[0][1]
        assert witness == {
            "kind": str(refusal),
            "claimed": "1",
            "task": pid,
            "entry": entry,
            "ip": rejected["ip"],
            "sp": witness["sp"],
            "lock": locks[n - 1],
            "outer": locks[n - 2],
            "reject_cpu": rejected["cpu"],
            "reject_owner": rejected["owner_task"],
            "acquired_cpu": str(executors[n - 2]),
            "acquired_owner": owners[n - 2],
            "injected": str(1 + refusal),
            "cancelled": "1",
            "acquired": "1",
            "returned": "2",
            "finished": "1",
            "end": "4",
            "initial": "1",
            "cancel_valid": "1",
            "acquire_valid": "1",
            "end_valid": "1",
            "valid": "1",
        }
        assert int(witness["sp"], 16)
        assert witness["reject_owner"] != witness["acquired_owner"]
        counters = [row for _, row in rows("kd_spin lock stats")]
        assert all(row["jit_disabled"] in ("0", "1") for row in counters)
        assert [row["lock"] for row in counters if row["jit_disabled"] == "1"] == (
            [locks[n - 1]] if refusal == 2 else []
        )
        # The last start is an allocated but unexecuted child. Its queued
        # requester acquires that lock and continues in the existing parent.
    else:
        assert not refusal_rows
    if local:
        executors[local_layer], owners[local_layer] = (
            executors[local_layer - 1],
            owners[local_layer - 1],
        )
    assert owners[n - 1] == inspections[n - 1][1]["owner"]
    order = list(range(n - 1))
    if reverse:
        order.reverse()
    outer_order = [i for i in order if i in physical]
    assert len(releases) == len(outer_order)
    assert [row["outer"] for _, row in releases] == [locks[i] for i in outer_order]
    for at, row in releases:
        i = locks.index(row["outer"])
        assert row["task"] == pid
        # Local acquisition clears WAITING; a subsequent remote child sets
        # it again. A shared owner may still retain the locally acquired lock.
        assert row["remote"] == str(
            int(not (local and local_layer == n - 1 and i == local_layer - 1))
        )
        remains = (
            local
            and i == local_layer - 1
            and (local_layer == n - 1 or order.index(i) < order.index(local_layer))
        )
        assert row["remaining"] == str(int(remains))
        assert starts[-1][0] < at < inspections[0][0]
        assert int(row["cpu"]) in candidates(i)
        assert row["owner_task"] == owners[i] and int(row["cpu"]) == executors[i]
    assert len(set(owners.values())) == n - local
    assert len({owners[i] for i in physical}) == n - local
    assert all(int(owner, 16) for owner in owners.values())
    assert not set(owners.values()) & {observed["owner"], observed["waiter"]}
    executed_cpus = [cpus[0]] + [executors[i] for i in physical]
    assert len(set(executed_cpus)) == n + 1 - local
    node_by_cpu = dict(zip(cpus, placement["role_nodes"]))
    executed_nodes = [node_by_cpu[cpu] for cpu in executed_cpus]
    if placement["require_cross_numa"]:
        assert all(a != b for a, b in pairwise(executed_nodes))

    translated = 0 if stage == 2 else 1 if stage == 4 else n - 1
    expected_rpc = [
        (locks[j], locks[i], str(executors[j]))
        for i in order[:translated]
        for j in physical
        if frame_for(i) <= j < physical[-1]
    ]
    rpc = rows("kd_remote unlock")
    assert len(rpc) == len(expected_rpc)
    release_at = {row["outer"]: at for at, row in releases}
    for (at, row), expected in zip(rpc, expected_rpc):
        assert row["task"] == pid and row["result"] == "0"
        assert (row["outer"], row["lock"], row["cpu"]) == expected
        if row["lock"] in release_at:
            assert release_at[row["lock"]] < at
        else:
            # The locally acquired ancestor has no independent frame/outer
            # callback. Its real owner replies after nested unlock; the exact
            # route above and independent physical-lock observer prove release.
            assert local and local_layer < n - 1 and row["lock"] == locks[local_layer]
            assert starts[-1][0] < at

    begins, completes, acks = (
        rows("kd_native begin"),
        rows("kd_native complete"),
        rows("kd_native ack"),
    )
    _, stats = one("kd_native stats")
    native = stage != 1
    ack_order = (
        [locks[i] for i in order[translated:]] + [locks[n - 1]] if native else []
    )
    assert stats == {
        "started": str(n if native else 0),
        "completed": str(n if native else 0),
        "unlocks": str(len(ack_order)),
    }
    assert len(begins) == len(completes) == (n if native else 0)
    assert len(acks) == len(ack_order)
    for _, row in begins + completes + acks:
        assert row["task"] == pid and row["mutex"] == "0"
    if native:
        assert {r["outer"] for _, r in begins} == set(locks[:n])
        assert {r["outer"] for _, r in completes} == set(locks[:n])
        assert (
            len({r["ip"] for _, r in begins}) == len({r["sp"] for _, r in begins}) == 1
        )
        assert [r["lock"] for _, r in acks] == ack_order
        assert [r["last_spin"] for _, r in acks] == ["0"] * (len(acks) - 1) + ["1"]
        assert max(at for at, _ in begins) < acks[0][0]
        assert observed_at < acks[-1][0]
        for _, row in begins:
            i = locks.index(row["outer"])
            released = i in order[:translated]
            assert row["entry"] == entry and int(row["cpu"]) == executors[i]
            assert row["outer_released"] == str(int(released))
            assert row["remaining"] == str(int(not released))
        for i, (at, _) in enumerate(releases):
            if i < translated:
                assert at < min(t for t, _ in begins)
            else:
                assert max(t for t, _ in begins) < at < acks[i - translated][0]
    else:
        for lock in locks[:n]:
            counters = [r for _, r in rows("kd_spin lock stats") if r["lock"] == lock]
            assert len(counters) == 1
            if readmit and lock == locks[readmit_layer]:
                # The real local lead must complete once to commit the NUMA
                # prefix. Only the one-refusal variant also runs the child.
                assert int(counters[0]["jit_success"]) == 3 - readmit
            elif local and lock == locks[local_layer]:
                # This counter counts child wrapper completions, not the
                # parent's translated instructions under a locally held lock.
                assert int(counters[0]["jit_success"]) == 0
            else:
                assert int(counters[0]["jit_success"]) > 0

    probes = rows("kd_deep native probe")
    assert len(probes) == int(native)
    if native:
        assert probes[0][1] == {
            "task": pid,
            "cpu": str(cpus[0]),
            "record": "2",
            "valid": "1",
        }
    changes = rows("kd_resume rename")
    assert len(changes) == (2 if renamed else 0)
    if renamed:
        assert changes[0][0] < acks[0][0] <= acks[-1][0] < changes[1][0]
        assert (
            changes[0][1]["new"] == "kd_renamed"
            and changes[1][1]["new"] == "klock_test"
        )
        for _, row in changes:
            assert row["task"] == pid and row["cpu"] == str(cpus[0])
            assert row["valid"] == "1" and row["preempt_before"] == row["preempt_after"]
            assert row["irq_before"] == row["irq_after"] == "0"
        assert (
            int(changes[0][1]["preempt_after"]) > 0
            and changes[1][1]["preempt_after"] == "0"
        )
    pending = [
        line for line in text.splitlines() if "reason=PENDING_LOCK_NATIVE" in line
    ]
    assert len(pending) == int(stage == 5)
    if stage == 5:
        assert lock_ip and all(r["ip"] == lock_ip for _, r in begins)
        m = re.search(
            r"entry=0x([0-9a-f]+) target=0x([0-9a-f]+) sp=0x([0-9a-f]+) "
            r"return=0x([0-9a-f]+) staged_ip=0x([0-9a-f]+) "
            r"staged_sp=0x([0-9a-f]+) mutex=0 error=-7",
            pending[0],
        )
        assert m
        assert m[1] == entry and m[2] == m[5] == lock_ip
        assert m[3] == m[6] == begins[0][1]["sp"] and int(m[4], 16)

    requests = rows("kd_deep request")
    assert len(requests) == 2
    for i, (_, row) in enumerate(requests, 1):
        expected = int(native and i == 2)
        assert (
            row["record"] == str(i)
            and row["armed"] == str(i - 1)
            and row["valid"] == "1"
        )
        assert row["before"] == row["called"] == row["after"] == str(expected)
    assert requests[1][1]["task"] == pid and requests[1][1]["cpu"] == str(cpus[0])
    # L opens before the owner logs its reply; an independent successor may
    # inspect it first. The logical continuation must still wait for all RPCs.
    rpc_deadline = min(at for at, _ in begins) if native else requests[1][0]
    assert all(at < rpc_deadline for at, _ in rpc)
    states = rows("kd_deep state")
    assert len(states) == n
    for i, (_, row) in enumerate(states):
        assert row == {
            "index": str(i),
            "operations": str(
                (12009 if i == n - 1 else 12008)
                + (
                    placement.get("defer_count", 1)
                    if i == placement.get("defer_layer")
                    else 0
                )
                + (2 if readmit and i == readmit_layer else 0)
            ),
            "valid": "1",
        }
    drain = rows("kd_deep drain")
    assert len(drain) == n + 1
    for i, (_, row) in enumerate(drain):
        assert row["index"] == str(i) and row["valid"] == "1"
        assert row["inside"] == row["word"] == row["owner"] == "0"
        assert row["queued"] in (("0", "-28") if i == n else ("0",))
    _, summary = one("kd_deep summary")
    assert summary == {
        "depth": str(n),
        "stage": str(stage),
        "reverse": str(int(reverse)),
        "requests": "2",
        "checked": "2",
        "prefix": "1",
        "suffix": "1",
        "observed": "1",
        "failures": "0",
        "abort": "0",
    }
    assert "valid=0" not in text
    deferred_stats = (
        None
        if readmit
        else validate_deferred(rows, placement, locks, releases, pid, executors)
    )
    result = {
        "cpus": executed_cpus,
        "nodes": executed_nodes,
        "native_frames": len(begins),
        "acks": len(acks),
        "rpc": len(rpc),
    }
    if deferred_stats is not None:
        result["deferred"] = deferred_stats
    if refusal:
        result["refusal"] = witness
    if readmit:
        result["readmit"] = readmit_witness
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("placement", type=Path)
    parser.add_argument("stage", type=int, choices=range(1, 6))
    parser.add_argument("--native-owner", action="store_true")
    parser.add_argument("--renamed", action="store_true")
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--lock-ip")
    parser.add_argument("--refusal", type=int, choices=(1, 2), default=0)
    args = parser.parse_args()
    result = validate(
        args.log.read_text(),
        json.loads(args.placement.read_text()),
        args.stage,
        args.native_owner,
        args.renamed,
        args.reverse,
        args.lock_ip,
        args.refusal,
    )
    print("deep remote protocol: " + json.dumps(result, sort_keys=True) + " PASS")


if __name__ == "__main__":
    main()
