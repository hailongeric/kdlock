#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""The candidates of a native screening pass that go on (README 4.2).

  pass.py DIR TAG [TAG...] [--ids] [--min-lock 10] [--pn 64]

DIR holds screen.txt and prof/ (screen.sh). A candidate passes when, at PN
workers in mode native,
  lock:   at least --min-lock percent of the profile's samples are in native
          lock code (spin, rwlock, mutex and rwsem slow paths and spinning),
  fall:   its rate at PN workers is below its rate at 16, or
  sleep:  the profile has at most 75% of the samples a busy machine gives
          and the candidate ran longer than the profile window (context
          switches were counted), i.e. its tasks sleep.
A point with no value (0) does not pass. Output: a table with the reasons,
or with --ids only the IDs that pass, one per line.
"""
import argparse
import os
import re

NATIVE_LOCK = re.compile(
    r"^((native_)?queued_spin_lock_slowpath|queued_(read|write)_lock_slowpath|osq_lock|"
    r"mutex_spin_on_owner|__mutex_lock.*|mutex_lock.*|rwsem_spin_on_owner|"
    r"rwsem_down_(read|write)_slowpath|rwsem_optimistic_spin|"
    r"_raw_spin_lock.*|_raw_read_lock.*|_raw_write_lock.*|__pv_queued_spin_lock_slowpath)$")

ap = argparse.ArgumentParser()
ap.add_argument("dir")
ap.add_argument("tags", nargs="+")
ap.add_argument("--ids", action="store_true")
ap.add_argument("--min-lock", type=float, default=10)
ap.add_argument("--pn", type=int, default=64)
a = ap.parse_args()
SAMPLES = 3 * 499 * 64

val, order, tag_of = {}, [], {}
for line in open(os.path.join(a.dir, "screen.txt")):
    f = line.partition(" | ")[0].split()
    if len(f) < 6 or f[0] not in a.tags or f[1] != "native":
        continue
    try:
        v = float(f[4])
    except ValueError:
        v = 0.0
    if f[2] not in order:
        order.append(f[2])
    val[(f[2], int(f[3]))] = v
    if int(f[3]) == a.pn:
        tag_of[f[2]] = f[0]


def profile(cid):
    path = os.path.join(a.dir, "prof", "%s-native-%s.txt" % (tag_of.get(cid, a.tags[0]), cid))
    if not os.path.exists(path):
        return None
    lock, cs, nsamp, top = 0.0, None, None, []
    for l in open(path):
        m = re.match(r"# Samples: ([\d.]+)([KM]?)", l)
        if m:
            nsamp = float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6}[m.group(2)]
            continue
        m = re.match(r"\s*([\d,]+)\s+context-switches", l)
        if m:
            cs = float(m.group(1).replace(",", "")) / 2
            continue
        m = re.match(r"\s*([\d.]+)%\s+\[[k.]\]\s+(\S+)", l)
        if m:
            if NATIVE_LOCK.match(m.group(2)):
                lock += float(m.group(1))
            if len(top) < 2:
                top.append("%s %.0f%%" % (m.group(2), float(m.group(1))))
    return lock, cs, (nsamp / SAMPLES) if nsamp else None, ", ".join(top)


rows = []
for cid in order:
    vp, v16 = val.get((cid, a.pn), 0), val.get((cid, 16))
    p = profile(cid)
    why = []
    if vp > 0:
        if p and p[0] >= a.min_lock:
            why.append("lock %.0f%%" % p[0])
        if v16 and vp < v16:
            why.append("fall %.2f" % (vp / v16))
        if p and p[2] is not None and p[2] <= 0.75 and p[1]:
            why.append("sleep (busy %.0f%%)" % (100 * p[2]))
    rows.append((cid, v16, vp, p, why))

if a.ids:
    print("\n".join(r[0] for r in rows if r[4]))
else:
    print("| candidate | 16 | %d | lock share | busy | context switches/s | top symbols | passes |" % a.pn)
    print("|---|---|---|---|---|---|---|---|")
    for cid, v16, vp, p, why in rows:
        print("| %s | %s | %.4g | %s | %s | %s | %s | %s |" % (
            cid, "%.4g" % v16 if v16 else "-", vp,
            "%.0f%%" % p[0] if p else "-", "%.0f%%" % (100 * p[2]) if p and p[2] else "-",
            "%.0f" % p[1] if p and p[1] is not None else "-", p[3] if p else "-",
            "; ".join(why) if why else ("no value" if vp <= 0 else "no")))
    print("\n%d of %d pass" % (sum(1 for r in rows if r[4]), len(rows)))
