"""Strict evidence checks for the controlled mode-8 remote A/B/C dependency."""

import argparse
import csv
import io
import json
import re
from itertools import pairwise
from pathlib import Path

from cpu_placement import capture_topology, validate_topology


def validate_multi_roots(
    text, placement, publications, statuses, quota=False,
    published_after=None, assemblies=None,
):
    """Two live A parents must send distinct logical packets to one B owner.

    Queue counts only open the workload gates. Actual returned JIT bodies and
    remote-start identities prove delegation; independent state records detect
    exchanged/replayed continuations. No live flags or version proof is implied.
    """
    validate_topology(placement, 14)
    assert placement["role_cpus"] == list(range(14))
    exits = list(csv.reader(io.StringIO(statuses), delimiter="\t"))
    assert len(exits) == 14
    assert {int(role): int(status) for role, status in exits} == dict.fromkeys(
        range(14), 0
    )
    published = [json.loads(line) for line in publications.splitlines()]
    assert len(published) == 3
    entries = {int(row["entry"], 16) for row in published}
    assert len(entries) == 3 and 0 not in entries
    assert all(
        type(row["status"]) is int
        and row["status"] == 0
        and int(row["code"], 16)
        for row in published
    )

    def rows(tag, separator=": "):
        return [
            (match.start(), dict(re.findall(r"(\w+)=([\w-]+)", match[1])))
            for match in re.finditer(re.escape(tag + separator) + r"([^\n]+)", text)
        ]

    def one(tag):
        found = rows(tag)
        assert len(found) == 1, (tag, found)
        return found[0]

    starts, done = rows("kd_multi start"), rows("kd_multi done")
    assert len(starts) == len(done) == 14
    roles = {int(row["role"]): (at, row) for at, row in starts}
    assert set(roles) == set(range(14))
    assert {int(row["role"]) for _, row in done} == set(roles)
    assert len({row["task"] for _, row in starts}) == 14
    assert len({row["self"] for _, row in starts}) == 14
    for at, row in done:
        role = int(row["role"])
        before, original = roles[role]
        assert at > before and row == original
        assert int(row["cpu"]) == placement["role_cpus"][role]
        assert int(row["task"]) > 0 and int(row["self"], 16)
        assert row["preempt"] == row["irq"] == "0"

    queued_at, queued = one("kd_multi queued")
    assert queued["count"] == "4" and queued["valid"] == "1"
    a = [int(queued[f"a{i}"], 16) for i in (0, 1)]
    b = int(queued["b"], 16)
    assert len(set(a + [b])) == 3 and all(a + [b])
    assert queued["first"] == roles[0][1]["task"]
    assert queued["second"] == roles[5][1]["task"]
    assert queued["b_owner"] == roles[10][1]["self"]
    assert all(at < queued_at for at, _ in starts)
    for lane, candidates in ((0, (2, 3)), (1, (7, 8))):
        assert queued[f"owner{lane}"] in {roles[r][1]["self"] for r in candidates}

    remote = rows("kd_remote start")
    assert len(remote) == 2
    assert {row["task"] for _, row in remote} == {
        roles[0][1]["task"], roles[5][1]["task"]
    }
    assert len({row["owner_task"] for _, row in remote}) == 1
    assert len({row["cpu"] for _, row in remote}) == 1
    assert len({row["entry"] for _, row in remote}) == 1
    nested_entry = int(remote[0][1]["entry"], 16)
    assert nested_entry in entries
    for at, row in remote:
        lane = 0 if row["task"] == queued["first"] else 1
        assert at > queued_at
        assert int(row["parent_outer"], 16) == a[lane]
        assert int(row["outer"], 16) == b and int(row["ip"], 16)
        owner_roles = [
            r for r in (11, 12) if roles[r][1]["self"] == row["owner_task"]
        ]
        assert len(owner_roles) == 1
        assert row["cpu"] == roles[owner_roles[0]][1]["cpu"]
        ended = next(position for position, end in done if end["task"] == row["task"])
        assert at < ended
    bodies = rows("JIT body witness")
    assert len(bodies) == 4
    assert all(
        int(row["entry"], 16) == nested_entry and row["body"] == "1"
        for _, row in bodies
    )
    for lock in a:
        matching = [at for at, row in bodies if int(row["lock"], 16) == lock]
        assert len(matching) == 1 and matching[0] < queued_at
    inner = [at for at, row in bodies if int(row["lock"], 16) == b]
    assert len(inner) == 2 and remote[0][0] < inner[0] < remote[1][0] < inner[1]

    records = rows("kd_multi record")
    assert len(records) == 2 and {row["lane"] for _, row in records} == {"0", "1"}
    assert {int(row["shared"]) for _, row in records} == {12006, 12007}
    for _, row in records:
        lane = int(row["lane"])
        token, expected = 0x12340001 + lane * 0x101, 0
        for _ in range(2):
            expected = (expected + token) ^ (token << 1)
        assert row["before"] == row["after"] == "2"
        assert int(row["value"], 16) == int(row["expected"], 16) == expected
    _, stats = one("kd_multi stats")
    assert stats == {
        "started": "3fff", "finished": "3fff", "failures": "0", "aborted": "0"
    }
    _, native = one("kd_native stats")
    _, services = one("kd_multi services")
    if quota:
        # Production needs B-local completion before the next child. This
        # SELFTEST schedule additionally waits at the ACK-drained pop for the
        # first TID to detach; it must never withhold an ACK needed for exit.
        assert native == {"started": "2", "completed": "2", "unlocks": "2"}
        assert services == {"quota": "1", "calls": "34", "observed": "1"}
        assert remote[0][1]["task"] == queued["first"]
        final = [json.loads(line) for line in published_after.splitlines()]
        assert len(final) == len(published)
        for before, after in zip(published, final):
            for key in ("entry", "tgid", "pid", "status", "code"):
                assert before[key] == after[key]
            assert after["observed_ns"] > before["observed_ns"]
        assembly = assemblies[nested_entry]
        targets = re.findall(
            r"/\* KD_HOSTCALL id=\d+ symbol=ktime_get(?:_ns)? \*/\nloc_([0-9a-f]+):",
            assembly,
        )
        assert len(targets) == 1
        limits = rows("reason=CALL_LIMIT_NATIVE", " ")
        assert len(limits) == 1
        limit_at, limit = limits[0]
        assert limit["hostcall"] == "1" and limit["task"] == queued["first"]
        assert int(limit["entry"], 16) == nested_entry
        assert int(limit["ip"], 16) == int(targets[0], 16)
        assert int(limit["lock"], 16) == b and int(limit["sp"], 16)
        assert f"loc_{int(limit['return'], 16):x}:" in assembly
        begins, completed, acks = (
            rows("kd_native begin"), rows("kd_native complete"), rows("kd_native ack")
        )
        assert len(begins) == len(completed) == len(acks) == 2
        observations = rows("kd_multi quota")
        assert len(observations) == 2
        assert inner[0] < limit_at < begins[0][0] < begins[1][0] < observations[0][0]
        for phase, (at, row) in enumerate(observations):
            assert row["phase"] == str(phase) and row["valid"] == "1"
            assert row["task"] == queued["first"]
            assert row["self"] == roles[0][1]["self"] and row["cpu"] == "0"
            assert row["a0"] == queued["owner0"] and row["a1"] == queued["owner1"]
            assert row["b"] == remote[0][1]["owner_task"]
            assert row["other_before"] == "2" and row["preempt"] == "1"
            assert row["other_after"] == "1" and row["irq"] == "0"
            assert row["other_shared"] == "12003" and row["sequence"] == "12006"
            assert row["calls"] == "34"
        for index, lock in enumerate((b, a[0])):
            begin_at, begin = begins[index]
            complete_at, complete = completed[index]
            ack_at, ack = acks[index]
            assert observations[1][0] < complete_at < ack_at
            assert begin["task"] == complete["task"] == ack["task"] == queued["first"]
            assert int(begin["outer"], 16) == int(complete["outer"], 16) == lock
            assert int(ack["lock"], 16) == lock
            for key in ("entry", "ip", "sp"):
                assert int(begin[key], 16) == int(limit[key], 16)
            assert begin["held"] == begin["remaining"] == "1"
            assert begin["outer_released"] == begin["mutex"] == "0"
            assert complete["mutex"] == ack["mutex"] == "0"
            assert ack["last_spin"] == str(index)
            owner = remote[0][1]["owner_task"] if not index else queued["owner0"]
            assert any(row["self"] == owner and row["cpu"] == begin["cpu"]
                       for _, row in starts)
        assert acks[0][0] < completed[1][0]
        assert completed[0][0] < remote[1][0]
        assert acks[1][0] < next(at for at, row in done if row["role"] == "0")
        arm_at, arm = one("kd_child_exit arm")
        exit_at, exited = one("kd_spin retirement")
        assert begins[0][0] < arm_at < begins[1][0]
        assert exit_at < acks[1][0] < next(at for at, row in done if row["role"] == "0")
        assert completed[0][0] < exit_at < remote[1][0]
        for row in (arm,):
            assert row["task"] == queued["first"] and row["valid"] == "1"
            assert row["owner"] == remote[0][1]["owner_task"]
            assert row["cpu"] == remote[0][1]["cpu"]
            assert int(row["outer"], 16) == b
            for key in ("entry", "ip", "sp"):
                assert int(row[key], 16) == int(limit[key], 16)
        assert arm["remaining"] == arm["alive"] == "1"
        assert exited == dict(task=queued["first"], child="1", retired="1", valid="1")
        assert not rows("kd_relay_exit arm") and not rows("kd_relay_exit release")
        _, hostcalls = one("kd_hostcall stats")
        assert hostcalls == {
            "exits": "17", "executed": "16", "resumed": "16",
            "rejected": "0", "failed": "0", "limit": "1",
        }
    else:
        assert services == {"quota": "0", "calls": "0", "observed": "0"}
        assert native == {"started": "0", "completed": "0", "unlocks": "0"}
        assert not rows("kd_native begin") and not rows("kd_native ack")
        assert not rows("kd_multi quota") and not rows("reason=CALL_LIMIT_NATIVE", " ")
        assert not rows("kd_child_exit arm") and not rows("kd_spin retirement")
    return {
        "roots": 2,
        "roles": 14,
        "jit_bodies": 4,
        "entry": hex(nested_entry),
        "shared_lock": hex(b),
        "waiters": [int(queued["first"]), int(queued["second"])],
        "b_executor": remote[0][1]["owner_task"],
        "quota_native": int(quota),
        "waiter_exit": int(quota),
    }


def _role_count(depth):
    assert depth in (2, 3), depth
    return 10 + 4 * (depth - 2)


def validate_placement(placement, depth):
    assert set(placement) == {
        "depth",
        "role_cpus",
        "role_nodes",
        "allowed_cpus",
        "online_cpus",
        "require_cross_numa",
    }
    assert type(placement["depth"]) is int and placement["depth"] == depth
    validate_topology(placement, _role_count(depth))
    nodes = placement["role_nodes"]
    assert type(placement["require_cross_numa"]) is bool
    if placement["require_cross_numa"]:
        groups = [(0,), (4, 6), (2, 5)]
        if depth == 3:
            groups.append((11, 12))
        for left, right in pairwise(groups):
            assert not {nodes[r] for r in left} & {nodes[r] for r in right}, (
                "every possible origin/executor hop must cross NUMA nodes",
                left,
                right,
            )
    return placement


def capture_placement(
    cpu_text,
    depth,
    require_cross_numa=False,
    cpu_root=Path("/sys/devices/system/cpu"),
    allowed_cpus=None,
):
    cpus = (
        [int(value) for value in cpu_text.split(",")]
        if cpu_text
        else list(range(_role_count(depth)))
    )
    return validate_placement(
        {
            **capture_topology(cpus, cpu_root, allowed_cpus),
            "depth": depth,
            "require_cross_numa": require_cross_numa,
        },
        depth,
    )


def _role_cpus(placement, depth):
    if placement is None:
        return list(range(_role_count(depth)))
    return validate_placement(placement, depth)["role_cpus"]


def _execution_placement(placement, cpus):
    # Without a captured topology, do not invent NUMA evidence for old logs.
    if placement is None:
        return {"cpus": cpus, "nodes": None, "require_cross_numa": False}
    node_by_cpu = dict(zip(placement["role_cpus"], placement["role_nodes"]))
    nodes = [node_by_cpu[cpu] for cpu in cpus]
    if placement["require_cross_numa"]:
        assert all(left != right for left, right in pairwise(nodes))
    return {
        "cpus": cpus,
        "nodes": nodes,
        "require_cross_numa": placement["require_cross_numa"],
    }


def validate_chain(text, stage, native_owner, renamed, reverse, placement=None):
    cpus = _role_cpus(placement, 3)

    def rows(tag):
        return [
            (match.start(), dict(re.findall(r"(\w+)=([\w-]+)", match[1])))
            for match in re.finditer(re.escape(tag) + r": ([^\n]+)", text)
        ]

    def one(tag):
        found = rows(tag)
        assert len(found) == 1, (tag, found)
        return found[0]

    assert stage in (1, 2, 3, 4) and not (stage == 1 and renamed)
    observed_at, observed = one("kd_chain observe")
    assert observed["valid"] == observed["prefix"] == "1", observed
    assert observed["suffix"] == observed["irq"] == "0"
    assert observed["preempt"] == "3"
    assert observed["cpu"] == str(cpus[9 if native_owner else 8])
    assert observed["origin_cpu"] == str(cpus[0])
    assert observed["comm"] == ("kd_native" if native_owner else "klock_test")
    a, b, c, d = (observed[key] for key in ("a", "b", "c", "d"))
    assert len({a, b, c, d}) == 4 and all(int(x, 16) for x in (a, b, c, d))
    for key in ("a_word", "b_word", "c_word", "d_word"):
        assert int(observed[key], 16) & 0xFF in (1, 3), observed
    assert observed["owner_task"] != observed["waiter"]
    assert observed["task"] != observed["waiter_pid"]
    if not native_owner:
        assert observed["a_owner"] == observed["b_owner"] == observed["owner_task"]
    pid = observed["waiter_pid"]
    starts = rows("kd_remote start")
    assert len(starts) == 2 and [row["outer"] for _, row in starts] == [b, c]
    child = {}
    for (_, row), parent, allowed in zip(starts, (a, b), ((2, 5), (11, 12))):
        assert row["task"] == pid and row["parent_outer"] == parent
        assert (
            row["cpu"] in {str(cpus[r]) for r in allowed} and row["entry"] != row["ip"]
        )
        child[row["outer"]] = row
    assert child[b]["entry"] == child[c]["entry"]
    assert child[b]["ip"] != child[c]["ip"]
    assert child[c]["owner_task"] == observed["c_owner"]
    releases = rows("kd_spin outer release")
    order = [b, a] if reverse else [a, b]
    assert len(releases) == 2 and [row["outer"] for _, row in releases] == order
    released = {}
    for at, row in releases:
        assert row["task"] == pid and row["remaining"] == "0" and row["remote"] == "1"
        assert starts[-1][0] < at < observed_at
        released[row["outer"]] = row
    assert released[a]["cpu"] in {str(cpus[r]) for r in (4, 6)}
    assert released[b]["cpu"] == child[b]["cpu"]
    assert released[b]["owner_task"] == child[b]["owner_task"]
    owners = {released[a]["owner_task"], child[b]["owner_task"], child[c]["owner_task"]}
    assert len(owners) == 3 and all(int(owner, 16) for owner in owners)
    assert not owners & {observed["waiter"], observed["owner_task"]}
    rpc = rows("kd_remote unlock")
    translated = 0 if stage == 2 else 1 if stage == 4 else 2
    expected_rpc = []
    for lock in order[:translated]:
        if lock == a:
            expected_rpc.append((a, a, released[a]["cpu"]))
        expected_rpc.append((b, lock, child[b]["cpu"]))
    assert len(rpc) == len(expected_rpc), (rpc, expected_rpc)
    for (_, row), (outer, lock, cpu) in zip(rpc, expected_rpc):
        assert row["task"] == pid and row["result"] == "0"
        assert (row["outer"], row["lock"], row["cpu"]) == (outer, lock, cpu)
    workload_at, workload = one("kd_chain workload")
    assert observed_at < workload_at
    assert workload == {
        "stage": str(stage),
        "native_owner": str(int(native_owner)),
        "reverse": str(int(reverse)),
        "depth": "3",
        "prefix": "1",
        "suffix": "1",
        "observed": "1",
    }
    _, stats = one("kd_native stats")
    begins, completes, acks = (
        rows("kd_native begin"),
        rows("kd_native complete"),
        rows("kd_native ack"),
    )
    if stage == 1:
        assert not begins and not completes and not acks
        assert stats == {"started": "0", "completed": "0", "unlocks": "0"}
        for lock in (a, b, c):
            records = [
                row for _, row in rows("kd_spin lock stats") if row["lock"] == lock
            ]
            assert len(records) == 1 and int(records[0]["jit_success"]) > 0
    else:
        expected_acks = order[translated:] + [c]
        assert stats == {
            "started": "3",
            "completed": "3",
            "unlocks": str(len(expected_acks)),
        }
        assert len(begins) == len(completes) == 3
        assert {row["outer"] for _, row in begins} == {a, b, c}
        assert {row["outer"] for _, row in completes} == {a, b, c}
        assert len(acks) == len(expected_acks)
        assert observed_at < acks[-1][0]
        assert max(when for when, _ in begins) < acks[0][0]
        assert [row["lock"] for _, row in acks] == expected_acks
        assert [row["last_spin"] for _, row in acks] == ["0"] * (len(acks) - 1) + ["1"]
        assert (
            len({row["ip"] for _, row in begins})
            == len({row["sp"] for _, row in begins})
            == 1
        )
        for _, row in begins + completes + acks:
            assert row["task"] == pid and row["mutex"] == "0"
        for _, row in begins:
            is_released = row["outer"] in order[:translated]
            assert row["entry"] == child[b]["entry"]
            assert row["outer_released"] == str(int(is_released))
            assert row["remaining"] == str(int(not is_released))
            cpu = (
                released[a]["cpu"] if row["outer"] == a else child[row["outer"]]["cpu"]
            )
            assert row["cpu"] == cpu
        # Untranslated ancestor releases happen only after all three packets
        # are registered; translated releases precede every native begin.
        for index, (at, _) in enumerate(releases):
            if index < translated:
                assert at < min(when for when, _ in begins)
            else:
                assert (
                    max(when for when, _ in begins) < at < acks[index - translated][0]
                )
        if renamed:
            changes = [
                (at, row) for at, row in rows("kd_resume rename") if row["task"] == pid
            ]
            assert len(changes) == 2
            assert (
                changes[0][1]["new"] == "kd_renamed"
                and changes[1][1]["new"] == "klock_test"
            )
            assert changes[0][0] < acks[0][0] <= acks[-1][0] < changes[1][0]
            for _, row in changes:
                assert (
                    row["valid"] == "1"
                    and row["preempt_before"] == row["preempt_after"]
                )
                assert row["irq_before"] == row["irq_after"] == "0"
            assert int(changes[0][1]["preempt_after"]) > 0
            assert changes[1][1]["preempt_after"] == "0"
    assert "valid=0" not in text
    assert not rows("kd_remote observe") and not rows("kd_remote workload")
    return _execution_placement(
        placement,
        [
            int(observed["origin_cpu"]),
            int(released[a]["cpu"]),
            int(child[b]["cpu"]),
            int(child[c]["cpu"]),
        ],
    )


def validate(text, stage, native_owner, renamed, placement=None):
    cpus = _role_cpus(placement, 2)

    def rows(tag):
        return [
            (match.start(), dict(re.findall(r"(\w+)=([\w-]+)", match[1])))
            for match in re.finditer(re.escape(tag) + r": ([^\n]+)", text)
        ]

    def one(tag):
        found = rows(tag)
        assert len(found) == 1, (tag, found)
        return found[0]

    observed_at, observed = one("kd_remote observe")
    assert observed["valid"] == observed["prefix"] == "1", observed
    assert observed["suffix"] == observed["irq"] == "0", observed
    assert observed["preempt"] == "2"
    assert observed["cpu"] == str(cpus[9 if native_owner else 8])
    assert observed["origin_cpu"] == str(cpus[0])
    assert observed["comm"] == ("kd_native" if native_owner else "klock_test")
    for key in ("a_word", "b_word", "c_word"):
        assert int(observed[key], 16) & 0xFF in (1, 3), observed
    assert int(observed["b_owner"], 16) and observed["b_owner"] != observed["waiter"]
    if not native_owner:
        assert (
            int(observed["a_owner"], 16) and observed["a_owner"] != observed["b_owner"]
        )

    pid, a, b = observed["waiter_pid"], observed["outer"], observed["inner"]
    starts = [(at, row) for at, row in rows("kd_remote start") if row["task"] == pid]
    assert len(starts) == 1, starts
    start_at, start = starts[0]
    assert start["owner_task"] == observed["b_owner"]
    assert start["outer"] == b and start["parent_outer"] == a
    assert (
        start["cpu"] in {str(cpus[r]) for r in (2, 5)} and start["entry"] != start["ip"]
    ), start
    releases = [
        (at, row) for at, row in rows("kd_spin outer release") if row["task"] == pid
    ]
    assert len(releases) == 1, releases
    release_at, release = releases[0]
    assert (
        release["outer"] == a
        and release["remaining"] == "0"
        and release["remote"] == "1"
    )
    assert (
        release["cpu"] in {str(cpus[r]) for r in (4, 6)}
        and release["cpu"] != start["cpu"]
    )
    assert release["owner_task"] not in {start["owner_task"], observed["waiter"]}
    assert start_at < release_at < observed_at

    rpc = [(at, row) for at, row in rows("kd_remote unlock") if row["task"] == pid]
    if stage == 2:
        assert not rpc, rpc
    else:
        assert len(rpc) == 1, rpc
        assert rpc[0][1]["outer"] == rpc[0][1]["lock"] == a
        assert rpc[0][1]["cpu"] == release["cpu"] and rpc[0][1]["result"] == "0"

    _, workload = one("kd_remote workload")
    assert workload == {
        "stage": str(stage),
        "native_owner": str(int(native_owner)),
        "prefix": "1",
        "suffix": "1",
        "observed": "1",
    }, workload
    _, stats = one("kd_native stats")
    begins = rows("kd_native begin")
    completes = rows("kd_native complete")
    acks = rows("kd_native ack")
    if stage == 1:
        assert not begins and not completes and not acks
        assert stats == {"started": "0", "completed": "0", "unlocks": "0"}
        for lock in (a, b):
            records = [
                row for _, row in rows("kd_spin lock stats") if row["lock"] == lock
            ]
            assert len(records) == 1 and int(records[0]["jit_success"]) > 0
    else:
        expected = 2 if stage == 2 else 1
        assert stats == {"started": "2", "completed": "2", "unlocks": str(expected)}
        assert len(begins) == len(completes) == 2 and len(acks) == expected
        assert {row["outer"] for _, row in begins} == {a, b}
        assert {row["outer"] for _, row in completes} == {a, b}
        for _, row in begins + completes + acks:
            assert row["task"] == pid and row["mutex"] == "0", row
        parent = next(row for _, row in begins if row["outer"] == a)
        child = next(row for _, row in begins if row["outer"] == b)
        assert parent["cpu"] == release["cpu"] and child["cpu"] == start["cpu"]
        assert parent["entry"] == child["entry"] == start["entry"]
        assert parent["ip"] == child["ip"] and parent["sp"] == child["sp"]
        assert parent["remaining"] == ("1" if stage == 2 else "0")
        assert parent["outer_released"] == ("0" if stage == 2 else "1")
        assert child["remaining"] == "1" and child["outer_released"] == "0"
        assert [row["lock"] for _, row in acks] == ([a, b] if stage == 2 else [b])
        assert [row["last_spin"] for _, row in acks] == (
            ["0", "1"] if stage == 2 else ["1"]
        )
        if renamed:
            changes = [
                (at, row) for at, row in rows("kd_resume rename") if row["task"] == pid
            ]
            assert len(changes) == 2, changes
            assert (
                changes[0][1]["new"] == "kd_renamed"
                and changes[1][1]["new"] == "klock_test"
            )
            assert changes[0][0] < acks[-1][0] < changes[1][0]
            for _, row in changes:
                assert (
                    row["valid"] == "1"
                    and row["preempt_before"] == row["preempt_after"]
                )
                assert row["irq_before"] == row["irq_after"] == "0"
            assert int(changes[0][1]["preempt_after"]) > 0
            assert changes[1][1]["preempt_after"] == "0"
    assert "valid=0" not in text
    return _execution_placement(
        placement, [int(observed["origin_cpu"]), int(release["cpu"]), int(start["cpu"])]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("stage", type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--native-owner", action="store_true")
    parser.add_argument("--renamed", action="store_true")
    parser.add_argument("--depth", type=int, choices=(2, 3), default=2)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--placement", type=Path)
    parser.add_argument("--multi", action="store_true")
    parser.add_argument("--publications", type=Path)
    parser.add_argument("--statuses", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--quota", action="store_true")
    parser.add_argument("--published-after", type=Path)
    parser.add_argument("--artifacts", type=Path, nargs="+")
    args = parser.parse_args()
    placement = json.loads(args.placement.read_text()) if args.placement else None
    if args.multi:
        assert args.stage == 1 and args.depth == 2
        assert not (args.reverse or args.native_owner or args.renamed)
        assert placement is not None and args.publications and args.statuses and args.result
        result = validate_multi_roots(
            args.log.read_text(), placement, args.publications.read_text(),
            args.statuses.read_text(), args.quota,
            args.published_after.read_text() if args.published_after else None,
            {int(path.parents[1].name, 16): (path / "jit.S").read_text()
             for path in args.artifacts} if args.artifacts else None,
        )
        args.result.write_text(json.dumps(result, indent=2) + "\n")
        print("[PASS] two logical roots / shared B JIT: " + json.dumps(result))
        return
    assert args.publications is args.statuses is args.result is None
    assert not args.quota and args.published_after is args.artifacts is None
    if args.depth == 3:
        execution = validate_chain(
            args.log.read_text(),
            args.stage,
            args.native_owner,
            args.renamed,
            args.reverse,
            placement,
        )
    else:
        assert args.stage in (1, 2, 3) and not args.reverse
        execution = validate(
            args.log.read_text(), args.stage, args.native_owner, args.renamed, placement
        )
    print("remote execution placement: " + json.dumps(execution, sort_keys=True))
    print(
        f"remote outer protocol: stage={args.stage} native_owner={int(args.native_owner)} PASS"
    )


if __name__ == "__main__":
    main()
