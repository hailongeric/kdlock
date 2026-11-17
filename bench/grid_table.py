#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""One row per (profile, workers) from a run_grid.py file: the rate of every
backend and the ratios, as CSV for plotting or as a markdown table.

    grid_table.py r10.jsonl                      # CSV to stdout
    grid_table.py r10.jsonl --format md          # markdown, one table per profile
    grid_table.py r10.jsonl --profiles spin_c01 mutex_c01
    grid_table.py r10.jsonl --stat min --format md

The value per point is the median over the rounds unless --stat says
otherwise; min and max of the rounds are always in the CSV, so the spread
stays visible. Points whose data oracle failed are counted in the `failed`
column and excluded from the statistics.
"""
import argparse
import collections
import json
import statistics
import sys

BACKENDS = ("native", "kd", "tclock")


def load(path):
    rates = collections.defaultdict(list)
    failed = collections.Counter()
    ident = {}
    for line in open(path):
        r = json.loads(line)
        key = (r["profile"], r["workers"], r["backend"])
        if r.get("ok"):
            rates[key].append(r["mops"])
        else:
            failed[key] += 1
        ident.setdefault("kernel", r.get("kernel"))
        ident.setdefault("build", r.get("build"))
        ident.setdefault("commit", r.get("commit"))
    return rates, failed, ident


def stat_of(values, stat):
    if not values:
        return None
    return {"median": statistics.median, "min": min, "max": max,
            "mean": statistics.mean}[stat](values)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("--format", choices=["csv", "md"], default="csv")
    ap.add_argument("--stat", choices=["median", "min", "max", "mean"], default="median")
    ap.add_argument("--profiles", nargs="+")
    ap.add_argument("--backends", nargs="+", default=list(BACKENDS))
    args = ap.parse_args()

    rates, failed, ident = load(args.file)
    profiles = args.profiles or sorted({k[0] for k in rates})
    workers = sorted({k[1] for k in rates})
    bes = [b for b in args.backends if any(k[2] == b for k in rates)]

    def val(p, n, b):
        return stat_of(rates.get((p, n, b), []), args.stat)

    if args.format == "csv":
        head = ["profile", "workers"]
        for b in bes:
            head += ["%s_mops" % b, "%s_min" % b, "%s_max" % b, "%s_rounds" % b]
        if "kd" in bes and "native" in bes:
            head.append("kd_over_native")
        if "kd" in bes and "tclock" in bes:
            head.append("kd_over_tclock")
        if "tclock" in bes and "native" in bes:
            head.append("tclock_over_native")
        head.append("failed")
        print(",".join(head))
        for p in profiles:
            for n in workers:
                if not any((p, n, b) in rates for b in bes):
                    continue
                row = [p, str(n)]
                for b in bes:
                    v = rates.get((p, n, b), [])
                    row += ["%.4f" % val(p, n, b) if v else "",
                            "%.4f" % min(v) if v else "",
                            "%.4f" % max(v) if v else "", str(len(v))]
                for a, b in (("kd", "native"), ("kd", "tclock"), ("tclock", "native")):
                    if a in bes and b in bes:
                        x, y = val(p, n, a), val(p, n, b)
                        row.append("%.4f" % (x / y) if x and y else "")
                row.append(str(sum(failed[(p, n, b)] for b in bes)))
                print(",".join(row))
        return 0

    print("Identity: %s %s commit %s. Value: %s of the rounds, Mops/s.\n"
          % (ident.get("kernel"), ident.get("build"), ident.get("commit"), args.stat))
    for p in profiles:
        ns = [n for n in workers if any((p, n, b) in rates for b in bes)]
        if not ns:
            continue
        print("### %s\n" % p)
        cols = ["workers"] + list(bes)
        if "kd" in bes and "native" in bes:
            cols.append("kd/Native")
        if "kd" in bes and "tclock" in bes:
            cols.append("kd/TCLock")
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for n in ns:
            row = ["%d" % n]
            for b in bes:
                v = val(p, n, b)
                row.append("%.2f" % v if v else "-")
            for a, b in (("kd", "native"), ("kd", "tclock")):
                if a in bes and b in bes:
                    x, y = val(p, n, a), val(p, n, b)
                    row.append("%.2f" % (x / y) if x and y else "-")
            print("| " + " | ".join(row) + " |")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
