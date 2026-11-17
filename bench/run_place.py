#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""The same nano point at several CPU placements, optionally under several
sets of kdlock core parameters, within one boot.

run_nano puts worker i on CPU first+i, so the first CPU decides how many
workers land on each NUMA node. With the worker count fixed, the difference
between "all on one node" and "split over two" is the cost of crossing nodes
and nothing else; the worker grid cannot show that, because there the
placement changes together with the count.

  run_place.py --out p.jsonl --profiles rwsem:1:20 rwlock:16:20 --workers 32
  run_place.py --out p.jsonl --profiles rwsem:1:20 --workers 32 --firsts 0 1 4 8 16
  run_place.py --out ab.jsonl --profiles rwsem:1:20 --workers 32 --backends kd \\
      --configs kd_rw_era_ns=0 kd_rw_era_ns=200000,kd_rw_era_press=25

A profile is family:lines:write-percent. Without --firsts each count runs
twice: from CPU 0, and centred on the boundary between node 0 and node 1.
With --configs every set is written to /sys/module/kernel/parameters before
its runs, the order of the sets rotates per round so that drift affects them
alike, and the values found at the start are put back at the end. Summarize
with place_summary.py.
"""
import argparse
import json
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_nano  # noqa: E402

PARAMS = "/sys/module/kernel/parameters"


def node_of_cpus():
    """CPU number -> NUMA node, from sysfs."""
    nodes = {}
    base = "/sys/devices/system/node"
    for d in os.listdir(base):
        if not d.startswith("node") or not d[4:].isdigit():
            continue
        for part in open("%s/%s/cpulist" % (base, d)).read().strip().split(","):
            lo, _, hi = part.partition("-")
            for c in range(int(lo), int(hi or lo) + 1):
                nodes[c] = int(d[4:])
    return nodes


def placement(nodes, first, n):
    """'32' for one node, '16+16' in node order otherwise."""
    per = {}
    for c in range(first, first + n):
        per[nodes.get(c, 0)] = per.get(nodes.get(c, 0), 0) + 1
    return "+".join(str(per[k]) for k in sorted(per))


def set_params(cfg):
    for kv in filter(None, cfg.split(",")):
        k, v = kv.split("=")
        with open("%s/%s" % (PARAMS, k), "w") as f:
            f.write(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--profiles", nargs="+", required=True, help="family:lines:write-pct")
    ap.add_argument("--backends", nargs="+", default=["native", "kd", "tclock"])
    ap.add_argument("--workers", type=int, nargs="+", default=[32])
    ap.add_argument("--firsts", type=int, nargs="+",
                    help="first CPUs (default: 0, and centred on the first node boundary)")
    ap.add_argument("--configs", nargs="+", default=[""],
                    help="sets of core parameters, each 'name=value,name=value'")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--ms", type=int, default=1000)
    ap.add_argument("--warmup-ms", type=int, default=300)
    ap.add_argument("--post", type=int, default=256)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    nodes = node_of_cpus()
    boundary = min((c for c in nodes if nodes[c] == 1), default=0)
    names = sorted({kv.split("=")[0] for c in args.configs for kv in c.split(",") if kv})
    saved = ",".join("%s=%s" % (k, open("%s/%s" % (PARAMS, k)).read().strip()) for k in names)
    ident = {"kernel": platform.release(), "build": platform.version(), "tag": args.tag}
    fd = os.open("/dev/kdbench", os.O_RDWR)
    bad = 0
    try:
        with open(args.out, "a") as out:
            for rnd in range(args.rounds):
                k = rnd % len(args.configs)
                for cfg in args.configs[k:] + args.configs[:k]:
                    set_params(cfg)
                    for prof in args.profiles:
                        fam, lines, pct = prof.split(":")
                        na = argparse.Namespace(family=fam, lines=int(lines), write_pct=int(pct),
                                                post=args.post, backend=None, first_cpu=0)
                        for n in args.workers:
                            firsts = args.firsts or sorted({0, max(0, boundary - n // 2)})
                            for first in firsts:
                                for be in args.backends:
                                    na.backend, na.first_cpu = be, first
                                    run_nano.run_once(fd, na, n, args.warmup_ms)
                                    before = run_nano.kd_stats() if be == "kd" else {}
                                    res = run_nano.run_once(fd, na, n, args.ms)
                                    after = run_nano.kd_stats() if be == "kd" else {}
                                    res.update(ident, profile=prof, workers=n, backend=be,
                                               first_cpu=first,
                                               placement=placement(nodes, first, n),
                                               cfg=cfg, round=rnd,
                                               kd_delta={x: after[x] - before.get(x, 0)
                                                         for x in after if x != "delegation"})
                                    out.write(json.dumps(res) + "\n")
                                    out.flush()
                                    bad += not res["ok"]
                                    print("%-13s n%-2d %-7s %-6s %-28s %7.3f %s" % (
                                        prof, n, res["placement"], be, cfg, res["mops"],
                                        "" if res["ok"] else "FAIL"), flush=True)
    finally:
        set_params(saved)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
