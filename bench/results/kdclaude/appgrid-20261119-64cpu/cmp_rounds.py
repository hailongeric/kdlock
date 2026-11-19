#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compare two rounds of the application grid at their common worker counts.

  cmp_rounds.py OLD.csv NEW.csv

Both files come from ../appgrid-20261118-64cpu/app_summary.py --csv. Per
benchmark and mode (native, kd off, kd on): the median and the range of
NEW/OLD over the worker counts both rounds have, and of NEW's on/off
against OLD's. The rounds are different boots and, for kd, different
kernels, so these ratios are indicators, not matched comparisons. Metis
values are seconds: its ratios are inverted so that above 1 means NEW is
faster.
"""
import csv
import statistics
import sys


def load(path):
    d, order = {}, []
    for r in csv.DictReader(open(path)):
        k = (r["bench"], r["variant"])
        if k not in order:
            order.append(k)
        d[k + (int(r["workers"]),)] = r
    return d, order


old, order = load(sys.argv[1])
new, _ = load(sys.argv[2])


def num(r, c):
    try:
        v = float(r[c])
        return v if v > 0 else None
    except (KeyError, ValueError):
        return None


def span(vals):
    if not vals:
        return "-"
    return "%.2f (%.2f-%.2f)" % (statistics.median(vals), min(vals), max(vals))


print("| benchmark | workers in both | native new/old | off new/old | on new/old | on/off old | on/off new |")
print("|---|---|---|---|---|---|---|")
for k in order:
    ns = sorted(n for (b, v, n) in old if (b, v) == k and (b, v, n) in new)
    if not ns:
        continue
    lower = k[0] == "metis"
    cols = []
    for c in ("native", "off", "on"):
        rs = []
        for n in ns:
            a, b = num(old[k + (n,)], c), num(new[k + (n,)], c)
            if a and b:
                rs.append(a / b if lower else b / a)
        cols.append(span(rs))
    for d in (old, new):
        rs = []
        for n in ns:
            a, b = num(d[k + (n,)], "off"), num(d[k + (n,)], "on")
            if a and b:
                rs.append(a / b if lower else b / a)
        cols.append(span(rs))
    print("| %s %s | %d | %s |" % (k[0], k[1], len(ns), " | ".join(cols)))
