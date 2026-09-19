"""Multi-frame signals protocol; keep per-role identity and exactly-once checks.

Private implementation of mutex_parallel_protocol. Moving this code does not
change signal authorization, real owner/ACK ordering or evidence acceptance.
"""
import hashlib
import json
import os
import re
import select
import signal
import subprocess
import time
from pathlib import Path
from mutex_parallel_events import rows_in

def verified_client(client, log_path, lane, flavor, pid):
    """Bind a recorded kernel task to a live, single-process test executable.

    Both controllers validate every participant before signalling any of them.
    The returned pidfd belongs to the caller; failed validation closes it here.
    """
    assert flavor in ("peer", "waiter") and pid > 0
    entered = re.findall(
        rf"^parallel {flavor} client enter: lane=(\d+) pid=(\d+)$",
        log_path.read_text(),
        re.MULTILINE,
    )
    assert entered == [(str(lane), str(pid))]
    handle = os.pidfd_open(pid, 0)
    try:
        assert not select.select([handle], [], [], 0)[0], "client already exited"
        proc = Path(f"/proc/{pid}")
        comm = "kd_native" if flavor == "peer" else "kd_renamed"
        argument = "kd_native" if flavor == "peer" else "klock_test"
        assert proc.joinpath("comm").read_text().strip() == comm
        assert proc.joinpath("exe").resolve() == client
        assert proc.joinpath("cmdline").read_bytes().split(b"\0")[:-1] == [
            os.fsencode(client),
            str(lane).encode(),
            argument.encode(),
            f"parallel-{flavor}".encode(),
        ]
        status = dict(
            line.split(":", 1)
            for line in proc.joinpath("status").read_text().splitlines()
        )
        assert int(status["Tgid"]) == pid and int(status["Threads"]) == 1
        return handle
    except BaseException:
        os.close(handle)
        raise


def signal_native_peers(phase, out):
    """Signal only identified single-process test clients through pidfds.

    No kernel task reference is added. Both real old frames must remain held
    across cancellation and the second wait-list observation.
    """
    from source_retirement import source

    expected = {"state": 0, "modules": 1, "frames": 2, "writers": 0}
    handles = []
    state_fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    path = out / "signal.json"
    try:
        state = source.info(state_fd)
        assert state == expected, state
        log = subprocess.check_output(["dmesg"], text=True, timeout=5)
        queues = [
            r
            for _, r in rows_in(log, "kd_parallel peer queued")
            if r["attempt"] == ("1" if phase == "signal" else "2")
        ]
        assert len(queues) == 2 and {int(r["lane"]) for r in queues} == {0, 1}
        if phase == "requeued":
            evidence = json.loads(path.read_text())
            assert {int(r["task"]) for r in queues} == {
                p["pid"] for p in evidence["peers"]
            }
            evidence["source"]["requeued"] = state
        else:
            client = (out.parent / "mutex-signal-client").resolve()
            evidence = {
                "source": {"before": state},
                "peers": [],
                "client_sha256": hashlib.sha256(client.read_bytes()).hexdigest(),
            }
            for lane in (0, 1):
                (queue,) = [r for r in queues if int(r["lane"]) == lane]
                assert queue["valid"] == "1"
                pid = int(queue["task"])
                handle = verified_client(
                    client, out / f"role-{lane}.log", lane, "peer", pid
                )
                handles.append(handle)
                evidence["peers"].append(
                    {"lane": lane, "pid": pid, "pidfd": True, "signum": signal.SIGUSR1}
                )
            for handle, peer in zip(handles, evidence["peers"]):
                peer["before_ns"] = time.monotonic_ns()
                signal.pidfd_send_signal(handle, signal.SIGUSR1, None, 0)
                peer["after_ns"] = time.monotonic_ns()
        path.write_text(json.dumps(evidence, indent=2) + "\n")
    finally:
        for handle in handles:
            os.close(handle)
        os.close(state_fd)


def validate_peer_signals(text, evidence, clients):
    """Userspace cancellation/explicit retry is a separate gate from kernel logs."""
    expected = {"state": 0, "modules": 1, "frames": 2, "writers": 0}
    assert evidence["source"] == {"before": expected, "requeued": expected}
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["client_sha256"])
    peers = evidence["peers"]
    assert len(peers) == 2 and {p["lane"] for p in peers} == {0, 1}
    cancelled = {
        int(r["lane"]): r for _, r in rows_in(text, "kd_parallel peer cancelled")
    }
    assert len(cancelled) == 2
    for peer in peers:
        lane, pid = peer["lane"], peer["pid"]
        assert peer["pidfd"] is True and peer["signum"] == signal.SIGUSR1
        assert 0 < peer["before_ns"] <= peer["after_ns"]
        assert int(cancelled[lane]["task"]) == pid
        lines = clients[lane].splitlines()
        assert lines == [
            f"parallel peer client enter: lane={lane} pid={pid}",
            f"parallel peer client cancelled: lane={lane} pid={pid} ret=-1 errno=4 signals=1",
            f"parallel peer client return: lane={lane} pid={pid} ret=0 errno=0 signals=1",
        ]
    return {"pidfd_signals": 2, "userspace_cancellations": 2, "explicit_retries": 2}


def waiter_hold(text, first, exited=False):
    """Check the bounded interval before signalling or releasing the survivor.

    This partial-log check cannot replace the final body/owner/record oracle.
    It ensures that task exit is observed between the two actual native frames.
    """
    arrivals = rows_in(text, "kd_parallel arrive")
    controls = rows_in(text, "kd_parallel routed native")
    assert len(arrivals) == len(controls) == 2
    lanes = {int(r["lane"]): r for _, r in arrivals}
    assert set(lanes) == {0, 1}
    assert {int(r["lane"]) for _, r in controls} == {0, 1}
    assert len({r["task"] for r in lanes.values()}) == 2
    for _, row in controls:
        old = lanes[int(row["lane"])]
        assert all(row[k] == old[k] for k in ("task", "waiter", "owner", "outer", "inner"))
        assert old["comm"] == row["comm"] == "kd_renamed"
        assert old["valid"] == row["valid"] == "1"
        assert row["acquired"] == row["released"] == "1"
        assert row["local_owner"] == old["waiter"] != old["owner"]
    resumes, done, acks, completes = (
        rows_in(text, label)
        for label in (
            "kd_parallel resume", "kd_parallel done", "kd_native ack",
            "kd_native complete",
        )
    )
    if not exited:
        assert not resumes and not done and not acks and not completes
    else:
        (resume_at, resume), = resumes
        (done_at, final), = done
        (complete_at, complete), = completes
        old = lanes[first]
        assert resume["lane"] == final["lane"] == str(first)
        assert resume["task"] == final["task"] == complete["task"] == old["task"]
        assert resume["owner"] == final["owner"] == old["owner"]
        assert resume["valid"] == final["valid"] == "1"
        assert resume["pending"] == resume["fatal"] == "1"
        assert len(acks) == 2
        assert [r["task"] for _, r in acks] == [old["task"]] * 2
        assert [r["lock"] for _, r in acks] == [old["inner"], old["outer"]]
        assert resume_at < acks[0][0] < complete_at < acks[1][0] < done_at
    assert not rows_in(text, "kd_parallel error")
    return lanes


def signal_original_waiters(out, first):
    """Keep pidfds across SIGKILL/exit and a surviving SIGUSR1 native frame.

    The shell closes source admission and releases the first fixture gate only
    after ready is published. On any failure release the second bounded gate;
    never cancel a delegated request or unlock a physical owner from Python.
    """
    from source_retirement import source

    params = Path("/sys/module/klock_module/parameters")
    handles = []
    fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    path = out / "waiter-signals.json"
    expected = {"state": 0, "modules": 1, "frames": 2, "writers": 0}
    try:
        assert first in (0, 1)
        assert (params / "mutex_parallel_source_hold").read_text().strip() == "Y"
        assert (params / "mutex_parallel_exit_hold").read_text().strip() == "Y"
        assert source.info(fd) == expected
        log = subprocess.check_output(["dmesg"], text=True, timeout=5)
        arrivals = waiter_hold(log, first)
        client = (out / "mutex-signal-client").resolve()
        evidence = {
            "first": first, "source": {"before": expected}, "waiters": [],
            "client_sha256": hashlib.sha256(client.read_bytes()).hexdigest(),
        }
        for lane in (0, 1):
            pid = int(arrivals[lane]["task"])
            handle = verified_client(
                client, out / f"role-{lane}-2.log", lane, "waiter", pid
            )
            handles.append(handle)
            evidence["waiters"].append({
                "lane": lane, "pid": pid, "pidfd": True,
                "signum": signal.SIGKILL if lane == first else signal.SIGUSR1,
            })
        assert source.info(fd) == expected
        for handle, waiter in zip(handles, evidence["waiters"]):
            waiter["before_ns"] = time.monotonic_ns()
            signal.pidfd_send_signal(handle, waiter["signum"], None, 0)
            waiter["after_ns"] = time.monotonic_ns()
        assert not select.select(handles, [], [], 0)[0], "waiter exited before release"
        path.write_text(json.dumps(evidence, indent=2) + "\n")
        (out / "waiter-signals.ready").touch()

        # Keep this exact pidfd open: an ACK, vanished /proc path or reused PID
        # alone cannot prove that the signalled original task has exited.
        assert select.select([handles[first]], [], [], 10)[0], "first waiter did not exit"
        deadline = time.monotonic() + 3
        after = {"state": 1, "modules": 1, "frames": 1, "writers": 1}
        while source.info(fd) != after:
            assert time.monotonic() < deadline, "first frame did not drain"
            time.sleep(0.01)
        assert not select.select([handles[1 - first]], [], [], 0)[0], "survivor exited"
        log = subprocess.check_output(["dmesg"], text=True, timeout=5)
        assert waiter_hold(log, first, exited=True) == arrivals
        observed = log.encode()
        evidence["source"]["after_exit"] = after
        evidence["after_exit"] = {
            "pidfd_exited": True, "survivor_alive": True,
            "observed_ns": time.monotonic_ns(), "log_bytes": len(observed),
            "log_sha256": hashlib.sha256(observed).hexdigest(),
        }
        evidence["complete"] = True
        path.write_text(json.dumps(evidence, indent=2) + "\n")
    finally:
        try:
            (params / "mutex_parallel_exit_hold").write_text("0\n")
        finally:
            for handle in handles:
                os.close(handle)
            os.close(fd)


def validate_waiter_signals(text, evidence, clients, statuses, first):
    """Join actual task exit, pending-signal packets and the final owner ACKs."""
    # The separately validated retired reload has native-only task identities.
    # Its observations must not stand in for either original JIT/native frame.
    text = text.split("kd_source reload: phase=begin", 1)[0]
    assert evidence["first"] == first and evidence["complete"] is True
    assert evidence["source"] == {
        "before": {"state": 0, "modules": 1, "frames": 2, "writers": 0},
        "after_exit": {"state": 1, "modules": 1, "frames": 1, "writers": 1},
    }
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["client_sha256"])
    observed = evidence["after_exit"]
    assert observed["pidfd_exited"] is True and observed["survivor_alive"] is True
    size = observed["log_bytes"]
    assert 0 < size < len(text.encode())
    prefix = text.encode()[:size]
    assert hashlib.sha256(prefix).hexdigest() == observed["log_sha256"]
    arrivals = waiter_hold(prefix.decode(), first, exited=True)
    waiters = evidence["waiters"]
    assert len(waiters) == 2 and {p["lane"] for p in waiters} == {0, 1}
    exits = [tuple(map(int, line.split())) for line in statuses.splitlines()]
    assert len(exits) == 8 and dict(exits) == {
        i: 137 if i == 4 + first else 0 for i in range(8)
    }
    for waiter in waiters:
        lane, pid = waiter["lane"], waiter["pid"]
        assert waiter["pidfd"] is True
        assert waiter["signum"] == (signal.SIGKILL if lane == first else signal.SIGUSR1)
        assert 0 < waiter["before_ns"] <= waiter["after_ns"] <= observed["observed_ns"]
        assert int(arrivals[lane]["task"]) == pid
        ((_, resume),) = [
            item for item in rows_in(text, "kd_parallel resume")
            if item[1]["task"] == str(pid)
        ]
        assert resume["pending"] == "1" and resume["fatal"] == str(int(lane == first))
        lines = [f"parallel waiter client enter: lane={lane} pid={pid}"]
        if lane != first:
            lines.append(
                f"parallel waiter client return: lane={lane} pid={pid} ret=0 errno=0 signals=1"
            )
        assert clients[lane].splitlines() == lines
    return {"pidfd_signals": 2, "fatal_exits": 1, "surviving_native_frames": 1,
            "nonfatal_returns": 1}
