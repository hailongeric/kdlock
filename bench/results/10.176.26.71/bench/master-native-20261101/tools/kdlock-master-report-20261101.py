"""Offline analysis of retained master campaign archives; no live work."""
from pathlib import Path
import argparse,csv,hashlib,json,math,tarfile
p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
GRID=[*range(1,9),*range(12,61,4)]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read_selected(name,predicate):
 path=a.archives/(name+'.tar.gz');found={}
 with tarfile.open(path,'r:gz') as t:
  for m in t:
   if m.isfile() and predicate(m.name):found[m.name]=json.load(t.extractfile(m))
 return found

def pair(label,by,metrics=('whole',)):
 rows=[];summary=[]
 for workload in sorted(by):
  group=by[workload];assert set(group)==set(GRID),(label,workload,'grid')
  for n in GRID:
   arms=group[n];assert set(arms)=={'native','kd'},(label,workload,n,'arms')
   row={'workload':workload,'workers':n}
   for metric in metrics:
    native,kd=(arms[x][metric] for x in ('native','kd'));assert native>0 and kd>0
    row.update({metric+'_native_ops_s':native,metric+'_kd_ops_s':kd,metric+'_change_pct':100*(kd/native-1)})
   rows.append(row)
  s={'workload':workload,'points':21}
  for metric in metrics:
   selected=[x for x in rows if x['workload']==workload]
   ratios=[x[metric+'_kd_ops_s']/x[metric+'_native_ops_s'] for x in selected]
   s[metric]={'geomean_change_pct':100*(math.exp(sum(map(math.log,ratios))/len(ratios))-1),'minimum_change_pct':100*(min(ratios)-1),'maximum_change_pct':100*(max(ratios)-1),'loss_points':sum(x<1 for x in ratios),'workers60_change_pct':selected[-1][metric+'_change_pct']}
  summary.append(s)
 out=a.output/label;out.mkdir()
 with (out/'points.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 (out/'points.json').write_text(json.dumps(rows,indent=2)+'\n')
 return summary

def insert(by,workload,n,arm,values):
 slot=by.setdefault(workload,{}).setdefault(n,{})
 assert arm not in slot,(workload,n,arm,'duplicate');slot[arm]=values

nano=read_selected('nano',lambda n:n.startswith('0-master-native-20261101/nano/') and len(n.split('/'))==4 and n.endswith('/records.json'))
assert len(nano)==10
by={};raw=[]
for name,records in nano.items():
 assert len(records)==42
 for r in records:
  assert r['execution_status']=='OK' and r['drained'] and r['measurement']['data_ok'] and r['measurement']['complete'] and r['repeat']==0 and not r['functional']
  assert r['threads'] in GRID and r['cpus']==list(range(r['threads'])) and r['collector_cpu']==63 and r['post_work_rounds']==256 and r['duration_ms']==2000
  arm='kd' if r['arm']=='kdlock' else r['arm'];assert arm in ('native','kd')
  m=r['measurement'];whole=m['completed']*1e9/m['wall_ns'];assert abs(whole-r['whole_ops_s'])<1e-6*whole
  workload=r['lock_kind']+'-c'+str(r['cachelines']).zfill(2)+'-w'+str(r['write_percent'])
  insert(by,workload,r['threads'],arm,{'whole':whole,'peak':r['peak_ops_s']});raw.append(r)
(a.output/'nano-records.json').write_text(json.dumps(raw,indent=2)+'\n')
summaries={'nano':pair('nano',by,('whole','peak'))}
by={};raw={}
for mode in ('native','kd'):
 found=read_selected(mode+'-mm',lambda n:n=='0-'+mode+'/mmap1-measure/run/result.json');assert len(found)==1
 result=next(iter(found.values()));assert result['passed'] and result['drained'] and result['planned']==42 and len(result['sessions'])==42 and result['mode']==mode
 raw[mode]=result
 for r in result['sessions']:
  assert r['passed'] and r['drained'] and r['scored'] and r['round']==0 and r['instrumentation']=='none'
  insert(by,r['model'],r['workers'],mode,{'whole':r['output']['pairs_per_nominal_second']})
assert raw['native']['binary_sha256']==raw['kd']['binary_sha256']
(a.output/'mmap1-records.json').write_text(json.dumps(raw,indent=2)+'\n');summaries['mmap1']=pair('mmap1',by)
found=read_selected('syscall',lambda n:n=='1-syscall-measure/result.json');assert len(found)==1
result=next(iter(found.values()));assert result['passed'] and result['drained'] and len(result['sessions'])==126
by={}
for r in result['sessions']:
 assert r['passed'] and r['drained'] and r['round']==0 and r['instrumentation']=='none'
 insert(by,r['kind'],r['workers'],r['arm'],{'whole':r['whole_throughput_ops_s']})
(a.output/'syscall-records.json').write_text(json.dumps(result,indent=2)+'\n');summaries['syscall']=pair('syscall',by)
(a.output/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
(a.output/'archive-sha256.json').write_text(json.dumps({n:digest(a.archives/(n+'.tar.gz')) for n in ['nano','native-mm','kd-mm','syscall']},indent=2)+'\n')
print(json.dumps(summaries,indent=2))
