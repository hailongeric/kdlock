"""Link raw CALL-entry register samples to actual JIT/native handoff records."""

import argparse
import json
import re
import struct
from pathlib import Path

STAMPS = {
    0: 0x1122334455667788,
    1: 0x2233445566778899,
    2: 0x33445566778899AA,
    3: 0x445566778899AABB,
    4: 0x5566778899AABBCC,
    8: 0x66778899AABBCCDD,
    9: 0x778899AABBCCDDEE,
    10: 0x8899AABBCCDDEEFF,
    11: 0x99AABBCCDDEEFF00,
    12: 0xAABBCCDDEEFF0011,
    13: 0xBBCCDDEEFF001122,
    14: 0xCCDDEEFF00112233,
    15: 0xDDEEFF0011223344,
}
SAMPLE_FIELDS = frozenset(
    [
        "task",
        "record",
        "seed",
        "buffer",
        "calls",
        "mask",
        "gpr0",
        "gpr1",
        "sp",
        "bp",
        "ip",
        "ret",
        "tag0",
        "tag1",
        "returned",
    ]
)


def rows(text, prefix):
    result = []
    for line in text.splitlines():
        if prefix not in line:
            continue
        fields = {}
        for item in line.split(prefix, 1)[1].split():
            pair = item.split("=", 1)
            assert len(pair) == 2 and pair[0] not in fields, "bad/duplicate field"
            fields[pair[0]] = pair[1]
        result.append(fields)
    return result


def number(value, base=10):
    pattern = r"[0-9]+" if base == 10 else r"[0-9a-fA-F]+"
    assert re.fullmatch(pattern, value), ("invalid number", value)
    parsed = int(value, base)
    assert parsed < 1 << 64, "oversized value"
    return parsed


def validate(text, probe_ip, requests, *, expect_jit=True):
    assert 0 < requests <= 65536 and probe_ip > 0
    summaries = rows(text, "kd_regs summary:")
    assert len(summaries) == 1, "missing/duplicate register summary"
    assert set(summaries[0]) == {"requests", "checked", "marked", "omitted", "failures"}
    summary = {key: number(value) for key, value in summaries[0].items()}
    assert summary["requests"] == summary["checked"] == requests
    assert summary["omitted"] == summary["failures"] == 0
    samples = rows(text, "kd_regs sample:")
    assert 0 < summary["marked"] == len(samples) <= 128
    identities, buffers, by_stack = set(), set(), {}
    for row in samples:
        assert set(row) == SAMPLE_FIELDS, "incomplete/unexpected sample fields"
        values = {
            key: number(value, 10 if key in {"task", "record", "calls"} else 16)
            for key, value in row.items()
            if key not in {"gpr0", "gpr1"}
        }
        task, record = values["task"], values["record"]
        assert task > 0 and record < requests and record not in identities
        assert values["buffer"] and values["buffer"] not in buffers
        identities.add(record)
        buffers.add(values["buffer"])
        seed = record + 1
        assert values["seed"] == seed and values["calls"] == 1
        assert values["mask"] == 0
        for key in ("gpr0", "gpr1"):
            assert re.fullmatch(r"[0-9a-fA-F]{128}", row[key]), "bad GPR bytes"
        gpr = struct.unpack("<16Q", bytes.fromhex(row["gpr0"] + row["gpr1"]))
        for index, stamp in STAMPS.items():
            assert gpr[index] == stamp ^ seed, ("register mismatch", record, index)
        assert gpr[5] == values["buffer"], "RDI lost sample identity"
        assert gpr[6] == values["bp"] != 0, "RBP mismatch"
        assert gpr[7] == values["sp"] != 0, "RSP mismatch"
        assert values["sp"] % 8 == values["bp"] % 8 == 0
        assert values["ret"] == values["ip"] != 0, "CALL return mismatch"
        assert values["tag0"] == 0x13579BDF2468ACE0 ^ seed
        assert values["tag1"] == 0xFEDCBA9876543210 ^ seed
        assert values["returned"] == 0x5A3CC396A5696996 ^ seed
        key = (task, values["sp"])
        assert key not in by_stack, "ambiguous reused native stack"
        by_stack[key] = record

    begins = rows(text, "kd_native begin:")
    if expect_jit:
        assert begins, "no actual native handoff"
    else:
        assert not begins, "native-only control unexpectedly delegated"
    matched = set()
    sample_tasks = {key[0] for key in by_stack}
    for begin in begins:
        assert {"task", "ip", "sp"} <= begin.keys(), "incomplete native handoff"
        task = number(begin["task"])
        assert task in sample_tasks, "native request has no register sample"
        if number(begin["ip"], 16) == probe_ip:
            key = (task, number(begin["sp"], 16))
            assert key in by_stack, "CALL-miss stack has no matching sample"
            # Ancestor relays may repeat this packet, but the callee runs once.
            matched.add(by_stack[key])
    if expect_jit:
        assert matched, "no JIT CALL miss at the capture callee"
    stats = rows(text, "kd_native stats:")
    assert len(stats) == 1
    assert set(stats[0]) == {"started", "completed", "unlocks"}
    assert number(stats[0]["started"]) == number(stats[0]["completed"]) == len(begins)
    if expect_jit:
        assert number(stats[0]["unlocks"]) > 0
    else:
        assert number(stats[0]["unlocks"]) == 0
    return {
        "requests": requests,
        "samples": len(samples),
        "jit_samples": len(matched),
        "native_frames": len(begins),
        "gprs": 16,
        "flags_checked": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("probe_ip", type=lambda value: int(value, 16))
    parser.add_argument("requests", type=int)
    parser.add_argument("--native-only", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            validate(
                args.log.read_text(),
                args.probe_ip,
                args.requests,
                expect_jit=not args.native_only,
            )
        )
    )


if __name__ == "__main__":
    main()
