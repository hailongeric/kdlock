#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Summarise app_grid.sh runs: one table per benchmark and variant.

  app_summary.py runs.txt TAG [--csv]

Rows are worker counts; columns the value per mode (native, kd off, kd on),
off/native and on/native, and for "on" the delegated sections and
handbacks of that point. Metis reports seconds (lower is better), so its
ratios are native time / kd time: above 1 means kd is faster, as for the
rates. One run per point: ratios near 1 are within run-to-run noise.
"""
import collections
import sys

path, tag = sys.argv[1], sys.argv[2]
csv = "--csv" in sys.argv
val = collections.defaultdict(dict)
deleg = {}
unit = {}
order = []
for line in open(path):
    head, _, rest = line.partition(" | ")
    f = head.split()
    if len(f) < 7 or f[0] != tag:
        continue
    mode, bench, var, n = f[1], f[2], f[3], int(f[4])
    try:
        v = float(f[5])
    except ValueError:
        continue
    key = (bench, var)
    if key not in order:
        order.append(key)
    unit[key] = f[6]
    val[key + (n,)][mode] = v
    if mode == "on":
        b, _, a = rest.partition("| ")
        b, a = b.split(), a.split()
        if len(b) >= 2 and len(a) >= 2 and b[0] != "-":
            deleg[key + (n,)] = (int(a[0]) - int(b[0]), int(a[1]) - int(b[1]))


def ratio(kd, nat, lower_better):
    if not kd or not nat:
        return "-"
    return "%.2f" % ((nat / kd) if lower_better else (kd / nat))


def fmt(x):
    if x is None:
        return "-"
    if x >= 1e6:
        return "%.2f M" % (x / 1e6)
    if x >= 1e4:
        return "%.0f k" % (x / 1e3)
    return "%.4g" % x


if csv:
    print("bench,variant,workers,native,off,on,off_native,on_native,delegated,handbacks")
for key in order:
    lb = unit[key] == "s"
    ns = sorted(k[2] for k in val if k[:2] == key)
    if not csv:
        print("\n### %s %s (%s%s)\n" % (key[0], key[1], unit[key], ", lower is better" if lb else ""))
        print("| workers | native | kd off | kd on | off/native | on/native | delegated, handbacks |")
        print("|---|---|---|---|---|---|---|")
    for n in ns:
        m = val[key + (n,)]
        d = deleg.get(key + (n,))
        row = (n, m.get("native"), m.get("off"), m.get("on"),
               ratio(m.get("off"), m.get("native"), lb), ratio(m.get("on"), m.get("native"), lb))
        if csv:
            print(",".join(map(str, (key[0], key[1]) + row + (d or ("", "")))))
        else:
            print("| %d | %s | %s | %s | %s | %s | %s |" % (
                row[0], fmt(row[1]), fmt(row[2]), fmt(row[3]), row[4], row[5],
                "%d, %d" % d if d else "-"))
