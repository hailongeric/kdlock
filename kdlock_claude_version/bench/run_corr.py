#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Correctness pass over every lock family and test body.

Runs short points and checks the data oracle of each (every worker made
progress, no reader saw a torn body, the counters add up to the completed
writes, the test bodies saw no broken invariant), plus the single-task
check of every kd API variant. Rates are not the purpose here. One JSON
line per point; exit status 1 if any point failed.

  run_corr.py --out corr.jsonl                 # Native and kd
  run_corr.py --out corr.jsonl --backends native kd tclock
"""

import argparse
import fcntl
import json
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_nano  # noqa: E402

BASE = ("spin", "mutex", "rwlock", "rwsem")
# family: (lines, write_pcts, workers, backends that have it)
POINTS = [
    ("spin", (1, 16), (100,), (1, 2, 3, 5, 8, 32), None),
    ("mutex", (1, 16), (100,), (1, 2, 3, 5, 8, 32), None),
    ("rwlock", (1, 16), (1, 20, 100), (1, 2, 8, 32), None),
    ("rwsem", (1, 16), (1, 20, 100), (1, 2, 8, 32), None),
    ("nest_spin", (1,), (50,), (2, 8, 32), ("native", "kd")),
    ("nest_mutex", (1,), (50,), (2, 8, 32), ("native", "kd")),
    ("mix", (1,), (100,), (2, 8, 32), ("native", "kd")),
    ("spin_curr", (1,), (100,), (2, 8, 32), ("native", "kd")),
    ("spin_curw", (1,), (100,), (2, 8, 32), ("native", "kd")),
    ("mutex_curr", (1,), (100,), (2, 8, 32), ("native", "kd")),
    ("mutex_curw", (1,), (100,), (2, 8, 32), ("native", "kd")),
    ("ww", (2,), (100,), (2, 8, 32), ("kd",)),
    ("spin_raw", (1,), (100,), (2, 8, 32), ("native", "kd")),
    ("spin_hb", (1, 16), (100,), (2, 3, 5, 8, 32), ("native", "kd")),
    ("rwlock_hb", (1,), (20, 100), (2, 8, 32), ("native", "kd")),
    ("rwsem_hb", (1,), (20, 100), (2, 8, 32), ("native", "kd")),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="JSON lines file (appended)")
    ap.add_argument("--backends", nargs="+", default=["native", "kd"],
                    choices=list(run_nano.BACKEND))
    ap.add_argument("--ms", type=int, default=300)
    ap.add_argument("--dev", default="/dev/kdbench")
    ap.add_argument("--tag", default="", help="free text stored with every line")
    args = ap.parse_args()

    ident = {"kernel": platform.release(), "build": platform.version(), "tag": args.tag}
    fd = os.open(args.dev, os.O_RDWR)
    total = bad = 0
    with open(args.out, "a") as out:
        failed = fcntl.ioctl(fd, run_nano.IOC_APITEST)
        out.write(json.dumps(dict(ident, api_test_failed_checks=failed)) + "\n")
        total += 1
        bad += bool(failed)
        print("api test: %d failed checks" % failed, flush=True)
        for family, lines_set, pcts, workers, only in POINTS:
            for backend in args.backends:
                if only and backend not in only:
                    continue
                for lines in lines_set:
                    for pct in pcts:
                        for n in workers:
                            a = argparse.Namespace(family=family, backend=backend, lines=lines,
                                                   write_pct=pct, post=64, first_cpu=0)
                            before = run_nano.kd_stats() if backend == "kd" else {}
                            res = run_nano.run_once(fd, a, n, args.ms)
                            after = run_nano.kd_stats() if backend == "kd" else {}
                            res.update(ident, family=family, backend=backend, lines=lines,
                                       write_pct=pct, workers=n,
                                       kd_delta={k: after[k] - before.get(k, 0)
                                                 for k in after if k != "delegation"})
                            out.write(json.dumps(res) + "\n")
                            out.flush()
                            total += 1
                            if not res["ok"]:
                                bad += 1
                                print("FAIL %s %s lines=%d pct=%d n=%d %s" %
                                      (family, backend, lines, pct, n, json.dumps(res)),
                                      flush=True)
    print("%d points, %d failed" % (total, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
