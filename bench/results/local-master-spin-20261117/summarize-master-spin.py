"""Summarize archived points; execute only inside the authorized local VM."""
import collections,csv,json,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1])
points=[json.loads(line) for line in (root/'points.jsonl').read_text().splitlines()]
counts=('offered','delegated','handback','sessions','stop_plain','numa_deferred','plain_deferred',
        'stop_resched','stop_ctx','stop_budget','mode_enter','mode_exit',
        'nested_local','nested_delegated','hb_frontier','hb_miss','hb_acquire',
        'hb_downgrade','hb_other')
fields=('phase','policy','family','backend','workers','lines','post','first_cpu','round','mops','ops','writes','ok')
with (root/'rates-and-counts.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields+counts,lineterminator='\n');w.writeheader()
    for p in points:
        row={k:p[k] for k in fields}
        row.update({k:p['kd_delta'].get(k,0) for k in counts})
        w.writerow(row)
groups=collections.defaultdict(list)
keys=('phase','policy','family','backend','workers','lines','post','first_cpu')
for p in points:
    if p['phase'] in ('three-way','daemon-off','outside-work','numa-packed','policy'):
        groups[tuple(p[k] for k in keys)].append(p)
summary=[]
for key,ps in sorted(groups.items()):
    row=dict(zip(keys,key));values=[p['mops'] for p in ps]
    row.update(n=len(ps),median=statistics.median(values),minimum=min(values),maximum=max(values),
               all_ok=all(p['ok'] for p in ps),counts_sum={k:sum(p['kd_delta'].get(k,0) for p in ps) for k in counts},
               rounds=[dict(round=p['round'],mops=p['mops'],counts={k:p['kd_delta'].get(k,0) for k in counts}) for p in ps])
    summary.append(row)
result=dict(identity=json.loads((root/'identity.json').read_text()),point_count=len(points),
            failed=sum(not p['ok'] for p in points),phases=dict(collections.Counter(p['phase'] for p in points)),
            counter_note='Approximate event deltas; not ownership evidence or measured physical batch length. Counts_sum covers all timed repetitions, not just the median-rate repetition.',
            cells=summary)
(root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(point_count=result['point_count'],failed=result['failed'],cells=len(summary))))
