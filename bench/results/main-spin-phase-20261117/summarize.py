"""Summarize completed local-VM evidence; no live module operations."""
import collections,csv,json,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1])
points=[json.loads(line) for line in (root/'points.jsonl').read_text().splitlines()]
counts=('offered','delegated','handback','handback_pinned','sessions','stop_plain','numa_deferred',
        'stop_resched','stop_ctx','stop_budget','mode_enter','mode_exit',
        'nested_local','nested_delegated','hb_frontier','hb_miss','hb_acquire','hb_downgrade','hb_other')
fields=('phase','policy','family','backend','workers','lines','post','first_cpu','round','mops','ops','writes','ok')
with (root/'rates-and-counts.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields+counts,lineterminator='\n');w.writeheader()
    for p in points:
        row={key:p[key] for key in fields}
        row.update({key:p['kd_delta'].get(key,0) for key in counts})
        w.writerow(row)
keys=('phase','policy','family','backend','workers','lines','post','first_cpu')
groups=collections.defaultdict(list)
for p in points:
    if p['phase'] in ('three-way','daemon-off','outside-work','numa-packed','policy'):
        groups[tuple(p[key] for key in keys)].append(p)
cells=[]
for key,ps in sorted(groups.items()):
    c=dict(zip(keys,key));rates=[p['mops'] for p in ps]
    c.update(n=len(ps),median=statistics.median(rates),minimum=min(rates),maximum=max(rates),
             all_ok=all(p['ok'] for p in ps),
             counts_sum={key:sum(p['kd_delta'].get(key,0) for p in ps) for key in counts},
             rounds=[{'round':p['round'],'mops':p['mops'],'counts':{key:p['kd_delta'].get(key,0) for key in counts}} for p in ps])
    cells.append(c)
by_family=collections.Counter()
for p in points:
    by_family[p['family']]+=p['kd_delta'].get('handback',0)
result={'identity':json.loads((root/'identity.json').read_text()),'point_count':len(points),
        'failed':sum(not p['ok'] for p in points),'phases':dict(collections.Counter(p['phase'] for p in points)),
        'handbacks_all_phases_by_family':dict(by_family),'cells':cells,
        'counter_note':'Approximate KD event deltas, not ownership evidence or measured physical chain length. Count sums cover all measured repetitions of the cell; the median rate can belong to one repetition. KD counts on TCLock points are not TCLock execution counts.'}
(root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'point_count':result['point_count'],'failed':result['failed'],'cells':len(cells)}))
