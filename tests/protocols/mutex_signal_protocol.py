"""Verify real mutex scheduling/ownership and control native signal clients."""

import argparse
import concurrent.futures
import contextlib
import csv
import ctypes
import io
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from native_only_protocol import Entry, entries

PARAMS = Path("/sys/module/klock_module/parameters")


def validate_nested_schedule(text, publication, placements, statuses):
    """A shared-CPU native B sleep must finish through the original JIT path.

    This is the existing seven-role mode 4 workload, not a PENDING/native-suffix
    gate. Kernel identities and the real wait-list observation distinguish
    actual scheduling from merely requesting overlapping taskset masks.
    """
    expected = dict(enumerate((1, 0, 1, 0, 0, 1, 1)))
    requested = list(csv.reader(io.StringIO(placements), delimiter="\t"))
    exits = list(csv.reader(io.StringIO(statuses), delimiter="\t"))
    assert len(requested) == len(exits) == 7
    assert {int(role): int(cpu) for role, cpu in requested} == expected
    assert {int(role): int(status) for role, status in exits} == dict.fromkeys(
        expected, 0
    )
    assert type(publication["status"]) is int and publication["status"] == 0
    entry = int(publication["entry"], 16)
    assert entry and int(publication["code"], 16)

    def rows(tag):
        return [
            (m.start(), dict(re.findall(r"(\w+)=([-\w]+)", m[1])))
            for m in re.finditer(re.escape(tag) + r": ([^\n]+)", text)
        ]

    def one(tag):
        found = rows(tag)
        assert len(found) == 1, (tag, found)
        return found[0]

    starts, ends = rows("kd_nested mutex role"), rows("kd_nested mutex done")
    assert len(starts) == len(ends) == 7
    assert {int(row["role"]) for _, row in starts} == set(expected)
    assert {int(row["role"]) for _, row in ends} == set(expected)
    assert len({row["task"] for _, row in starts}) == 7
    assert len({row["self"] for _, row in starts}) == 7
    roles = {int(row["role"]): (at, row) for at, row in starts}
    completed = {int(row["role"]): at for at, row in ends}
    for at, row in ends:
        role = int(row["role"])
        before, original = roles[role]
        assert before < at and row == original
        assert int(row["cpu"]) == expected[role]
        assert row["preempt"] == row["irq"] == "0"
        assert int(row["task"]) > 0 and int(row["self"], 16)

    blocked_at, blocked = one("kd_nested mutex blocked")
    assert blocked["queued"] == blocked["valid"] == "1"
    assert blocked["holder"] == roles[1][1]["task"]
    assert blocked["b_owner"] == roles[1][1]["self"]
    assert blocked["executor"] == roles[4][1]["task"]
    assert blocked["a_owner"] == roles[4][1]["self"]
    assert blocked["cpu"] == blocked["executor_cpu"] == "0"
    a, b = int(blocked["a"], 16), int(blocked["b"], 16)
    assert a and b and a != b
    assert all(at < blocked_at for at, _ in starts)
    assert blocked_at < completed[0] and blocked_at < completed[1]
    body_at, body = one("JIT body witness")
    assert int(body["entry"], 16) == entry
    assert int(body["lock"], 16) == a and body["body"] == "1"
    assert roles[0][0] < body_at < blocked_at
    _, native = one("kd_native stats")
    assert native == {"started": "0", "completed": "0", "unlocks": "0"}
    assert not rows("kd_native begin") and not rows("kd_native ack")
    return {
        "roles": 7,
        "cpus": 2,
        "executor": int(blocked["executor"]),
        "holder": int(blocked["holder"]),
        "shared_cpu": 0,
        "jit_bodies": 1,
        "native_frames": 0,
    }


def validate_shared_b(text, publications, placements, statuses, probe):
    """Two A frames share Linux B, not a remotely delegated B combiner.

    Join the retained native frame to its original waiter and both real Linux
    sleepers. ACK logging follows physical unlock, so the next owner can run
    before the previous ACK log: do not invent a global log-order barrier.
    """
    expected = {**dict(enumerate(range(8))), 10: 8}
    for raw, values in ((placements, expected), (statuses, dict.fromkeys(expected, 0))):
        rows = list(csv.reader(io.StringIO(raw), delimiter="\t"))
        assert len(rows) == len(values)
        assert {int(key): int(value) for key, value in rows} == values
    assert len(publications) == 2
    published = {int(p["entry"], 16) for p in publications}
    assert len(published) == 2 and all(published)
    assert all(type(p["status"]) is int and p["status"] == 0 and
               int(p["code"], 16) for p in publications)
    assert int(probe, 16)

    def rows(tag):
        return [(m.start(), dict(re.findall(r"(\w+)=([-\w]+)", m[1])))
                for m in re.finditer(re.escape(tag) + r": ([^\n]+)", text)]

    def one(tag):
        found = rows(tag)
        assert len(found) == 1, (tag, found)
        return found[0]

    starts, ends = rows("kd_shared role"), rows("kd_shared done")
    assert len(starts) == len(ends) == 9
    roles = {int(row["role"]): (at, row) for at, row in starts}
    done = {int(row["role"]): at for at, row in ends}
    assert set(roles) == set(done) == set(expected)
    assert len({r["task"] for _, r in starts}) == 9
    assert len({r["self"] for _, r in starts}) == 9
    for at, row in ends:
        role = int(row["role"])
        before, original = roles[role]
        assert before < at and row == original
        assert int(row["task"]) > 0 and int(row["self"], 16)
        assert int(row["cpu"]) == expected[role]
        assert row["preempt"] == row["irq"] == "0"
        assert row["comm"] == ("kd_native" if role == 10 else "klock_test")

    held = rows("kd_shared retained")
    assert len(held) == 2 and [r["phase"] for _, r in held] == ["0", "1"]
    outer0, outer1, inner = (held[0][1][k] for k in ("outer0", "outer1", "inner"))
    assert len({outer0, outer1, inner}) == 3 and all(
        int(value, 16) for value in (outer0, outer1, inner)
    )
    for at, row in held:
        assert row["task"] == roles[2][1]["task"]
        assert row["self"] == roles[2][1]["self"] and row["cpu"] == "2"
        assert row["a0"] == row["b"] == roles[1][1]["self"]
        assert row["a1"] == roles[5][1]["self"]
        assert row["executor"] == roles[5][1]["task"]
        assert row["peer"] == roles[10][1]["task"]
        assert (row["outer0"], row["outer1"], row["inner"]) == (outer0, outer1, inner)
        assert row["queued"] == "2" and row["valid"] == "1"
        assert row["before"] == "12002" and row["held"] == row["after"] == "12001"
        assert row["sequence"] == "24003" and row["preempt"] == row["irq"] == "0"
        assert all(roles[r][0] < at < done[r] for r in (1, 2, 5, 6, 10))

    bodies = rows("JIT body witness")
    assert len(bodies) == 2 and {int(r["entry"], 16) for _, r in bodies} == published
    assert {r["lock"] for _, r in bodies} == {outer0, outer1}
    assert all(r["body"] == "1" and at < held[0][0] for at, r in bodies)
    entries_by_lock = {r["lock"]: r["entry"] for _, r in bodies}
    assert [int(entries_by_lock[lock], 16) for lock in (outer0, outer1)] == [
        int(p["entry"], 16) for p in publications
    ]
    begin_at, begin = one("kd_native begin")
    assert begin["task"] == roles[2][1]["task"] and begin["cpu"] == "1"
    assert begin["outer"] == outer0 and begin["entry"] == entries_by_lock[outer0]
    assert int(begin["ip"], 16) == int(probe, 16) and int(begin["sp"], 16)
    assert begin["held"] == begin["remaining"] == "2"
    assert begin["mutex"] == "1" and begin["outer_released"] == "0"
    assert next(at for at, r in bodies if r["lock"] == outer0) < begin_at < held[0][0]
    acks = rows("kd_native ack")
    assert len(acks) == 2 and [r["lock"] for _, r in acks] == [inner, outer0]
    assert all(at > held[1][0] and r["task"] == begin["task"] and
               r["mutex"] == "1" and r["last_spin"] == "0" for at, r in acks)
    _, native = one("kd_native stats")
    assert native == {"started": "1", "completed": "1", "unlocks": "2"}
    _, mutex = one("kd_mutex stats")
    assert all(mutex[k] == "1" for k in ("jit_success", "jit_resume", "nested_queued", "nested_jit"))

    peer_at, peer = one("kd_shared peer")
    assert held[1][0] < peer_at < done[10]
    assert peer["task"] == roles[10][1]["task"]
    assert peer["self"] == peer["owner"] == roles[10][1]["self"]
    assert peer["lock"] == inner and peer["comm"] == "kd_native"
    records = rows("kd_shared record")
    assert len(records) == 2 and {r["lane"] for _, r in records} == {"0", "1"}
    sequences = {}
    for at, row in records:
        lane = int(row["lane"])
        assert at > max(done.values()) and row["owner"] == "0"
        assert row["lock"] == (outer0, outer1)[lane] and row["visits"] == "12005"
        assert row["before"] == row["held"] == row["after"] == "12002"
        value, token = 0, 0x12340001 + lane * 0x101
        for _ in range(12002):
            value = ((value + token) & ((1 << 64) - 1)) ^ (token << 1)
        assert int(row["value"], 16) == value
        sequences[lane] = int(row["sequence"])
    assert sequences[0] == 24003
    assert {sequences[1], int(peer["sequence"])} == {24004, 24005}
    _, stats = one("kd_shared stats")
    assert stats == {"claimed": "4ff", "observed": "1", "peer_sequence": peer["sequence"],
                     "owner": "0", "failures": "0"}
    return {"roles": 9, "jit_bodies": 2, "native_frames": 1, "owner_acks": 2,
            "b_sequence": 24005, "peer_sequence": int(peer["sequence"])}


def wait_ready(artifact, timeout=30, lock_kind=2):
    """A generated file can precede device upload. Wait on the published entry."""
    artifact = Path(artifact)
    rip = int(artifact.parent.parent.name, 16)
    tgid = int(artifact.parent.name)
    assert ctypes.sizeof(Entry) == 64 and Entry.rip.offset == 16
    deadline = time.monotonic() + timeout
    while True:
        found = [
            entry for entry in entries() if entry.rip == rip and entry.tgid == tgid
        ]
        assert len(found) <= 1, "ambiguous JIT registration"
        if found:
            entry = found[0]
            assert entry.lock_kind == lock_kind and entry.code, (
                "invalid lock registration"
            )
            assert entry.status in (-1, 0), (
                f"unexpected pre-entry status {entry.status}"
            )
            if entry.status == 0:
                return {
                    "entry": hex(rip),
                    "tgid": tgid,
                    "pid": entry.pid,
                    "status": entry.status,
                    "code": hex(entry.code),
                    "observed_ns": time.monotonic_ns(),
                }
        assert time.monotonic() < deadline, "kernel JIT publication timed out"
        time.sleep(0.01)


def validate_call_quota(text, before, publication, after, assembly, statuses):
    """Join CALL packets, original callers and ACKs, not just a quota warning.

    The ordinary mode-5 phase must still finish through JIT. Only the final
    five-caller phase uses 17 clock services followed by native scalar work;
    normal JIT returns from both a clock and the scalar service. No callee
    learning or entry replay is allowed. Register/stack rejection is covered by
    production units; these observations do not certify arbitrary instructions
    or flags.
    """
    assert before and text.startswith(before), "missing pre-quota log prefix"
    assert "reason=CALL_LIMIT_NATIVE" not in before
    assert "kd_native begin:" not in before
    exits = list(csv.reader(io.StringIO(statuses), delimiter="\t"))
    assert len(exits) == 2 and dict(exits) == {"holder": "0", "waiters": "0"}
    assert type(publication["status"]) is int and publication["status"] == 0
    assert int(publication["entry"], 16) and int(publication["code"], 16)
    for key in ("entry", "tgid", "pid", "status", "code"):
        assert after[key] == publication[key], (key, publication, after)
    assert after["observed_ns"] > publication["observed_ns"]
    entry = int(publication["entry"], 16)
    targets = re.findall(
        r"/\* KD_HOSTCALL id=\d+ symbol=ktime_get(?:_ns)? \*/\nloc_([0-9a-f]+):",
        assembly,
    )
    assert len(targets) == 1, "expected one typed clock service"
    scalar = re.findall(
        r"/\* KD_HOSTCALL id=3 symbol=int_sqrt \*/\nloc_([0-9a-f]+):", assembly
    )
    assert len(scalar) == 1 and scalar[0] != targets[0], "missing distinct scalar service"

    def rows(tag, separator=": "):
        return [
            (m.start(), dict(re.findall(r"(\w+)=([-\w]+)", m[1])))
            for m in re.finditer(re.escape(tag + separator) + r"([^\n]+)", text)
        ]

    def one(tag):
        found = rows(tag)
        assert len(found) == 1, (tag, found)
        return found[0][1]

    quota = rows("reason=CALL_LIMIT_NATIVE", " ")
    count = len(quota)
    assert 0 < count <= 5
    begins = rows("kd_native begin")
    acks = rows("kd_native ack")
    completed = rows("kd_native complete")
    done = rows("kd_hostcall quota done")
    assert len(begins) == len(acks) == len(completed) == count
    assert len(done) == 5 and len({row["task"] for _, row in done}) == 5
    assert len({row["task"] for _, row in quota}) == count
    for at, row in done:
        assert at >= len(before) and int(row["task"]) > 0
        assert row["repeats"] == "17" and row["cpu"] in ("0", "1", "2", "3", "4")
        assert row["preempt"] == row["irq"] == "0"

    def task_row(found, task):
        matched = [(at, row) for at, row in found if row["task"] == task]
        assert len(matched) == 1, (task, matched)
        return matched[0]

    locks = set()
    for at, row in quota:
        assert at >= len(before) and row["hostcall"] == "1"
        assert int(row["entry"], 16) == entry
        assert int(row["ip"], 16) == int(targets[0], 16)
        assert int(row["sp"], 16) and int(row["return"], 16)
        assert f"loc_{int(row['return'], 16):x}:" in assembly
        lock = int(row["lock"], 16)
        assert lock
        locks.add(lock)
        begin_at, begin = task_row(begins, row["task"])
        ack_at, ack = task_row(acks, row["task"])
        complete_at, complete = task_row(completed, row["task"])
        done_at, _ = task_row(done, row["task"])
        assert at < begin_at < complete_at < ack_at < done_at
        for key in ("entry", "ip", "sp"):
            assert int(begin[key], 16) == int(row[key], 16)
        assert int(begin["outer"], 16) == lock
        assert begin["held"] == begin["remaining"] == begin["mutex"] == "1"
        assert begin["outer_released"] == "0"
        assert int(ack["lock"], 16) == int(complete["outer"], 16) == lock
        assert ack["mutex"] == complete["mutex"] == "1"
        assert ack["last_spin"] == "0"
    assert len(locks) == 1
    native = one("kd_native stats")
    assert native == dict.fromkeys(("started", "completed", "unlocks"), str(count))
    mutex = one("kd_mutex stats")
    normal = int(mutex["jit_success"])
    assert normal >= 2 and int(mutex["jit_resume"]) == normal
    services = one("kd_hostcall stats")
    assert services == {
        "exits": str(2 * normal + 17 * count),
        "executed": str(2 * normal + 16 * count),
        "resumed": str(2 * normal + 16 * count),
        "rejected": "0",
        "failed": "0",
        "limit": str(count),
    }
    bodies = rows("JIT body witness")
    assert len(bodies) == normal + count
    assert sum(at < len(before) for at, _ in bodies) == normal
    for _, body in bodies:
        assert int(body["entry"], 16) == entry
        assert int(body["lock"], 16) in locks and body["body"] == "1"
    return {
        "normal_jit": normal,
        "quota_native": count,
        "quota_callers": len(done),
        "jit_bodies": len(bodies),
        "hostcall_executed": int(services["executed"]),
        "hostcall_resumed": int(services["resumed"]),
        "pending_callee": hex(int(targets[0], 16)),
    }


def validate(text, identities, probe_ip):
    def rows(label):
        return [
            (match.start(), dict(re.findall(r"(\w+)=(-?\w+)", match[1])))
            for match in re.finditer(re.escape(label) + r": ([^\n]*)", text)
        ]

    def one(label):
        found = rows(label)
        assert len(found) == 1, (label, found)
        return found[0]

    def expect(row, **values):
        assert all(row.get(key) == str(value) for key, value in values.items()), (
            row,
            values,
        )

    probe = identities["probe"]
    race = identities.get("race", False)
    handoff = identities.get("handoff", False)
    head = probe & 1
    borrowed_at, borrowed = one("kd_signal borrowed")
    waiter = int(borrowed["waiter"])
    owner, lock = borrowed["owner"], borrowed["lock"]
    assert int(owner, 16) and owner != borrowed["task"]
    assert int(borrowed["owner_pid"]) in identities["owner_tasks"]
    assert waiter in identities["waiter_tasks"]
    assert int(borrowed["owner_pid"]) != waiter
    begin_at, begin = one("kd_native begin")
    expect(begin, task=waiter, outer=lock, held=1, mutex=1, ip=probe_ip)
    ack_at, ack = one("kd_native ack")
    expect(ack, task=waiter, lock=lock, mutex=1, last_spin=0)
    _, native = one("kd_native stats")
    expect(native, started=1, completed=1, unlocks=1)

    arrivals = rows("kd_signal arrive")
    results = rows("kd_signal result")
    assert len(arrivals) == len(results) == 2
    result_by_role = {}
    candidate_acquired = 0
    for _, row in arrivals:
        role = int(row["role"])
        expect(row, task=identities["native_pids"][role], comm=identities["comm"])
    assert sorted(int(row["role"]) for _, row in arrivals) == [0, 1]
    for position, row in results:
        role = int(row["role"])
        assert role not in result_by_role
        acquired = role == 1 or (race and row["ret"] == "0")
        expect(
            row,
            task=identities["native_pids"][role],
            ret=0 if acquired else -4,
            entered=int(acquired),
            unlocked=int(acquired),
        )
        result_by_role[role] = position
        if role == 0:
            candidate_acquired = int(acquired)
        if race:
            assert int(row["ns"]) > 0
            assert row["pending"] in ("0", "1") and row["fatal"] in ("0", "1")
            if acquired:
                assert int(row["self"], 16) and row["owner"] == row["self"]
            else:
                expect(row, pending=1, fatal=int(probe >= 3))

    queues = rows("kd_signal queue")
    assert len(queues) == (2 if race else 3)
    positions = [(1, 0, -1), (2, 0, 1)] if head else [(1, -1, 0), (2, 1, 0)]
    if not race:
        positions.append((1, -1, 0))
    for (_, row), (count, cancel, survivor) in zip(queues, positions):
        expect(
            row,
            count=count,
            cancel=cancel,
            survivor=survivor,
            owner=owner,
            waiter=waiter,
        )
    assert begin_at < borrowed_at < queues[0][0] < queues[1][0]
    if race:
        assert not rows("kd_signal cancelled")
        ready_at, ready = one("kd_signal ready")
        expect(ready, waiter=waiter, owner=owner, handoff=int(handoff))
        gate_at, gate = one("kd_signal gate")
        expect(gate, task=borrowed["owner_pid"], owner=owner, queued=2)
        assert int(gate["word"], 16) & ~7 == int(owner, 16)
        unlocks = rows("kd_signal unlock")
        assert len(unlocks) == 2
        unlock_at, before = unlocks[0]
        done_at, after = unlocks[1]
        expect(before, done=0, task=borrowed["owner_pid"], owner=owner)
        expect(after, done=1, task=borrowed["owner_pid"])
        assert int(before["word"], 16) & ~7 == int(owner, 16)
        assert int(before["queued"]) in (1, 2)
        assert queues[1][0] < ready_at < gate_at < unlock_at < done_at
        assert int(before["ns"]) < int(after["ns"])
        handoffs = rows("kd_signal handoff")
        assert len(handoffs) == int(handoff)
        if handoff:
            at, row = handoffs[0]
            expect(
                row,
                first=identities["native_pids"][0 if head else 1],
                owner=owner,
                queued=2,
            )
            assert int(row["word"], 16) & ~7 == int(owner, 16)
            assert all(int(r["word"], 16) & 2 for r in (row, gate, before))
            assert queues[1][0] < at < ready_at
        trigger = identities["trigger"]
        for name in ("signal", "release"):
            assert 0 < trigger[name]["before_ns"] <= trigger[name]["after_ns"]
        assert trigger["signal"]["pid"] == identities["native_pids"][0]
        assert trigger["signal"]["signum"] == (9 if probe >= 3 else 10)
        assert trigger["release"]["written"] == 2
        assert trigger["release"]["before_ns"] <= int(before["ns"])
        for _, row in results:
            assert int(row["ns"]) >= (
                int(before["ns"])
                if row["ret"] == "0"
                else trigger["signal"]["before_ns"]
            )
        expected = identities["expect"]
        assert expected in ("either", "acquired", "cancelled")
        assert expected == "either" or candidate_acquired == (expected == "acquired")
        for name in ("holder", "owner", "waiter", "tail", "native-0", "native-1"):
            assert identities["exitcodes"][name] == (
                -9 if name == "native-0" and probe >= 3 else 0
            )
    else:
        cancelled_at, cancelled = one("kd_signal cancelled")
        expect(
            cancelled,
            cancel=identities["native_pids"][0],
            waiter=waiter,
            owner=owner,
            ret=-4,
            entered=0,
            unlocked=0,
        )
        assert queues[1][0] < result_by_role[0] < queues[2][0] < cancelled_at < ack_at
        assert cancelled_at < result_by_role[1]
    nonfatal = rows("kd_signal nonfatal")
    assert len(nonfatal) == (1 if probe >= 3 else 0)
    if nonfatal:
        position, row = nonfatal[0]
        expect(
            row,
            cancel=identities["native_pids"][0],
            pending=1,
            fatal=0,
            queued=2,
            owner=owner,
        )
        assert int(row["checks"]) > 1
        assert queues[1][0] < position < result_by_role[0]
    _, stats = one("kd_signal stats")
    expect(
        stats,
        probe=probe,
        phase=9 if race else 6,
        failures=0,
        owner=0,
        word=0,
        queued=0,
    )
    assert int(stats["nonfatal"]) == (int(nonfatal[0][1]["checks"]) if nonfatal else 0)
    return candidate_acquired


def trigger_race(
    pid,
    signum,
    cpus,
    offset_us,
    *,
    release_parameter="mutex_signal_release",
    pidfd=None,
):
    """Race two real syscalls; their recorded windows are not linearization points."""
    # Share the same trigger for native peers and the progressed original waiter.
    # Restrict the destination to these test gates, never an arbitrary sysfs path.
    assert release_parameter in ("mutex_signal_release", "native_waiter_release")
    barrier = threading.Barrier(3, timeout=5)

    def worker(name, cpu, delay, fd):
        os.sched_setaffinity(0, {cpu})
        barrier.wait()
        if delay:
            time.sleep(delay / 1_000_000)
        result = {"cpu": cpu, "before_ns": time.monotonic_ns()}
        if name == "signal":
            if pidfd is None:
                os.kill(pid, signum)
            else:
                signal.pidfd_send_signal(pidfd, signum, None, 0)
                result["pidfd"] = 1
            result.update(pid=pid, signum=int(signum))
        else:
            result["written"] = os.write(fd, b"1\n")
        result["after_ns"] = time.monotonic_ns()
        return result

    with (
        (PARAMS / release_parameter).open("wb", buffering=0) as release,
        concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = {
            "signal": pool.submit(worker, "signal", cpus[0], max(0, offset_us), None),
            "release": pool.submit(
                worker, "release", cpus[2], max(0, -offset_us), release.fileno()
            ),
        }
        barrier.wait()
        return {name: future.result(timeout=5) for name, future in futures.items()}


def run(args):
    cpus = [int(cpu) for cpu in args.cpus.split(",")]
    assert len(cpus) == len(set(cpus)) == 6
    assert set(cpus) <= os.sched_getaffinity(0)
    out = Path(args.output)
    processes = {}
    native = {}
    assert -50000 <= args.race_us <= 50000
    assert not args.handoff or args.race
    identities = {
        "probe": args.probe,
        "comm": args.comm,
        "cpus": cpus,
        "race": args.race,
        "handoff": args.handoff,
        "race_us": args.race_us,
        "expect": args.expect,
        "exitcodes": {},
    }

    def interrupted(signum, frame):
        raise TimeoutError(f"signal {signum} interrupted signal-test controller")

    def phase(expected, name="mutex_signal_phase", at_least=False):
        deadline = time.monotonic() + 12
        while True:
            value = int((PARAMS / name).read_text())
            if value >= expected if at_least else value == expected:
                return
            assert time.monotonic() < deadline, f"phase {expected} timed out"
            assert all(p.poll() in (None, 0) for p in processes.values()), (
                "participant failed early"
            )
            time.sleep(0.01)

    def tasks(process):
        return [int(path.name) for path in Path(f"/proc/{process.pid}/task").iterdir()]

    signal.signal(signal.SIGTERM, interrupted)
    with contextlib.ExitStack() as stack:

        def start(name, cpu, command):
            log = stack.enter_context((out / f"{name}.log").open("w"))
            process = subprocess.Popen(
                ["taskset", "-c", str(cpu), *command],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            processes[name] = process
            return process

        try:
            (PARAMS / "mutex_signal_armed").write_text("1\n")
            start("holder", cpus[0], [args.bench, "1", "1", "1000", "1", "3"])
            phase(1)
            owner = start("owner", cpus[1], [args.bench, "1", "1", "1000", "1", "3"])
            phase(1, "mutex_signal_private")
            waiter = start("waiter", cpus[2], [args.bench, "1", "1", "1000", "1", "3"])
            phase(2, "mutex_signal_private")
            start("tail", cpus[3], [args.bench, "1", "1", "1000", "1", "3"])
            phase(2)
            identities["owner_tasks"] = tasks(owner)
            identities["waiter_tasks"] = tasks(waiter)
            first = 0 if args.probe & 1 else 1

            def client(role):
                command = [args.client, str(role), args.comm]
                if args.race and role == 0:
                    command.append("race-kill" if args.probe >= 3 else "race-int")
                return command

            native[first] = start(f"native-{first}", cpus[4], client(first))
            phase(3)
            native[1 - first] = start(f"native-{1 - first}", cpus[5], client(1 - first))
            phase(4, at_least=args.race)
            identities["native_pids"] = [native[i].pid for i in (0, 1)]
            if not args.race or args.probe >= 3:
                native[0].send_signal(signal.SIGUSR1)
            if args.probe >= 3:
                phase(5, at_least=args.race)
                if not args.race:
                    native[0].send_signal(signal.SIGKILL)
            if args.race:
                phase(7)
                identities["trigger"] = trigger_race(
                    native[0].pid,
                    signal.SIGKILL if args.probe >= 3 else signal.SIGUSR1,
                    cpus,
                    args.race_us,
                )
            for name, process in processes.items():
                expected = (
                    -signal.SIGKILL if name == "native-0" and args.probe >= 3 else 0
                )
                identities["exitcodes"][name] = process.wait(timeout=20)
                assert process.returncode == expected, (
                    name,
                    process.returncode,
                    expected,
                )
            assert int((PARAMS / "mutex_signal_phase").read_text()) == (
                9 if args.race else 6
            )
        finally:
            live = [p for p in processes.values() if p.poll() is None]
            if live:
                # Release fixture waits first; never unload code while an ioctl lives.
                (PARAMS / "mutex_signal_abort").write_text("1\n")
                for process in native.values():
                    if process.poll() is None:
                        process.kill()
                for process in live:
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        print(
                            f"LIVE participant pid={process.pid}; retain modules for VM recovery",
                            flush=True,
                        )
            identities["exitcodes"].update(
                {name: p.poll() for name, p in processes.items()}
            )
            (out / "identities.json").write_text(
                json.dumps(identities, indent=2) + "\n"
            )
    assert all(process.poll() is not None for process in processes.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ready = sub.add_parser("ready")
    ready.add_argument("--artifact", required=True)
    ready.add_argument("--output", required=True)
    nested = sub.add_parser("nested")
    nested.add_argument("--output", required=True)
    shared = sub.add_parser("shared")
    shared.add_argument("--output", required=True)
    quota = sub.add_parser("quota")
    quota.add_argument("--output", required=True)
    quota.add_argument("--artifact", required=True)
    controller = sub.add_parser("run")
    for name in ("bench", "client", "cpus", "output"):
        controller.add_argument(f"--{name}", required=True)
    controller.add_argument("--probe", type=int, choices=range(1, 5), required=True)
    controller.add_argument(
        "--comm", choices=("kd_native", "klock_test"), required=True
    )
    controller.add_argument("--race", action="store_true")
    controller.add_argument("--handoff", action="store_true")
    controller.add_argument("--race-us", type=int, default=0)
    controller.add_argument(
        "--expect", choices=("either", "cancelled", "acquired"), default="either"
    )
    oracle = sub.add_parser("validate")
    oracle.add_argument("--dmesg", required=True)
    oracle.add_argument("--identities", required=True)
    oracle.add_argument("--probe-ip", required=True)
    oracle.add_argument("--result", required=True)
    args = parser.parse_args()
    if args.command == "ready":
        result = wait_ready(args.artifact)
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
        print(
            f"[PASS] kernel JIT publication: entry={result['entry']} status=0 tgid={result['tgid']}"
        )
    elif args.command == "nested":
        out = Path(args.output)
        result = validate_nested_schedule(
            (out / "final.log").read_text(),
            json.loads((out / "published.json").read_text()),
            (out / "placements.tsv").read_text(),
            (out / "statuses.tsv").read_text(),
        )
        (out / "protocol.json").write_text(json.dumps(result, indent=2) + "\n")
        print("[PASS] seven mutex roles on two CPUs: real B wait, JIT completion")
    elif args.command == "shared":
        out = Path(args.output)
        result = validate_shared_b(
            (out / "final.log").read_text(),
            json.loads((out / "published.json").read_text()),
            (out / "placements.tsv").read_text(),
            (out / "statuses.tsv").read_text(),
            (out / "probe.txt").read_text().strip(),
        )
        (out / "protocol.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"[PASS] shared native B, retained owner and next A JIT: {result}")
    elif args.command == "run":
        run(args)
    elif args.command == "quota":
        out = Path(args.output)
        assert (out / "enabled.txt").read_text().strip() == "Y"
        assert (out / "disabled.txt").read_text().strip() == "N"
        result = validate_call_quota(
            (out / "final.log").read_text(),
            (out / "before-quota.log").read_text(),
            json.loads((out / "published.json").read_text()),
            json.loads((out / "published-after.json").read_text()),
            (Path(args.artifact) / "jit.S").read_text(),
            (out / "statuses.tsv").read_text(),
        )
        (out / "protocol.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"[PASS] typed service returns and quota CALL/owner-ACK: {result}")
    else:
        acquired = validate(
            Path(args.dmesg).read_text(),
            json.loads(Path(args.identities).read_text()),
            args.probe_ip,
        )
        Path(args.result).write_text(str(12006 + acquired) + "\n")
        print(
            f"[PASS] signal queue/owner/native-return/ACK witnesses; candidate acquired={acquired}"
        )


if __name__ == "__main__":
    main()
