#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Native, kd off and kd on per candidate at 64 workers (reduced round).

  s4_summary.py DATA_DIR [--sort]

Native values from the tags s3 (application groups) and s5-w64 (the clean
rerun of the reduced pass; s4-w64 was disturbed, README section 6), kd
off and on from s4-w64 (and s4b-w64: the on pass of the candidates
added after the clean native pass). Counters of the kd-on point: delegated sections,
handbacks, hb_region. Lock share: from the native pass table
(DATA_DIR/s5-native-pass.md). One run per point: a screening.
"""
import re
import sys

d = sys.argv[1].rstrip("/")
nat, kd, cnt, order = {}, {}, {}, []
C = "delegated handback hb_frontier hb_miss offered plain sessions hb_region done_in_region".split()
for line in open(d + "/screen.txt"):
    parts = line.rstrip("\n").split(" | ")
    f = parts[0].split()
    if len(f) < 6 or f[3] != "64":
        continue
    try:
        v = float(f[4])
    except ValueError:
        v = 0.0
    if f[1] == "native" and f[0] in ("s3", "s5-w64"):
        if v or f[2] not in nat:
            nat[f[2]] = v
    elif f[0] in ("s4-w64", "s4b-w64") and f[1] in ("off", "on"):
        kd.setdefault(f[2], {})[f[1]] = v
        if f[2] not in order:
            order.append(f[2])
        if f[1] == "on" and len(parts) == 3:
            b, a = parts[1].split(), parts[2].split()
            if len(a) == len(C) and len(b) == len(C):
                cnt[f[2]] = {k: int(y) - int(x) for k, x, y in zip(C, b, a)}
lock = {}
for l in open(d + "/s5-native-pass.md"):
    f = [x.strip() for x in l.split("|")]
    if len(f) >= 9 and f[1] not in ("candidate", "---"):
        lock[f[1]] = f[4]
r = lambda a, b: a / b if a and b else None
rows = []
for c in order:
    n, o, x = nat.get(c), kd[c].get("off"), kd[c].get("on")
    rows.append((c, n, r(o, n), r(x, n), r(x, o), cnt.get(c, {})))
if "--sort" in sys.argv:
    rows.sort(key=lambda t: -(t[3] or 0))
fmt = lambda v: "%.2f" % v if v else "-"
print("| candidate | native lock share | native | off/native | on/native | on/off | delegated | handbacks | hb_region |")
print("|---|---|---|---|---|---|---|---|---|")
for c, n, a, b, e, k in rows:
    print("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
        c, lock.get(c, "-"), "%.4g" % n if n else "-", fmt(a), fmt(b), fmt(e),
        k.get("delegated", "-"), k.get("handback", "-"), k.get("hb_region", "-")))
ok = [t for t in rows if t[2]]
print()
print("%d candidates; off/native below 0.90: %s" % (
    len(rows), ", ".join("%s %.2f" % (t[0], t[2]) for t in ok if t[2] < 0.90) or "none"))
print("on/native at least 1.10: %s" % (", ".join("%s %.2f" % (t[0], t[3]) for t in rows if t[3] and t[3] >= 1.10) or "none"))
print("on/native below 0.90: %s" % (", ".join("%s %.2f" % (t[0], t[3]) for t in rows if t[3] and t[3] < 0.90) or "none"))
