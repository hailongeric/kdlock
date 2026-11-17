#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Before and after the optimizations, each against its own native boots.

runs.txt holds two comparisons of suite.sh: tags b1-b6 (kdall1 against
kdnat1) and a1-a6 (kdall3 against kdnat1, later boots). For each, the
ratio of medians to that comparison's native runs; a ratio is marked "~"
when the three kd runs overlap the three native runs.

  before_after.py runs.txt
"""
import statistics
import sys
from collections import defaultdict

vals = defaultdict(lambda: defaultdict(list))
order = []
for line in open(sys.argv[1]):
    f = line.partition(" | ")[0].split()
    if len(f) < 6 or f[0][0] not in "ab" or not f[0][1:].isdigit():
        continue
    try:
        v = float(f[5])
    except ValueError:
        continue
    key = (f[2], f[3], int(f[4]))
    if key not in order:
        order.append(key)
    vals[key][(f[0][0], f[1])].append(v)


def ratio(kd, nat):
    if not kd or not nat:
        return "-"
    r = statistics.median(kd) / statistics.median(nat)
    overlap = max(min(kd), min(nat)) <= min(max(kd), max(nat))
    return ("~%.2f" if overlap else "**%.2f**") % r


print("| workload | threads | before: off/native | before: on/native | after: off/native | after: on/native |")
print("|---|---|---|---|---|---|")
for key in order:
    m = vals[key]
    print("| %s %s | %d | %s | %s | %s | %s |" % (
        key[0], key[1], key[2],
        ratio(m[("b", "off")], m[("b", "native")]), ratio(m[("b", "on")], m[("b", "native")]),
        ratio(m[("a", "off")], m[("a", "native")]), ratio(m[("a", "on")], m[("a", "native")])))
