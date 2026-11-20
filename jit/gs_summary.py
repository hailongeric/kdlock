#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise kd_daemon.py --gs-report: which per-CPU data delegated sections
can touch.

  gs_summary.py REPORT [--site PATTERN] [--all]

The report has one JSON line per image built; the last line of a site is
its current image. Printed: per class the symbols, in how many sites'
images they occur, and how many reading and writing instructions there
are. Classes:

  origin    redirected to the origin's value (current_task, the stack
            canary, the top of stack)
  cpu       this_cpu_off, cpu_number and the preempt count: what the
            per-CPU region analysis follows
  executor  everything else; the copy uses the executor's own
  pointer   %gs with a register: a per-CPU pointer computed at run time
            (this_cpu_ptr() of a dynamically allocated variable)

An "executor" symbol whose value belongs to the task rather than to the
CPU is a defect: the section would read or write the executor's instead
of the origin's. Without --all only the executor and pointer classes are
listed. With --site, only sites whose function matches (substring).
"""
import collections
import json
import sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit(__doc__)
pat = sys.argv[sys.argv.index("--site") + 1] if "--site" in sys.argv else None
if pat in args:
    args.remove(pat)
show_all = "--all" in sys.argv
last = {}
for line in open(args[0]):
    try:
        d = json.loads(line)
    except ValueError:
        continue
    last[d["site"]] = d
sites = [d for d in last.values() if not pat or pat in d["where"]]
agg = collections.defaultdict(lambda: [set(), 0, 0, set()])
for d in sites:
    for name, cls, rd, wr, funcs in d["gs"]:
        a = agg[(cls, name)]
        a[0].add(d["where"])
        a[1] += rd
        a[2] += wr
        a[3].update(funcs)
print("%d sites (%d instructions in their images)" % (len(sites), sum(d["insns"] for d in sites)))
print("| class | symbol | sites | reads | writes | in functions (first 4) |")
print("|---|---|---|---|---|---|")
for (cls, name), (st, rd, wr, funcs) in sorted(agg.items(), key=lambda kv: (kv[0][0], -len(kv[1][0]), kv[0][1])):
    if not show_all and cls not in ("executor", "pointer"):
        continue
    fn = sorted(funcs)
    print("| %s | %s | %d | %d | %d | %s%s |" % (cls, name, len(st), rd, wr, ", ".join(fn[:4]),
                                               " ..." if len(fn) > 4 else ""))
