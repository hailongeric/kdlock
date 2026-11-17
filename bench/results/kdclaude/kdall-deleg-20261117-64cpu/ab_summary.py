#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise ab.txt from deleg_ab.sh as a Markdown table.

For each workload and thread count, the rounds r1..r3 give one "off" and one
"on" value each. The table shows every value, the medians, on/off, and for
"on" the kd stat changes over the run (delegated sections, handbacks).
"""

import re
import statistics
import sys
from collections import defaultdict

vals = defaultdict(lambda: {"off": [], "on": []})
deleg = defaultdict(list)
hand = defaultdict(list)
order = []
for line in open(sys.argv[1]):
    # Each side of the line starts with delegated and handback; deleg_mm.sh
    # adds more counters after them.
    m = re.match(r"r(\d)-(on|off) (\w+) (\S+) (\d+) (.*?) \| (\d+) (\d+)[\d ]* \| (\d+) (\d+)", line)
    if not m:
        continue
    _r, mode, kind, name, n, body = m.group(1, 2, 3, 4, 5, 6)
    d0, h0, d1, h1 = map(int, m.group(7, 8, 9, 10))
    if kind == "api":
        v = int(body.split()[0])
    elif kind == "wis":
        v = int(re.search(r"average:(\d+)", body).group(1))
    else:
        v = int(re.search(r"Total: (\d+)", body).group(1))
    key = (kind, name, int(n))
    if key not in order:
        order.append(key)
    vals[key][mode].append(v)
    if mode == "on":
        deleg[key].append(d1 - d0)
        hand[key].append(h1 - h0)


def fmt(v):
    return "%.3g M" % (v / 1e6) if v >= 1e6 else "%.0f k" % (v / 1e3) if v >= 1e4 else "%d" % v


print("| workload | threads | off (r1, r2, r3) | on (r1, r2, r3) | on/off (medians) | delegated per run (median) | handbacks per run (median) |")
print("|---|---|---|---|---|---|---|")
for key in order:
    off, on = vals[key]["off"], vals[key]["on"]
    if not off or not on:
        continue
    mo, mn = statistics.median(off), statistics.median(on)
    print("| %s %s | %d | %s | %s | **%.2f** | %s | %s |" % (
        key[0], key[1], key[2], ", ".join(fmt(x) for x in off), ", ".join(fmt(x) for x in on),
        mn / mo, fmt(statistics.median(deleg[key])), fmt(statistics.median(hand[key]))))
