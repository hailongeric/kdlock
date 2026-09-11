"""Real shadow-map pressure within the existing dual-frame native interval."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

COUNT = 1025
CAPACITY = 1024
PARAMETERS = Path("/sys/module/kdlock_km/parameters")


def rows(text, label):
    return [
        (m.start(), dict(re.findall(r"(\w+)=(\w+)", m[1])))
        for m in re.finditer(re.escape(label) + r": ([^\n]*)", text)
    ]


def validate_shadow_pool(text, evidence):
    """Require actual map membership and native exclusion, not merely ENOMEM."""
    base, stride = evidence["base"], evidence["stride"]
    entry = evidence["entry"]
    assert type(base) is int and base > 0 and type(stride) is int and stride > 0
    assert type(entry) is int and entry > 0
    assert evidence["count"] == COUNT
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["module_sha256"])
    ((_, layout),) = rows(text, "kd_parallel shadow layout")
    assert layout == {"base": f"{base:x}", "stride": str(stride), "count": str(COUNT)}
    addresses = {f"{base + i * stride:x}" for i in range(COUNT)}
    promoted = re.findall(r"kd_hotlock selftest promote: lock=([0-9a-f]+)", text)
    assert len(promoted) == COUNT and set(promoted) == addresses
    snapshots = evidence["snapshots"]
    assert set(snapshots) == {"prepare", "held", "filled", "drained"}
    for phase, snapshot in snapshots.items():
        assert snapshot["source"] == {
            "state": 0,
            "modules": 1,
            "frames": 0 if phase == "prepare" else 2,
            "writers": 0,
        }
        assert type(snapshot["allocated"]) is int
    before = snapshots["held"]["allocated"]
    assert 0 < snapshots["prepare"]["allocated"] <= before < CAPACITY
    assert (
        snapshots["filled"]["allocated"]
        == snapshots["drained"]["allocated"]
        == CAPACITY
    )
    arrivals, resumes = (
        rows(text, "kd_parallel arrive"),
        rows(text, "kd_parallel resume"),
    )
    assert len(arrivals) == len(resumes) == 2
    start, end = max(at for at, _ in arrivals), min(at for at, _ in resumes)
    records = rows(text, "kd_parallel shadow record")
    filled = [(at, row) for at, row in records if row["role"] == "0"]
    queued = [(at, row) for at, row in records if row["role"] != "0"]
    assert len(filled) == COUNT and len(queued) == 3
    assert [int(row["index"]) for _, row in filled] == list(range(COUNT))
    assert start < filled[0][0] < filled[-1][0] < min(at for at, _ in queued)
    assert max(at for at, _ in queued) < end
    new = CAPACITY - before
    old_tasks = {r["task"] for _, r in arrivals}
    old_owners = {r[k] for _, r in arrivals for k in ("owner", "waiter")}
    expected_refusals = []
    for _, row in records:
        index, role, updates = int(row["index"]), int(row["role"]), int(row["updates"])
        assert 0 <= index < COUNT and 0 <= role <= 3
        assert row["lock"] == f"{base + index * stride:x}"
        assert row["valid"] == "1" and row["owner"] == row["waiter"]
        assert int(row["owner"], 16) > 0 and int(row["task"]) > 0
        assert row["owner"] not in old_owners and row["task"] not in old_tasks
        assert row["registered"] == str(int(not role and index < new))
        if role:
            assert index == COUNT - 1 and updates in (2, 3, 4)
        else:
            assert updates == 1
        value = index + 7
        for _ in range(updates):
            value = value * 33 + index + 1
        assert int(row["value"], 16) == value
        if (not role and index >= new) or role >= 2:
            expected_refusals.append((row["task"], row["lock"]))
    assert len({row["task"] for _, row in filled}) == 1
    roles = {int(row["role"]): row for _, row in queued}
    assert set(roles) == {1, 2, 3} and len({r["task"] for r in roles.values()}) == 3
    assert roles[1]["updates"] == "2"
    assert {roles[role]["updates"] for role in (2, 3)} == {"3", "4"}
    ((queue_at, queue),) = rows(text, "kd_parallel shadow queued")
    assert queue == {
        "task": roles[1]["task"],
        "owner": roles[1]["owner"],
        "lock": roles[1]["lock"],
        "count": "2",
        "matched": "3",
    }
    assert filled[-1][0] < queue_at < min(at for at, _ in queued)
    refused = rows(text, "mutex shadow fallback")
    assert len(refused) == len(expected_refusals)
    assert sorted((r["task"], r["lock"]) for _, r in refused) == sorted(
        expected_refusals
    )
    assert all(start < at < end and int(r["entry"], 16) == entry for at, r in refused)
    assert not any(
        int(r["entry"], 16) == entry for _, r in rows(text, "JIT body witness")
    )
    return {
        "allocated_shadows": CAPACITY,
        "previous_shadows": before,
        "new_shadows": new,
        "filler_records": COUNT,
        "native_queue_records": 3,
        "target_refusals": len(refused),
    }


def capture(phase, out):
    """Read module identity/counts; only preparation controls promotion."""
    from elftools.elf.elffile import ELFFile

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "disassem"))
    import device_session as source

    module = root / "klock_module/klock_module.ko"
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    path = out / "shadow-pool.json"
    symbols = {
        row[2]: int(row[0], 16)
        for line in Path("/proc/kallsyms").read_text().splitlines()
        if len(row := line.split()) == 4 and row[3] == "[klock_module]"
    }
    if phase == "prepare":
        with module.open("rb") as stream:
            elf = ELFFile(stream)
            table = elf.get_section_by_name(".symtab")
            (array,) = table.get_symbol_by_name("kd_shadow_capacity_locks")
            (function,) = table.get_symbol_by_name("kd_shadow_capacity_acquire")
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
                        == "mutex_lock"
                    ):
                        assert relocation["r_info_type"] in (2, 4)
                        calls.append(symbols[function.name] + offset + 4)
            (entry,) = calls
        evidence = {
            "base": symbols["kd_shadow_capacity_locks"],
            "stride": array["st_size"] // COUNT,
            "count": COUNT,
            "entry": entry,
            "module_sha256": digest,
            "snapshots": {},
        }
        # Do not write table entries or reserve requests. The following real
        # acquisitions must independently account for every newly occupied slot.
        for i in range(COUNT):
            (PARAMETERS / "spin_selftest_promote").write_text(
                hex(evidence["base"] + i * evidence["stride"]) + "\n"
            )
    else:
        evidence = json.loads(path.read_text())
        assert evidence["base"] == symbols["kd_shadow_capacity_locks"]
        assert evidence["module_sha256"] == digest
    fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    try:
        state = source.info(fd)
    finally:
        os.close(fd)
    assert state == {
        "state": source.OPEN,
        "modules": 1,
        "frames": 0 if phase == "prepare" else 2,
        "writers": 0,
    }
    allocated = int((PARAMETERS / "mutex_selftest_shadow_count").read_text())
    assert 0 < allocated <= CAPACITY
    assert phase not in evidence["snapshots"]
    evidence["snapshots"][phase] = {"source": state, "allocated": allocated}
    path.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "held", "filled", "drained"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    capture(args.phase, args.output)
