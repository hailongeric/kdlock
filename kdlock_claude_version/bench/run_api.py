#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Syscall workloads on switchable lock objects (CONFIG_KDLOCK_API).

Runs bench/api_stress for each mode, worker count and backend. The kd_api
core parameter decides which lock new objects get (0 native, a family
bit mask for kdlock); every run starts a new process, whose files table,
files, pipes, lock contexts and xattr sets are created after the setting,
so Native and kd alternate within one boot. uts_sem is fixed at boot
(kd_uts=1 on the command line): the uts mode reports which one it ran on
and is compared across two boots.

  run_api.py --out api.jsonl --modes setfd ofd pipe seek xattr \\
             --workers 1 4 8 16 32 --rounds 2 --seconds 5

A point fails if api_stress reports a mismatch or exits non-zero, does not
finish, or the kernel log reports a problem while it ran.
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

KD_API = "/sys/module/kernel/parameters/kd_api"
KD_UTS = "/sys/module/kernel/parameters/kd_uts"
# Family bit per mode (kd_sw_spin.h): spin 1, rwlock 2, mutex 4, rwsem 8.
FAMILY = {"setfd": 1, "ofd": 1, "pipe": 4, "seek": 4, "xattr": 2, "uts": 8}


def run_point(binary, mode, workers, seconds, arg):
    cmd = [binary, mode, str(workers), str(seconds)] + ([str(arg)] if arg is not None else [])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds + 120)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    res = {"returncode": p.returncode, "stderr": p.stderr[-2000:]}
    for line in p.stdout.splitlines():
        f = line.split()
        if f[:1] == ["mode"] and "rate" in f:
            res["ops"] = int(f[f.index("ops") + 1])
            res["rate"] = float(f[f.index("rate") + 1])
            res["elapsed"] = float(f[f.index("seconds") + 1])
            res["verdict"] = f[-1]
    res["ok"] = p.returncode == 0 and res.get("verdict") == "ok"
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--bin", default="/root/api_stress")
    ap.add_argument("--modes", nargs="+", default=["setfd", "ofd", "pipe", "seek", "xattr"])
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 4, 8, 16, 32])
    ap.add_argument("--backends", nargs="+", default=["native", "kd"])
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--seconds", type=int, default=5)
    ap.add_argument("--arg", type=int, default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--warmup", type=int, default=3,
                    help="seconds of one untimed kd run per mode first, so the daemon "
                         "has translated its sites before timing (0: none)")
    args = ap.parse_args()

    ident = {"kernel": platform.release(), "build": platform.version(), "tag": args.tag}
    if os.path.exists(KD_UTS):
        ident["kd_uts"] = open(KD_UTS).read().strip()
    bad = 0
    if args.warmup:
        for mode in args.modes:
            with open(KD_API, "w") as f:
                f.write(str(FAMILY[mode]))
            run_point(args.bin, mode, max(args.workers), args.warmup, args.arg)
            with open(KD_API, "w") as f:
                f.write("0")
            time.sleep(5)
    with open(args.out, "a") as out:
        for rnd in range(args.rounds):
            for mode in args.modes:
                for n in args.workers:
                    k = (rnd + n) % len(args.backends)
                    for backend in args.backends[k:] + args.backends[:k]:
                        if mode == "uts":
                            backend = "kd" if ident.get("kd_uts") == "Y" else "native"
                        with open(KD_API, "w") as f:
                            f.write(str(FAMILY[mode] if backend == "kd" else 0))
                        complaints = len(run_corr.kernel_complaints())
                        before = run_nano.kd_stats()
                        res = run_point(args.bin, mode, n, args.seconds, args.arg)
                        after = run_nano.kd_stats()
                        with open(KD_API, "w") as f:
                            f.write("0")
                        new = run_corr.kernel_complaints()[complaints:]
                        if new:
                            res["ok"] = False
                            res["kernel_complaints"] = new
                        res.update(ident, mode=mode, workers=n, backend=backend, round=rnd,
                                   seconds=args.seconds, arg=args.arg, time=time.time(),
                                   kd_delta={x: after[x] - before.get(x, 0)
                                             for x in after if x != "delegation"})
                        out.write(json.dumps(res) + "\n")
                        out.flush()
                        bad += not res["ok"]
                        d = res["kd_delta"]
                        print("%-6s n%-2d %-6s %s %12s  deleg %d hb %d" % (
                            mode, n, backend, "ok  " if res["ok"] else "FAIL",
                            "%.0f" % res["rate"] if "rate" in res else "-",
                            d.get("delegated", 0), d.get("handback", 0)), flush=True)
                        if mode == "uts":
                            break
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
