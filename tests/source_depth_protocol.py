"""Observe two learned source pins inside the existing mutex depth workload.

Only run controls at joined-wave boundaries with the daemon stopped/paused.
ELF identity, loader references and source pins are different observations;
actual JIT execution still requires the depth workload's retained-owner oracle.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from elftools.elf.elffile import ELFFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "disassem"))
import device_session as source
from native_only_protocol import entries
from source_retirement import writer_refused

ROOT = Path(__file__).resolve().parents[1]
MAIN, HELPER = "klock_module", "kd_depth_source"
SYMBOLS = {MAIN: "kd_resume_depth_mutex", HELPER: "kd_depth_source_enter"}
# Each source contributes one pin. The helper also has one native loader
# reference from MAIN, which must survive pin release until MAIN unloads.
PHASES = {
    "root": (1, 1, 0, 1, 1),
    "local-miss": (1, 1, 1, 1, 1),
    "local-ready": (1, 1, 0, 1, 1),
    "foreign-miss": (2, 1, 1, 1, 2),
    "ready": (2, 0, 0, 1, 2),
    "drained": (2, 0, 0, 1, 2),
    "retired": (0, 0, -3, 0, 1),
    "detached": (0, 0, -3, None, 0),
    "unloaded": (0, 0, -3, None, None),
}


def module_snapshot(name):
    directory = Path("/sys/module") / name
    if not directory.exists():
        return None
    path = ROOT / "workload_modules/lock_scenarios" / f"{name}.ko"
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        text = elf.get_section_by_name(".text")
        (symbol,) = elf.get_section_by_name(".symtab").get_symbol_by_name(SYMBOLS[name])
        assert elf.get_section(symbol["st_shndx"]).name == ".text"
        start = int((directory / "sections/.text").read_text(), 16)
        end = start + text["sh_size"]
        address = start + symbol["st_value"]
    # Check the relocated ELF symbol against the actual live module, not a
    # symbol name in a generated comment or the mere existence of a .ko file.
    (live,) = [
        int(row[0], 16)
        for line in Path("/proc/kallsyms").read_text().splitlines()
        if len(row := line.split()) == 4 and row[2:] == [SYMBOLS[name], f"[{name}]"]
    ]
    assert address == live
    return {
        "text_start": start,
        "text_end": end,
        "callee": address,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "refcnt": int((directory / "refcnt").read_text()),
        "holders": sorted(path.name for path in (directory / "holders").iterdir()),
    }


def snapshot(fd):
    return {
        "info": source.info(fd),
        "modules": {name: module_snapshot(name) for name in SYMBOLS},
        "registry": [
            {
                "entry": entry.rip,
                "code": entry.code,
                "tgid": entry.tgid,
                "kind": entry.lock_kind,
                "status": entry.status,
                "target": entry.target,
            }
            for entry in entries()
        ],
    }


def validate(phase, observation, entry, baseline=None):
    """Reject missing/early/retained pins, unexpected holders and stale images."""
    count, writers, status, main_refs, helper_refs = PHASES[phase]
    state = source.RETIRED if status == -3 else source.OPEN
    assert observation["info"] == {
        "state": state,
        "modules": count,
        "frames": 0,
        "writers": writers,
    }, (phase, observation["info"])
    assert set(observation["modules"]) == set(SYMBOLS)
    for name, refs in ((MAIN, main_refs), (HELPER, helper_refs)):
        module = observation["modules"][name]
        if refs is None:
            assert module is None, (phase, name, module)
            continue
        assert module is not None and module["refcnt"] == refs, (phase, name, module)
        assert module["holders"] == (
            [MAIN] if name == HELPER and main_refs is not None else []
        )
        assert 0 < module["text_start"] <= module["callee"] < module["text_end"]
        assert re.fullmatch("[0-9a-f]{64}", module["sha256"])
        if baseline:
            original = baseline["modules"][name]
            assert all(
                module[key] == original[key]
                for key in ("text_start", "text_end", "callee", "sha256")
            )
    (registered,) = observation["registry"]
    assert registered["entry"] == entry and registered["code"] > 0
    assert registered["kind"] == 2 and registered["status"] == status
    main, helper = (observation["modules"][name] for name in (MAIN, HELPER))
    if main and helper:
        assert main["text_start"] <= entry < main["text_end"]
        assert (
            main["text_end"] <= helper["text_start"]
            or helper["text_end"] <= main["text_start"]
        )
    expected_target = 0
    if phase != "root":
        owner = MAIN if phase.startswith("local-") else HELPER
        expected_target = (baseline or observation)["modules"][owner]["callee"]
    assert registered["target"] == expected_target, registered
    if baseline:
        (original,) = baseline["registry"]
        assert all(
            registered[key] == original[key]
            for key in ("entry", "code", "tgid", "kind")
        )


def validate_learning(before, after, entry, target):
    """Require a new JIT-to-native miss/record/ACK in this exact joined wave.

    Reusing an earlier miss or a matching assembly label is not proof that the
    second learned CALL level executed. The capacity wave separately proves
    the completed external helper/RET and seven retained child owners.
    """
    assert after.startswith(before), "learning history was lost or replaced"
    text = after[len(before) :]
    begins = [
        dict(re.findall(r"(\w+)=(\w+)", line))
        for line in re.findall(r"kd_native begin: ([^\n]+)", text)
    ]
    assert begins, "no new native handoff in learning wave"
    assert "reason=PENDING_LOCK_NATIVE" not in text
    bodies = re.findall(
        r"JIT body witness: entry=([0-9a-f]+) lock=([0-9a-f]+) body=1\b", text
    )
    assert len(bodies) == len(begins)
    assert len({event["task"] for event in begins}) == len(begins)
    for event in begins:
        assert int(event["entry"], 16) == entry and int(event["ip"], 16) == target
        assert event["held"] == event["mutex"] == event["remaining"] == "1"
        assert event["outer_released"] == "0"
        assert all(int(e, 16) == entry and lock == event["outer"] for e, lock in bodies)
        pid = event["task"]
        assert len(re.findall(r"kd_native complete: task=" + pid + r" \b", text)) == 1
        acks = re.findall(
            r"kd_native ack: task=" + pid + r" lock=(\w+) mutex=1\b", text
        )
        assert acks == [event["outer"]]
        assert (
            len(
                re.findall(
                    r"kd_depth mutex: task="
                    + pid
                    + r" retained=0 children=8 valid=1 record=\d+",
                    text,
                )
            )
            == 1
        )


def observe(fd, out, phase, entry):
    baseline = (
        None if phase == "root" else json.loads((out / "source-root.json").read_text())
    )
    current = snapshot(fd)
    # Save a failing observation too; never manufacture the expected state.
    (out / f"source-{phase}.json").write_text(json.dumps(current, indent=2) + "\n")
    validate(phase, current, entry, baseline)
    if phase in {"local-miss", "foreign-miss"}:
        owner = MAIN if phase == "local-miss" else HELPER
        name = SYMBOLS[owner]
        validate_learning(
            (out / f"before-learning-{name}.log").read_text(),
            (out / f"after-learning-{name}.log").read_text(),
            entry,
            current["modules"][owner]["callee"],
        )
    return current


def retire(fd, out, entry):
    observe(fd, out, "drained", entry)
    refusals = {}
    for name in (MAIN, HELPER):
        result = subprocess.run(
            ["rmmod", name], capture_output=True, text=True, timeout=5, check=False
        )
        assert result.returncode != 0 and "in use" in result.stderr, result
        refusals[name] = result.stderr
    (out / "source-unload-refusals.json").write_text(
        json.dumps(refusals, indent=2) + "\n"
    )
    # MAIN's sole source pin must drop before its normal unload. HELPER still
    # has its loader holder until MAIN exits; these are not two source pins.
    fcntl.ioctl(fd, source.RETIRE)
    observe(fd, out, "retired", entry)
    writer_refused()
    subprocess.run(["rmmod", MAIN], check=True, timeout=5)
    observe(fd, out, "detached", entry)
    subprocess.run(["rmmod", HELPER], check=True, timeout=5)
    observe(fd, out, "unloaded", entry)
    writer_refused()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "root",
            "local-miss",
            "local-ready",
            "foreign-miss",
            "ready",
            "retire",
        ),
    )
    parser.add_argument("out", type=Path)
    parser.add_argument("entry", type=lambda value: int(value, 16))
    args = parser.parse_args()
    fd = os.open(source.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
    try:
        if args.phase == "retire":
            retire(fd, args.out, args.entry)
        else:
            observe(fd, args.out, args.phase, args.entry)
    finally:
        os.close(fd)
    print(f"PASS source-depth: {args.phase}")


if __name__ == "__main__":
    main()
