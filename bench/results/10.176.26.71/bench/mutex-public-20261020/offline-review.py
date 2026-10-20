#!/usr/bin/env python3
"""Source-host inert archive and arithmetic audit; never execute retained code."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
from statistics import median
import sys


HELPER = "bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py"
WORKLOADS = ("c01", "c08", "rcuht", "seek-set", "seek-end", "pipebytes", "pipecap")
ARMS = ("baseline-kd", "public-kd", "native", "tclock")
WORKERS = (*range(1, 9), *range(12, 61, 4))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "raw", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.report / "offline-review.json"
    if output.exists() or output.resolve().is_relative_to(args.raw.resolve()):
        raise ValueError("use a new receipt outside inert raw inputs")
    # This is the maintained, already reviewed source-host archive reader.
    # No source, binary or Python file obtained from the tar is executed.
    helper_path = args.repo / HELPER
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("inert_archive_reader", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    class MatrixAudit(helper.Audit):
        def retained_target(self, target):
            """Resolve retained absolute links in memory, never in the host FS.

            Matrix views add one level: workspace/disassem -> view/source/
            disassem -> the copied bundle/source/disassem. The tar contains the
            directory only at that final path, so literal inventory membership
            is insufficient. Every traversed link still has its archived target
            and metadata checked by the inherited reader.
            """
            seen = set()
            for _ in range(16):
                if target in seen or not target.startswith(self.guest_base):
                    return False
                seen.add(target)
                path = target[len(self.guest_base):]
                if not helper.safe_relative(path):
                    return False
                parts = path.split("/")
                for length in range(1, len(parts) + 1):
                    item = self.inventory.get("/".join(parts[:length]), {})
                    if item.get("link") is not None:
                        target = item["link"]
                        if length < len(parts):
                            target += "/" + "/".join(parts[length:])
                        break
                else:
                    return path in self.inventory
            return False

        def check(self, value, label, detail=None):
            if label == "symlink_target_retained":
                value = self.retained_target(detail["target"])
            return super().check(value, label, detail)

    audit = MatrixAudit(args)
    audit.windows = []
    results = {}

    def relative(path):
        if not path.startswith(audit.guest_base):
            raise ValueError("path outside retained round: " + path)
        value = path[len(audit.guest_base):]
        if not helper.safe_relative(value):
            raise ValueError("unsafe retained path: " + value)
        return value

    def phase():
        groups, links = audit.load_archives()
        results.update(groups=groups, symlinks=len(links))
        health = audit.jread("health.json")
        environment = audit.jread("matrix/environment.json")
        audit.equal("final_health_idle", health["idle"], True)
        audit.equal("health_boot", health["boot_id"], audit.archive["boot_id"])
        audit.equal("measurement_boot", environment["boot_id"], health["boot_id"])
        audit.equal("health_session_counts", [health["completed"], health["session_kernel_logs"]],
                    [1764, 1764])
        audit.equal("health_faults", health["per_session_kernel_faults"], [])
        audit.equal("health_complete", health["matrix_state"], "COMPLETE")
        frozen = audit.jread("frozen-inputs.json")
        audit.equal("bundle_set", sorted(frozen),
                    sorted(f"{v}/{w}" for v in ("baseline", "current") for w in WORKLOADS))
        for name, bundle in frozen.items():
            prefix = relative(bundle["bundle"]) + "/"
            sources = audit.jread(prefix + "source-sha256.json")
            audit.equal("source_identity", bundle["source_identity"],
                        digest(json.dumps(sources, sort_keys=True).encode()), name)
            for filename, expected in bundle["files"].items():
                audit.equal("frozen_input_hash", audit.files.get(relative(filename)), expected, filename)
            for filename, expected in sources.items():
                audit.expect("source_path_safe", helper.safe_relative(filename), filename)
                audit.equal("source_manifest_hash", audit.files.get(prefix + "source/" + filename),
                            expected, [name, filename])
        harness = audit.jread("harness-inputs.json")
        for path, expected in harness.items():
            prefix = "/root/host_fs/kdlock/"
            if not path.startswith(prefix):
                raise ValueError("unexpected harness source path")
            name = path[len(prefix):]
            audit.equal("harness_hash", audit.files.get("harness/" + name), expected, name)
            if name in audit.names("d21a1e3"):
                audit.equal("harness_committed_hash", digest(audit.git_bytes("d21a1e3", name)),
                            expected, name)
        state = audit.jread("matrix/status.json")
        records = audit.jread("matrix/records.json")
        plan = audit.jread("matrix/plan.json")
        order = []
        for wi, workload in enumerate(WORKLOADS):
            for ti, workers in enumerate(WORKERS):
                for repeat in range(3):
                    offset = (wi + ti + repeat) % 4
                    order.extend((workload, workers, repeat, arm)
                                 for arm in ARMS[offset:] + ARMS[:offset])
        audit.equal("complete_state", [state["state"], state["completed"], state["planned"]],
                    ["COMPLETE", 1764, 1764])
        audit.equal("record_count", len(records), 1764)
        audit.equal("session_status_count", len(state["sessions"]), 1764)
        audit.equal("execution_order", audit.jread("matrix/execution-order.json"), order)
        audit.equal("plan_count", len(plan), len(records))
        grouped = defaultdict(list)
        for index, (row, wanted) in enumerate(zip(records, order)):
            workload, workers, repeat, arm = wanted
            name = relative(row["evidence_path"])
            audit.equal("session_identity", [row["comparison_workload"], row["threads"],
                        row["repeat"], row["comparison_arm"]], wanted, name)
            audit.equal("plan_binding", {k: row.get(k) for k in plan[index]}, plan[index], name)
            audit.equal("saved_session_binding", row, audit.jread(name + "/session.json"), name)
            audit.equal("state_session_binding", state["sessions"][index],
                        dict(name=row["name"], status=row["execution_status"], drained=row["drained"],
                             path=row["evidence_path"]), name)
            audit.expect("session_verdict", row["execution_status"] in ("OK", "NO_JIT") and
                         row["drained"] is True and not row.get("cleanup_error"), name)
            audit.equal("source_binding", row["source_identity"],
                        frozen[("baseline" if arm == "baseline-kd" else "current") + "/" + workload]
                        ["source_identity"], name)
            audit.equal("caller_shell", row["caller_shell"],
                        "mutex_outer_cookie" if arm == "baseline-kd" else
                        "mutex_public_direct" if arm == "public-kd" else "c", name)
            audit.equal("worker_prefix", row["cpus"], list(range(workers)), name)
            audit.equal("numa_nodes", row["cpu_nodes"], [int(c >= 32) for c in range(workers)], name)
            audit.equal("kernel_identity", row["kernel_identity"], audit.files["matrix/kernel-identity.json"], name)
            audit.equal("topology_identity", row["topology_identity"], audit.files["matrix/topology.json"], name)
            audit.expect("ordinary_instrumentation",
                         not any(row.get(k) for k in ("diagnostic", "pmu", "perf_record")), name)
            audit.expect("kernel_log_clean", not helper.FAULT.search(
                audit.contents[name + "/kernel.log"].decode(errors="replace")), name)
            m = row["measurement"]
            raw = audit.jread(name + "/measure.json")
            audit.expect("raw_measurement_binding", all(m.get(k) == v for k, v in raw.items()), name)
            synthetic = workload in ("c01", "c08", "rcuht")
            audit.expect("business_oracle", (m["complete"] and m["data_ok"]) if synthetic else m["ok"], name)
            if synthetic:
                delta = [b - a for a, b in zip(m["before"], m["after"])]
                if workload == "rcuht":
                    audit.expect("hash_oracle", m["hash_integrity_ok"] and delta[0] == m["completed"]
                                 and m["before"][0] == sum(m["before"][1:4])
                                 and m["after"][0] == sum(m["after"][1:4])
                                 and not any(m["before"][4:] + m["after"][4:]), name)
                else:
                    audit.equal("cacheline_effects", delta,
                                [m["completed"] if i < int(workload[1:]) else 0 for i in range(16)], name)
            whole = m["completed"] * 1e9 / m["wall_ns"] if row["execution_status"] == "OK" else None
            if "whole_throughput_ops_s" in row:
                audit.equal("retained_whole_rate", row["whole_throughput_ops_s"], whole, name)
            copy = dict(row, whole_throughput_ops_s=whole)
            audit.peak(copy, name)
            entries = row.get("jit_bodies")
            completed = row.get("jit_completions")
            if row["arm"] == "kdlock":
                audit.expect("entry_bounds", type(entries) is int and 0 <= entries <= m["completed"], name)
                if synthetic:
                    evidence = "WITNESSED_JIT" if entries else "NO_JIT"
                elif completed is None:
                    evidence = "UNMEASURED"
                else:
                    audit.expect("return_bounds", type(completed) is int and 0 <= completed <= entries, name)
                    evidence = "RETURNED_JIT" if completed else "PARTIAL_JIT" if entries else "NO_JIT"
                audit.equal("source_retired", row["retired"],
                            dict(state=2, modules=0, frames=0, writers=0), name)
                audit.equal("publication_stable", row["published_before"], row["published_after"], name)
                for filename, expected in row["published_before"]["images"].items():
                    audit.expect("published_image_hash", any(
                        p.startswith(name + "/workspace/") and Path(p).name == filename and value == expected
                        for p, value in audit.files.items()), [name, filename])
            else:
                evidence = "NOT_APPLICABLE"
            grouped[(workload, workers, arm, evidence)].append(row)
        summaries = audit.jread("matrix/summary.json")
        audit.equal("summary_group_set", sorted((r["workload"], r["threads"], r["arm"],
                    r["execution_class"]) for r in summaries), sorted(grouped))
        for row in summaries:
            key = row["workload"], row["threads"], row["arm"], row["execution_class"]
            rows = grouped[key]
            good = [r for r in rows if r["execution_status"] == "OK"]
            rates = [r["measurement"]["completed"] * 1e9 / r["measurement"]["wall_ns"] for r in good]
            audit.equal("summary_repeats", row["comparable_three_repeats"],
                        sorted(r["repeat"] for r in good) == [0, 1, 2], key)
            for field, value in (("planned", len(rows)), ("accepted", len(good)),
                                 ("whole_min", min(rates) if rates else None),
                                 ("whole_median", median(rates) if rates else None),
                                 ("whole_max", max(rates) if rates else None),
                                 ("whole_spread_pct", 100 * (max(rates) - min(rates)) / median(rates)
                                  if rates else None),
                                 ("peak_max", max(r["measurement"]["peak"]["throughput_ops_s"]
                                                  for r in good) if good else None),
                                 ("p95_latency_ns", None)):
                audit.equal("summary_" + field, row[field], value, key)
        comparisons = audit.jread("matrix/comparisons.json")
        public = [r for r in summaries if r["arm"] == "public-kd"]
        audit.equal("comparison_set",
                    sorted((r["workload"], r["threads"], r["public_execution_class"],
                            r["comparator"]) for r in comparisons),
                    sorted((r["workload"], r["threads"], r["execution_class"], arm)
                           for r in public for arm in ("baseline-kd", "native", "tclock")))
        for row in comparisons:
            candidates = [r for r in public if r["workload"] == row["workload"]
                          and r["threads"] == row["threads"]
                          and r["execution_class"] == row["public_execution_class"]]
            controls = [r for r in summaries if r["workload"] == row["workload"]
                        and r["threads"] == row["threads"] and r["arm"] == row["comparator"]
                        and (r["arm"] != "baseline-kd" or
                             r["execution_class"] == row["public_execution_class"])]
            candidate = candidates[0]
            complete = (candidate["comparable_three_repeats"] and len(controls) == 1
                        and controls[0]["comparable_three_repeats"])
            ratio = candidate["whole_median"] / controls[0]["whole_median"] if complete else None
            separated = candidate["whole_max"] < .95 * controls[0]["whole_min"] if complete else None
            gate = ("INCOMPLETE" if not complete else "MEETS_PROVISIONAL_5_PERCENT" if ratio >= .95
                    else "LOSS_BEYOND_OBSERVED_RANGE" if separated
                    else "LOSS_NOT_SEPARATED_AT_5_PERCENT_MARGIN")
            key = row["workload"], row["threads"], row["public_execution_class"], row["comparator"]
            audit.equal("comparison_ratio", row["whole_median_ratio"], ratio, key)
            audit.equal("comparison_observed_range", row["loss_exceeds_observed_range"], separated, key)
            audit.equal("comparison_gate", row["throughput_gate"], gate, key)
            audit.equal("latency_unmeasured", row["p95_latency_gate"], "UNMEASURED", key)
            audit.equal("overall_open", row["overall_acceptance"], "OPEN", key)
        results.update(sessions=len(records), classes=dict(Counter(k[3] for k in grouped)),
                       source_bundles=len(frozen), harness_files=len(harness),
                       windows=len(audit.windows), summary_groups=len(summaries),
                       comparisons=len(comparisons))

    try:
        phase()
    except Exception as error:
        audit.expect("audit_exception", False, repr(error))
    receipt = dict(passed=not audit.issues, captured_utc=datetime.now(timezone.utc).isoformat(),
        host=socket.gethostname(), scope=__doc__, script_sha256=digest(Path(__file__).read_bytes()),
        helper_sha256=digest(helper_path.read_bytes()),
        archive_manifest_sha256=digest((args.raw / "archives.json").read_bytes()),
        checks=dict(audit.counts), total_checks=sum(audit.counts.values()), issues=audit.issues,
        results=results, windows=audit.windows,
        limits=["No retained executable or source code is executed.",
                "Source/ELF/JIT hashes and retained verdicts do not establish a new live correctness test.",
                "Synthetic entry witnesses are distinct from returned API bodies.",
                "No operation p95 latency measurement; overall acceptance remains open."])
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(dict(passed=receipt["passed"], checks=receipt["total_checks"],
                         issues=len(receipt["issues"]), results=results)))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
