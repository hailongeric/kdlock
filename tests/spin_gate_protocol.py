"""Real gate-map exhaustion inside the existing spin ticket/native interval."""

import argparse
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


def validate_gate_pool(text, evidence, statuses):
    """Keep map refusal, retained owners and native exclusion inseparable."""
    base, stride, entry = (evidence[key] for key in ("base", "stride", "entry"))
    assert all(type(value) is int and value > 0 for value in (base, stride, entry))
    assert evidence["count"] == COUNT
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["module_sha256"])
    assert statuses == "0\t0\n1\t0\n2\t0\n"
    ((_, layout),) = rows(text, "kd_gate layout")
    assert layout == {"base": f"{base:x}", "stride": str(stride), "count": str(COUNT)}
    addresses = {f"{base + i * stride:x}" for i in range(COUNT)}
    promoted = re.findall(r"kd_hotlock selftest promote: lock=([0-9a-f]+)", text)
    assert len([addr for addr in promoted if addr in addresses]) == COUNT
    assert addresses <= set(promoted)
    snapshots = evidence["snapshots"]
    assert set(snapshots) == {"prepare", "held", "filled", "drained"}
    for phase, snapshot in snapshots.items():
        assert snapshot["source"] == {
            "state": 0,
            "modules": 1,
            "frames": 0 if phase == "prepare" else 1,
            "writers": 0,
        }
        assert snapshot["phase"] == (0 if phase == "prepare" else 1)
        assert type(snapshot["allocated"]) is int
    before = snapshots["held"]["allocated"]
    assert 0 < snapshots["prepare"]["allocated"] <= before < CAPACITY
    assert (
        snapshots["filled"]["allocated"]
        == snapshots["drained"]["allocated"]
        == CAPACITY
    )
    ((start, held),) = rows(text, "kd_gate hold")
    ((end, resumed),) = rows(text, "kd_gate resume")
    assert held == resumed and held["valid"] == "1" and held["cpu"] == "1"
    assert int(held["a"], 16) and int(held["b"], 16) and held["a"] != held["b"]
    ((native_at, native),) = rows(text, "kd_native begin")
    ((blocked_at, blocked),) = rows(text, "kd_pending spin blocked")
    ((acquired_at, acquired),) = rows(text, "kd_pending spin acquired")
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
    assert stats == {"locks": str(COUNT), "roles": "7", "phase": "2", "valid": "1"}
    return {
        "allocated_gates": CAPACITY,
        "previous_gates": before,
        "new_gates": new,
        "filler_records": COUNT,
        "native_queue_records": 2,
        "target_refusals": len(refused),
        "retained_frames": 1,
    }


def capture(phase, out):
    """Promote only in preparation; later snapshots do not alter map/owners."""
    from elftools.elf.elffile import ELFFile

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "disassem"))
    import device_session as source

    module = root / "klock_module/klock_module.ko"
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    path = out / "gate-pool.json"
    symbols = {
        row[2]: int(row[0], 16)
        for line in Path("/proc/kallsyms").read_text().splitlines()
        if len(row := line.split()) == 4 and row[3] == "[klock_module]"
    }
    if phase == "prepare":
        with module.open("rb") as stream:
            elf = ELFFile(stream)
            table = elf.get_section_by_name(".symtab")
            (array,) = table.get_symbol_by_name("kd_gate_capacity_locks")
            (function,) = table.get_symbol_by_name("kd_gate_capacity_acquire")
            assert array["st_size"] % COUNT == 0
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
                        0 <= offset < function["st_size"]
                        and linked.get_symbol(relocation["r_info_sym"]).name
                        == "_raw_spin_lock"
                    ):
                        assert relocation["r_info_type"] in (2, 4)
                        calls.append(symbols[function.name] + offset + 4)
            (entry,) = calls
        evidence = {
            "base": symbols["kd_gate_capacity_locks"],
            "stride": array["st_size"] // COUNT,
            "count": COUNT,
            "entry": entry,
            "module_sha256": digest,
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
    if phase == "held":
        deadline = time.monotonic() + 10
        while int((WORKLOAD / "native_gate_phase").read_text()) != 1:
            assert time.monotonic() < deadline, "original native interval not reached"
            time.sleep(0.02)
    fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    try:
        state = source.info(fd)
    finally:
        os.close(fd)
    assert state == {
        "state": source.OPEN,
        "modules": 1,
        "frames": 0 if phase == "prepare" else 1,
        "writers": 0,
    }
    allocated = int((PARAMETERS / "spin_selftest_gate_count").read_text())
    current_phase = int((WORKLOAD / "native_gate_phase").read_text())
    assert current_phase == (0 if phase == "prepare" else 1)
    assert 0 < allocated <= CAPACITY and phase not in evidence["snapshots"]
    evidence["snapshots"][phase] = {
        "source": state,
        "allocated": allocated,
        "phase": current_phase,
    }
    path.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=("prepare", "held", "filled", "drained", "validate")
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
