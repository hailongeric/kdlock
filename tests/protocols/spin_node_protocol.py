"""Strict drained reservation evidence, not a universal node-count bound."""

import argparse
import json
import re
from pathlib import Path

COUNTERS = (
    "native",
    "virtual",
    "native_full",
    "virtual_full",
    "context_missing",
    "prepare_cancel",
    "native_return",
    "remote_return",
    "combiner",
    "head",
    "poll",
)
FIELDS = set(COUNTERS) | {
    "cpu",
    "live",
    "actual",
    "peak",
    "peak_task",
    "peak_preempt",
    "peak_irq",
    "first_event",
    "first_count",
    "first_expected",
    "first_task",
    "first_preempt",
    "first_irq",
}


def records(log, prefix, fields):
    rows = []
    for line in log.splitlines():
        if prefix not in line:
            continue
        tokens = line.split(prefix, 1)[1].split()
        assert all(re.fullmatch(r"[a-z_]+=-?\d+", token) for token in tokens)
        pairs = [token.split("=") for token in tokens]
        assert len(pairs) == len(dict(pairs)) and set(dict(pairs)) == fields
        rows.append({key: int(value) for key, value in pairs})
    return rows


def validate(log, placement, profile):
    assert set(profile) == {"enabled", "kind"}
    assert type(profile["enabled"]) is bool and profile["kind"] in (
        "physical",
        "remote",
    )
    rows = records(log, "kd_node trace:", FIELDS)
    summaries = records(log, "kd_node summary:", {"cpus", "capacity", "record_bytes"})
    if not profile["enabled"]:
        assert not rows and not summaries, (
            "disabled profile must not emit node evidence"
        )
        return {"enabled": False}
    assert len(summaries) == 1 and rows, "missing drained node evidence"
    summary = summaries[0]
    assert summary == {"cpus": len(rows), "capacity": 4, "record_bytes": 128}
    cpus = [row["cpu"] for row in rows]
    assert len(set(cpus)) == len(cpus) and min(cpus) >= 0
    assert set(placement["online_cpus"]) <= set(cpus)
    totals = dict.fromkeys(COUNTERS, 0)
    for row in rows:
        assert all(row[key] >= 0 for key in FIELDS)
        assert row["live"] == row["actual"] == 0
        assert all(row[key] == 0 for key in FIELDS if key.startswith("first_"))
        reserved = row["native"] + row["virtual"]
        returned = sum(
            row[key]
            for key in (
                "prepare_cancel",
                "native_return",
                "remote_return",
                "combiner",
                "head",
            )
        )
        assert reserved == returned, f"unbalanced CPU {row['cpu']}"
        assert row["peak"] == (1 if reserved else 0), (
            "stop deepening: unexpected node peak"
        )
        if reserved:
            assert row["peak_task"] > 0 and row["peak_preempt"] & 255
            # IRQ-off task callers are valid. This observes reservation,
            # which can precede masking for a virtual request from mutex.
            assert row["peak_irq"] in (0, 1)
        else:
            assert row["peak_task"] == row["peak_preempt"] == row["peak_irq"] == 0
            assert row["poll"] == 0
        assert (
            row["native_full"]
            == row["virtual_full"]
            == row["context_missing"]
            == row["prepare_cancel"]
            == 0
        )
        for key in COUNTERS:
            totals[key] += row[key]
    assert totals["native"] > 0 and totals["combiner"] > 0
    if profile["kind"] == "physical":
        depth = placement["depth"]
        assert type(depth) is int and 1 <= depth <= 8
        by_cpu = {row["cpu"]: row for row in rows}
        assert by_cpu[0]["native"] > 0 and by_cpu[0]["combiner"] >= depth
        assert by_cpu[0]["virtual"] >= depth - 1
        assert all(by_cpu[cpu]["native"] > 0 for cpu in range(1, depth + 1))
    else:
        assert totals["virtual"] > 0 and totals["poll"] > 0
    return {"enabled": True, "peak": 1, "cpus": len(rows), **totals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("profile", "validate"))
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("third", nargs="?")
    args = parser.parse_args()
    if args.command == "profile":
        assert (
            args.first in ("0", "1")
            and args.second in ("physical", "remote")
            and args.third is None
        )
        result = {"enabled": args.first == "1", "kind": args.second}
    else:
        result = validate(
            Path(args.first).read_text(),
            json.loads(Path(args.second).read_text()),
            json.loads(Path(args.third).read_text()),
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
