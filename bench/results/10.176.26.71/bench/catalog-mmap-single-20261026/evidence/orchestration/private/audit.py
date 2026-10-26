"""Read-only audit of retained single-round private MM evidence and published rates."""
import csv,hashlib,importlib.util,json,sys,tarfile
from pathlib import Path
ROOT=Path('/home/eric/vm/vm-shared/kdlock');BASE=Path(__file__).resolve().parent
REPORT=ROOT/'bench/results/10.176.26.71/bench/catalog-mmap-single-20261026'
spec=importlib.util.spec_from_file_location('mmap_audit_timing',ROOT/'bench/mmap_fault/timing.py');timing=importlib.util.module_from_spec(spec);spec.loader.exec_module(timing)
rows=[];archives=[];frozen=0
for workload,total in [('mmap',21),('fault',63)]:
 result=json.loads((BASE/(workload+'-result.json')).read_text());assert result['passed'] and result['drained'] and len(result['sessions'])==total
 archive=BASE/(workload+'-archive.stdout')
 published=list(csv.DictReader((REPORT/workload/'table.csv').open()))
 assert len(published)==total
 with tarfile.open(archive) as t:
  keys=set()
  for r,p in zip(result['sessions'],published):
   key=(r['threads'],r['arm']);assert key not in keys;keys.add(key)
   assert r['repeat']==0 and r['observation']=='plain' and r['passed'] and r['drained']
   raw=t.extractfile(workload+'/'+r['name']+'/client.jsonl').read()
   client=[json.loads(line) for line in raw.splitlines()]
   checked=timing.validate(client,r);assert checked==r['measurement']
   assert int(p['threads'])==r['threads'] and p['arm']==r['arm'] and float(p['ops_s'])==checked['whole_ops_s']
   assert json.load(t.extractfile(workload+'/'+r['name']+'/result.json'))['measurement']==checked
   rows.append(dict(workload=workload,threads=r['threads'],arm=r['arm'],client_sha256=hashlib.sha256(raw).hexdigest(),peak_status=checked['peak_status']))
 archives.append(dict(path=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bytes=archive.stat().st_size))
archive=BASE/'private-full-archive.stdout'
with tarfile.open(archive) as t:
 inputs=json.load(t.extractfile(BASE.name+'/prepare/inputs.json'))
 prefix='/root/kdlock-evidence/10.176.26.71/bench/'+BASE.name+'/'
 manifest=json.loads((BASE/'source-manifest.json').read_text())
 for path,h in inputs['files'].items():
  if path.startswith(prefix):data=t.extractfile(BASE.name+'/'+path[len(prefix):]).read()
  else:
   assert path.startswith('/root/host_fs/kdlock/')
   rel=path.removeprefix('/root/host_fs/kdlock/');assert manifest['files'][rel]==h
   data=(ROOT/rel).read_bytes()
  assert hashlib.sha256(data).hexdigest()==h,path
  frozen+=1
archives.append(dict(path=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bytes=archive.stat().st_size))
result=dict(passed=True,measurements=len(rows),single_round=True,strict_qualified=False,frozen_input_hashes=frozen,optional_peak_unavailable=sum(r['peak_status']=='unavailable' for r in rows),archives=archives,receipts=rows)
(BASE/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('archives','receipts')}))
