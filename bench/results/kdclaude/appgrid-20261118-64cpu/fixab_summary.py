#!/usr/bin/env python3
"""Summarise fix_ab.sh output: per benchmark and thread count, the mean of
the two rounds per mode (off, new, old), the ratios new/off, old/off and
new/old, and per mode the delegated, handback, hb_miss and hb_region
counts the points added, with the memcg lock bytes after the mode.

  fixab_summary.py data/k13-fixab.txt
"""
import re
import sys
from collections import defaultdict

vals = defaultdict(list)
cnt = defaultdict(lambda: defaultdict(int))
bytes_after = {}
for line in open(sys.argv[1]):
    f = line.split(" | ")
    head = f[0].split()
    if len(head) != 6 or head[1] not in ("off", "new", "old"):
        continue
    _tag, mode, _rnd, bench, thr, v = head
    vals[(bench, int(thr), mode)].append(int(v))
    for k, d in re.findall(r"(\w+)\+(-?\d+)", f[1]):
        cnt[mode][k] += int(d)
    bytes_after[mode] = f[2].strip()

print("| benchmark | threads | off | new | old | new/off | old/off | new/old |")
print("|---|---:|---:|---:|---:|---:|---:|---:|")
for bench in ("mmap1", "mmap2", "brk1", "page_fault1"):
    for thr in (1, 8, 32, 64):
        m = {}
        for mode in ("off", "new", "old"):
            v = vals.get((bench, thr, mode))
            m[mode] = sum(v) / len(v) if v else None
        if not all(m.values()):
            continue
        print("| %s | %d | %.0f | %.0f | %.0f | %.2f | %.2f | %.2f |" % (
            bench, thr, m["off"], m["new"], m["old"], m["new"] / m["off"],
            m["old"] / m["off"], m["new"] / m["old"]))
print()
print("| mode | delegated | handback | hb_miss | hb_frontier | hb_region | done_in_region | lock bytes after (obj_stock, memcg_stock) |")
print("|---|---:|---:|---:|---:|---:|---:|---|")
for mode in ("off", "new", "old"):
    c = cnt[mode]
    print("| %s | %d | %d | %d | %d | %d | %d | %s |" % (
        mode, c["delegated"], c["handback"], c["hb_miss"], c["hb_frontier"],
        c["hb_region"], c["done_in_region"], bytes_after.get(mode, "")))
