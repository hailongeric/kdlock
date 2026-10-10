#!/usr/bin/env python3
"""Create a bounded-run performance report from immutable guest evidence.

Run plots in the recovery guest. Host use is limited to offline JSON/CSV
analysis with --no-plots. No archive members are extracted or executed.
"""
import argparse
import collections
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import statistics
import sys
import tarfile


ARMS = ("native", "tclock", "kdlock")
LABELS = {"native": "Linux Native", "tclock": "TCLock", "kdlock": "KDLock"}
COLORS = {"native": "#626973", "tclock": "#0072B2", "kdlock": "#D55E00"}
FAMILIES = ("rwlock-rcuht", "spin-cacheline", "mutex-cacheline")
TITLES = {"rwlock-rcuht": "Rwlock · RCU hash table", "spin-cacheline": "Spin · one cache line",
          "mutex-cacheline": "Mutex · one cache line"}
JSON_NAMES = {"records.json", "plan.json", "environment.json", "parity.json", "source-state.json",
              "host-environment.json", "run-metadata.json", "metadata.json", "source-sha256.json",
              "build-sha256.json", "validation.json", "guest-environment.json", "kernel-identity.json",
              "final-audit.json", "host-final-state.json"}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_inputs(path):
    """Read only bounded regular JSON payloads; reject unsafe member paths."""
    documents = {}
    if path.is_dir():
        for file in sorted(path.rglob("*.json")):
            if file.name not in JSON_NAMES:
                continue
            if file.is_symlink() or any(parent.is_symlink() for parent in file.parents if parent != path.parent):
                raise ValueError(f"symlink in evidence path: {file}")
            if file.stat().st_size > 64 * 1024 * 1024:
                raise ValueError(f"oversized JSON: {file}")
            documents[file.relative_to(path).as_posix()] = json.loads(file.read_text())
    else:
        with tarfile.open(path, "r:*") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts:
                    raise ValueError(f"unsafe archive path: {member.name}")
                if name.name not in JSON_NAMES:
                    continue
                if not member.isfile() or member.size > 64 * 1024 * 1024:
                    raise ValueError(f"unsafe JSON member: {member.name}")
                if member.name in documents:
                    raise ValueError(f"duplicate JSON member: {member.name}")
                with archive.extractfile(member) as stream:
                    documents[member.name] = json.load(stream)
    return documents


def valid(row):
    # This is performance-data acceptance, matching the runner's valid() gate.
    # JIT acceptance is a distinct verdict: Native/TCLock may leave it null,
    # and an adaptive KD sample can validly finish with no returned JIT body.
    # A runner-rejected NO_JIT has execution_status != OK and is excluded here.
    m = row.get("measurement", {})
    return (row.get("execution_status") == "OK" and row.get("drained") is True
            and m.get("data_ok") is True and m.get("complete") is True
            and not row.get("functional", False) and row.get("duration_ms", 0) > 0
            and m.get("completed", 0) > 0 and m.get("wall_ns", 0) > 0
            and m.get("peak", {}).get("throughput_ops_s", 0) > 0)


def finite(value):
    if value is not None and (not isinstance(value, (float, int)) or not math.isfinite(value)):
        raise ValueError(f"invalid numeric metric: {value!r}")
    return value


def sample(family, row):
    m = row.get("measurement", {})
    peak = m.get("peak", {})
    arm = row["arm"]
    jit = row.get("jit_bodies", 0)
    accepted = valid(row)
    execution_type = ("ACTUAL_JIT" if jit > 0 else "NO_JIT") if arm == "kdlock" else "NATIVE_IMPLEMENTATION"
    return dict(family=family, workload=row.get("workload"), write_percent=row.get("write_percent"),
                cachelines=row.get("cachelines"), threads=row["threads"], arm=arm,
                name=row["name"], repeat=row.get("repeat"), execution_status=row.get("execution_status"),
                accepted=accepted, drained=row.get("drained"), complete=m.get("complete"),
                data_ok=m.get("data_ok"), jit_bodies=jit, execution_type=execution_type,
                jit_status=row.get("jit_status"), jit_acceptance=row.get("jit_acceptance"),
                delegated_bodies=row.get("delegated_bodies"),
                delegation_status=row.get("delegation_status", row.get("tclock_delegation_status")),
                jit_share=row.get("jit_share"), jit_writer_share=row.get("jit_writer_share"),
                duration_ms=row.get("duration_ms"), peak_window_ms=row.get("peak_window_ms"),
                peak_settle_ms=row.get("peak_settle_ms"), collector_cpu=row.get("collector_cpu"),
                cpus=row.get("cpus"), cpu_nodes=row.get("cpu_nodes"),
                post_work_rounds=row.get("post_work_rounds", row.get("layout", {}).get("post_work_rounds")),
                caller_shell=row.get("caller_shell"), cookie_storage=row.get("cookie_storage"),
                provider_ubsan=row.get("provider_ubsan", row.get("kd_provider_ubsan")),
                spin_entry_ratio_limit=row.get("spin_entry_ratio_limit"),
                spin_prefetch=row.get("spin_prefetch"), numa_policy=row.get("numa_policy"),
                delegation_batch_limit=row.get("delegation_batch_limit"),
                completed=m.get("completed"), wall_ns=m.get("wall_ns"),
                peak_ops_s=finite(peak.get("throughput_ops_s")),
                whole_ops_s=finite(m["completed"] * 1e9 / m["wall_ns"]) if m.get("wall_ns", 0) > 0 else None)


def group_key(s):
    return s["family"], s["write_percent"], s["threads"], s["arm"]


def group_statistics(key, rows, status=None):
    accepted = [s for s in rows if s["accepted"]]
    family, percent, threads, arm = key
    result = dict(family=family, write_percent=percent, threads=threads, arm=arm,
                  expected_rounds=3, sessions=len(rows), valid_rounds=len(accepted),
                  complete=len(rows) == 3 and len(accepted) == 3,
                  actual_jit_rounds=sum(s["jit_bodies"] > 0 for s in accepted),
                  no_jit_rounds=sum(s["jit_bodies"] == 0 for s in accepted) if arm == "kdlock" else None,
                  execution_status_counts=dict(collections.Counter(s["execution_status"] for s in rows)),
                  jit_status_counts=dict(collections.Counter(s["jit_status"] or "UNRECORDED" for s in rows)),
                  jit_acceptance_counts=dict(collections.Counter(s["jit_acceptance"] or "UNRECORDED" for s in rows)),
                  delegation_status_counts=dict(collections.Counter(s["delegation_status"] or "UNRECORDED" for s in rows)),
                  execution_type=status or ("NATIVE_IMPLEMENTATION" if arm != "kdlock" else
                      "MIXED" if len({s["execution_type"] for s in accepted}) > 1 else
                      accepted[0]["execution_type"] if accepted else "NO_VALID_SAMPLE"),
                  samples=[s["name"] for s in rows])
    for metric in ("peak", "whole"):
        values = [s[metric + "_ops_s"] for s in accepted]
        result[metric + "_min_ops_s"] = min(values) if values else None
        result[metric + "_median_ops_s"] = statistics.median(values) if values else None
        result[metric + "_max_ops_s"] = max(values) if values else None
        result[metric + "_spread_pct"] = 100 * (max(values) - min(values)) / statistics.median(values) if len(values) > 1 else None
    best = max(accepted, key=lambda s: s["peak_ops_s"]) if accepted else None
    result["best_peak_session"] = best["name"] if best else None
    result["best_peak_ops_s"] = best["peak_ops_s"] if best else None
    return result


def csv_write(path, rows):
    if not rows:
        path.write_text("")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, (list, dict)) else v
                         for k, v in row.items()} for row in rows)


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def comparisons(groups):
    points = collections.defaultdict(dict)
    for g in groups:
        points[(g["family"], g["write_percent"], g["threads"])][g["arm"]] = g
    result = []
    for (family, percent, threads), arms in sorted(points.items(), key=lambda p: (p[0][0], p[0][1] or -1, p[0][2])):
        r = dict(family=family, write_percent=percent, threads=threads, status="INCOMPLETE")
        if set(arms) == set(ARMS) and all(g["complete"] for g in arms.values()):
            kd = arms["kdlock"]
            r.update(kd_execution_type=kd["execution_type"], kd_actual_jit_rounds=kd["actual_jit_rounds"],
                     kd_no_jit_rounds=kd["no_jit_rounds"])
            for arm in ("native", "tclock"):
                for metric, field in (("best_peak", "best_peak_ops_s"), ("median_whole", "whole_median_ops_s")):
                    r[f"kd_over_{arm}_{metric}"] = kd[field] / arms[arm][field]
            ratios = [v for k, v in r.items() if k.startswith("kd_over_")]
            r["descriptive_throughput_status"] = "PASS" if all(v >= 1 for v in ratios) else "FAIL"
            # Preserve the runner's status-separated parity convention. The
            # pooled 3-round overview remains descriptive if JIT is mixed.
            r["status"] = "MIXED_EXECUTION" if kd["execution_type"] == "MIXED" else r["descriptive_throughput_status"]
        result.append(r)
    return result


def table(rows, headers, columns):
    return "| " + " | ".join(headers) + " |\n| " + " | ".join("---" for _ in headers) + " |\n" + "\n".join(
        "| " + " | ".join(str(col(r)) for col in columns) + " |" for r in rows)


def rate(value):
    return f"{value / 1e6:.3f}" if value is not None else "—"


def range_rate(r, metric):
    return f'{rate(r[metric + "_min_ops_s"])} / {rate(r[metric + "_median_ops_s"])} / {rate(r[metric + "_max_ops_s"])}'


def markdown(groups, samples, comparison, info):
    total, accepted = len(samples), sum(s["accepted"] for s in samples)
    passed = sum(r["status"] == "PASS" for r in comparison)
    kd_samples = [s for s in samples if s["arm"] == "kdlock" and s["accepted"]]
    jit_samples = sum(s["jit_bodies"] > 0 for s in kd_samples)
    metadata = {PurePosixPath(name).name: data for name, data in info["captured_metadata"].items()}
    source = metadata.get("source-state.json", {})
    host = metadata.get("host-environment.json", {})
    governors = sorted(set(host.get("governors", {}).values()))
    selected = []
    for family, percent, workers in (("rwlock-rcuht", 1, 56), ("rwlock-rcuht", 20, 56),
                                     ("spin-cacheline", None, 36), ("mutex-cacheline", None, 36)):
        arms = {r["arm"]: r for r in groups if (r["family"], r["write_percent"], r["threads"]) ==
                (family, percent, workers)}
        if set(arms) == set(ARMS):
            selected.append(dict(case=TITLES[family] + (f" · {percent}% writes" if percent else ""),
                                 workers=workers, arms=arms))
    lines = ["# Performance measurements on 10.176.26.71", "",
             f"This report covers {total} timed sessions in the 64-vCPU guest; {accepted} satisfy execution, business-result, full measurement and drain checks.", "",
             f"KD met both Linux Native and TCLock on both best warmed peak and median whole-run throughput in **{passed} of {len(comparison)} selected configurations**. The per-case comparisons below retain every measured throughput deficit.", "",
             "Selected larger-worker results, in **Mops/s**; each cell is **best warmed peak / median whole-run**. Compare backends within each row, since rwlock and spin/mutex perform different work:", "",
             table(selected, ["Workload", "Workers", "Linux Native", "TCLock", "KDLock"],
                   [lambda r: r["case"], lambda r: r["workers"],
                    *[lambda r, arm=arm: rate(r["arms"][arm]["best_peak_ops_s"]) + " / " +
                      rate(r["arms"][arm]["whole_median_ops_s"]) for arm in ARMS]]), "",
             "The VM has 32 cores per NUMA node, each vCPU pinned to the same host core. Workers use consecutive CPUs starting at 0; 32 workers fit node 0, while 36 and 56 workers span both nodes. Collector CPU 63 is excluded from workers and shares its host core with QEMU service threads.", "",
             f"Source was synchronized from `380G10` at Git HEAD `{source.get('git_head', 'unrecorded')}` **plus {len(source.get('git_status', '').splitlines())} captured working-tree edits**; the source manifest identifies the actual tested bytes. Host `{host.get('hostname', 'unrecorded')}` used governor `{', '.join(governors) or 'unrecorded'}` throughout; frequency policy was preserved.", "",
             "Each backend/configuration has three rounds: 2,000 ms measured duration, 300 ms warmed peak window after a 300 ms settling interval, with 48,000 warmup operations per worker. Rwlock uses the RCU hash-table workload with 1% or 20% writes and 4 post-work rounds; spin/mutex use one shared cache line and the frozen 64-round post-work default.", "",
             f"Of {len(kd_samples)} valid KD sessions, **{jit_samples} returned JIT bodies and {len(kd_samples)-jit_samples} were NO_JIT native controls**. Tables and open chart markers identify those controls; their throughput does not prove JIT gain. Status-separated aggregates and the original rwlock parity verdict are retained. Failed or undrained samples are excluded from scores and produce gaps in primary curves.", "",
             "All rates below are **million operations per second (Mops/s)**. Peak is the highest valid warmed 300 ms window across three rounds. Whole-run is completed operations divided by measured wall time. Range columns show min / median / max. Spread is `(max − min) / median × 100%`, separately for each metric; it is observed variation, not a confidence interval.", "",
             "![Whole-run throughput](whole-throughput.png)", "",
             "![Best warmed peak throughput](peak-throughput.png)", ""]
    for family, percent in (("rwlock-rcuht", 1), ("rwlock-rcuht", 20), ("spin-cacheline", None), ("mutex-cacheline", None)):
        subset = [r for r in groups if r["family"] == family and r["write_percent"] == percent]
        if not subset:
            continue
        subset.sort(key=lambda r: (r["threads"], ARMS.index(r["arm"])))
        title = TITLES[family] + (f" · {percent}% writes" if percent is not None else "")
        lines += [f"## {title}", "", table(subset,
                  ["Workers", "Backend", "Valid", "Best peak", "Peak min / median / max", "Peak spread", "Whole min / median / max", "Whole spread", "KD returned-body evidence"],
                  [lambda r: r["threads"], lambda r: LABELS[r["arm"]],
                   lambda r: f'{r["valid_rounds"]}/{r["sessions"]}', lambda r: rate(r["best_peak_ops_s"]),
                   lambda r: range_rate(r, "peak"), lambda r: f'{r["peak_spread_pct"]:.2f}%' if r["peak_spread_pct"] is not None else "—",
                   lambda r: range_rate(r, "whole"), lambda r: f'{r["whole_spread_pct"]:.2f}%' if r["whole_spread_pct"] is not None else "—",
                   lambda r: f'{r["actual_jit_rounds"]} JIT / {r["no_jit_rounds"]} NO_JIT ({r["execution_type"]})' if r["arm"] == "kdlock" else "not applicable"]), ""]
    lines += ["## Backend comparisons", "", "Ratios compare KDLock with each backend at the same workload and worker count. A ratio above 1 means higher observed throughput. PASS requires both best warmed peak and median whole-run throughput to meet both comparators. MIXED_EXECUTION retains the descriptive ratios but does not convert mixed JIT/NO_JIT evidence into a status-separated parity pass.", "",
              table(comparison, ["Case", "Workers", "KD / Native peak", "KD / Native whole", "KD / TCLock peak", "KD / TCLock whole", "Throughput status"],
                    [lambda r: r["family"] + (f' {r["write_percent"]}%' if r["write_percent"] is not None else ""), lambda r: r["threads"],
                     *[lambda r, k=k: f'{r[k]:.3f}×' if k in r else "—" for k in
                       ("kd_over_native_best_peak", "kd_over_native_median_whole", "kd_over_tclock_best_peak", "kd_over_tclock_median_whole")],
                     lambda r: r["status"]]), "", "## Evidence and limits", "",
              "This is a bounded workload selection, not the full project test suite or benchmark matrix. It measures current source bytes in one VM boot; it does not establish gains against the original host or the earlier 60-vCPU migration run. Host governor and measured ranges remain part of the evidence rather than a claim of fixed-frequency reproducibility.", "",
              "- [Raw session metrics](samples.csv)", "- [Three-round statistics](statistics.csv)",
              "- [Status-separated statistics](statistics-by-execution.csv)",
              "- [Comparison ratios](comparison.csv)", "- [Environment and provenance](evidence.json)", "",
              "Commands, kernel identity, boot policy, source/ELF hashes, raw worker measurements, publication/retirement evidence and failed samples remain in the accompanying raw archive. The report exporter does not rerun or modify any benchmark.", ""]
    environments = info["environments"]
    if environments:
        lines += ["## Captured environment and commands", "", table(
            [{"family": family, "env": env} for family, env in environments.items()],
            ["Runner", "Guest kernel", "Verified live Build ID", "Preemption", "Recovery snapshot"],
            [lambda r: r["family"], lambda r: r["env"].get("uname", ["", "", "unrecorded"])[2],
             lambda r: r["env"].get("kernel_identity", {}).get("running_build_id", "unrecorded"),
             lambda r: r["env"].get("preemption", "unrecorded").strip(),
             lambda r: r["env"].get("snapshot_tag", "unrecorded")]), ""]
        for family, env in environments.items():
            import shlex
            lines += [f"{family}:", "", "```sh", shlex.join(env.get("argv", [])), "```", ""]
    failures = [s for s in samples if not s["accepted"]]
    if failures:
        lines += ["## Excluded sessions", "", table(failures, ["Family", "Session", "Execution", "Drained", "Data OK"],
                  [lambda r: r["family"], lambda r: r["name"], lambda r: r["execution_status"], lambda r: r["drained"], lambda r: r["data_ok"]]), ""]
    return "\n".join(lines)


def plot(groups, output, node_cores):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.titleweight": "bold", "axes.labelcolor": "#303743",
                         "text.color": "#202832", "axes.edgecolor": "#BCC3CC",
                         "grid.color": "#DCE1E8", "grid.alpha": .7,
                         "svg.fonttype": "none", "savefig.facecolor": "white"})
    panels = (("rwlock-rcuht", 1), ("rwlock-rcuht", 20), ("spin-cacheline", None), ("mutex-cacheline", None))
    for metric in ("whole", "peak"):
        fig, axs = plt.subplots(2, 2, figsize=(14, 10), dpi=160)
        for ax, (family, percent) in zip(axs.flat, panels):
            subset = [r for r in groups if r["family"] == family and r["write_percent"] == percent]
            ticks = sorted({r["threads"] for r in subset})
            ax.set_title(TITLES[family] + (f" · {percent}% writes" if percent is not None else ""), loc="left", pad=14)
            if not ticks:
                ax.text(.5, .5, "No timed samples", transform=ax.transAxes, ha="center")
                continue
            xmax = max(ticks) + max(1.5, max(ticks) * .045)
            ax.set_xlim(0, xmax)
            if max(ticks) > node_cores:
                ax.axvspan(node_cores + .5, xmax, color="#F2F4F7", zorder=0)
                ax.axvline(node_cores + .5, color="#88919D", linestyle=":", linewidth=1.2)
                ax.text(.98, .97, "workers span 2 nodes", transform=ax.transAxes, ha="right", va="top", fontsize=9, color="#5F6873")
            incomplete = []
            for arm in ARMS:
                rows = sorted((r for r in subset if r["arm"] == arm), key=lambda r: r["threads"])
                x = [r["threads"] for r in rows]
                y = np.array([(r["whole_median_ops_s"] if metric == "whole" else r["best_peak_ops_s"])
                              if r["complete"] else np.nan for r in rows]) / 1e6
                low = np.array([r[metric + "_min_ops_s"] if r["complete"] else np.nan for r in rows]) / 1e6
                high = np.array([r[metric + "_max_ops_s"] if r["complete"] else np.nan for r in rows]) / 1e6
                incomplete.extend(f'{LABELS[arm]} at {r["threads"]} workers ({r["valid_rounds"]}/3 valid)'
                                  for r in rows if not r["complete"])
                color = COLORS[arm]
                ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=5.7, label=LABELS[arm], zorder=3)
                ax.errorbar(x, y, yerr=[np.maximum(0, y-low), np.maximum(0, high-y)], fmt="none", ecolor=color,
                            capsize=3.5, elinewidth=1.15, alpha=.75, zorder=2)
                if arm == "kdlock":
                    for r, xx, yy in zip(rows, x, y):
                        if not r["complete"]:
                            continue
                        if r["execution_type"] == "NO_JIT":
                            ax.plot(xx, yy, marker="o", markerfacecolor="white", markeredgecolor=color, markeredgewidth=1.8, markersize=7, zorder=5)
                        elif r["execution_type"] == "MIXED":
                            ax.plot(xx, yy, marker="D", markerfacecolor="white", markeredgecolor=color, markeredgewidth=1.8, markersize=7, zorder=5)
            if incomplete:
                ax.text(.025, .045, "Curve gaps: " + "; ".join(incomplete), transform=ax.transAxes,
                        ha="left", va="bottom", fontsize=8.3, color="#59636F", wrap=True,
                        bbox={"facecolor": "white", "edgecolor": "none", "alpha": .85, "pad": 3})
            ax.set_xticks(ticks)
            ax.set_xlabel("Worker cores")
            ax.set_ylabel("Throughput (Mops/s)")
            ax.set_ylim(bottom=0)
            ax.grid(axis="y")
            ax.spines[["top", "right"]].set_visible(False)
        title = "Whole-run throughput" if metric == "whole" else "Best warmed peak throughput"
        subtitle = ("Median of 3 valid rounds · whiskers show min–max" if metric == "whole" else
                    "Highest valid 300 ms peak across 3 rounds · whiskers extend to lowest round peak")
        fig.suptitle(title + " on 10.176.26.71", x=.07, y=.98, ha="left", fontsize=20, fontweight="bold")
        fig.text(.07, .932, subtitle + "\n64 vCPUs · 32 cores per node · collector CPU 63 · 2 s measured duration", ha="left", va="top", fontsize=11, color="#59636F", linespacing=1.6)
        handles = [Line2D([0], [0], color=COLORS[a], marker="o", linewidth=2, label=LABELS[a]) for a in ARMS]
        handles += [Line2D([0], [0], color=COLORS["kdlock"], marker="o", markerfacecolor="white", linestyle="none", label="KD: NO_JIT")]
        if any(g["execution_type"] == "MIXED" for g in groups):
            handles += [Line2D([0], [0], color=COLORS["kdlock"], marker="D", markerfacecolor="white", linestyle="none", label="KD: mixed JIT / NO_JIT")]
        fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, bbox_to_anchor=(.5, .015), fontsize=10)
        fig.subplots_adjust(top=.82, bottom=.13, left=.075, right=.97, hspace=.42, wspace=.22)
        stem = "whole-throughput" if metric == "whole" else "peak-throughput"
        fig.savefig(output / (stem + ".png"), dpi=180)
        svg_path = output / (stem + ".svg")
        fig.savefig(svg_path)
        svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text().splitlines()) + "\n")
        plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="run directory or evidence.tar.gz")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--metadata", type=Path, help="additional captured source/host metadata JSON")
    p.add_argument("--no-plots", action="store_true", help="offline host analysis; do not import plotting packages")
    p.add_argument("--expect-sessions", type=int, default=144)
    p.add_argument("--expect-vcpus", type=int, default=64)
    p.add_argument("--collector-cpu", type=int, default=63)
    p.add_argument("--node-cores", type=int, default=32)
    args = p.parse_args()
    if not args.no_plots and (os.uname().release != "6.1.159-kdclobber2" or os.geteuid() != 0):
        raise ValueError("render figures inside the recovery guest; host archive analysis must use --no-plots")
    docs = read_inputs(args.input)
    samples, envs, original_parity = [], {}, {}
    for name, data in sorted(docs.items()):
        pure = PurePosixPath(name)
        if pure.name == "records.json":
            family = pure.parent.name
            if family not in FAMILIES:
                continue
            if not isinstance(data, list):
                raise ValueError(f"records must be a list: {name}")
            samples.extend(sample(family, row) for row in data)
        elif pure.name == "environment.json" and pure.parent.name in FAMILIES:
            envs[pure.parent.name] = data
        elif pure.name == "parity.json":
            original_parity[name] = data
    if not samples:
        raise ValueError("no records for rwlock-rcuht / spin-cacheline / mutex-cacheline")
    if args.expect_sessions and len(samples) != args.expect_sessions:
        raise ValueError(f"expected {args.expect_sessions} sessions, found {len(samples)}")
    if args.expect_sessions == 144:
        counts = dict(collections.Counter(s["family"] for s in samples))
        expected = {"rwlock-rcuht": 72, "spin-cacheline": 36, "mutex-cacheline": 36}
        if counts != expected or set(envs) != set(FAMILIES):
            raise ValueError(f"incomplete bounded matrix/environment: {counts}")
        if len({(s["family"], s["name"]) for s in samples}) != len(samples):
            raise ValueError("duplicate session identities")
        if any((s["duration_ms"], s["peak_window_ms"], s["peak_settle_ms"]) != (2000, 300, 300)
               for s in samples):
            raise ValueError("timing configuration differs from the bounded report")
        if any(s["family"] == "rwlock-rcuht" and
               (s["workload"] != "rcuht" or s["post_work_rounds"] != 4 or
                s["write_percent"] not in (1, 20) or s["threads"] not in (1, 16, 32, 56)) or
               s["family"] != "rwlock-rcuht" and
               (s["workload"] != "cacheline" or s["cachelines"] != 1 or s["threads"] not in (1, 16, 32, 36))
               for s in samples):
            raise ValueError("workload selection differs from the bounded report")
    for family, env in envs.items():
        actual_cpus = env.get("topology", {}).get("online_cpus", [])
        if args.expect_vcpus and actual_cpus != list(range(args.expect_vcpus)):
            raise ValueError(f"{family}: expected {args.expect_vcpus} vCPUs, found {len(actual_cpus)}")
    if any(s["collector_cpu"] != args.collector_cpu or args.collector_cpu in s["cpus"] for s in samples):
        raise ValueError("collector CPU differs or overlaps workers")
    if any(s["cpus"] != list(range(s["threads"])) or
           s["cpu_nodes"] != [cpu // args.node_cores for cpu in s["cpus"]] for s in samples):
        raise ValueError("worker CPU/node placement differs from consecutive pinned topology")
    grouped = collections.defaultdict(list)
    separated = collections.defaultdict(list)
    for s in samples:
        grouped[group_key(s)].append(s)
        separated[group_key(s) + (s["execution_type"],)].append(s)
    if args.expect_sessions == 144 and any(len(rows) != 3 or {s["repeat"] for s in rows} != {0, 1, 2}
                                           for rows in grouped.values()):
        raise ValueError("need the three distinct planned repeats per backend configuration")
    groups = [group_statistics(key, rows) for key, rows in grouped.items()]
    separate_groups = [group_statistics(key[:4], rows, key[4]) for key, rows in separated.items()]
    groups.sort(key=lambda r: (FAMILIES.index(r["family"]), r["write_percent"] or -1, r["threads"], ARMS.index(r["arm"])))
    comparison = comparisons(groups)
    info = dict(input=str(args.input), archive_sha256=digest(args.input) if args.input.is_file() else None,
                sessions=len(samples), accepted_sessions=sum(s["accepted"] for s in samples),
                excluded_sessions=sum(not s["accepted"] for s in samples),
                execution_status_counts=dict(collections.Counter(s["execution_status"] for s in samples)),
                groups=len(groups), environments=envs, original_runner_parity=original_parity,
                captured_metadata={name: value for name, value in docs.items() if PurePosixPath(name).name in
                                   {"source-state.json", "host-environment.json", "run-metadata.json", "metadata.json", "validation.json",
                                    "guest-environment.json", "kernel-identity.json", "final-audit.json", "host-final-state.json"}},
                mixed_execution_groups=[g for g in groups if g["execution_type"] == "MIXED"],
                statistics_policy="Three-repeat descriptive backend overview; status-separated aggregates retained; excluded samples never scored; spread=(max-min)/median*100",
                report_generator_sha256=digest(Path(__file__)),
                reporting_environment=dict(python=sys.executable, python_version=sys.version,
                                           kernel=os.uname().release,
                                           packages={name: importlib.metadata.version(name) for name in
                                                     ("matplotlib", "numpy")} if not args.no_plots else {}),
                acceptance_policy="Execution OK + drained + complete + data_ok + valid timed metrics; raw jit_acceptance is a separate verdict and null does not veto valid baseline/adaptive performance evidence",
                plots_generated_in_guest=not args.no_plots)
    if args.metadata:
        info["additional_metadata"] = json.loads(args.metadata.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    for stem, rows in (("samples", samples), ("statistics", groups), ("statistics-by-execution", separate_groups), ("comparison", comparison)):
        csv_write(args.output / (stem + ".csv"), rows)
        json_write(args.output / (stem + ".json"), rows)
    json_write(args.output / "evidence.json", info)
    (args.output / "README.md").write_text(markdown(groups, samples, comparison, info))
    if not args.no_plots:
        plot(groups, args.output, args.node_cores)
    print(json.dumps({"output": str(args.output), "sessions": info["sessions"], "accepted": info["accepted_sessions"],
                      "excluded": info["excluded_sessions"], "groups": len(groups), "mixed_groups": len(info["mixed_execution_groups"]),
                      "comparison": dict(collections.Counter(r["status"] for r in comparison))}, sort_keys=True))


if __name__ == "__main__":
    main()
