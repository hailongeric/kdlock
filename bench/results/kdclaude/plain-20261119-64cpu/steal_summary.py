#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""steal_summary.py TAG-steal.txt [NATIVE_RUNS TAG]: the rates of steal_ab.sh
per test and worker count with stealing off and on (mean over the rounds),
their ratio, and, with app_grid.sh lines of a native pass given, each
against native (another boot: an indicator)."""
import collections
import sys

d = collections.defaultdict(list)
cnt = collections.defaultdict(lambda: collections.Counter())
order = []
for l in open(sys.argv[1]):
    h, _, rest = l.partition(" | ")
    f = h.split()
    if len(f) != 6 or not f[2].startswith("steal"):
        continue
    k = (f[3], int(f[4]))
    if k not in order:
        order.append(k)
    d[k + (f[2],)].append(float(f[5]))
    for x in rest.split():
        name, _, v = x.partition("+")
        cnt[k + (f[2],)][name] += int(v)
nat = {}
if len(sys.argv) > 3:
    for l in open(sys.argv[2]):
        f = l.split()
        if len(f) > 6 and f[0] == sys.argv[3] and f[1] == "native" and f[2] == "wis":
            nat[(f[3], int(f[4]))] = float(f[5])
print("| test | workers | steal off | steal on | on/off | off/native | on/native | wr_steal, wr_handoff, parked (on) | parked (off) |")
print("|---|---|---|---|---|---|---|---|---|")
for k in order:
    a = sum(d[k + ("steal0",)]) / max(1, len(d[k + ("steal0",)]))
    b = sum(d[k + ("steal1",)]) / max(1, len(d[k + ("steal1",)]))
    n = nat.get(k)
    c1, c0 = cnt[k + ("steal1",)], cnt[k + ("steal0",)]
    print("| %s | %d | %.4g | %.4g | %.2f | %s | %s | %d, %d, %d | %d |" % (
        k[0], k[1], a, b, b / a if a else 0, "%.2f" % (a / n) if n else "-", "%.2f" % (b / n) if n else "-",
        c1["wr_steal"], c1["wr_handoff"], c1["parked"], c0["parked"]))
