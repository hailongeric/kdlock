#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Run the nano grid, alternating the backends at every point.

For each profile and worker count, the runs of all selected backends (Native,
kd, and with --backends also the original TCLock) follow each other, in an
order that rotates per round and point, so slow drift of the host affects
them alike. Every result line carries the identity needed to compare it: kernel
release and build, source commit, profile, workers, round, backend and, for
kd, the execution-class counter deltas. Start the translator daemon first;
it does not affect the native locks.

  run_grid.py --out grid.jsonl --rounds 1
  run_grid.py --profiles mutex_c01 rwsem_c16_w20 --workers 1 8 32 --rounds 3
  run_grid.py --backends native kd tclock --out grid3.jsonl   # TCLock bench build
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_nano  # noqa: E402

# name: (family, lines, write_pct, post)
PROFILES = {
    "spin_c01": ("spin", 1, 100, 64),
    "spin_c08": ("spin", 8, 100, 64),
    "mutex_c01": ("mutex", 1, 100, 256),
    "mutex_c16": ("mutex", 16, 100, 256),
    "rwsem_c01_w1": ("rwsem", 1, 1, 256),
    "rwsem_c01_w20": ("rwsem", 1, 20, 256),
    "rwsem_c16_w1": ("rwsem", 16, 1, 256),
    "rwsem_c16_w20": ("rwsem", 16, 20, 256),
    "rwlock_c01_w1": ("rwlock", 1, 1, 256),
    "rwlock_c01_w20": ("rwlock", 1, 20, 256),
    "rwlock_c16_w1": ("rwlock", 16, 1, 256),
    "rwlock_c16_w20": ("rwlock", 16, 20, 256),
    # Writers only: the delegation path of the rw families without readers.
    "rwsem_c01_w100": ("rwsem", 1, 100, 256),
    "rwlock_c01_w100": ("rwlock", 1, 100, 256),
    # `current` inside the section; compare with spin_c01 / mutex_c01.
    "spin_c01_curr": ("spin_curr", 1, 100, 64),
    "spin_c01_curw": ("spin_curw", 1, 100, 64),
    "mutex_c01_curr": ("mutex_curr", 1, 100, 256),
    "mutex_c01_curw": ("mutex_curw", 1, 100, 256),
    # The plain path alone, and sections that are handed back.
    "spin_c01_raw": ("spin_raw", 1, 100, 64),
    "spin_c01_hb": ("spin_hb", 1, 100, 64),
    "rwlock_c01_hb": ("rwlock_hb", 1, 100, 256),
    "rwsem_c01_hb": ("rwsem_hb", 1, 100, 256),
    "mutex_c01_hb": ("mix", 1, 100, 256),
    # The clobber entries (kd_api.h kd_*_cl()); Native and TCLock run their
    # ordinary bodies, so these compare with the profiles without _cl.
    "spin_c01_cl": ("spin_cl", 1, 100, 64),
    "spin_c08_cl": ("spin_cl", 8, 100, 64),
    "mutex_c01_cl": ("mutex_cl", 1, 100, 256),
    "mutex_c16_cl": ("mutex_cl", 16, 100, 256),
    "rwlock_c01_w100_cl": ("rwlock_cl", 1, 100, 256),
    "rwlock_c16_w20_cl": ("rwlock_cl", 16, 20, 256),
    "rwsem_c01_w100_cl": ("rwsem_cl", 1, 100, 256),
    "rwsem_c16_w20_cl": ("rwsem_cl", 16, 20, 256),
}
# The default grid; the other profiles are run on request.
GRID = [p for p in PROFILES if not p.endswith(("_curr", "_curw", "_raw", "_hb", "_w100", "_cl"))]
# 1-8 one by one, then every fourth up to 64 (the user asked for this grid on
# 2026-11-15; rounds up to 9 had 40, 48, 56, 64 instead of every fourth).
WORKERS = [1, 2, 3, 4, 5, 6, 7, 8] + list(range(12, 65, 4))


def identity():
    src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        commit = subprocess.run(["git", "-C", src, "rev-parse", "--short=12", "HEAD"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", src, "status", "--porcelain", "--", src],
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit, dirty = "", ""
    # A tree without .git (a synced copy) names its source through KD_COMMIT/KD_DIRTY.
    commit = commit or os.environ.get("KD_COMMIT", "")
    dirty = dirty or os.environ.get("KD_DIRTY", "")
    return {"kernel": platform.release(), "build": platform.version(),
            "commit": commit or "unknown", "dirty": bool(dirty)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="JSON lines file (appended)")
    ap.add_argument("--profiles", nargs="+", default=GRID, choices=PROFILES)
    ap.add_argument("--workers", type=int, nargs="+", default=WORKERS)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--ms", type=int, default=2000)
    ap.add_argument("--warmup-ms", type=int, default=500)
    ap.add_argument("--dev", default="/dev/kdbench")
    ap.add_argument("--commit", help="source commit, when git cannot run here")
    ap.add_argument("--backends", nargs="+", default=["native", "kd"],
                    choices=list(run_nano.BACKEND))
    args = ap.parse_args()

    ident = identity()
    if args.commit:
        ident["commit"] = args.commit
    fd = os.open(args.dev, os.O_RDWR)
    bad = 0
    with open(args.out, "a") as out:
        for rnd in range(args.rounds):
            for name in args.profiles:
                family, lines, wpct, post = PROFILES[name]
                for n in args.workers:
                    k = (rnd + n) % len(args.backends)
                    order = args.backends[k:] + args.backends[:k]
                    for backend in order:
                        a = argparse.Namespace(family=family, backend=backend, lines=lines,
                                               write_pct=wpct, post=post, first_cpu=0)
                        run_nano.run_once(fd, a, n, args.warmup_ms)
                        before = run_nano.kd_stats() if backend == "kd" else {}
                        res = run_nano.run_once(fd, a, n, args.ms)
                        after = run_nano.kd_stats() if backend == "kd" else {}
                        res.update(ident, profile=name, family=family, lines=lines,
                                   write_pct=wpct, post=post, workers=n, round=rnd,
                                   backend=backend, ms=args.ms, time=time.time(),
                                   kd_delta={k: after[k] - before.get(k, 0)
                                             for k in after if k != "delegation"},
                                   delegation=after.get("delegation"))
                        out.write(json.dumps(res) + "\n")
                        out.flush()
                        bad += not res["ok"]
                        print("%-15s n%-2d %-6s %s %7.3f" % (name, n, backend,
                              "ok  " if res["ok"] else "FAIL", res["mops"]), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
