#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarize run_grid.py output: kd vs Native (and TCLock) per profile and worker count.

Rates are medians over rounds (one round gives no variance claim; the
number of rounds is printed). For kd the execution class is shown as shares
of all completed operations: delegated, handed back, plain (queued without
delegation); the rest is uncontended or local. Points that failed the data
oracle are marked and excluded.

  grid_summary.py grid.jsonl [more.jsonl ...] [--profiles mutex_c01 ...]
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--profiles", nargs="*")
    args = ap.parse_args()

    pts = defaultdict(list)
    idents = set()
    for path in args.files:
        with open(path) as f:
            for line in f:
                d = json.loads(line)
                idents.add((d["kernel"], d["build"], d["commit"], d["dirty"]))
                pts[(d["profile"], d["workers"], d["backend"])].append(d)
    if len(idents) != 1:
        print("WARNING: mixed identities, do not pool:", sorted(idents))
    else:
        print("identity:", next(iter(idents)))

    profiles = sorted({p for p, _, _ in pts})
    if args.profiles:
        profiles = [p for p in profiles if p in args.profiles]
    has_tc = any(b == "tclock" for _, _, b in pts)
    for prof in profiles:
        print("\n%s" % prof)
        print("  %3s %8s %8s %6s %3s  %6s %6s %6s %6s" %
              ("n", "native", "kd", "kd/nat", "rds", "deleg", "handbk", "plain", "fail") +
              ("  %8s %6s" % ("tclock", "kd/tc") if has_tc else ""))
        for n in sorted({w for p, w, _ in pts if p == prof}):
            nat = [d for d in pts.get((prof, n, "native"), ()) if d["ok"]]
            kd = [d for d in pts.get((prof, n, "kd"), ()) if d["ok"]]
            tc = [d for d in pts.get((prof, n, "tclock"), ()) if d["ok"]]
            fails = sum(not d["ok"] for b in ("native", "kd", "tclock")
                        for d in pts.get((prof, n, b), ()))
            if not nat or not kd:
                print("  %3d  missing (fail=%d)" % (n, fails))
                continue
            mn = statistics.median(d["mops"] for d in nat)
            mk = statistics.median(d["mops"] for d in kd)
            ops = sum(d["ops"] for d in kd) or 1

            def share(key):
                return sum(d["kd_delta"].get(key, 0) for d in kd) / ops

            line = ("  %3d %8.3f %8.3f %6.2f %3d  %5.0f%% %5.1f%% %5.0f%% %6d" %
                    (n, mn, mk, mk / mn if mn else 0, min(len(nat), len(kd)),
                     100 * share("delegated"), 100 * share("handback"),
                     100 * share("plain"), fails))
            if has_tc:
                if tc:
                    mt = statistics.median(d["mops"] for d in tc)
                    line += "  %8.3f %6.2f" % (mt, mk / mt if mt else 0)
                else:
                    line += "  %8s %6s" % ("-", "-")
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
