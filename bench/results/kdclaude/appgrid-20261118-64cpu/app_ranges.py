#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Application grid ratios by worker range, from app_summary.py --csv.

  app_ranges.py app-g1.csv

Per benchmark: min-max of off/native and on/native within 1-8, 12-32 and
36-64 workers, the values at 32 and at the largest worker count of the
grid (64 in g1, 60 in g2), and the delegated sections there (on). Metis
ratios are native time / kd time (above 1: kd faster).
"""
import csv
import sys

rows = list(csv.DictReader(open(sys.argv[1])))
keys = []
for r in rows:
    k = (r["bench"], r["variant"])
    if k not in keys:
        keys.append(k)
ranges = [(1, 8), (12, 32), (36, 64)]
top = max(int(r["workers"]) for r in rows)

def fmt(x):
    x = float(x)
    if x >= 1e6:
        return "%.2fM" % (x / 1e6)
    if x >= 1e4:
        return "%.0fk" % (x / 1e3)
    return "%.3g" % x

print("| benchmark | off/native 1-8 | 12-32 | 36-64 | on/native 1-8 | 12-32 | 36-64 | native / off / on at 32 | at %d | delegated at %d |" % (top, top))
print("|---|" + "---|" * 9)
for k in keys:
    rs = [r for r in rows if (r["bench"], r["variant"]) == k]
    def span(col):
        out = []
        for lo, hi in ranges:
            v = [float(r[col]) for r in rs if lo <= int(r["workers"]) <= hi and r[col] not in ("", "-")]
            out.append("%.2f-%.2f" % (min(v), max(v)) if v else "-")
        return out
    def at(n):
        r = [r for r in rs if int(r["workers"]) == n]
        return " / ".join(fmt(r[0][c]) for c in ("native", "off", "on")) if r else "-"
    d64 = [r["delegated"] for r in rs if int(r["workers"]) == top]
    if k[0] == "apache" and k[1] == "default":
        r = rs[0]
        print("| apache default (once) | %s | | | %s | | | %s | | %s |" % (
            r["off_native"], r["on_native"], " / ".join(fmt(r[c]) for c in ("native", "off", "on")), r["delegated"]))
        continue
    print("| %s %s | %s | %s | %s | %s |" % (k[0], k[1], " | ".join(span("off_native")),
          " | ".join(span("on_native")), at(32) + " | " + at(top), d64[0] if d64 else "-"))
