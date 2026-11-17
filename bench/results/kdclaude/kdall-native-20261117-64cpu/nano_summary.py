#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise run_grid.py output: kd/native per profile and worker count.

  nano_summary.py OUT.jsonl [OUT.jsonl.era0]

With a second file (the same boot, kd_rw_era_ns=0), its kd rates are shown
next to the first file's, as a ratio to the same native median.
"""
import json
import statistics
import sys
from collections import defaultdict


def load(path):
    d, bad = defaultdict(list), 0
    for line in open(path):
        r = json.loads(line)
        if not r.get("ok"):
            bad += 1
            continue
        d[(r["profile"], r["workers"], r["backend"])].append(r["mops"])
    return d, bad


d, bad = load(sys.argv[1])
e, ebad = load(sys.argv[2]) if len(sys.argv) > 2 else ({}, 0)
print("failed points: %d%s" % (bad, ", era0: %d" % ebad if len(sys.argv) > 2 else ""))
print("| profile | workers | native | kd | kd/native |%s" % (" kd, eras off | /native |" if e else ""))
print("|---|---|---|---|---|%s" % ("---|---|" if e else ""))
profiles = []
for k in d:
    if k[0] not in profiles:
        profiles.append(k[0])
for p in profiles:
    for w in sorted({k[1] for k in d if k[0] == p}):
        n, k = d[(p, w, "native")], d[(p, w, "kd")]
        nat = statistics.median(n)
        row = "| %s | %d | %s | %s | **%.2f** |" % (
            p, w, "/".join("%.2f" % x for x in n), "/".join("%.2f" % x for x in k),
            statistics.median(k) / nat)
        if e:
            k0 = e.get((p, w, "kd"))
            row += (" %s | %.2f |" % ("/".join("%.2f" % x for x in k0), statistics.median(k0) / nat)
                    if k0 else " | |")
        print(row)
