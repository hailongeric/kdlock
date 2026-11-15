#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""A will-it-scale test with the mmap lock of each new mm chosen per run.

The kernel needs CONFIG_KDLOCK_MM. The kd_mm core parameter decides which
lock a new mm gets (0 native rw_semaphore, 1 kdlock rwsem), so every run
starts new processes after setting it and Native and kd alternate within
one boot. The workloads are the unchanged will-it-scale tests in bench/wis
(TCLocks' copy): mmap1 (map 128 MiB of anonymous private memory and unmap it
untouched), mmap2 (the same with a file mapping), page_fault1 (touch every
page of a 128 MiB anonymous mapping, so the fault path, not mmap itself) and
brk1.

  run_mmap1.py --out mmap1.jsonl --workers 1 2 4 8 16 32 --rounds 2
  run_mmap1.py --out pf1.jsonl --test page_fault1 --models processes

Per point: the harness's own warmup, then --samples one-second samples;
the result is its `average` (iterations per second over all tasks) with
the kdlock counter deltas. Workers run on CPUs 0..N-1 (`-n 1`).

A point fails if the harness does not finish, exits non-zero, or the
kernel log reports a problem while it ran.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_corr  # noqa: E402
import run_nano  # noqa: E402

KD_MM = "/sys/module/kernel/parameters/kd_mm"


def run_point(binary, workers, samples, timeout):
    t0 = time.time()
    try:
        p = subprocess.run([binary, "-t", str(workers), "-s", str(samples), "-n", "1"],
                           capture_output=True, text=True, timeout=timeout, cwd="/tmp")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    avg = None
    for line in p.stdout.splitlines():
        if line.startswith("average:"):
            avg = int(line.split(":")[1])
    return {"ok": p.returncode == 0 and avg is not None, "rate": avg,
            "returncode": p.returncode, "elapsed": time.time() - t0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--wis", default="/root/wis/build")
    ap.add_argument("--test", default="mmap1",
                    help="will-it-scale test name in --wis (mmap1, mmap2, page_fault1, brk1)")
    ap.add_argument("--models", nargs="+", default=["threads", "processes"])
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8, 16, 24, 32])
    ap.add_argument("--backends", nargs="+", default=["native", "kd"])
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    ident = {"kernel": platform.release(), "build": platform.version(), "tag": args.tag,
             "test": args.test}
    bad = 0
    with open(args.out, "a") as out:
        for rnd in range(args.rounds):
            for model in args.models:
                for n in args.workers:
                    k = (rnd + n) % len(args.backends)
                    for backend in args.backends[k:] + args.backends[:k]:
                        with open(KD_MM, "w") as f:
                            f.write("1" if backend == "kd" else "0")
                        complaints = len(run_corr.kernel_complaints())
                        before = run_nano.kd_stats()
                        res = run_point("%s/%s_%s" % (args.wis, args.test, model), n, args.samples,
                                        60 + 10 * args.samples)
                        after = run_nano.kd_stats()
                        new = run_corr.kernel_complaints()[complaints:]
                        if new:
                            res["ok"] = False
                            res["kernel_complaints"] = new
                        res.update(ident, model=model, workers=n, backend=backend, round=rnd,
                                   samples=args.samples, time=time.time(),
                                   kd_delta={k: after[k] - before.get(k, 0)
                                             for k in after if k != "delegation"})
                        out.write(json.dumps(res) + "\n")
                        out.flush()
                        bad += not res["ok"]
                        d = res["kd_delta"]
                        print("%-9s n%-2d %-6s %s %8s  deleg %d hb %d" % (
                            model, n, backend, "ok  " if res["ok"] else "FAIL",
                            res.get("rate"), d.get("delegated", 0), d.get("handback", 0)),
                            flush=True)
    with open(KD_MM, "w") as f:
        f.write("0")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
