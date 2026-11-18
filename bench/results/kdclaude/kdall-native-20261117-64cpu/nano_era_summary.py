#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise nano_era.sh: kd rate per era bound, relative to 200 us.

  nano_era_summary.py DIR
"""
import glob
import json
import os
import re
import statistics
import sys
from collections import defaultdict

d = defaultdict(list)
bad = 0
for path in glob.glob(os.path.join(sys.argv[1], "nera-*.jsonl.*")):
    m = re.match(r"nera-(\w+)\.jsonl\.(\d+)$", os.path.basename(path))
    mode, era = m.group(1), int(m.group(2))
    for line in open(path):
        r = json.loads(line)
        if not r.get("ok"):
            bad += 1
            continue
        d[(mode, r["profile"], r["workers"], era)].append(r["mops"])
print("failed points: %d" % bad)
eras = [200000, 1000000, 2000000]
for mode in ("plain", "deleg"):
    print("\n%s\n" % mode)
    print("| profile | workers | 200 us | 1 ms | 2 ms | 1 ms / 200 us | 2 ms / 200 us |")
    print("|---|---|---|---|---|---|---|")
    for key in sorted({k[1:3] for k in d if k[0] == mode}):
        v = [d[(mode,) + key + (e,)] for e in eras]
        if not all(v):
            continue
        m0 = statistics.median(v[0])
        print("| %s | %d | %s | **%.2f** | **%.2f** |" % (
            key[0], key[1], " | ".join("/".join("%.2f" % x for x in xs) for xs in v),
            statistics.median(v[1]) / m0, statistics.median(v[2]) / m0))
