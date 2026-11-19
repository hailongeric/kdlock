#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""nano_ab_summary.py TAG-nano.jsonl: per profile and worker count, native's
rate (median over all settings and rounds; the setting does not touch it)
and kd's rate and kd/native per setting (median over the rounds)."""
import collections
import json
import statistics
import sys

kd = collections.defaultdict(list)
nat = collections.defaultdict(list)
dele = collections.defaultdict(list)
settings, keys = [], []
for l in open(sys.argv[1]):
    r = json.loads(l)
    if not r["ok"]:
        continue
    k = (r["profile"], r["workers"])
    if k not in keys:
        keys.append(k)
    s = r["commit"]
    if s not in settings:
        settings.append(s)
    if r["backend"] == "native":
        nat[k].append(r["mops"])
    else:
        kd[k + (s,)].append(r["mops"])
        dele[k + (s,)].append(r["kd_delta"].get("delegated", 0))
print("| profile | workers | native | " + " | ".join("kd %s | /native | delegated" % s for s in settings) + " |")
print("|---|---|---|" + "---|---|---|" * len(settings))
for k in keys:
    n = statistics.median(nat[k])
    cells = []
    for s in settings:
        v = statistics.median(kd[k + (s,)]) if kd[k + (s,)] else 0
        cells.append("%.2f | %.2f | %d" % (v, v / n, statistics.median(dele[k + (s,)]) if dele[k + (s,)] else 0))
    print("| %s | %d | %.2f | %s |" % (k[0], k[1], n, " | ".join(cells)))
