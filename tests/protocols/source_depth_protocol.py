"""Offline source-pin evidence validation; no retired workload loader controls."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "disassem"))
import device_session as source
from native_only_protocol import entries

ROOT = Path(__file__).resolve().parents[2]
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
