"""Read-only archive analysis on 380G10 after hash-verified download."""
import csv,hashlib,json,tarfile
from pathlib import Path
raw=Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/raw/nano-four-lock-20261101')
report=Path('/tmp/kdlock-nano-four-lock-results-20261102/bench/results/10.176.26.71/bench/nano-four-lock-20261101')
assert json.loads((raw/'download-receipt.json').read_text())['completed']
(report/'archives').mkdir(exist_ok=True)
stats={};health={};rows=[]
for base in sorted(raw.iterdir()):
 if not base.is_dir() or not (base/'archives.json').exists():continue
 receipt=json.loads((base/'archives.json').read_text());assert receipt['completed'] and receipt['guest_idle']
 (report/'archives'/(base.name+'.json')).write_bytes((base/'archives.json').read_bytes())
 for group in receipt['groups']:
  # The download receipt already hashes every byte. Read only selected metadata.
  with tarfile.open(base/group['file'],'r:gz') as arc:
   for m in arc:
    if not m.isfile():continue
    if m.name.endswith('/perf-stat.json') and len(Path(m.name).parts)<=5:
     v=json.load(arc.extractfile(m));stats[m.name]=v
     for event,d in v.get('events',{}).items():
      rows.append(dict(archive=base.name,member=m.name,event=event,completed_operations=v.get('completed_operations'),value=d.get('value'),unit=d.get('unit'),per_completed_op=d.get('reported_unit_per_completed_op'),runtime_percent=d.get('runtime_percent'),status=d.get('scaling_status'),scope=v.get('scope')))
    if m.name.endswith('/final-health.json') and len(Path(m.name).parts)==2:
     health[base.name]=json.load(arc.extractfile(m))
(report/'pmu-counters.json').write_text(json.dumps(stats,indent=2)+'\n')
with (report/'pmu-counters.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
(report/'correctness/final-health.json').write_text(json.dumps(health,indent=2)+'\n')
(report/'archives/download-receipt.json').write_bytes((raw/'download-receipt.json').read_bytes())
print(json.dumps(dict(perf_stat_records=len(stats),event_rows=len(rows),health_records=len(health))))
