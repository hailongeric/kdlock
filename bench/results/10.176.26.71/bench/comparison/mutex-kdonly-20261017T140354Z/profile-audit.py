#!/usr/bin/env python3
"""Replay PMU diagnostics separately from the scored benchmark matrices."""
import argparse,importlib.util,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('profile_base',HERE/'legacy-audit.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root,out=a.root.resolve(),a.output.resolve();out.mkdir(parents=True,exist_ok=True)
status=base.read(root/'status.json');base.check(status['state']=='COMPLETE' and status['completed']==8,'unfinished profile')
rows=[];audits={}
for v in ('baseline','compat'):
 folder=root/v/'c01-post64';audit,records=base.audit_c01(folder);audits[v]=audit
 base.check({(r['threads'],r['repeat'],r['arm']) for r in records}=={(2,i,'kdlock') for i in range(4)},'profile coverage')
 for r in records:
  d=folder/r['name'];m=r['measurement'];values={}
  for line in (d/'pmu.csv').read_text().splitlines():
   f=line.split(';')
   if len(f)>2:
    try:values[f[2]]=float(f[0])
    except ValueError:pass
  base.check(all(values.get(n,0)>0 for n in ('cycles','instructions','task-clock')),'missing PMU counter')
  row=dict(version=v,repeat=r['repeat'],sequence=r['sequence'],whole_mops=m['completed']*1e3/m['wall_ns'],ops=m['completed'],cycles_per_op=values['cycles']/m['completed'],instructions_per_op=values['instructions']/m['completed'],mean_ghz=values['cycles']/values['task-clock']/1e6,jit_bodies=r['jit_bodies'],placement=base.read(d/'memory-placement.json'),pmu=values)
  row['hot_stats']=[s for s in (d/'kernel.log').read_text().splitlines() if re.search(r'hotlock.*cpu=[01]\b|mutex.*origin|mutex.*fast',s)]
  rows.append(row)
base.check(len(rows)==8,'missing diagnostic rows')
base.save(out/'profile-samples.json',rows)
base.save(out/'profile-verification.json',dict(status='PASS',sessions=8,accepted=8,drained=8,excluded_from_scores=True,perf=base.read(root/'perf-tool.json'),checks=audits))
print(json.dumps(dict(status='PASS',sessions=8,excluded_from_scores=True)))
