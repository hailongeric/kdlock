#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarize a run_place.py file: per profile, worker count and placement,
the median rate of every column and its ratio to the first column.

    place_summary.py p.jsonl                  # columns: backend (and config)
    place_summary.py ab.jsonl --fair          # add least/most operations per worker
    place_summary.py ab.jsonl --counters era_gate era_claim era_idle
    place_summary.py p.jsonl --cross          # each placement over the one-node rate

A column is a backend, or a backend under one parameter set when the file
has several. --cross answers "what does crossing nodes cost": the rate of a
placement divided by the rate of the same column with all workers on one
node. Points whose data check failed are listed and left out.
"""
import argparse
import collections
import json
import statistics
import sys


def place_of(r, node_cpus):
    if "placement" in r:
        return r["placement"]
    # Files from before the field existed: two nodes of node_cpus CPUs.
    f, n = r["first_cpu"], r["workers"]
    a = max(0, min(node_cpus, f + n) - f)
    return "+".join(str(x) for x in (a, n - a) if x)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("--fair", action="store_true")
    ap.add_argument("--cross", action="store_true")
    ap.add_argument("--counters", nargs="+", default=[])
    ap.add_argument("--node-cpus", type=int, default=32)
    args = ap.parse_args()

    rate = collections.defaultdict(list)
    fair = collections.defaultdict(list)
    cnt = collections.defaultdict(list)
    cols, keys, failed = [], [], 0
    for line in open(args.file):
        r = json.loads(line)
        col = (r.get("backend", "kd"), r.get("cfg", ""))
        key = (r["profile"], r["workers"], place_of(r, args.node_cpus))
        if not r.get("ok"):
            failed += 1
            print("FAILED: %s %s" % (key, col), file=sys.stderr)
            continue
        if col not in cols:
            cols.append(col)
        if key not in keys:
            keys.append(key)
        rate[(key, col)].append(r["mops"])
        fair[(key, col)].append(r["min_worker_ops"] / max(1, r["max_worker_ops"]))
        d = r.get("kd_delta") or {}
        cnt[(key, col)].append([d.get(c, 0) for c in args.counters])

    def order(k):
        parts = [int(x) for x in k[2].split("+")]
        return (k[0], k[1], len(parts) > 1, -parts[0])
    keys.sort(key=order)
    multi_be = len({c[0] for c in cols}) > 1
    multi_cfg = len({c[1] for c in cols}) > 1
    names = ["/".join(x for x in ((c[0] if multi_be or not multi_cfg else ""),
                                  (c[1] if multi_cfg else "")) if x) or c[0] for c in cols]
    for i, n in enumerate(names):
        print("[%d] %s" % (i + 1, n))
    print()
    head = "%-13s %3s %-7s" % ("profile", "n", "place")
    for i in range(len(cols)):
        head += "  %13s" % ("[%d]" % (i + 1))
    print(head)
    for key in keys:
        row = "%-13s %3d %-7s" % key
        base = None
        for col in cols:
            v = rate.get((key, col))
            if not v:
                row += "  %13s" % "-"
                continue
            m = statistics.median(v)
            if args.cross:
                one = rate.get(((key[0], key[1], str(key[1])), col))
                ref = statistics.median(one) if one else None
            else:
                base = base or m
                ref = base
            row += "  %6.2f (%4.2f)" % (m, m / ref) if ref else "  %6.2f       " % m
            if args.fair:
                row += " f%.2f" % statistics.median(fair[(key, col)])
            for j, c in enumerate(args.counters):
                row += " %s=%d" % (c[4:] if c.startswith("era_") else c,
                                   statistics.median(x[j] for x in cnt[(key, col)]))
        print(row)
    if failed:
        print("\n%d failed point(s) left out" % failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
