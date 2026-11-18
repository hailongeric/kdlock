#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise era_ab.sh: rate per test, worker count and era setting.

Reads DIR/era-<round>-<cfg>.txt (mm_diag.sh format). Prints the rates of
the rounds, the median relative to "base", and per setting the medians of
sections per session and of era_gate per run.

  era_summary.py DIR
"""
import glob
import os
import re
import statistics
import sys
from collections import defaultdict

rate = defaultdict(list)
per_sess = defaultdict(list)
gate = defaultdict(list)
prefix = sys.argv[2] if len(sys.argv) > 2 else "era"
for path in sorted(glob.glob(os.path.join(sys.argv[1], prefix + "-*-*.txt"))):
    cfg = re.match(prefix + r"-\d+-(\w+)\.txt", os.path.basename(path)).group(1)
    key = None
    cnt = {}

    def flush():
        if key:
            rate[key + (cfg,)].append(cnt.get("rate", 0))
            s = cnt.get("sessions", 0)
            per_sess[key + (cfg,)].append(cnt.get("delegated", 0) / s if s else 0)
            gate[key + (cfg,)].append(cnt.get("era_gate", 0))

    for line in open(path):
        m = re.match(r"== (\S+) (\d+) rate (\d+) ctxt (\d+)", line)
        if m:
            flush()
            key = (m.group(1), int(m.group(2)))
            cnt = {"rate": int(m.group(3))}
            continue
        m = re.match(r"\s+(\S+)\s+(-?\d+)$", line)
        if m and key:
            cnt[m.group(1)] = int(m.group(2))
    flush()

order = ["base", "era0", "press400", "e500", "e1000", "r200"]
cfgs = [c for c in order if any(k[2] == c for k in rate)]
others = [c for c in cfgs if c != "base"]
print("| test | workers | " + " | ".join("%s (k/s)" % c for c in cfgs) + " | " +
      " | ".join("%s/base" % c for c in others) + " | sections per session (%s) | era_gate per run (%s) |"
      % (" / ".join(cfgs), " / ".join(cfgs)))
print("|---|---|" + "---|" * (len(cfgs) + len(others) + 2))
for key in sorted({k[:2] for k in rate}):
    med = {c: statistics.median(rate[key + (c,)]) for c in cfgs if rate[key + (c,)]}
    print("| %s | %d | %s | %s | %s | %s |" % (
        key[0], key[1],
        " | ".join("/".join("%.0f" % (x / 1e3) for x in rate[key + (c,)]) for c in cfgs),
        " | ".join("%.2f" % (med[c] / med["base"]) for c in others),
        " / ".join("%.0f" % statistics.median(per_sess[key + (c,)]) for c in cfgs),
        " / ".join("%.0f" % statistics.median(gate[key + (c,)]) for c in cfgs)))
