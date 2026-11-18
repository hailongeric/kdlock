#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise woken_ab.sh and rstall_ab.sh (one boot, settings alternating).

  ab_summary.py woken FILE      locktorture writes per setting of kd_mutex_woken
  ab_summary.py rstall FILE     will-it-scale rates per reader-stall setting
  ab_summary.py nano DIR TAG    rwsem nano bodies, TAG-nano.jsonl.<setting>

Prints the values of every round, the medians, the ratio to the reference
setting (kd_mutex_woken=0, or nostall), and the median counters.
"""
import glob
import json
import os
import re
import statistics
import sys
from collections import defaultdict


def med(v):
    return statistics.median(v) if v else 0


def fmt(x):
    if x >= 1e6:
        return "%.1f M" % (x / 1e6)
    if x >= 1e3:
        return "%.0f k" % (x / 1e3)
    return "%.2f" % x


def counters(tail):
    f = tail.split()
    return {f[i]: int(f[i + 1]) for i in range(0, len(f) - 1, 2)}


def table(rows, cfgs, ref, label):
    print("| %s | %s | %s |" % (label, " | ".join(cfgs),
                                " | ".join("%s/%s" % (c, ref) for c in cfgs if c != ref)))
    print("|" + "---|" * (1 + len(cfgs) + len(cfgs) - 1))
    for key in sorted(rows):
        vals = rows[key]
        cells = [" / ".join(fmt(x) for x in vals.get(c, [])) for c in cfgs]
        r = ["%.2f" % (med(vals.get(c, [])) / med(vals[ref])) if med(vals.get(ref, [])) else "-"
             for c in cfgs if c != ref]
        print("| %s | %s | %s |" % (" ".join(str(k) for k in key), " | ".join(cells), " | ".join(r)))


def woken(path):
    rows = defaultdict(lambda: defaultdict(list))
    cnt = defaultdict(lambda: defaultdict(list))
    for line in open(path):
        m = re.match(r"woken=(\d) (\S+) (\S+) round (\d) writes (\d+) success (\d) \|(.*)", line)
        if not m:
            continue
        s, t, w, _, wr, ok, tail = m.groups()
        cfg = "woken%s" % s
        rows[(t, w)][cfg].append(int(wr))
        for k, v in counters(tail).items():
            cnt[(t, w, cfg)][k].append(v)
        if ok != "1":
            print("not SUCCESS:", line.strip())
    table(rows, ["woken1", "woken0"], "woken0", "test writers")
    print("\nmedian counters per 30 s run:\n")
    for key in sorted(cnt):
        print("  %-28s %s" % (" ".join(key), " ".join("%s %d" % (k, med(v)) for k, v in sorted(cnt[key].items()))))


def rstall(path):
    rows = defaultdict(lambda: defaultdict(list))
    cnt = defaultdict(lambda: defaultdict(list))
    for line in open(path):
        m = re.match(r"(stall|nostall|rspin0) (\S+) (\d+) round (\d) rate (\d+) \|(.*)", line)
        if not m:
            continue
        cfg, t, n, _, v, tail = m.groups()
        rows[(t, int(n))][cfg].append(int(v))
        for k, x in counters(tail).items():
            cnt[(t, n, cfg)][k].append(x)
    table(rows, ["stall", "nostall", "rspin0"], "nostall", "test threads")
    print("\nmedian counters per 5 s run:\n")
    for key in sorted(cnt):
        print("  %-30s %s" % (" ".join(key), " ".join("%s %d" % (k, med(v)) for k, v in sorted(cnt[key].items()))))


def nano(d, tag):
    rows = defaultdict(lambda: defaultdict(list))
    for path in glob.glob(os.path.join(d, tag + "-nano.jsonl.*")):
        cfg = path.rsplit(".", 1)[1]
        for line in open(path):
            r = json.loads(line)
            if not r.get("ok") or r.get("torn_reads"):
                print("data check failed:", cfg, r["profile"], r["workers"])
            rows[(r["profile"], r["workers"])][cfg].append(r["mops"])
    table(rows, ["stall", "nostall"], "nostall", "profile workers")


if __name__ == "__main__":
    {"woken": woken, "rstall": rstall}.get(sys.argv[1], lambda p: nano(p, sys.argv[3]))(sys.argv[2])
