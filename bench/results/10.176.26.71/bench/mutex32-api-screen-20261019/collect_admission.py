#!/usr/bin/env python3
"""Read completed real_api session evidence; never run workloads or alter inputs.

Run in the VM after both matrix invocations finish. Final hotlock rows are
whole-session observations: entries/contentions are unfinished-batch residuals,
not measured-phase totals. Missing evidence never establishes cold admission.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys


EXPECTED = {(kind, query, 16, threads, repeat)
            for kind, query in (("pipebytes", "query"), ("pipecap", "query"),
                                ("seek", "set"), ("seek", "end"))
            for threads in (1, 8, 32, 60) for repeat in range(3)}
PREFIXES = {"ratio": "kd_hotlock mutex ratio:",
            "lock_heat": "kd_hotlock final:",
            "mutex_stats": "kd_mutex stats:",
            "task_stats": "kd_mutex tasks:"}
RATIO_FIELDS = ("cpu", "entries", "contentions", "last_entries", "checks",
                "cpu_hot", "window")
REFUSALS = ("jit_not_ready", "jit_failure", "frame_failure", "node_overflow",
            "context_busy")
ZERO_MUTEX_FIELDS = ("slowpath", "combiner", "handoff", "jit_success",
                     "jit_resume", "active_waiters", "reserved_nodes",
                     "origin_acquires", "origin_releases", "multi_slot",
                     "max_waiters_per_cpu", "nested_lock", "nested_fast",
                     "nested_queued", "nested_jit", "nested_unlock",
                     "nested_abort_release") + REFUSALS
TASK_FIELDS = ("active_tasks", "task_alloc_failure", "task_reroutes")


def integer(value):
    return type(value) is int and value >= 0


def load_input(path, files):
    data = path.read_bytes()
    files[str(path)] = {"sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data)}
    return data.decode("utf-8")


def parse_log(text, errors):
    result = {name: [] for name in PREFIXES}
    for number, raw in enumerate(text.splitlines(), 1):
        for name, prefix in PREFIXES.items():
            if prefix not in raw:
                continue
            fields = {}
            for token in raw.split(prefix, 1)[1].split():
                if "=" not in token:
                    errors.append(f"kernel.log:{number}: malformed token {token!r}")
                    continue
                key, value = token.split("=", 1)
                if key in fields:
                    errors.append(f"kernel.log:{number}: duplicate field {key}")
                fields[key] = (int(value) if key != "address" and
                               re.fullmatch(r"-?\d+", value) else value)
            if name == "lock_heat" and fields.get("type") != "mutex":
                continue
            result[name].append({"line": number, "raw": raw, "fields": fields})
    return result


def observed_range(rows, field):
    values = [row["fields"][field] for row in rows
              if integer(row["fields"].get(field))]
    return {"min": min(values), "max": max(values)} if values else None


def collect(directory):
    files, errors = {}, []
    result = {"path": str(directory), "files": files, "errors": errors,
              "diagnosis": "INCOMPLETE_OR_UNACCEPTED", "matrix_key": None}
    try:
        record = json.loads(load_input(directory / "session.json", files))
        if not isinstance(record, dict):
            raise ValueError("session.json must contain an object")
        log = parse_log(load_input(directory / "kernel.log", files), errors)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(str(exc))
        return result
    result["identity"] = {key: record.get(key) for key in
                          ("name", "arm", "kind", "query", "entries", "threads",
                           "repeat", "cpus", "source_identity", "kernel_identity",
                           "topology_identity", "execution_status", "drained")}
    key = [record.get(field) for field in ("kind", "query", "entries", "threads", "repeat")]
    if (all(isinstance(value, str) for value in key[:2]) and
            all(integer(value) for value in key[2:])):
        result["matrix_key"] = key
    else:
        errors.append("missing or invalid matrix identity")
    if record.get("arm") != "kdlock":
        errors.append("expected a KD session")
    cpus = record.get("cpus")
    if (not isinstance(cpus, list) or not cpus or
            not all(integer(cpu) for cpu in cpus) or len(set(cpus)) != len(cpus) or
            record.get("threads") != len(cpus)):
        errors.append("invalid worker CPU list")
        cpus = []
    measurement = record.get("measurement")
    if not isinstance(measurement, dict):
        measurement = {}
    entries, completed, eligible = (record.get(field) for field in
                                    ("jit_bodies", "jit_completions", "jit_eligible_operations"))
    valid_jit = (all(integer(v) for v in (entries, completed, eligible)) and
                 0 <= completed <= entries <= eligible and
                 eligible == measurement.get("completed") and eligible > 0 and
                 record.get("jit_evidence_version") == 2)
    jit_class = ("PASS" if completed else "PARTIAL_JIT" if entries else "NO_JIT") if valid_jit else "INVALID"
    if not valid_jit or record.get("jit_status") != jit_class:
        errors.append("invalid or inconsistent measured JIT evidence")
    accepted = (record.get("execution_status") == "OK" and record.get("drained") is True and
                measurement.get("ok") is True)
    result["measured_phase"] = {"accepted_by_runner": accepted,
                                "completed": measurement.get("completed"),
                                "jit_bodies": entries, "jit_completions": completed,
                                "jit_eligible_operations": eligible, "jit_class": jit_class,
                                "recorded_jit_status": record.get("jit_status")}
    result["whole_session_final"] = log
    ratios = log["ratio"]
    for row in ratios:
        f = row["fields"]
        if (not all(integer(f.get(field)) for field in RATIO_FIELDS) or
                f.get("scope") != "unfinished_batch" or f.get("role") != "DONE" or
                f.get("window") != 1024 or f.get("cpu_hot") not in (0, 1)):
            errors.append(f"kernel.log:{row['line']}: incomplete or unexpected ratio row")
    observed_cpus = [r["fields"].get("cpu") for r in ratios]
    if len(set(observed_cpus)) != len(observed_cpus):
        errors.append("duplicate final ratio rows for a CPU")
    missing_cpus = sorted(set(cpus) - set(observed_cpus))
    if missing_cpus:
        errors.append(f"missing worker CPU ratio rows: {missing_cpus}")
    for name, required in (("mutex_stats", ZERO_MUTEX_FIELDS), ("task_stats", TASK_FIELDS)):
        if len(log[name]) != 1:
            errors.append(f"expected exactly one {name} line, found {len(log[name])}")
        elif not all(integer(log[name][0]["fields"].get(field)) for field in required):
            errors.append(f"incomplete or negative {name} fields")
    for row in log["lock_heat"]:
        f = row["fields"]
        if (not all(integer(f.get(field)) for field in ("cpu", "count", "cpu_hot", "lock_hot")) or
                not isinstance(f.get("address"), str) or f.get("role") != "DONE"):
            errors.append(f"kernel.log:{row['line']}: incomplete final lock-heat row")
    stats = log["mutex_stats"][0]["fields"] if len(log["mutex_stats"]) == 1 else {}
    tasks = log["task_stats"][0]["fields"] if len(log["task_stats"]) == 1 else {}
    result["observed"] = {
        "ratio_cpu_count": len(ratios), "missing_worker_cpus": missing_cpus,
        "extra_observed_cpus": sorted(cpu for cpu in set(observed_cpus) - set(cpus) if integer(cpu)),
        "final_batch_entries_range": observed_range(ratios, "entries"),
        "final_batch_contentions_range": observed_range(ratios, "contentions"),
        "completed_heat_checks_range": observed_range(ratios, "checks"),
        "cpu_hot_range": observed_range(ratios, "cpu_hot"),
        "final_lock_heat_rows": len(log["lock_heat"]),
        "slowpath": stats.get("slowpath"), "combiner": stats.get("combiner"),
        "refusals": {field: stats.get(field) for field in REFUSALS},
        "task_alloc_failure": tasks.get("task_alloc_failure"),
    }
    # With zero completed checks, these residuals cover the entire session.
    # A cold final snapshot after one or more checks cannot establish that
    # admission was always cold; preserve it without making that inference.
    cold = (not errors and accepted and jit_class == "NO_JIT" and bool(ratios) and
            not log["lock_heat"] and
            all(row["fields"]["checks"] == row["fields"]["last_entries"] ==
                row["fields"]["cpu_hot"] == 0 and
                row["fields"]["contentions"] < row["fields"]["window"] and
                row["fields"]["entries"] >= row["fields"]["contentions"]
                for row in ratios) and
            all(stats.get(field) == 0 for field in ZERO_MUTEX_FIELDS) and
            all(tasks.get(field) == 0 for field in TASK_FIELDS))
    result["cold_admission_accounts_for_no_jit"] = cold
    if cold:
        result["diagnosis"] = "NO_JIT_CPU_ADMISSION_NEVER_REACHED_FIRST_CHECK"
    elif not errors and accepted:
        result["diagnosis"] = ("MEASURED_JIT_" + jit_class if jit_class != "NO_JIT" else
                               "NO_JIT_CAUSE_NOT_ESTABLISHED")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base, output = args.base.resolve(), args.output.resolve()
    if output.name in {"session.json", "kernel.log"}:
        parser.error("output must not replace an input evidence file")
    sessions, errors = [], []
    for part in ("pipes", "seek"):
        folder = base / part
        if not folder.is_dir():
            errors.append(f"missing invocation directory: {folder}")
            continue
        # Include incomplete named KD directories instead of silently omitting
        # missing session.json or kernel.log files. Controls are not read.
        for directory in sorted(folder.glob("*-kdlock")):
            if directory.is_dir():
                sessions.append(collect(directory))
    keys = [tuple(s["matrix_key"]) for s in sessions if s["matrix_key"] is not None]
    counts = Counter(keys)
    missing, extra = sorted(EXPECTED - set(keys)), sorted(set(keys) - EXPECTED)
    duplicates = sorted(key for key, count in counts.items() if count != 1)
    coverage = not missing and not extra and not duplicates and len(sessions) == len(EXPECTED)
    if not coverage:
        errors.append("observed sessions do not exactly cover the expected 48-session KD matrix")
    nojit = [s for s in sessions if s.get("measured_phase", {}).get("jit_class") == "NO_JIT"]
    explained = [s for s in sessions if s.get("cold_admission_accounts_for_no_jit")]
    complete = coverage and not errors and not any(s["errors"] for s in sessions)
    result = {
        "schema": 1, "base": str(base), "status": "COMPLETE" if complete else "INCOMPLETE",
        "scope": {
            "status": "COMPLETE means all 48 session records and required final diagnostics were collected and parsed; acceptance and cold-admission findings are separate aggregate fields.",
            "inputs": "Only pipes/ and seek/ KD session.json and kernel.log files.",
            "final_counters": "Whole provider session, including setup, warmup, measurement and cleanup; not measurement-only.",
            "ratio_rows": "entries/contentions are final unfinished-batch residuals; checks counts completed comparisons. With checks=0 no comparison reset occurred.",
            "cold_proof": "All worker CPU rows present; every observed CPU has checks=last_entries=cpu_hot=0 and contentions<1024; no lock-heat records or delegation/refusal/task activity; accepted measured NO_JIT.",
            "limits": "Final heat alone cannot exclude earlier admission when checks>0. Does not identify why contention samples are sparse, or infer lost images, regressions or admission bugs. Runner acceptance is read from recorded fields, not independently rerun.",
        },
        "coverage": {"expected_kd_sessions": len(EXPECTED), "observed_kd_sessions": len(sessions),
                     "missing_matrix_keys": missing, "extra_matrix_keys": extra,
                     "duplicate_matrix_keys": duplicates},
        "aggregate": {
            "runner_accepted_sessions": sum(s.get("measured_phase", {}).get("accepted_by_runner", False) for s in sessions),
            "jit_classes": dict(Counter(s.get("measured_phase", {}).get("jit_class", "UNKNOWN") for s in sessions)),
            "diagnoses": dict(Counter(s["diagnosis"] for s in sessions)),
            "observed_no_jit_sessions": len(nojit), "cold_explained_no_jit_sessions": len(explained),
            "all_observed_no_jit_sessions_explained": bool(nojit) and len(nojit) == len(explained),
            "all_planned_kd_sessions_are_cold_no_jit": complete and len(explained) == len(EXPECTED),
        },
        "errors": errors, "sessions": sessions,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "status": result["status"],
                      "aggregate": result["aggregate"]}, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
