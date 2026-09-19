"""Multi-frame pools protocol; keep per-role identity and exactly-once checks.

Private implementation of mutex_parallel_protocol. Moving this code does not
change signal authorization, real owner/ACK ordering or evidence acceptance.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from native_only_protocol import NATIVE_ONLY
from mutex_parallel_events import rows_in

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

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "disassem"))
    import device_session as source

    path = out / "code-pool.json"
    evidence = {"snapshots": {}} if phase == "prepare" else json.loads(path.read_text())
    module = root / "workload_modules/lock_scenarios/klock_module.ko"
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
                    if linked.get_symbol(relocation["r_info_sym"]).name in {"mutex_lock", "kd_mutex_lock_clobber_v1"}:
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
