#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""What the discover pass saw: per candidate the lock users that asked for
delegation and are outside the allow list (screen.sh discover runs with an
empty list, so every contended delegable lock call is one), and per lock
user the candidates that contend there.

  discover_summary.py DATA_DIR TAG

Counts are the daemon's request events, which the kernel rate-limits: they
order the sites of one candidate, they are not acquisition counts.
"""
import collections
import os
import re
import sys

d, tag = sys.argv[1].rstrip("/"), sys.argv[2]
per, by = {}, collections.defaultdict(list)
for fn in sorted(os.listdir(d + "/discover")):
    if not fn.startswith(tag + "-"):
        continue
    cid = fn[len(tag) + 1:-4]
    sites = collections.Counter()
    for l in open(d + "/discover/" + fn):
        m = re.match(r"\s+(\d+)\s+0x[0-9a-f]+\s+(\S+?)\+0x", l)
        if m:
            sites[m.group(2)] += int(m.group(1))
    per[cid] = sites
    for s, n in sites.items():
        by[s].append((n, cid))
print("| candidate | lock users asking for delegation (requests) |")
print("|---|---|")
for cid, sites in per.items():
    print("| %s | %s |" % (cid, ", ".join("%s %d" % x for x in sites.most_common(4)) or "none"))
print()
print("| lock user | candidates | requests | which |")
print("|---|---|---|---|")
for s, l in sorted(by.items(), key=lambda kv: -sum(n for n, _ in kv[1])):
    tot = sum(n for n, _ in l)
    if tot < 20:
        continue
    l.sort(reverse=True)
    print("| %s | %d | %d | %s |" % (s, len(l), tot, ", ".join(c for _, c in l[:6]) + (" ..." if len(l) > 6 else "")))
