#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Run nano points against /dev/kdbench and print one JSON object per point.

For the kd backend start the translator first (jit/kd_daemon.py); this
script only records kdlock's counters before and after each point so the
execution class (delegated / handed back / local) is visible next to the
rate. Everything here is meant to be read by a human or a small script:

  run_nano.py --family mutex --backend kd --lines 1 --workers 1 8 16 32
  run_nano.py --family rwsem --backend native --write-pct 20 --workers 8 60

Per point: warmup run, then `--repeat` measured runs. A run fails (and is
reported with "ok": false) when a worker made no progress, a reader saw a
torn body, or the counters do not add up to the completed writes.
"""

import argparse
import fcntl
import json
import os
import struct
import sys

MAXW = 64
IN_FMT = "<8I"
OUT_FMT = "<5Q" + "Q" * MAXW + "Q" * MAXW
RUN_FMT = IN_FMT + OUT_FMT[1:]
FAMILY = {"spin": 0, "mutex": 1, "rwlock": 2, "rwsem": 3,
          # test bodies (nesting, handback); see kd_bench_uapi.h
          "nest_spin": 4, "nest_mutex": 5, "mix": 6,
          # `current` inside the section (read / write); ww mutex test body
          "spin_curr": 7, "spin_curw": 8, "mutex_curr": 9, "mutex_curw": 10, "ww": 11,
          # raw (never delegated) spin acquire; handback bodies
          "spin_raw": 12, "spin_hb": 13, "rwlock_hb": 14, "rwsem_hb": 15}
BACKEND = {"native": 0, "kd": 1, "tclock": 2}
# _IOWR('B', 1, struct kdb_run)
IOC = (3 << 30) | (struct.calcsize(RUN_FMT) << 16) | (ord("B") << 8) | 1
IOC_APITEST = (ord("B") << 8) | 2      # _IO('B', 2)
STATS = "/sys/kernel/debug/kdlock_stats"


def kd_stats():
    try:
        with open(STATS) as f:
            return {k: int(v) for k, v in (l.split() for l in f)}
    except OSError:
        return {}


def run_once(fd, args, workers, ms):
    req = struct.pack(IN_FMT, FAMILY[args.family], BACKEND[args.backend], args.lines,
                      args.write_pct, args.post, workers, args.first_cpu, ms)
    buf = bytearray(req + bytes(struct.calcsize(RUN_FMT) - len(req)))
    fcntl.ioctl(fd, IOC, buf, True)
    f = struct.unpack(RUN_FMT, bytes(buf))
    elapsed, ops, writes, bad, delta = f[8:13]
    wops, wwr = f[13:13 + MAXW][:workers], f[13 + MAXW:13 + 2 * MAXW][:workers]
    lines = args.lines
    ok = all(wops) and bad == 0 and delta == writes * lines
    res = {"ok": ok, "mops": ops / elapsed * 1e3 if elapsed else 0.0, "ops": ops,
           "writes": writes, "torn_reads": bad, "sum_delta": delta,
           "min_worker_ops": min(wops), "max_worker_ops": max(wops)}
    if getattr(args, "per_worker", False):
        res["worker_ops"] = list(wops)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dev", default="/dev/kdbench")
    ap.add_argument("--api-test", action="store_true",
                    help="run the single-task check of every kd API variant and exit")
    ap.add_argument("--family", choices=FAMILY)
    ap.add_argument("--backend", choices=BACKEND)
    ap.add_argument("--lines", type=int, default=1, help="1..16; the ww body needs 2")
    ap.add_argument("--write-pct", type=int, default=100,
                    help="rwlock/rwsem: writer share; nest_*: outer share; "
                         "spin, mutex and mix are always 100")
    ap.add_argument("--post", type=int, default=256)
    ap.add_argument("--workers", type=int, nargs="+")
    ap.add_argument("--first-cpu", type=int, default=0)
    ap.add_argument("--ms", type=int, default=2000)
    ap.add_argument("--warmup-ms", type=int, default=1000)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--per-worker", action="store_true",
                    help="add the operations of every worker (worker i runs on CPU first+i)")
    args = ap.parse_args()

    fd = os.open(args.dev, os.O_RDWR)
    if args.api_test:
        failed = fcntl.ioctl(fd, IOC_APITEST)
        print(json.dumps({"api_test_failed_checks": failed}))
        return 1 if failed else 0
    if not (args.family and args.backend and args.workers):
        ap.error("--family, --backend and --workers are required")
    bad = False
    for n in args.workers:
        # Warmup also gives the translator time to publish images.
        run_once(fd, args, n, args.warmup_ms)
        for rep in range(args.repeat):
            before = kd_stats() if args.backend == "kd" else {}
            res = run_once(fd, args, n, args.ms)
            after = kd_stats() if args.backend == "kd" else {}
            res.update(family=args.family, backend=args.backend, lines=args.lines,
                       write_pct=args.write_pct
                       if args.family in ("rwlock", "rwsem", "nest_spin", "nest_mutex",
                                          "rwlock_hb", "rwsem_hb") else 100,
                       post=args.post, workers=n, rep=rep,
                       kd_delta={k: after[k] - before.get(k, 0) for k in after if k != "delegation"})
            print(json.dumps(res), flush=True)
            bad |= not res["ok"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
