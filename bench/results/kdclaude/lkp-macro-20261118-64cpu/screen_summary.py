#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise screen.sh: per candidate, the rate at 16 and 64 workers, the
scaling 64/16, and from the 64-worker profile the lock share, the busy
share and the context switches (README 4.2).

  screen_summary.py DIR TAG [--mode native] [--cmp off]

DIR holds screen.txt and prof/. Lock share: samples in lock functions over
all samples of the profile. Busy share: samples over 3 s x 499 Hz x 64
CPUs, so a workload whose threads sleep shows a low busy share. With
--cmp MODE, the ratio of that mode's rate to the first mode's is added.
"""
import argparse
import os
import re

NATIVE_LOCK = re.compile(
    r"^((native_)?queued_spin_lock_slowpath|queued_(read|write)_lock_slowpath|osq_lock|"
    r"mutex_spin_on_owner|__mutex_lock.*|mutex_lock.*|rwsem_spin_on_owner|"
    r"rwsem_down_(read|write)_slowpath|rwsem_optimistic_spin|"
    r"_raw_spin_lock.*|_raw_read_lock.*|_raw_write_lock.*|__pv_queued_spin_lock_slowpath)$")
KD_LOCK = re.compile(r"^kd_.*")
SAMPLES = 3 * 499 * 64

ap = argparse.ArgumentParser()
ap.add_argument("dir")
ap.add_argument("tag")
ap.add_argument("--mode", default="native")
ap.add_argument("--cmp")
a = ap.parse_args()

val = {}
order = []
for line in open(os.path.join(a.dir, "screen.txt")):
    f = line.partition(" | ")[0].split()
    if len(f) < 6 or f[0] != a.tag:
        continue
    mode, cid, n = f[1], f[2], int(f[3])
    try:
        v = float(f[4])
    except ValueError:
        v = 0.0
    if cid not in order:
        order.append(cid)
    val[(mode, cid, n)] = (v, f[5])


def profile(mode, cid):
    path = os.path.join(a.dir, "prof", "%s-%s-%s.txt" % (a.tag, mode, cid))
    if not os.path.exists(path):
        return None
    cs = tot = lock = 0.0
    top = []
    nsamp = None
    for l in open(path):
        m = re.match(r"# Samples: ([\d.]+)([KM]?)", l)
        if m:
            nsamp = float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6}[m.group(2)]
            continue
        m = re.match(r"\s*([\d,]+)\s+context-switches", l)
        if m:
            cs = float(m.group(1).replace(",", ""))
            continue
        m = re.match(r"\s*([\d.]+)%\s+\[[k.]\]\s+(\S+)", l)
        if m:
            pct, sym = float(m.group(1)), m.group(2)
            tot += pct
            if NATIVE_LOCK.match(sym) or (mode != "native" and KD_LOCK.match(sym)):
                lock += pct
            if len(top) < 3:
                top.append("%s %.0f%%" % (sym, pct))
    return lock, cs / 2, ", ".join(top), (nsamp / SAMPLES) if nsamp else None


print("| candidate | unit | 16 | 64 | 64/16 | lock share at 64 | busy at 64 | context switches/s at 64 | top symbols at 64 |%s" %
      (" %s/%s at 16 | at 64 |" % (a.cmp, a.mode) if a.cmp else ""))
print("|---|---|---|---|---|---|---|---|---|%s" % ("---|---|" if a.cmp else ""))
for cid in order:
    v16 = val.get((a.mode, cid, 16), (0, ""))
    v64 = val.get((a.mode, cid, 64), (0, ""))
    p = profile(a.mode, cid)
    sc = "%.2f" % (v64[0] / v16[0]) if v16[0] else "-"
    row = "| %s | %s | %.4g | %.4g | %s | %s | %s | %s | %s |" % (
        cid, v16[1] or v64[1], v16[0], v64[0], sc,
        "%.0f%%" % p[0] if p else "-",
        "%.0f%%" % (100 * p[3]) if p and p[3] else "-",
        "%.0f" % p[1] if p else "-", p[2] if p else "-")
    if a.cmp:
        r = []
        for n in (16, 64):
            b = val.get((a.mode, cid, n), (0,))[0]
            c = val.get((a.cmp, cid, n), (0,))[0]
            r.append("%.2f" % (c / b) if b and c else "-")
        row += " %s | %s |" % tuple(r)
    print(row)
