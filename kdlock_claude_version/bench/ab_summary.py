#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Median [min-max] per point and parameter value of a run_ab.sh output."""
import json, sys, statistics
from collections import defaultdict
pts = defaultdict(list)
for l in open(sys.argv[1]):
    d = json.loads(l)
    if d["ok"]:
        pts[(d["profile"], d["workers"], d["backend"], d["commit"])].append(d["mops"])
vals = sorted({k[3] for k in pts})
print("%-14s %3s %-7s " % ("profile", "n", "backend") + " ".join("%22s" % v for v in vals))
for key in sorted({k[:3] for k in pts}):
    row = []
    for v in vals:
        m = pts.get(key + (v,), [])
        row.append("%7.3f [%5.2f-%5.2f]" % (statistics.median(m), min(m), max(m)) if m else "%22s" % "-")
    print("%-14s %3d %-7s " % key + " ".join(row))
