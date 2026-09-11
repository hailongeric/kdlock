"""Check live frames with context/node refusal and injected task allocation failure."""

import argparse
import hashlib
import json
import os
import re
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

from mutex_shadow_protocol import validate_shadow_pool
from native_only_protocol import NATIVE_ONLY


def rows_in(text, label):
    return [
        (match.start(), dict(re.findall(r"(\w+)=(\w+)", match[1])))
        for match in re.finditer(re.escape(label) + r": ([^\n]*)", text)
    ]


def validate_renamed_waiters(text):
    """Require a native C unlock between renaming and the borrowed B/A ACKs.

    Matching only aggregate reroutes could hide restored target eligibility or
    a wrong-task unlock. These observations stay inside the original two frames.
    """
    renames = rows_in(text, "kd_resume rename")
    controls = rows_in(text, "kd_parallel routed native")
    arrivals = rows_in(text, "kd_parallel arrive")
    assert len(renames) == 4 and len(controls) == len(arrivals) == 2
    assert {r["lane"] for _, r in controls} == {"0", "1"}
    locks = {r[k] for _, r in arrivals for k in ("outer", "inner")}
    assert len({r["local"] for _, r in controls}) == 2
    assert not locks.intersection(r["local"] for _, r in controls)
    assert {r["task"] for _, r in renames} == {r["task"] for _, r in arrivals}
    for arrival_at, arrival in arrivals:
        task, lane = arrival["task"], arrival["lane"]
        (renamed_at, renamed), (restored_at, restored) = [
            item for item in renames if item[1]["task"] == task
        ]
        ((control_at, control),) = [
            item for item in controls if item[1]["lane"] == lane
        ]
        for row, old, new in (
            (renamed, "klock_test", "kd_renamed"),
            (restored, "kd_renamed", "klock_test"),
        ):
            assert row["old"] == old and row["new"] == new
            assert row["cpu"] == arrival["cpu"] and row["valid"] == "1"
            assert all(
                row[k] == "0"
                for k in ("preempt_before", "preempt_after", "irq_before", "irq_after")
            )
        assert all(
            control[k] == arrival[k]
            for k in ("task", "waiter", "owner", "outer", "inner")
        )
        assert control["local_owner"] == arrival["waiter"]
        assert control["owner"] != control["local_owner"]
        assert int(control["local"], 16) and control["after_owner"] == "0"
        assert control["acquired"] == control["released"] == control["valid"] == "1"
        assert control["comm"] == arrival["comm"] == "kd_renamed"
        ((begin_at, _),) = [
            item for item in rows_in(text, "kd_native begin") if item[1]["task"] == task
        ]
        ((resume_at, resume),) = [
            item
            for item in rows_in(text, "kd_parallel resume")
            if item[1]["task"] == task
        ]
        ((done_at, done),) = [
            item
            for item in rows_in(text, "kd_parallel done")
            if item[1]["task"] == task
        ]
        acks = [
            item for item in rows_in(text, "kd_native ack") if item[1]["task"] == task
        ]
        assert len(acks) == 2 and [r["lock"] for _, r in acks] == [
            arrival["inner"],
            arrival["outer"],
        ]
        assert resume["comm"] == done["comm"] == "kd_renamed"
        assert begin_at < renamed_at < arrival_at < resume_at
        assert max(at for at, _ in arrivals) < control_at < resume_at
        assert resume_at < acks[0][0] < acks[1][0] < done_at < restored_at
    assert max(at for at, _ in controls) < min(
        at for at, _ in rows_in(text, "kd_parallel peer try")
    )
    capacity = rows_in(text, "kd_parallel code record")
    assert not capacity or max(at for at, _ in controls) < min(at for at, _ in capacity)
    return {
        "renamed_waiters": 2,
        "native_acquisitions": 2,
        "native_unlocks": 2,
        "restored_after_acks": 2,
    }


def validate_native_peers(text, first):
    """Match actual Linux B waiters to two retained frames, not kdlock ACKs.

    Both peers cancel an interruptible wait, return to userspace and requeue
    before either old suffix. The first B peer must
    acquire/release while the other frame still retains B; the second follows
    that frame's later resume. Neither peer may become a generated executor.
    """

    def lanes(label):
        rows = rows_in(text, "kd_parallel " + label)
        result = {int(row["lane"]): (at, row) for at, row in rows}
        assert len(rows) == len(result) == 2 and set(result) == {0, 1}
        return result

    def attempts(label):
        rows = rows_in(text, "kd_parallel " + label)
        result = {(int(r["lane"]), int(r["attempt"])): (at, r) for at, r in rows}
        assert len(rows) == len(result) == 4
        assert set(result) == {(lane, attempt) for lane in (0, 1) for attempt in (1, 2)}
        return result

    arrivals, resumes, done, cancelled, acquired, released = (
        lanes(label)
        for label in (
            "arrive",
            "resume",
            "done",
            "peer cancelled",
            "peer acquired",
            "peer released",
        )
    )
    tries, queued = attempts("peer try"), attempts("peer queued")
    assert text.count("kd_parallel peer ") == 15
    tasks = {r["task"] for _, r in tries.values()}
    waiters = {r["waiter"] for _, r in tries.values()}
    assert len(tasks) == len(waiters) == 2
    assert tasks.isdisjoint(r["task"] for _, r in arrivals.values())
    assert waiters.isdisjoint(
        r[key] for _, r in arrivals.values() for key in ("waiter", "owner")
    )
    for lane in (0, 1):
        _, old = arrivals[lane]
        ta, tr = tries[lane, 1]
        qa, q = queued[lane, 1]
        ca, c = cancelled[lane]
        retry_at, retry = tries[lane, 2]
        requeue_at, requeue = queued[lane, 2]
        aa, a = acquired[lane]
        ra, r = released[lane]
        assert max(at for at, _ in arrivals.values()) < ta < qa < resumes[first][0]
        assert resumes[lane][0] < aa < ra and qa < aa
        assert all(tr[k] == old[v] for k, v in (("lock", "inner"), ("owner", "owner")))
        assert tr["comm"] == "kd_native" and tr["result"] == "0"
        assert int(tr["waiter"], 16) and int(tr["task"]) > 0
        assert all(q[k] == tr[k] for k in ("task", "waiter", "lock", "owner"))
        assert q["queued"] == q["matched"] == "1"
        assert (
            max(queued[i, 1][0] for i in (0, 1))
            < ca
            < retry_at
            < requeue_at
            < resumes[first][0]
        )
        assert all(c[k] == tr[k] for k in ("task", "waiter", "lock", "owner"))
        assert c["other_owner"] == arrivals[1 - lane][1]["owner"]
        assert {
            k: c[k]
            for k in (
                "error",
                "pending",
                "fatal",
                "queued",
                "matched",
                "cancelled",
                "acquired",
                "released",
                "valid",
            )
        } == {
            "error": "4",
            "pending": "1",
            "fatal": "0",
            "queued": "0",
            "matched": "0",
            "cancelled": "1",
            "acquired": "0",
            "released": "0",
            "valid": "1",
        }
        assert retry == dict(tr, attempt="2") and requeue == dict(q, attempt="2")
        assert all(a[k] == tr[k] for k in ("task", "waiter", "lock"))
        assert a["owner"] == a["waiter"]
        assert a["other"] == arrivals[1 - lane][1]["inner"]
        assert r["task"] == tr["task"] and r["value"] == a["value"]
        assert int(r["value"], 16) == ((0x700 + lane) * 33 + 17) ^ 0x5A5A
        assert r["acquired"] == r["released"] == "1"
        assert all(row["valid"] == "1" for row in (tr, q, a, r))
        if lane == first:
            assert a["other_owner"] == arrivals[1 - lane][1]["owner"]
            assert a["cross_try"] == "0" and ra < resumes[1 - lane][0]
        else:
            assert a["cross_try"] == "2"
            assert done[first][0] < aa and released[first][0] < aa
    ((_, stats),) = rows_in(text, "kd_parallel peer stats")
    assert stats == {
        "completed": "3",
        "acquired": "2",
        "released": "2",
        "cancelled": "2",
        "valid": "1",
    }
    assert not any(
        r["task"] in tasks
        for label in ("kd_native begin", "kd_native ack", "kd_native complete")
        for _, r in rows_in(text, label)
    )
    return {
        "failed_tries": 5,
        "queued": 4,
        "cancelled": 2,
        "acquired": 2,
        "released": 2,
    }


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
                entered = re.findall(
                    r"^parallel peer client enter: lane=(\d+) pid=(\d+)$",
                    (out / f"role-{lane}.log").read_text(),
                    re.MULTILINE,
                )
                assert len(entered) == 1 and int(entered[0][0]) == lane
                pid = int(entered[0][1])
                handle = os.pidfd_open(pid, 0)
                handles.append(handle)
                assert not select.select([handle], [], [], 0)[0], "peer already exited"
                proc = Path(f"/proc/{pid}")
                assert proc.joinpath("comm").read_text().strip() == "kd_native"
                assert proc.joinpath("exe").resolve() == client
                assert proc.joinpath("cmdline").read_bytes().split(b"\0")[:-1] == [
                    os.fsencode(client),
                    str(lane).encode(),
                    b"kd_native",
                    b"parallel-peer",
                ]
                status = dict(
                    line.split(":", 1)
                    for line in proc.joinpath("status").read_text().splitlines()
                )
                assert int(status["Tgid"]) == pid and int(status["Threads"]) == 1
                (queue,) = [r for r in queues if int(r["lane"]) == lane]
                assert int(queue["task"]) == pid and queue["valid"] == "1"
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


def validate_code_pool(text, evidence, published):
    """Require real capacity and queue fallback while both older frames live.

    Cold root registrations are not translations. Match immutable allocated
    block identities and the loaded mutex CALL sites without manufacturing a
    registry entry or crediting any filler record as generated execution.
    """
    sites = evidence["sites"]
    assert set(sites) == {str(i) for i in range(64)}
    assert len({site["entry"] for site in sites.values()}) == 64
    assert len({site["function"] for site in sites.values()}) == 64
    assert all(site["entry"] > site["function"] > 0 for site in sites.values())
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["module_sha256"])
    assert "JIT code block pool ready: 64/64" in text
    published = {p["entry"] for p in published}
    snapshots = evidence["snapshots"]
    assert set(snapshots) == {"prepare", "held", "filled", "drained"}
    registries = {}
    for phase, snapshot in snapshots.items():
        assert snapshot["source"] == {
            "state": 0,
            "modules": 1,
            "frames": 0 if phase == "prepare" else 2,
            "writers": 0,
        }
        registry = {e["entry"]: e for e in snapshot["registry"]}
        assert len(registry) == len(snapshot["registry"])
        assert len({e["code"] for e in registry.values()}) == len(registry)
        assert all(
            e["code"] and e["pid"] == 0 and e["kind"] == 2 for e in registry.values()
        )
        assert published <= registry.keys()
        for entry, row in registry.items():
            assert row["status"] == (
                int(phase != "prepare") if entry in published else -1
            )
        registries[phase] = registry
    before, held, full, final = (
        registries[p] for p in ("prepare", "held", "filled", "drained")
    )
    assert sites["0"]["entry"] in before and len(held) < 64
    assert len(full) == 64 and final == full
    assert {e: full[e] for e in held} == held
    assert {e: held[e] for e in before if e not in published} == {
        e: row for e, row in before.items() if e not in published
    }
    new_sites = [
        sites[str(i)]["entry"] for i in range(64) if sites[str(i)]["entry"] not in held
    ]
    assert set(full) - set(held) == set(new_sites[: 64 - len(held)])
    missing = {i for i, s in sites.items() if s["entry"] not in full}
    assert "63" in missing and missing
    for entry in published:
        assert full[entry]["code"] == before[entry]["code"]

    records = rows_in(text, "kd_parallel code record")
    filled = [(at, row) for at, row in records if row["role"] == "1"]
    queued = [(at, row) for at, row in records if row["role"] != "1"]
    assert len(records) == 67 and len(filled) == 64 and len(queued) == 3
    assert [int(row["site"]) for _, row in filled] == list(range(64))
    finishes = {int(row["role"]): (at, row) for at, row in queued}
    assert set(finishes) == {3, 4, 5}
    arrivals = rows_in(text, "kd_parallel arrive")
    resumes = rows_in(text, "kd_parallel resume")
    assert len(arrivals) == len(resumes) == 2
    start = max(at for at, _ in arrivals)
    end = min(at for at, _ in resumes)
    assert start < filled[0][0] < filled[-1][0] < min(at for at, _ in queued)
    assert max(at for at, _ in queued) < end
    outer_locks = {row[k] for _, row in arrivals for k in ("outer", "inner")}
    old_tasks = {row["task"] for _, row in arrivals}
    old_owners = {row[k] for _, row in arrivals for k in ("waiter", "owner")}
    for _, row in records:
        site, role = int(row["site"]), int(row["role"])
        assert int(row["fn"], 16) == sites[str(site)]["function"]
        assert (
            int(row["lock"], 16) == evidence["lock"] and row["lock"] not in outer_locks
        )
        assert row["task"] not in old_tasks
        assert row["owner"] == row["waiter"] and row["owner"] not in old_owners
        assert int(row["owner"], 16) and row["updates"] == row["valid"] == "1"
        assert (
            int(row["value"], 16) == ((site if role == 1 else role) + 7) * 33 + site + 1
        )
        assert role == 1 or site == 63
    assert len({row["task"] for _, row in filled}) == 1
    assert len({row["task"] for _, row in queued}) == 3
    ((queue_at, queue),) = rows_in(text, "kd_parallel code queued")
    assert int(queue["lock"], 16) == evidence["lock"] and int(queue["waiters"]) >= 3
    assert filled[-1][0] < queue_at < min(at for at, _ in queued)

    # This diagnostic has key/value fields after a space, not a second colon.
    exhausted = [
        (m.start(), dict(re.findall(r"(\w+)=(\w+)", m[1])))
        for m in re.finditer(r"kd_exe_add: code block pool exhausted ([^\n]*)", text)
    ]
    for site in missing:
        assert any(
            int(r["entry"], 16) == sites[site]["entry"]
            and r["kind"] == "2"
            and start < at < end
            for at, r in exhausted
        )
    refusal = [
        (at, row)
        for at, row in rows_in(text, "mutex JIT not ready")
        if int(row["entry"], 16) == sites["63"]["entry"]
    ]
    ((refusal_at, row),) = refusal
    assert row["task"] == finishes[3][1]["task"]
    assert row["waiter"] == finishes[4][1]["task"] and row["cpu"] == "9"
    assert int(row["lock"], 16) == evidence["lock"]
    assert queue_at < refusal_at < finishes[4][0]
    ((_, stats),) = rows_in(text, "kd_parallel code stats")
    assert stats == {
        "warm": "12000",
        "filled": "64",
        "claimed": "63",
        "updates": "12067",
        "lock": "0",
    }
    return {
        "allocated_blocks": 64,
        "cold_sites": 64,
        "missing_sites": len(missing),
        "native_queue_records": 3,
        "pre_wrapper_refusals": len(refusal),
    }


def capture_code_pool(phase, out):
    """Read-only guest observations; the workload alone creates registrations."""
    import hashlib

    from elftools.elf.elffile import ELFFile
    from native_only_protocol import entries

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "disassem"))
    import device_session as source

    path = out / "code-pool.json"
    evidence = {"snapshots": {}} if phase == "prepare" else json.loads(path.read_text())
    module = root / "klock_module/klock_module.ko"
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    symbols = {
        row[2]: int(row[0], 16)
        for line in Path("/proc/kallsyms").read_text().splitlines()
        if len(row := line.split()) == 4 and row[3] == "[klock_module]"
    }
    if phase == "prepare":
        sites = {}
        with module.open("rb") as stream:
            elf = ELFFile(stream)
            symtab = elf.get_section_by_name(".symtab")
            lock_calls = {}
            for section in elf.iter_sections():
                if section["sh_type"] != "SHT_RELA":
                    continue
                linked = elf.get_section(section["sh_link"])
                for relocation in section.iter_relocations():
                    if linked.get_symbol(relocation["r_info_sym"]).name == "mutex_lock":
                        assert relocation["r_info_type"] in (2, 4)
                        lock_calls.setdefault(section["sh_info"], []).append(
                            relocation["r_offset"]
                        )
            for i in range(64):
                name = f"kd_pool_site_{i}"
                (symbol,) = symtab.get_symbol_by_name(name)
                calls = []
                for address in lock_calls.get(symbol["st_shndx"], []):
                    offset = address - symbol["st_value"]
                    if 0 <= offset < symbol["st_size"]:
                        calls.append(symbols[name] + offset + 4)
                (entry,) = calls
                sites[str(i)] = {"function": symbols[name], "entry": entry}
    else:
        # Retain the parsed CALL offsets only with identical module bytes and
        # all loaded bases. Re-parsing ELF while owners wait needlessly uses
        # their bounded observation window; this is not caching test PASS.
        sites = evidence["sites"]
        assert all(
            s["function"] == symbols[f"kd_pool_site_{i}"] for i, s in sites.items()
        )
    identity = {
        "sites": sites,
        "lock": symbols["kd_pool_lock"],
        "module_sha256": digest,
    }
    if phase == "prepare":
        evidence.update(identity)
    else:
        assert all(evidence[key] == value for key, value in identity.items())
    fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    try:
        deadline = time.monotonic() + 6
        while True:
            state = source.info(fd)
            log = subprocess.check_output(["dmesg"], text=True, timeout=2)
            if phase != "held" or (
                state["frames"] == 2
                and len(rows_in(log, "kd_parallel arrive")) == 2
                # The renamed native C calls must finish while admission is
                # still OPEN; later retirement must not hide early misrouting.
                and len(rows_in(log, "kd_parallel routed native")) == 2
            ):
                break
            assert time.monotonic() < deadline, (
                "live frames/native routing not observed"
            )
            time.sleep(0.01)
        assert state == {
            "state": source.OPEN,
            "modules": 1,
            "frames": 0 if phase == "prepare" else 2,
            "writers": 0,
        }, state
        snapshot = [
            {
                "entry": e.rip,
                "code": e.code,
                "status": e.status,
                "kind": e.lock_kind,
                "pid": e.pid,
                "tgid": e.tgid,
            }
            for e in entries()
        ]
    finally:
        os.close(fd)
    assert phase not in evidence["snapshots"]
    evidence["snapshots"][phase] = {"source": state, "registry": snapshot}
    (out / f"code-pool-{phase}.log").write_text(log)
    if phase == "prepare":
        assert sites["0"]["entry"] in {e["entry"] for e in snapshot}, (
            "pool lock did not promote"
        )
    if phase in ("filled", "drained"):
        assert len(snapshot) == 64 and sites["63"]["entry"] not in {
            e["entry"] for e in snapshot
        }
    path.write_text(json.dumps(evidence, indent=2) + "\n")


def retired_reload(text, published, first, metadata):
    """Validate the native replacement incarnation before separating its logs.

    The old JIT oracle still sees the full provider counters. Only this fully
    checked source-module interval is excluded from its two old lane records.
    """
    begin, end = "kd_source reload: phase=begin", "kd_source reload: phase=end"
    assert text.count(begin) == text.count(end) == 1
    before, native = text.split(begin)
    native, after = native.split(end)
    assert metadata["completed"] and metadata["first"] == first
    symbols = metadata["before"]
    assert symbols == metadata["after"] and set(symbols) == {
        "kd_parallel_cs0",
        "kd_parallel_cs1",
        "kd_parallel_native",
        "parallel_lanes",
    }
    assert all(symbols.values()) and re.fullmatch(
        r"[0-9a-f]{64}", metadata["module_sha256"]
    )
    assert set(map(int, metadata["sites"])) == {p["entry"] for p in published}
    assert set(metadata["sites"].values()) == {"kd_parallel_cs0", "kd_parallel_cs1"}
    assert metadata["state"] == {"state": 2, "modules": 0, "frames": 0, "writers": 0}
    assert all(e["status"] == NATIVE_ONLY for e in metadata["registry"])
    registry = {e["entry"]: e for e in metadata["registry"]}
    assert all(registry[p["entry"]]["code"] == p["code"] for p in published)
    assert not re.search(
        r"JIT body witness:|kd_native (begin|ack|complete):|kd_resume rename:|kd_parallel (error|routed native|code [^:]+|peer [^:]+|shadow [^:]+):|BUG:|WARNING:|panic|soft lockup|unable to handle",
        native,
    )

    def lanes(label, source=native):
        rows = rows_in(source, label)
        assert len(rows) == 2, (label, rows)
        result = {int(row["lane"]): (at, row) for at, row in rows}
        assert set(result) == {0, 1}
        return result

    old = lanes("kd_parallel arrive", before)
    queued, arrive, resume, done = (
        lanes("kd_parallel " + name)
        for name in ("native queued", "arrive", "resume", "done")
    )
    assert int(old[0][1]["outer"], 16) == symbols["parallel_lanes"]
    assert len({row["waiter"] for _, row in arrive.values()}) == 2
    for lane in (0, 1):
        qa, q = queued[lane]
        aa, a = arrive[lane]
        ra, r = resume[lane]
        da, d = done[lane]
        assert int(q["waiters"]) >= 3 and qa < aa < ra < da
        assert a["owner"] == a["waiter"] and int(a["owner"], 16)
        assert int(a["cpu"]) == 4 * lane + 2 and a["valid"] == "1"
        assert all(a[key] == old[lane][1][key] for key in ("outer", "inner", "record"))
        assert all(a[key] == "1" for key in ("before", "held"))
        assert all(a[key] == "0" for key in ("called", "after"))
        prefix = (lane * 8 + 3) * 3 + 17
        assert int(a["value"], 16) == prefix
        assert all(r[key] == a[key] for key in ("task", "owner"))
        assert r["arrived"] == "3" and int(r["done"]) == (
            0 if lane == first else 1 << first
        )
        assert r["valid"] == "1"
        assert all(d[key] == a[key] for key in ("task", "waiter", "owner", "record"))
        assert all(
            d[key] == "1" for key in ("before", "held", "called", "after", "valid")
        )
        assert int(d["value"], 16) == prefix ^ 0x5A5A
    assert max(at for at, _ in arrive.values()) < resume[first][0]
    assert done[first][0] < resume[1 - first][0]
    records = rows_in(native, "kd_parallel retired record")
    keyed = {(int(row["lane"]), int(row["role"])): row for _, row in records}
    assert len(records) == len(keyed) == 6
    assert set(keyed) == {(lane, role) for lane in (0, 1) for role in (1, 2, 3)}
    assert len({row["task"] for row in keyed.values()}) == 6
    for (lane, role), row in keyed.items():
        assert int(row["owner"], 16) and row["owner"] == row["waiter"]
        assert all(row[k] == "1" for k in ("before", "held", "called", "after"))
        assert int(row["value"], 16) == ((lane * 8 + role + 1) * 3 + 17) ^ 0x5A5A
        if role == 2:
            assert all(
                row[k] == done[lane][1][k] for k in ("task", "waiter", "owner", "value")
            )
    for _, row in lanes("kd_parallel lane").values():
        assert {
            key: row[key] for key in ("sequence", "digest", "claimed", "a", "b")
        } == {"sequence": "3", "digest": "486", "claimed": "15", "a": "0", "b": "0"}
    ((_, stats),) = rows_in(native, "kd_parallel stats")
    assert stats == {
        "first": str(first),
        "shared_cpu": "0",
        "pressure": "0",
        "pressure_done": "0",
        "arrived": "3",
        "done": "3",
        "failures": "0",
    }
    return before + after


def validate(
    text,
    published,
    probe,
    first,
    shared_cpu=False,
    after=None,
    pressure=False,
    reload=None,
    code_pool=None,
    native_peers=False,
    shadow_pool=None,
):
    assert first in (0, 1)
    assert not shared_cpu or first == 1
    assert not pressure or shared_cpu
    native_count = 2 - int(shared_cpu)
    # Validate replacement first, then isolate its two native arrivals. A
    # combined capacity/lifetime gate still has only two old JIT frames.
    if reload is not None:
        assert not shared_cpu and not pressure
        text = retired_reload(text, published, first, reload)
    else:
        assert "kd_source reload:" not in text, "unvalidated source replacement"
    capacity = (
        validate_code_pool(text, code_pool, published)
        if code_pool is not None
        else None
    )
    if code_pool is not None:
        assert not shared_cpu and not pressure
    else:
        assert not rows_in(text, "kd_parallel code record"), (
            "unvalidated code-pool workload"
        )
    if native_peers:
        assert not shared_cpu and not pressure
        peers = validate_native_peers(text, first)
        routing = validate_renamed_waiters(text)
    else:
        assert "kd_parallel peer " not in text, "unvalidated native peers"
        assert not rows_in(text, "kd_parallel routed native")
        assert not rows_in(text, "kd_resume rename")
        peers = None
        routing = None
    if shadow_pool is not None:
        assert not shared_cpu and not pressure and code_pool is not None
        shadows = validate_shadow_pool(text, shadow_pool)
    else:
        assert "kd_parallel shadow " not in text, "unvalidated shadow-table pressure"
        shadows = None

    def rows(label):
        return rows_in(text, label)

    def expect(row, **values):
        assert all(row.get(key) == str(value) for key, value in values.items()), (
            row,
            values,
        )

    def number(row, key, base=10):
        assert key in row, (key, row)
        return int(row[key], base)

    def lanes(label):
        items = rows(label)
        assert len(items) == 2, (label, items)
        result = {number(row, "lane"): (at, row) for at, row in items}
        assert set(result) == {0, 1}, (label, result)
        return result

    assert len(published) == 2 and all(item["kind"] == 2 for item in published)
    entries = {item["entry"] for item in published}
    assert len(entries) == len({item["code"] for item in published}) == 2
    assert all(item["entry"] and item["code"] for item in published)
    assert probe and not rows("kd_parallel error")
    assert "reason=PENDING_LOCK_NATIVE" not in text
    assert not rows("kd_mutex outer release")
    arrivals, resumes, done = (
        lanes(f"kd_parallel {label}") for label in ("arrive", "resume", "done")
    )
    begins, bodies, acks, completes = (
        rows(label)
        for label in (
            "kd_native begin",
            "JIT body witness",
            "kd_native ack",
            "kd_native complete",
        )
    )
    assert len(begins) == len(bodies) == len(completes) == native_count
    assert len(acks) == 2 * native_count
    executed = {number(row, "entry", 16) for _, row in begins}
    assert len(executed) == native_count and executed <= entries
    if after is not None:
        # Cross-check the device state against the actual body/lock witnesses;
        # count-only checks could accept the wrong entry remaining NORMAL.
        assert len(after) == 2 and {item["entry"] for item in after} == entries
        before = {item["entry"]: item for item in published}
        for item in after:
            assert item["code"] == before[item["entry"]]["code"]
            assert item["status"] == int(item["entry"] in executed)
            if item["status"] == 1:
                assert item["target"] == probe
    # Distinct live tasks, physical owners, records and mutex pairs rule out a
    # second log referring to the first frame or a waiter unlocking as owner.
    assert len({row["task"] for _, row in arrivals.values()}) == 2
    assert len({row["record"] for _, row in arrivals.values()}) == 2
    assert len(
        {row[key] for _, row in arrivals.values() for key in ("waiter", "owner")}
    ) == 4 - int(shared_cpu)
    assert (
        len({row[key] for _, row in arrivals.values() for key in ("outer", "inner")})
        == 4
    )
    for lane, (arrival_at, arrival) in arrivals.items():
        task = arrival["task"]
        own_begins = [item for item in begins if item[1]["task"] == task]
        own_bodies = [item for item in bodies if item[1]["lock"] == arrival["outer"]]
        own_completes = [item for item in completes if item[1]["task"] == task]
        own_acks = [item for item in acks if item[1]["task"] == task]
        resume_at, resume = resumes[lane]
        done_at, final = done[lane]
        expect(
            arrival,
            before=1,
            held=1,
            called=0,
            after=0,
            cpu=1 if pressure and lane else lane * 4 + 2,
            valid=1,
        )
        for key in ("waiter", "owner", "outer", "inner", "record"):
            assert number(arrival, key, 16)
        prefix = (lane * 8 + 3) * 3 + 17
        assert number(arrival, "value", 16) == prefix
        expect(
            resume,
            task=task,
            owner=arrival["owner"],
            arrived=3,
            done=0 if lane == first else 1 << first,
            valid=1,
        )
        expect(
            final,
            task=task,
            waiter=arrival["waiter"],
            owner=arrival["owner"],
            record=arrival["record"],
            before=1,
            held=1,
            called=1,
            after=1,
            valid=1,
        )
        assert number(final, "value", 16) == prefix ^ 0x5A5A
        assert arrival_at < resume_at < done_at
        if shared_cpu and lane == 1:
            # This waiter never borrowed locks or entered generated code. Its
            # own native mutex owner, not a fabricated ACK, authorizes B/A.
            assert not (own_begins or own_bodies or own_completes or own_acks)
            assert arrival["owner"] == arrival["waiter"]
        else:
            ((begin_at, begin),) = own_begins
            ((body_at, body),) = own_bodies
            ((complete_at, complete),) = own_completes
            expect(
                begin,
                outer=arrival["outer"],
                ip=f"{probe:x}",
                held=2,
                mutex=1,
                cpu=lane * 4 + 1,
                outer_released=0,
                remaining=2,
            )
            assert number(begin, "sp", 16)
            expect(body, entry=begin["entry"], lock=begin["outer"], body=1)
            expect(complete, outer=arrival["outer"], mutex=1)
            assert arrival["owner"] != arrival["waiter"]
            assert len(own_acks) == 2
            for (_, ack), key in zip(own_acks, ("inner", "outer")):
                expect(ack, lock=arrival[key], mutex=1, last_spin=0)
            assert body_at < begin_at < arrival_at
            assert resume_at < own_acks[0][0] < complete_at < own_acks[1][0] < done_at
    # Arrival is inside the native callee while both A/B owners still wait.
    # The first final ACK must precede the second retained-owner observation.
    assert max(at for at, _ in arrivals.values()) < resumes[first][0]
    assert done[first][0] < resumes[1 - first][0] < done[1 - first][0]
    refused, contenders = rows("mutex JIT context busy"), rows("kd_parallel contender")
    if shared_cpu:
        ((refusal_at, refusal),) = refused
        ((contender_at, contender),) = contenders
        expect(
            refusal,
            task=contender["task"],
            waiter=arrivals[1][1]["task"],
            lock=arrivals[1][1]["outer"],
            cpu=1,
        )
        expect(contender, cpu=1, valid=1)
        assert {number(refusal, "entry", 16)} == entries - executed
        assert contender["task"] not in {r["task"] for _, r in arrivals.values()}
        assert number(contender, "owner", 16)
        assert contender["owner"] not in {
            row[key] for _, row in arrivals.values() for key in ("waiter", "owner")
        }
        assert arrivals[0][0] < refusal_at < contender_at < arrivals[1][0]
    else:
        assert not refused and not contenders

    fallbacks = rows("mutex node fallback")
    task_fallbacks = rows("mutex task fallback")
    pressure_done = rows("kd_parallel pressure done")
    if pressure:
        ((fallback_at, fallback),) = fallbacks
        ((task_at, task_fallback),) = task_fallbacks
        assert len(pressure_done) == 2
        finishes = {number(row, "role"): (at, row) for at, row in pressure_done}
        assert set(finishes) == {5, 6}
        expect(fallback, slots="f")
        assert arrivals[0][0] < fallback_at < task_at < refused[0][0]
        for role, refusal_at, refusal in (
            (5, fallback_at, fallback),
            (6, task_at, task_fallback),
        ):
            finish_at, final = finishes[role]
            expect(refusal, task=final["task"], lock=arrivals[1][1]["outer"], cpu=1)
            assert {number(refusal, "entry", 16)} == entries - executed
            expect(
                final,
                owner=final["waiter"],
                outer=arrivals[1][1]["outer"],
                inner=arrivals[1][1]["inner"],
                before=1,
                held=1,
                called=1,
                after=1,
                cpu=1,
                valid=1,
            )
            assert number(final, "value", 16) == ((9 + role) * 3 + 17) ^ 0x5A5A
            assert number(final, "record", 16) and number(final, "waiter", 16)
            assert final["record"] not in {r["record"] for _, r in arrivals.values()}
            assert final["task"] not in {
                *(r["task"] for _, r in arrivals.values()),
                contenders[0][1]["task"],
            }
            assert final["owner"] not in {
                *(r[k] for _, r in arrivals.values() for k in ("waiter", "owner")),
                contenders[0][1]["owner"],
            }
            # Both failed new requests must finish B/A themselves while the
            # old frame still retains A0/B0. A refusal log or aggregate final
            # count cannot substitute for the completed caller's exact record.
            assert refusal_at < finish_at < resumes[0][0]
        for key in ("task", "record", "owner", "waiter"):
            assert len({row[key] for _, row in pressure_done}) == 2
    else:
        assert not fallbacks and not task_fallbacks and not pressure_done
    for lane, (_, row) in lanes("kd_parallel lane").items():
        count = 12004 + 2 * int(pressure and lane == 1)
        digest = 0
        for sequence in range(1, count + 1):
            digest = (digest * 33 + sequence) & ((1 << 64) - 1)
        expect(row, sequence=count, claimed=111 if pressure and lane else 15, a=0, b=0)
        assert number(row, "digest", 16) == digest
    for label, expected in (
        (
            "kd_parallel stats",
            {
                "first": first,
                "shared_cpu": int(shared_cpu),
                "pressure": int(pressure),
                "pressure_done": 3 * int(pressure),
                "arrived": 3,
                "done": 3,
                "failures": 0,
            },
        ),
        (
            "kd_native stats",
            {
                "started": native_count,
                "completed": native_count,
                "unlocks": 2 * native_count,
            },
        ),
        (
            "kd_mutex stats",
            {"context_busy": int(shared_cpu), "node_overflow": int(pressure)},
        ),
        ("kd_mutex tasks", {"active_tasks": 0, "task_alloc_failure": int(pressure)}),
    ):
        (item,) = rows(label)
        expect(item[1], **expected)
    if shared_cpu:
        assert number(rows("kd_mutex stats")[0][1], "multi_slot") >= 1
    assert re.search(r"kd_exec invariant_failures=0\b", text)
    return {
        "first": first,
        "shared_cpu": bool(shared_cpu),
        "pressure": bool(pressure),
        "jit_bodies": native_count,
        "native_frames": native_count,
        "overlapping_native_frames": 0 if shared_cpu else 2,
        "context_refusals": int(shared_cpu),
        "native_node_fallbacks": int(pressure),
        "native_task_fallbacks": int(pressure),
        "owner_acks": 2 * native_count,
        "records": 6 + 2 * int(pressure),
        "transitions": 24008 + 2 * int(pressure),
        "reloaded_native_records": 6 if reload is not None else 0,
        "reloaded_native_transitions": 6 if reload is not None else 0,
        "code_pool": capacity,
        "native_peers": peers,
        "native_routing": routing,
        "shadow_pool": shadows,
    }


if __name__ == "__main__":
    if sys.argv[1:2] == ["native-peers"]:
        parser = argparse.ArgumentParser(description=signal_native_peers.__doc__)
        parser.add_argument("phase", choices=("signal", "requeued"))
        parser.add_argument("output", type=Path)
        args = parser.parse_args(sys.argv[2:])
        signal_native_peers(args.phase, args.output)
        raise SystemExit(0)
    if sys.argv[1:2] == ["code-pool"]:
        parser = argparse.ArgumentParser(description=capture_code_pool.__doc__)
        parser.add_argument("phase", choices=("prepare", "held", "filled", "drained"))
        parser.add_argument("output", type=Path)
        args = parser.parse_args(sys.argv[2:])
        capture_code_pool(args.phase, args.output)
        raise SystemExit(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("published", type=Path)
    parser.add_argument("probe", type=lambda value: int(value, 16))
    parser.add_argument("first", type=int, choices=(0, 1))
    parser.add_argument("--shared-cpu", type=int, choices=(0, 1), default=0)
    parser.add_argument("--pressure", type=int, choices=(0, 1), default=0)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--reload-metadata", type=Path)
    parser.add_argument("--code-pool-metadata", type=Path)
    parser.add_argument("--native-peers", type=Path)
    parser.add_argument("--shadow-pool-metadata", type=Path)
    args = parser.parse_args()
    result = validate(
        args.log.read_text(),
        json.loads(args.published.read_text()),
        args.probe,
        args.first,
        args.shared_cpu,
        json.loads(args.after.read_text()),
        args.pressure,
        json.loads(args.reload_metadata.read_text()) if args.reload_metadata else None,
        json.loads(args.code_pool_metadata.read_text())
        if args.code_pool_metadata
        else None,
        bool(args.native_peers),
        json.loads(args.shadow_pool_metadata.read_text())
        if args.shadow_pool_metadata
        else None,
    )
    if args.native_peers:
        result["native_peer_signals"] = validate_peer_signals(
            args.log.read_text(),
            json.loads((args.native_peers / "signal.json").read_text()),
            [(args.native_peers / f"role-{lane}.log").read_text() for lane in (0, 1)],
        )
    print(json.dumps(result))
