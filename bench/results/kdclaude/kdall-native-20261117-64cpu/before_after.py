#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Before and after the optimizations, each against its own native boots.

runs.txt holds the comparisons of suite.sh, one series of tags per letter:
b1-b6 (kdall1 against kdnat1), a1-a6 (kdall3 against kdnat1, later boots)
and c1-c6 (kdall9 against kdnat8, section 8). For each series, the ratio of
medians to that series' native runs; a ratio is marked "~" when the kd runs
overlap the native runs.

  before_after.py runs.txt [BEFORE AFTER]    series letters, default b a
"""
import statistics
import sys
from collections import defaultdict

vals = defaultdict(lambda: defaultdict(list))
order = []
bs, as_ = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("b", "a")
for line in open(sys.argv[1]):
    f = line.partition(" | ")[0].split()
    if len(f) < 6 or f[0][0] not in (bs, as_) or not f[0][1:].isdigit():
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
        ratio(m[(bs, "off")], m[(bs, "native")]), ratio(m[(bs, "on")], m[(bs, "native")]),
        ratio(m[(as_, "off")], m[(as_, "native")]), ratio(m[(as_, "on")], m[(as_, "native")])))
