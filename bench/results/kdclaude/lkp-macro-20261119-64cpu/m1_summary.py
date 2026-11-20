#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""The macro set (p4_macro.sh): native, kd off and kd on per worker count.

  m1_summary.py DATA_DIR/m1-screen.txt

Per workload: the native rate, kd off / native and kd on / native at each
worker count, and for kd on the delegated sections and handbacks summed
over its points. One run per point.
"""
import sys
from collections import OrderedDict, defaultdict

C = "delegated handback hb_frontier hb_miss offered plain sessions hb_region done_in_region".split()
val = defaultdict(dict)
cnt = defaultdict(lambda: defaultdict(int))
order, ns = OrderedDict(), set()
for line in open(sys.argv[1]):
    parts = line.rstrip("\n").split(" | ")
    f = parts[0].split()
    if len(f) < 6 or f[0] != "m1":
        continue
    try:
        v = float(f[4])
    except ValueError:
        v = 0.0
    mode, cid, n = f[1], f[2], int(f[3])
    val[(cid, mode)][n] = v
    order[cid] = f[5]
    ns.add(n)
    if mode == "on" and len(parts) == 3:
        b, a = parts[1].split(), parts[2].split()
        if len(a) == len(C) == len(b):
            for k, x, y in zip(C, b, a):
                cnt[cid][k] += int(y) - int(x)
ns = sorted(ns)
r = lambda a, b: "%.2f" % (a / b) if a and b else "-"
print("| workload | | " + " | ".join(str(n) for n in ns) + " | delegated, handbacks, hb_region |")
print("|---|---|" + "---|" * len(ns) + "---|")
low = []
for cid, unit in order.items():
    nat, off, on = val[(cid, "native")], val[(cid, "off")], val[(cid, "on")]
    print("| %s | native, %s | %s | |" % (cid, unit, " | ".join("%.4g" % nat[n] if nat.get(n) else "-" for n in ns)))
    print("| | off/native | %s | |" % " | ".join(r(off.get(n), nat.get(n)) for n in ns))
    k = cnt[cid]
    print("| | on/native | %s | %d, %d, %d |" % (" | ".join(r(on.get(n), nat.get(n)) for n in ns),
                                              k["delegated"], k["handback"], k["hb_region"]))
    for n in ns:
        for m, d, bound in (("off", off, 0.93), ("on", on, 0.90)):
            if nat.get(n) and d.get(n) and d[n] / nat[n] < bound:
                low.append("%s %s %d %.2f" % (cid, m, n, d[n] / nat[n]))
print()
print("below the bounds (off 0.93, on 0.90): " + ("; ".join(low) if low else "none"))
