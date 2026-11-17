#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""More threads than CPUs: the same nano point with 1, 2, 4... workers per CPU.

The workers of a run share `--cpus` CPUs (worker i is bound to CPU
first + i % cpus), so with a factor of 2 every CPU has two runnable threads
that take the same lock. What that changes is who can be taken off its CPU:
a spinlock holder or waiter cannot (preemption is off), a mutex or rwsem
holder can, and so can a waiter that is not spinning.

  run_oversub.py --out o.jsonl --profiles mutex:1:100 rwsem:1:20 --cpus 16
  run_oversub.py --out o.jsonl --profiles spin:1:100 --cpus 8 16 --factors 1 2 4 8

A profile is family:lines:write-percent. The backends alternate per point.
TCLock runs only where every CPU has one worker. Its mutex and rwsem
adapters allow one registered task per CPU, and its spinlock with two
workers per CPU crashed the guest twice within seconds, on build #82 with
nothing else running ("stack-protector: Kernel stack is corrupted in:
__schedule", in a second worker of a CPU; kd and Native ran the same point
cleanly before it). A point in which some worker completed no
operation at all is reported as failed by run_nano ("ok": false); here that
is a result (a starved worker), so the rate is kept and `starved` counts
such workers.
"""
import argparse
import json
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_nano  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--profiles", nargs="+", required=True, help="family:lines:write-pct")
    ap.add_argument("--backends", nargs="+", default=["native", "kd"])
    ap.add_argument("--cpus", type=int, nargs="+", default=[16])
    ap.add_argument("--factors", type=int, nargs="+", default=[1, 2, 4],
                    help="workers per CPU")
    ap.add_argument("--first-cpu", type=int, default=0)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--ms", type=int, default=2000)
    ap.add_argument("--warmup-ms", type=int, default=500)
    ap.add_argument("--post", type=int, default=256)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    ident = {"kernel": platform.release(), "build": platform.version(), "tag": args.tag}
    fd = os.open("/dev/kdbench", os.O_RDWR)
    with open(args.out, "a") as out:
        for rnd in range(args.rounds):
            for prof in args.profiles:
                fam, lines, pct = prof.split(":")
                for cpus in args.cpus:
                    for factor in args.factors:
                        n = cpus * factor
                        if n > run_nano.MAXW:
                            continue
                        k = (rnd + factor) % len(args.backends)
                        for be in args.backends[k:] + args.backends[:k]:
                            if be == "tclock" and factor > 1:
                                continue
                            na = argparse.Namespace(family=fam, lines=int(lines),
                                                    write_pct=int(pct), post=args.post,
                                                    backend=be, first_cpu=args.first_cpu,
                                                    cpus=cpus, per_worker=True)
                            try:
                                run_nano.run_once(fd, na, n, args.warmup_ms)
                                before = run_nano.kd_stats() if be == "kd" else {}
                                res = run_nano.run_once(fd, na, n, args.ms)
                                after = run_nano.kd_stats() if be == "kd" else {}
                            except OSError as e:
                                print("%-13s %2d x%d %-6s error %s" % (prof, cpus, factor, be, e),
                                      flush=True)
                                continue
                            w = res.pop("worker_ops")
                            res.update(ident, profile=prof, workers=n, cpus=cpus, factor=factor,
                                       backend=be, round=rnd,
                                       starved=sum(1 for x in w if not x),
                                       # CPU share: operations of a CPU's workers together.
                                       min_cpu_ops=min(sum(w[c::cpus]) for c in range(cpus)),
                                       max_cpu_ops=max(sum(w[c::cpus]) for c in range(cpus)),
                                       kd_delta={x: after[x] - before.get(x, 0)
                                                 for x in after if x != "delegation"})
                            out.write(json.dumps(res) + "\n")
                            out.flush()
                            print("%-13s %2d cpus x%d %-6s %7.3f Mops  worker min/max %.2f%s" % (
                                prof, cpus, factor, be, res["mops"],
                                res["min_worker_ops"] / max(1, res["max_worker_ops"]),
                                "  starved %d" % res["starved"] if res["starved"] else ""),
                                flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
