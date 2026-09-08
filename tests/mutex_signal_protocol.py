"""Control real ioctl processes and verify native mutex cancellation witnesses."""

import argparse
import concurrent.futures
import contextlib
import ctypes
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
    elif args.command == "run":
        run(args)
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
