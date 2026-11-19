#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Native, kd off and kd on per candidate (README 4.4).

  on_summary.py screen.txt TAG [--sort]

Per candidate and worker count: the three rates, on/native and on/off,
and for "on" the delegated sections, sessions and handbacks of the point
(frontier, miss). One run per point: a screening, not a result. --sort
orders by on/native at 64 workers.
"""
import sys
from collections import defaultdict

path, tag = sys.argv[1], sys.argv[2]
val = defaultdict(dict)
cnt = {}
order = []
for line in open(path):
    parts = line.rstrip("\n").split(" | ")
    f = parts[0].split()
    if len(f) < 6 or f[0] != tag:
        continue
    mode, cid, n = f[1], f[2], int(f[3])
    try:
        v = float(f[4])
    except ValueError:
        v = 0.0
    if cid not in order:
        order.append(cid)
    val[(cid, n)][mode] = v
    if mode == "on" and len(parts) >= 3:
        b, a = parts[1].split(), parts[2].split()
        if len(a) >= 7 and len(b) >= 7:
            d = [int(x) - int(y) for x, y in zip(a, b)]
            # delegated handback hb_frontier hb_miss offered plain sessions
            cnt[(cid, n)] = d


def r(x, y):
    return x / y if x and y else 0.0


rows = []
for cid in order:
    for n in (16, 64):
        m = val.get((cid, n))
        if not m:
            continue
        d = cnt.get((cid, n))
        rows.append((cid, n, m.get("native", 0), m.get("off", 0), m.get("on", 0),
                     r(m.get("on"), m.get("native")), r(m.get("on"), m.get("off")), d))
if "--sort" in sys.argv:
    key = {cid: on64 for cid, n, _, _, _, on64, _, _ in rows if n == 64}
    rows.sort(key=lambda x: (-key.get(x[0], 0), x[0], x[1]))


def fmt(x):
    if x >= 1e6:
        return "%.2f M" % (x / 1e6)
    if x >= 1e4:
        return "%.0f k" % (x / 1e3)
    return "%.4g" % x


print("| candidate | workers | native | kd off | kd on | on/native | on/off | delegated | sessions | handbacks (frontier, miss) |")
print("|---|---|---|---|---|---|---|---|---|---|")
for cid, n, nat, off, on, rn, ro, d in rows:
    print("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        cid, n, fmt(nat), fmt(off), fmt(on),
        "**%.2f**" % rn if rn >= 1.1 else "%.2f" % rn, "%.2f" % ro,
        fmt(d[0]) if d else "-", fmt(d[6]) if d else "-",
        "%s (%s, %s)" % (fmt(d[1]), fmt(d[2]), fmt(d[3])) if d else "-"))
