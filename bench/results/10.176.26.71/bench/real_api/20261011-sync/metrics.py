#!/usr/bin/env python3
"""Derive report facts from accepted final records; no execution or tuning."""
import json
from pathlib import Path
import runpy
import sys

base = Path(sys.argv[1])
records, rows = [], []
for run in sorted(base.glob('real-sync-*-final-v1')):
    rs = json.loads((run/'records.json').read_text())
    assert all(r['execution_status'] == 'OK' and r['drained'] for r in rs)
    summarize = runpy.run_path(str(run/'source/bench/real_api/report.py'))['summarize']
    records.extend(rs)
    rows.extend(summarize(rs))
groups = {}
for row in rows:
    key = (row['kind'], row['query'], row['entries'], row['threads'])
    groups.setdefault(key, {})[row['arm']] = row
points = []
for (kind, query, entries, threads), arms in sorted(groups.items()):
    assert set(arms) == {'stock','native','tclock','kdlock'}
    assert all(r['accepted'] == 3 for r in arms.values())
    kd = arms['kdlock']
    ratios = {f'{metric}_{other}': kd[f'{metric}_{stat}']/arms[other][f'{metric}_{stat}']
              for metric, stat in (('whole','median'),('peak','max'))
              for other in ('stock','native','tclock')}
    points.append(dict(kind=kind, query=query, entries=entries, threads=threads,
                       strict_pass=all(ratios[f'{metric}_{other}'] >= 1
                                       for metric in ('whole','peak') for other in ('native','tclock')),
                       ratios=ratios, arms=arms))
stats = dict(accepted=len(records), operations=sum(r['measurement']['completed'] for r in records),
             points=len(points), multithread_points=sum(p['threads'] > 1 for p in points),
             strict_multithread_pass=sum(p['threads'] > 1 and p['strict_pass'] for p in points),
             kinds={})
for kind in sorted({r['kind'] for r in records}):
    rs = [r for r in records if r['kind'] == kind]
    kd = [r for r in rs if r['arm'] == 'kdlock']
    busy = [r for r in kd if r['threads'] >= 16]
    tc = [r for r in rs if r['arm'] == 'tclock' and isinstance(r['tclock_delegation'],int)]
    stats['kinds'][kind] = dict(sessions=len(rs), operations=sum(r['measurement']['completed'] for r in rs),
        kd_sessions=len(kd), kd_jit_positive=sum(r['jit_bodies'] > 0 for r in kd),
        jit_bodies=sum(r['jit_bodies'] for r in kd),
        eligible=sum(r['jit_eligible_operations'] for r in kd),
        busy_jit_share_range=[min(r['jit_share'] for r in busy),max(r['jit_share'] for r in busy)],
        no_jit=[r['name'] for r in kd if not r['jit_bodies']],
        tclock_delegated=sum(r['tclock_delegation'] for r in tc) if tc else None,
        tclock_busy_share_range=([min(r['tclock_delegation']/r['measurement']['completed'] for r in tc if r['threads'] >= 16),
                                 max(r['tclock_delegation']/r['measurement']['completed'] for r in tc if r['threads'] >= 16)]
                                if tc else None))
print(json.dumps(dict(stats=stats,points=points), indent=2))
