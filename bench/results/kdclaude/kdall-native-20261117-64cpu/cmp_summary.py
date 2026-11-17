#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise runs.txt of suite.sh: kdall1 (off, on) against kdnat1 (native).

One row per workload and thread count: every value per mode (one per boot,
in boot order), the medians, on/native and off/native, and for "on" the
median delegated sections and handbacks per run. Rows of tags given with
--skip (learning passes) are left out.

  cmp_summary.py runs.txt [--skip learn] [--mode TAG=MODE ...]

--mode gives the runs of one tag another mode name, for runs of a second
kd kernel: those become an extra column, compared with native as well.
"""
import argparse
import re
import statistics
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("runs")
ap.add_argument("--skip", action="append", default=[])
ap.add_argument("--mode", action="append", default=[], help="TAG=MODE")
args = ap.parse_args()
relabel = dict(m.split("=", 1) for m in args.mode)

vals = defaultdict(lambda: defaultdict(list))
deleg = defaultdict(list)
hand = defaultdict(list)
order = []
for line in open(args.runs):
    left, _, rest = line.partition(" | ")
    f = left.split()
    if len(f) < 6 or any(f[0].startswith(s) for s in args.skip):
        continue
    tag, mode, kind, name, n, v = f[:6]
    mode = relabel.get(tag, mode)
    try:
        v = float(v)
    except ValueError:
        continue
    key = (kind, name, int(n))
    if key not in order:
        order.append(key)
    vals[key][mode].append(v)
    c = [x for x in re.split(r"\s*\|\s*", rest.strip())]
    if mode == "on" and len(c) == 2 and c[0] != "-":
        a, b = [list(map(int, x.split())) for x in c]
        deleg[key].append(b[0] - a[0])
        hand[key].append(b[1] - a[1])


def fmt(v):
    if v >= 1e6:
        return "%.3g M" % (v / 1e6)
    if v >= 1e4:
        return "%.0f k" % (v / 1e3)
    return "%d" % v


def med(xs):
    return statistics.median(xs) if xs else None


modes = ["off", "on"] + sorted({m for m in relabel.values()} - {"off", "on", "native"})
modes = [m for m in modes if any(vals[k][m] for k in order)]
print("| workload | threads | native | " + " | ".join("kd %s" % m for m in modes) + " | " +
      " | ".join("%s/native" % m for m in modes) + " | delegated, handbacks per on run (median) |")
print("|---|---|---|" + "---|" * (2 * len(modes)) + "---|")
for key in order:
    m = vals[key]
    nat = med(m["native"])

    def ratio(x):
        return "**%.2f**" % (x / nat) if x and nat else "-"

    print("| %s %s | %d | %s | %s | %s | %s |" % (
        key[0], key[1], key[2],
        ", ".join(fmt(x) for x in m["native"]),
        " | ".join(", ".join(fmt(x) for x in m[md]) for md in modes),
        " | ".join(ratio(med(m[md])) for md in modes),
        "%s, %s" % (fmt(med(deleg[key])), fmt(med(hand[key]))) if deleg[key] else "-"))
