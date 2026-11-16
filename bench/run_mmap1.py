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
  run_mmap1.py --out ev.jsonl --test page_fault_shared2 --events

The page_fault_shared tests (bench/wis/tests/page_fault_shared.h, not from
TCLocks) fault on one mapping shared by all threads: 1 with user faults only
(per-VMA lock), 2 with an mprotect pair per pass that splits and merges the
shared VMA (mmap_lock for writing, and faults behind it fall back to
mmap_lock for reading), 3 the same with every fault made from kernel mode
(read() from /dev/zero), which always takes mmap_lock for reading.

--events runs each point under `perf stat -a` and records, per second, the
mmap_lock acquisitions started for reading and for writing (tracepoint
mmap_lock:mmap_lock_start_locking, both backends: it is in mmap_lock.h,
above the backend choice) and the times a native rw_semaphore, of any
object, went to its slow path to wait (lock:contention_begin with only the
read or the write flag; kdlock's own waits are in the kd counters instead).
The tracepoints cost time, so rates of --events runs are not comparable
with plain runs.

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


# perf stat events of --events: (name in the result, event, filter)
EVENTS = [
    ("mmap_read", "mmap_lock:mmap_lock_start_locking", "write == 0"),
    ("mmap_write", "mmap_lock:mmap_lock_start_locking", "write == 1"),
    # LCB_F_READ / LCB_F_WRITE alone: a sleeping rw_semaphore waiter
    ("rwsem_wait_read", "lock:contention_begin", "flags == 2"),
    ("rwsem_wait_write", "lock:contention_begin", "flags == 4"),
]


def run_point(binary, workers, samples, timeout, events=False):
    t0 = time.time()
    cmd = [binary, "-t", str(workers), "-s", str(samples), "-n", "1"]
    if events:
        ev = []
        for _, e, f in EVENTS:
            ev += ["-e", e, "--filter", f]
        cmd = ["perf", "stat", "-a", "-x", ",", "-o", "/tmp/run_mmap1.perf"] + ev + ["--"] + cmd
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd="/tmp")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    counts = None
    if events:
        counts = {}
        with open("/tmp/run_mmap1.perf") as f:
            rows = [l.split(",") for l in f if l[:1].isdigit() or l.startswith("<")]
        for (name, _, _), row in zip(EVENTS, rows):
            counts[name] = int(row[0]) if row[0].isdigit() else None
    avg = None
    for line in p.stdout.splitlines():
        if line.startswith("average:"):
            avg = int(line.split(":")[1])
    # The processes model does not notice a task that aborted; a task that
    # stops counting shows as a lower rate, all of them as 0.
    res = {"ok": p.returncode == 0 and bool(avg), "rate": avg,
           "returncode": p.returncode, "elapsed": time.time() - t0}
    if counts is not None:
        res["events_per_s"] = {k: (v / res["elapsed"] if v is not None else None)
                               for k, v in counts.items()}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--wis", default="/root/wis/build")
    ap.add_argument("--test", default="mmap1",
                    help="will-it-scale test name in --wis (mmap1, mmap2, page_fault1, brk1, page_fault_shared1-3)")
    ap.add_argument("--models", nargs="+", default=["threads", "processes"])
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8, 16, 24, 32])
    ap.add_argument("--backends", nargs="+", default=["native", "kd"])
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--events", action="store_true",
                    help="count mmap_lock acquisitions and rwsem waits with perf stat")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    ident = {"kernel": platform.release(), "build": platform.version(), "tag": args.tag,
             "test": args.test, "events": args.events}
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
                                        60 + 10 * args.samples, args.events)
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
                        ev = res.get("events_per_s")
                        print("%-9s n%-2d %-6s %s %8s  deleg %d hb %d%s" % (
                            model, n, backend, "ok  " if res["ok"] else "FAIL",
                            res.get("rate"), d.get("delegated", 0), d.get("handback", 0),
                            "" if not ev else "  /s: " + " ".join(
                                "%s %.0f" % (k, v or 0) for k, v in ev.items())),
                            flush=True)
    with open(KD_MM, "w") as f:
        f.write("0")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
