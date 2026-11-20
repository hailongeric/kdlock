#!/usr/bin/env python3
"""k21_summary.py DATA_DIR: kdall21 off and on against its native twin kdnat18 (reduced grid)."""
import sys, collections

D = sys.argv[1].rstrip('/') + '/'


def rows(fn, tags):
    for l in open(D + fn):
        h, _, rest = l.partition(" | ")
        f = h.split()
        if len(f) < 6 or f[0] not in tags:
            continue
        try:
            v = float(f[5])
        except ValueError:
            continue
        b, _, a = rest.partition("| ")
        b, a = b.split(), a.split()
        dl = (int(a[0]) - int(b[0]), int(a[1]) - int(b[1])) if len(a) > 1 and len(b) > 1 else (0, 0)
        yield f[0], f[1], (f[2], f[3], int(f[4])), v, dl


nat, kd, dl = {}, collections.OrderedDict(), {}
for fn in ('n18-runs.txt', 'n18-leveldb-runs.txt'):
    for tag, mode, key, v, _ in rows(fn, ('n18',)):
        nat[key] = v
for fn in ('k21-runs.txt', 'k21-leveldb-runs.txt'):
    for tag, mode, key, v, d in rows(fn, ('k21', 'k21-after')):
        m = mode if tag == 'k21' else 'after'
        kd.setdefault(key, {})[m] = v
        dl[key + (m,)] = d
print("| bench | variant | workers | native | off/native | on/native | on/off | on: delegated, handbacks | on, after LevelDB / native |")
print("|---|---|---|---|---|---|---|---|---|")
r = lambda a, b: "%.2f" % (a / b) if a and b else "-"
low = []
for key, v in kd.items():
    n = nat.get(key)
    print("| %s | %s | %d | %s | %s | %s | %s | %d, %d | %s |" % (
        key + ("%.4g" % n if n else "-", r(v.get('off'), n), r(v.get('on'), n), r(v.get('on'), v.get('off')))
        + dl.get(key + ('on',), (0, 0)) + (r(v.get('after'), n),)))
    for m, bound in (('off', 0.93), ('on', 0.90)):
        if n and v.get(m) and v[m] / n < bound:
            low.append("%s %s %d %s %.2f" % (key + (m, v[m] / n)))
print()
print("below the bounds (off 0.93, on 0.90):", "; ".join(low) if low else "none")
