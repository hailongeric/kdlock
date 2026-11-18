#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise nat_check.sh: oversubscription and ww points, kd against native.

  natc_summary.py DIR TAG [TAG ...]

For each tag (one boot of a kdnat kernel): run_oversub.py points per
profile, first CPU and workers per CPU (rate, kd/native, least/most
operations per worker, starved workers), and the ww body at 32 and 64
workers.
"""
import json
import os
import statistics
import sys
from collections import defaultdict

base = sys.argv[1]
for tag in sys.argv[2:]:
    print("\n## %s\n" % tag)
    d = defaultdict(list)
    fair = defaultdict(list)
    starved = defaultdict(int)
    path = os.path.join(base, "%s-oversub.jsonl" % tag)
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            key = (r["profile"], r.get("tag", ""), r["factor"], r["backend"])
            d[key].append(r["mops"])
            fair[key].append(r["min_worker_ops"] / max(1, r["max_worker_ops"]))
            starved[key] += r.get("starved", 0)
        print("| profile | placement | workers per CPU | native | kd | kd/native | least/most native, kd | starved native, kd |")
        print("|---|---|---|---|---|---|---|---|")
        for k in sorted({k[:3] for k in d}):
            n, kd = d[k + ("native",)], d[k + ("kd",)]
            if not n or not kd:
                continue
            print("| %s | %s | %d | %s | %s | **%.2f** | %.2f, %.2f | %d, %d |" % (
                k[0], {"first0": "32 CPUs of node 0", "first16": "16+16 CPUs"}.get(k[1], k[1]), k[2],
                "/".join("%.2f" % x for x in n), "/".join("%.2f" % x for x in kd),
                statistics.median(kd) / statistics.median(n),
                statistics.median(fair[k + ("native",)]), statistics.median(fair[k + ("kd",)]),
                starved[k + ("native",)], starved[k + ("kd",)]))
    rows = []
    for w in (32, 64):
        v = {}
        for b in ("native", "kd"):
            p = os.path.join(base, "%s-ww-%s-%d.json" % (tag, b, w))
            if not os.path.exists(p):
                continue
            rates = [json.loads(l)["mops"] for l in open(p) if l.strip().startswith("{") and '"mops"' in l]
            if rates:
                v[b] = rates
        if len(v) == 2:
            rows.append("| ww body | %d | %s | %s | **%.2f** |" % (
                w, "/".join("%.2f" % x for x in v["native"]), "/".join("%.2f" % x for x in v["kd"]),
                statistics.median(v["kd"]) / statistics.median(v["native"])))
    if rows:
        print("\n| body | workers | native | kd | kd/native |\n|---|---|---|---|---|")
        print("\n".join(rows))
