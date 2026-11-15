#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""One row per (test, model, workers) from run_mmap1.py files: the rate of
each backend, the ratio, and how much delegation actually happened.

    wis_table.py wis_*.jsonl                 # markdown, one table per test
    wis_table.py wis_mmap1.jsonl --format csv

The rate per point is the median over the rounds; min and max are in the CSV,
so the spread stays visible. The delegation columns are the median of the
kdlock counter deltas of the kd rounds: `delegated` counts waiter sections the
combiner executed, `sessions` counts sessions opened, `handback` sessions that
returned the lock to the origin instead, `vdown` the write sides kept at a
downgrade. They are what separates "kdlock is not helping" from "kdlock is not
even running here".
"""
import argparse
import collections
import json
import statistics


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--format", choices=["md", "csv"], default="md")
    args = ap.parse_args()

    rates = collections.defaultdict(list)
    counters = collections.defaultdict(list)
    ident = {}
    for path in args.files:
        for line in open(path):
            r = json.loads(line)
            key = (r["test"], r["model"], r["workers"], r["backend"])
            if r.get("ok"):
                rates[key].append(r["rate"])
                d = r.get("kd_delta") or {}
                counters[key].append([d.get(k, 0) for k in
                                      ("delegated", "sessions", "handback", "vdown")])
            ident.setdefault("kernel", r.get("kernel"))
            ident.setdefault("build", r.get("build"))

    def med(v):
        return statistics.median(v) if v else None

    def cnt(key):
        c = counters.get(key, [])
        return [int(statistics.median([x[i] for x in c])) if c else 0 for i in range(4)]

    tests = sorted({k[0] for k in rates})
    if args.format == "csv":
        print("test,model,workers,native_rate,native_min,native_max,kd_rate,kd_min,"
              "kd_max,kd_over_native,delegated,sessions,handback,vdown")
        for t in tests:
            for m in ("threads", "processes"):
                for n in sorted({k[2] for k in rates if k[0] == t and k[1] == m}):
                    nv = rates.get((t, m, n, "native"), [])
                    kv = rates.get((t, m, n, "kd"), [])
                    row = [t, m, str(n)]
                    for v in (nv, kv):
                        row += ["%.0f" % med(v) if v else "", "%.0f" % min(v) if v else "",
                                "%.0f" % max(v) if v else ""]
                    row.append("%.4f" % (med(kv) / med(nv)) if nv and kv else "")
                    row += [str(x) for x in cnt((t, m, n, "kd"))]
                    print(",".join(row))
        return 0

    print("Identity: %s %s. Rate: median of the rounds, ops/s.\n"
          % (ident.get("kernel"), ident.get("build")))
    for t in tests:
        for m in ("threads", "processes"):
            ns = sorted({k[2] for k in rates if k[0] == t and k[1] == m})
            if not ns:
                continue
            print("### %s / %s\n" % (t, m))
            print("| workers | native | kd | kd/Native | delegated | sessions "
                  "| handback | vdown |")
            print("|---|---|---|---|---|---|---|---|")
            for n in ns:
                nv = rates.get((t, m, n, "native"), [])
                kv = rates.get((t, m, n, "kd"), [])
                print("| %d | %s | %s | %s | %d | %d | %d | %d |" % (
                    n, "%.0f" % med(nv) if nv else "-", "%.0f" % med(kv) if kv else "-",
                    "%.3f" % (med(kv) / med(nv)) if nv and kv else "-",
                    *cnt((t, m, n, "kd"))))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
