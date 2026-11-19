#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Nano grid ratios by worker range: kd (delegated) against native and
TCLock, and kd in plain mode against native, from nano_grid.sh output.

  nano_ranges.py g1-nano.jsonl g1-nano-plain.jsonl

Medians over the rounds per point; min-max of the per-point ratios within
1-8 workers (one node, few), 12-32 (one node) and 36-64 (both nodes).
"""
import collections
import json
import statistics
import sys

def load(path):
    d = collections.defaultdict(list)
    for line in open(path):
        r = json.loads(line)
        if r["ok"] and not r.get("torn_reads"):
            d[(r["profile"], r["workers"], r["backend"])].append(r["mops"])
    return {k: statistics.median(v) for k, v in d.items()}

g, p = load(sys.argv[1]), load(sys.argv[2])
profiles = []
for (prof, _, _) in g:
    if prof not in profiles:
        profiles.append(prof)
ranges = [("1-8", range(1, 9)), ("12-32", range(12, 33)), ("36-64", range(36, 65))]
top = max(n for (_, n, _) in g)	# 64 in g1, 60 in g2

def span(prof, num, den, src_num, src_den):
    out = []
    for name, rg in ranges:
        rs = [src_num[(prof, n, num)] / src_den[(prof, n, den)] for n in rg
              if (prof, n, num) in src_num and (prof, n, den) in src_den]
        out.append("%.2f-%.2f" % (min(rs), max(rs)) if rs else "-")
    return out

print("| profile | kd/native 1-8 | 12-32 | 36-64 | kd/TCLock 1-8 | 12-32 | 36-64 | plain kd/native 1-8 | 12-32 | 36-64 | kd Mops/s at 32 / %d | native | TCLock |" % top)
print("|---|" + "---|" * 12)
for prof in profiles:
    a = span(prof, "kd", "native", g, g)
    b = span(prof, "kd", "tclock", g, g)
    c = span(prof, "kd", "native", p, g)
    at = lambda be: "%.2f / %.2f" % (g.get((prof, 32, be), 0), g.get((prof, top, be), 0))
    print("| %s | %s | %s | %s | %s | %s | %s |" % (prof, " | ".join(a), " | ".join(b), " | ".join(c),
                                                   at("kd"), at("native"), at("tclock")))
