"""Real gate-map exhaustion inside the existing spin ticket/native interval."""

import argparse
import errno
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from mutex_shadow_protocol import rows

COUNT = 1025
CAPACITY = 1024
PARAMETERS = Path("/sys/module/kdlock_km/parameters")
WORKLOAD = Path("/sys/module/klock_module/parameters")


def pending_calls(text):
    """WARN reason rows have a space separator and signed errno, not a colon."""
    return [
        (m.start(), dict(re.findall(r"(\w+)=(-?\w+)", m[1])))
        for m in re.finditer(r"reason=PENDING_LOCK_NATIVE ([^\n]*)", text)
    ]


def validate_progress(text, evidence, start, end, old_task):
    """Join a returned JIT prefix to genuine ENOMEM, native C and one A ACK.

    The older ticket frame must surround this whole request. Do not count the
    independent cold callers or an ordinary observer CALL miss as this proof.
    """
    progress = evidence["progress"]
    outer, entry, target, return_ip = (
        progress[key] for key in ("outer", "entry", "target", "return")
    )
    assert all(type(v) is int and v > 0 for v in (outer, entry, target, return_ip))
    assert entry != return_ip and entry != evidence["entry"]
    inner = evidence["base"] + (COUNT - 1) * evidence["stride"]
    callers = rows(text, "kd_gate progress caller")
    assert len(callers) == 6
    roles = {int(r["role"]): (at, r) for at, r in callers}
    assert set(roles) == set(range(3, 9))
    assert len({r["task"] for _, r in callers}) == 6
    assert len({r["self"] for _, r in callers}) == 6
    for role, (at, row) in roles.items():
        assert start < at < end and row["cpu"] == str(role + 10)
        assert row["pins"] == "0" and row["valid"] == "1"
        assert int(row["task"]) > 0 and int(row["self"], 16) > 0
        assert row["task"] != old_task
    pid = roles[6][1]["task"]

    def one(label, task=None):
        candidates = (
            pending_calls(text) if label == "reason=PENDING_LOCK_NATIVE"
            else rows(text, label)
        )
        found = [
            (at, r) for at, r in candidates
            if task is None or r["task"] == task
        ]
        assert len(found) == 1, (label, found)
        return found[0]

    ((body_at, body),) = [
        (at, r) for at, r in rows(text, "JIT body witness")
        if int(r["entry"], 16) == entry and int(r["lock"], 16) == outer
    ]
    assert body["body"] == "1"
    pending_at, pending = one("reason=PENDING_LOCK_NATIVE", pid)
    assert int(pending["entry"], 16) == entry
    assert int(pending["target"], 16) == target
    assert int(pending["return"], 16) == int(pending["staged_ip"], 16) == return_ip
    assert int(pending["staged_sp"], 16) == int(pending["sp"], 16) + 8
    assert int(pending["error"]) == -errno.ENOMEM
    assert pending["mutex"] == pending["outer_released"] == "0"
    begin_at, begin = one("kd_native begin", pid)
    assert all(begin[k] == "1" for k in ("held", "remaining"))
    assert begin["mutex"] == begin["outer_released"] == "0"
    assert int(begin["outer"], 16) == outer and int(begin["entry"], 16) == entry
    assert int(begin["ip"], 16) == target
    assert int(begin["sp"], 16) == int(pending["sp"], 16)
    executor_role = int(begin["cpu"]) - 10
    assert executor_role in (4, 5)
    executor = roles[executor_role][1]
    blocked_at, blocked = one("kd_gate progress blocked")
    acquired_at, acquired = one("kd_gate progress acquired", pid)
    prefix = (7 * 33 + 0x12340001 + 17) * 33 + 0x12340001
    for row in (blocked, acquired):
        assert int(row["outer"], 16) == outer and int(row["lock"], 16) == inner
        assert row["owner"] == executor["self"]
        assert row["before"] == "2" and row["inner"] == "0" and row["after"] == "1"
        assert int(row["value"], 16) == prefix and row["valid"] == "1"
    assert all(blocked[k] == roles[8][1][k] for k in ("task", "self", "cpu"))
    assert all(acquired[k] == roles[6][1][k] for k in ("task", "self", "cpu"))
    assert blocked["waiter"] == acquired["self"]
    assert blocked["pins"] == "1" and acquired["pins"] == "2"
    word = int(blocked["word"], 16)
    assert word & 0xFF == 1 and word & ~0xFF
    complete_at, complete = one("kd_native complete", pid)
    ack_at, ack = one("kd_native ack", pid)
    assert int(complete["outer"], 16) == int(ack["lock"], 16) == outer
    assert complete["mutex"] == ack["mutex"] == "0" and ack["last_spin"] == "1"
    assert start < body_at < pending_at < begin_at < blocked_at < acquired_at
    assert acquired_at < min(complete_at, ack_at) <= max(complete_at, ack_at) < end
    assert ack_at < roles[6][0] and complete_at < roles[executor_role][0]
    refusal = (executor["task"], f"{inner:x}", executor["cpu"])
    ((refusal_at, _),) = [
        (at, r) for at, r in rows(text, "kd_gate refusal")
        if (r["task"], r["lock"], r["cpu"]) == refusal
    ]
    assert body_at < refusal_at < pending_at
    ((_, stats),) = rows(text, "kd_gate progress stats")
    assert stats == {
        "before": "2",
        "inner": "1",
        "after": "2",
        "value": f"{(prefix ^ 0x24680002) + 17:x}",
        "direct": "3",
        "observed": "1",
        "phase": "2",
        "valid": "1",
    }
    assert len(pending_calls(text)) == 2
    assert {r["task"] for _, r in rows(text, "kd_native begin")} == {old_task, pid}
    ((_, native_stats),) = rows(text, "kd_native stats")
    assert native_stats == {"started": "2", "completed": "2", "unlocks": "2"}
    return refusal


def validate_gate_pool(text, evidence, statuses):
    """Keep map refusal, retained owners and native exclusion inseparable."""
    base, stride, entry = (evidence[key] for key in ("base", "stride", "entry"))
    assert all(type(value) is int and value > 0 for value in (base, stride, entry))
    assert evidence["count"] == COUNT
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["module_sha256"])
    assert statuses == "".join(f"{role}\t0\n" for role in range(9))
    ((_, layout),) = rows(text, "kd_gate layout")
    assert layout == {"base": f"{base:x}", "stride": str(stride), "count": str(COUNT)}
    addresses = {f"{base + i * stride:x}" for i in range(COUNT)}
    promoted = re.findall(r"kd_hotlock selftest promote: lock=([0-9a-f]+)", text)
    assert len([addr for addr in promoted if addr in addresses]) == COUNT
    assert addresses <= set(promoted)
    snapshots = evidence["snapshots"]
    assert set(snapshots) == {"prepare", "held", "filled", "progress", "drained"}
    publication = evidence["progress"]["publication"]
    assert publication["entry"] == evidence["progress"]["entry"]
    assert publication["status"] == 0 and publication["kind"] == 1
    assert publication["code"] > 0
    assert len(evidence["progress"]["artifacts"]) == 3
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        for item in evidence["progress"]["artifacts"]
    )
    for phase, snapshot in snapshots.items():
        assert snapshot["source"] == {
            "state": 0,
            "modules": 1,
            "frames": 0 if phase == "prepare" else 2 if phase == "progress" else 1,
            "writers": 0,
        }
        assert snapshot["phase"] == (0 if phase == "prepare" else 1)
        assert snapshot["progress_phase"] == (
            1 if phase == "progress" else 2 if phase == "drained" else 0
        )
        assert snapshot["publication"] == publication
        assert type(snapshot["allocated"]) is int
    before = snapshots["held"]["allocated"]
    assert 0 < snapshots["prepare"]["allocated"] <= before < CAPACITY
    assert (
        snapshots["filled"]["allocated"]
        == snapshots["progress"]["allocated"]
        == snapshots["drained"]["allocated"]
        == CAPACITY
    )
    ((start, held),) = rows(text, "kd_gate hold")
    ((end, resumed),) = rows(text, "kd_gate resume")
    assert held == resumed and held["valid"] == "1" and held["cpu"] == "1"
    assert int(held["a"], 16) and int(held["b"], 16) and held["a"] != held["b"]
    ((blocked_at, blocked),) = rows(text, "kd_pending spin blocked")
    ((acquired_at, acquired),) = rows(text, "kd_pending spin acquired")
    ((native_at, native),) = [
        (at, r) for at, r in rows(text, "kd_native begin")
        if r["task"] == blocked["task"]
    ]
    assert native["task"] == blocked["task"] == acquired["task"]
    assert native["mutex"] == "0" and native["held"] == "1"
    assert native_at < blocked_at < start < end < acquired_at
    records = rows(text, "kd_gate record")
    filled = [(at, row) for at, row in records if row["role"] == "0"]
    queued = [(at, row) for at, row in records if row["role"] != "0"]
    assert len(filled) == COUNT and len(queued) == 2
    assert [int(row["index"]) for _, row in filled] == list(range(COUNT))
    assert start < filled[0][0] < filled[-1][0] < min(at for at, _ in queued)
    assert max(at for at, _ in queued) < end
    new = CAPACITY - before
    expected_refusals = []
    for _, row in records:
        index, role, updates = (int(row[key]) for key in ("index", "role", "updates"))
        assert 0 <= index < COUNT and 0 <= role <= 2
        assert row["lock"] == f"{base + index * stride:x}"
        assert row["valid"] == "1" and row["pins"] == "0"
        assert int(row["task"]) > 0 and row["task"] not in {
            native["task"],
            held["task"],
        }
        assert row["cpu"] == str(9 + role)
        assert row["registered"] == str(int(not role and index < new))
        assert updates == (role + 1 if role else 1)
        if role:
            assert index == COUNT - 1
        value = index + 7
        for _ in range(updates):
            value = value * 33 + index + 1
        assert int(row["value"], 16) == value
        if (not role and index >= new) or role == 2:
            expected_refusals.append((row["task"], row["lock"], row["cpu"]))
    assert len({row["task"] for _, row in filled}) == 1
    roles = {int(row["role"]): row for _, row in queued}
    assert set(roles) == {1, 2}
    assert len({filled[0][1]["task"], roles[1]["task"], roles[2]["task"]}) == 3
    ((queue_at, queue),) = rows(text, "kd_gate queued")
    assert all(queue[key] == roles[1][key] for key in ("task", "cpu", "lock"))
    word = int(queue["value"], 16)
    assert word & 0xFF in (1, 3) and word & ~0xFF
    assert filled[-1][0] < queue_at < min(at for at, _ in queued)
    expected_refusals.append(
        validate_progress(text, evidence, start, end, native["task"])
    )
    refused = rows(text, "kd_gate refusal")
    assert sorted((r["task"], r["lock"], r["cpu"]) for _, r in refused) == sorted(
        expected_refusals
    )
    assert all(start < at < end for at, _ in refused)
    # This independent cold site is deliberately not translated. Existing
    # returned body/packet/ACK oracles still validate the original JIT waiter.
    assert not any(
        int(r["entry"], 16) == entry for _, r in rows(text, "JIT body witness")
    )
    ((_, stats),) = rows(text, "kd_gate stats")
    assert stats == {"locks": str(COUNT), "roles": "1ff", "phase": "2", "valid": "1"}
    return {
        "allocated_gates": CAPACITY,
        "previous_gates": before,
        "new_gates": new,
        "filler_records": COUNT,
        "native_queue_records": 2,
        "target_refusals": len(refused),
        "retained_frames": 1,
        "progressed_gate_refusals": 1,
        "overlapping_frames": 2,
    }


def spin_returns(elf, symbols, name):
    """Resolve only actual E8 source CALLs, never a guessed compiler offset."""
    table = elf.get_section_by_name(".symtab")
    (function,) = table.get_symbol_by_name(name)
    data = elf.get_section(function["st_shndx"]).data()
    calls = []
    for section in elf.iter_sections():
        if (
            section["sh_type"] != "SHT_RELA"
            or section["sh_info"] != function["st_shndx"]
        ):
            continue
        linked = elf.get_section(section["sh_link"])
        for relocation in section.iter_relocations():
            offset = relocation["r_offset"] - function["st_value"]
            if (
                0 < offset < function["st_size"]
                and linked.get_symbol(relocation["r_info_sym"]).name == "_raw_spin_lock"
            ):
                assert relocation["r_info_type"] in (2, 4)
                assert data[relocation["r_offset"] - 1] == 0xE8
                calls.append(symbols[name] + offset + 4)
    return sorted(calls)


def capture(phase, out):
    """Promote only in preparation; later snapshots do not alter map/owners."""
    from elftools.elf.elffile import ELFFile

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "disassem"))
    import device_session as source
    from native_only_protocol import entries

    module = root / "workload_modules/lock_scenarios/klock_module.ko"
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    path = out / "gate-pool.json"
    symbols = {
        row[2]: int(row[0], 16)
        for line in Path("/proc/kallsyms").read_text().splitlines()
        if len(row := line.split()) == 4 and row[3] == "[klock_module]"
    }
    if phase == "promote-root":
        (PARAMETERS / "spin_selftest_promote").write_text(
            hex(symbols["kd_gate_progress_outer"]) + "\n"
        )
        return
    if phase == "prepare":
        with module.open("rb") as stream:
            elf = ELFFile(stream)
            table = elf.get_section_by_name(".symtab")
            (array,) = table.get_symbol_by_name("kd_gate_capacity_locks")
            assert array["st_size"] % COUNT == 0
            (entry,) = spin_returns(elf, symbols, "kd_gate_capacity_acquire")
            progress_entry, return_ip = spin_returns(
                elf, symbols, "kd_gate_progress_root"
            )
        (target,) = [
            int(fields[0], 16)
            for line in Path("/proc/kallsyms").read_text().splitlines()
            if len(fields := line.split()) == 3 and fields[2] == "_raw_spin_lock"
        ]
        evidence = {
            "base": symbols["kd_gate_capacity_locks"],
            "stride": array["st_size"] // COUNT,
            "count": COUNT,
            "entry": entry,
            "module_sha256": digest,
            "progress": {
                "outer": symbols["kd_gate_progress_outer"],
                "entry": progress_entry,
                "return": return_ip,
                "target": target,
            },
            "snapshots": {},
        }
        for i in range(COUNT):
            (PARAMETERS / "spin_selftest_promote").write_text(
                hex(evidence["base"] + i * evidence["stride"]) + "\n"
            )
    else:
        evidence = json.loads(path.read_text())
        assert evidence["base"] == symbols["kd_gate_capacity_locks"]
        assert evidence["module_sha256"] == digest
    if phase in ("held", "progress"):
        parameter = (
            "native_gate_phase" if phase == "held" else "native_gate_progress_phase"
        )
        deadline = time.monotonic() + 10
        while int((WORKLOAD / parameter).read_text()) != 1:
            assert time.monotonic() < deadline, "native interval not reached"
            time.sleep(0.02)
    fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    try:
        state = source.info(fd)
    finally:
        os.close(fd)
    assert state == {
        "state": source.OPEN,
        "modules": 1,
        "frames": 0 if phase == "prepare" else 2 if phase == "progress" else 1,
        "writers": 0,
    }
    allocated = int((PARAMETERS / "spin_selftest_gate_count").read_text())
    current_phase = int((WORKLOAD / "native_gate_phase").read_text())
    assert current_phase == (0 if phase == "prepare" else 1)
    progress_phase = int((WORKLOAD / "native_gate_progress_phase").read_text())
    assert progress_phase == (
        1 if phase == "progress" else 2 if phase == "drained" else 0
    )
    progress = evidence["progress"]
    (published,) = [e for e in entries() if e.rip == progress["entry"]]
    publication = dict(
        entry=published.rip, status=published.status, code=published.code,
        kind=published.lock_kind, pid=published.pid, tgid=published.tgid,
    )
    assert (
        publication["status"] == 0
        and publication["kind"] == 1
        and publication["code"]
    )
    if phase == "prepare":
        progress["publication"] = publication
        (assembly,) = root.glob(f"daemon/0x{progress['entry']:x}/*/asm")
        progress["artifacts"] = [
            dict(
                path=str((assembly / name).relative_to(root)),
                sha256=hashlib.sha256((assembly / name).read_bytes()).hexdigest(),
            )
            for name in ("jit.S", "jit.bin", "bin.txt")
        ]
    else:
        assert publication == progress["publication"]
        for item in progress["artifacts"]:
            digest = hashlib.sha256((root / item["path"]).read_bytes()).hexdigest()
            assert digest == item["sha256"]
    assert 0 < allocated <= CAPACITY and phase not in evidence["snapshots"]
    evidence["snapshots"][phase] = {
        "source": state,
        "allocated": allocated,
        "phase": current_phase,
        "progress_phase": progress_phase,
        "publication": publication,
    }
    path.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=("promote-root", "prepare", "held", "filled", "progress", "drained", "validate"),
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.phase == "validate":
        print(
            json.dumps(
                validate_gate_pool(
                    (args.output / "gate-protocol.log").read_text(),
                    json.loads((args.output / "gate-pool.json").read_text()),
                    (args.output / "gate-role-status.tsv").read_text(),
                ),
                sort_keys=True,
            )
        )
    else:
        capture(args.phase, args.output)
