#!/usr/bin/env python3
"""Best observed kdlock throughput versus median native throughput, per configuration."""
import argparse
import csv
import json
import statistics
from pathlib import Path

COMPARISON_POLICY = "best_kdlock_over_median_native"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def valid(record):
    return (record.get("execution_status") == "OK" and record.get("drained") is True
            and record.get("measurement", {}).get("data_ok") is True
            and record.get("measurement", {}).get("complete") is True)


def pair_ratio(native, kdlock):
    """A missing body is not a preparation/data failure or a JIT acceptance."""
    if not (valid(native) and valid(kdlock)):
        return None
    if native["arm"] != "native" or kdlock["arm"] != "kdlock":
        raise ValueError("invalid pair arms")
    for key in ("cachelines", "threads", "iterations", "cpus", "repeat"):
        if native[key] != kdlock[key]:
            raise ValueError(f"paired {key} differs")
    if native.get("cpu_nodes") != kdlock.get("cpu_nodes"):
        raise ValueError("paired CPU NUMA nodes differ")
    n, k = native["measurement"], kdlock["measurement"]
    return (k["completed"] / k["wall_ns"]) / (n["completed"] / n["wall_ns"])


def placement(record):
    # Older saved scans have no per-session node list; keep that unknown
    # instead of inferring topology from CPU numbers when re-summarizing them.
    nodes = sorted(set(record.get("cpu_nodes", [])))
    return dict(numa_nodes=",".join(map(str, nodes)),
                numa_scope=("single_node" if len(nodes) == 1 else
                            "cross_node" if nodes else "unknown"))


def csv_file(path, fields, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def best_comparison(rows):
    """Select only valid sessions of one workload/placement, with an audit trail.

    This is an observed best, not a paired ratio or a typical-case estimate.
    A fastest NO_JIT session stays NO_JIT. Failed or undrained sessions have no
    throughput and cannot win; an absent baseline leaves the ratio empty.
    """
    settings = {(r["iterations"], r["cpus"], r["numa_nodes"]) for r in rows}
    if len(settings) != 1:
        raise ValueError("cannot compare different iterations or CPU placements")
    native = [r for r in rows if r["arm"] == "native" and r["throughput_ops_s"] is not None]
    kdlock = [r for r in rows if r["arm"] == "kdlock" and r["throughput_ops_s"] is not None]
    baseline = statistics.median(r["throughput_ops_s"] for r in native) if native else None
    # Plan order resolves exact ties reproducibly; take every accompanying
    # field from this same session, never a maximum assembled across samples.
    best = max(kdlock, key=lambda r: r["throughput_ops_s"]) if kdlock else None
    result = dict(valid_native_sessions=len(native), valid_kdlock_sessions=len(kdlock),
                  best_kdlock_session=best["name"] if best else None,
                  best_kdlock_over_median_native=(best["throughput_ops_s"] / baseline
                                                if best and baseline else None))
    for metric in ("throughput_ops_s", "amortized_ns_op", "jit_bodies", "jit_share", "jit_status"):
        result[f"best_kdlock_{metric}"] = best[metric] if best else None
    return result


def summarize(out):
    plan = json.loads((out / "plan.json").read_text())
    records = {}
    rows = []
    for spec in plan:
        path = out / spec["name"] / "session.json"
        r = json.loads(path.read_text()) if path.exists() else dict(
            spec, execution_status="NOT_RUN", drained=False)
        records[spec["name"]] = r
        m = r.get("measurement", {})
        good = valid(r)
        row = {k: spec[k] for k in ("name", "cachelines", "threads", "iterations",
                                    "repeat", "arm")}
        row.update(placement(spec))
        row.update(cpus=",".join(map(str, spec["cpus"])),
                   execution_status=r["execution_status"], drained=r.get("drained", False),
                   jit_status=r.get("jit_status"), data_ok=m.get("data_ok"),
                   completed=m.get("completed"), wall_ns=m.get("wall_ns"),
                   worker_cpu_ns=m.get("worker_cpu_ns"),
                   throughput_ops_s=m["completed"] * 1e9 / m["wall_ns"] if good else None,
                   amortized_ns_op=m["wall_ns"] / m["completed"] if good else None,
                   jit_bodies=r.get("jit_bodies"), jit_share=r.get("jit_share"))
        rows.append(row)
    csv_file(out / "raw.csv", list(rows[0]), rows)
    pairs = []
    for i in range(0, len(plan), 2):
        a, b = (records[s["name"]] for s in plan[i:i+2])
        n, k = (a, b) if a["arm"] == "native" else (b, a)
        pairs.append(dict(cachelines=a["cachelines"], threads=a["threads"],
                          **placement(a),
                          iterations=a["iterations"], repeat=a["repeat"],
                          order=f"{a['arm']}->{b['arm']}",
                          kdlock_over_native=pair_ratio(n, k),
                          jit_status=k.get("jit_status"),
                          native_session=n["name"], kdlock_session=k["name"]))
    csv_file(out / "pairs.csv", list(pairs[0]), pairs)
    summaries = []
    for lines, threads in dict.fromkeys((s["cachelines"], s["threads"]) for s in plan):
        selected = [r for r in rows if (r["cachelines"], r["threads"]) == (lines, threads)]
        ratios = [p["kdlock_over_native"] for p in pairs
                  if (p["cachelines"], p["threads"]) == (lines, threads)
                  and p["kdlock_over_native"] is not None]
        entry = dict(cachelines=lines, threads=threads, valid_pairs=len(ratios),
                     numa_nodes=selected[0]["numa_nodes"], numa_scope=selected[0]["numa_scope"],
                     median_kdlock_over_native=statistics.median(ratios) if ratios else None,
                     measured_jit_bodies=sum(r["jit_bodies"] or 0 for r in selected
                                            if r["execution_status"] == "OK"),
                     no_jit_sessions=sum(r["jit_status"] == "NO_JIT" for r in selected))
        for arm in ("native", "kdlock"):
            for metric in ("throughput_ops_s", "amortized_ns_op", "jit_share"):
                values = [r[metric] for r in selected if r["arm"] == arm
                          and r["execution_status"] == "OK" and r[metric] is not None]
                entry[f"median_{arm}_{metric}"] = statistics.median(values) if values else None
        entry.update(best_comparison(selected))
        summaries.append(entry)
    csv_file(out / "summary.csv", list(summaries[0]), summaries)
    coverage = {str(lines): any(r["cachelines"] == lines and valid(r)
                               and (r.get("jit_bodies") or 0) > 0 for r in records.values())
                for lines in dict.fromkeys(s["cachelines"] for s in plan)}
    result = dict(comparison_policy=COMPARISON_POLICY,
                  sessions=len(plan), completed=sum(valid(r) for r in records.values()),
                  jit_verified_by_cachelines=coverage,
                  all_sizes_jit_verified=all(coverage.values()), configurations=summaries)
    write_json(out / "summary.json", result)
    print("Observed best kdlock / median native; throughput includes post-lock work when present.")
    print("lines threads  valid N/K  native median Mops/s  kdlock best Mops/s  best/median  best JIT share/status")
    for r in summaries:
        ratio = r["best_kdlock_over_median_native"]
        ratio_text = f"{ratio:.4f}" if ratio is not None else "--"
        native = r["median_native_throughput_ops_s"]
        best = r["best_kdlock_throughput_ops_s"]
        native_text = f"{native / 1e6:.3f}" if native is not None else "--"
        best_text = f"{best / 1e6:.3f}" if best is not None else "--"
        share = r["best_kdlock_jit_share"]
        share_text = f"{share:.2%}" if share is not None else "--"
        print(f"{r['cachelines']:5} {r['threads']:7} "
              f"{r['valid_native_sessions']:4}/{r['valid_kdlock_sessions']:<4} "
              f"{native_text:>20} {best_text:>19} {ratio_text:>12}  "
              f"{share_text} {r['best_kdlock_jit_status'] or '--'}")
        print(f"  best={r['best_kdlock_session'] or '--'}; "
              f"NUMA {r['numa_nodes'] or '--'} / {r['numa_scope']}")
    for size, checked in coverage.items():
        if not checked:
            print(f"{size} cacheline(s): JIT comparison remains UNVERIFIED")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    summarize(parser.parse_args().output)
