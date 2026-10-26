"""Read-only replay of retained shared-mm receipts and final recovery evidence."""
import csv,hashlib,json,sys,tarfile
from pathlib import Path
ROOT=Path('/home/eric/vm/vm-shared/kdlock');BASE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'bench/mmap_lock'))
import aggregate,window
sys.path.insert(0,str(ROOT/'bench/catalog_single'));import collect
plan=json.loads((BASE/'plan.json').read_text());assert plan['state']=='completed_recovered'
assert plan['consumed']==dict(measured_sessions=42,payload_cycles=42,boots=3,full_host_captures=88)
results=plan['completed_results'];assert len(results)==42
report=ROOT/'bench/results/10.176.26.71/bench/catalog-mmap-single-20261026/shared-mm'
published=list(csv.DictReader((report/'table.csv').open()));assert len(published)==42
archive=BASE/'kd-archive.stdout';receipts=[]
with tarfile.open(archive) as t:
 for r,p in zip(results,published):
  name=f"{r['backend']}-n{r['spec']['threads']}";prefix=BASE.name+'/'+name+'/'
  assert r['passed'] and r['drained'] and r['spec']['repeat']==0
  window.check_settling(r['post_setup_settling'])
  raw=t.extractfile(prefix+'client.jsonl').read();assert hashlib.sha256(raw).hexdigest()==r['raw']['sha256']
  rows=[json.loads(line) for line in raw.splitlines()];m=aggregate.validate(rows,r['spec']);assert m==r['measurement']
  assert json.load(t.extractfile(prefix+'result.json'))==r
  assert p['arm']==r['backend'] and int(p['threads'])==r['spec']['threads'] and float(p['ops_s'])==m['pairs_s']
  receipts.append(dict(backend=r['backend'],threads=r['spec']['threads'],sha256=r['raw']['sha256'],peak_status=m['peak_status']))
 expected={(mode,n) for mode in ('native','kd') for n in list(range(1,9))+list(range(12,61,4))}
 assert {(r['backend'],r['threads']) for r in receipts}==expected
 for mode in ('native','kd'):
  ready=json.load(t.extractfile(BASE.name+'/'+mode+'-ready/result.json'))
  assert ready['passed'] and ready['kernel_identity']['running_build_id']=='ef5179e8def44f0255adcd62585f62f118fee30f'
  assert {r['boot_id'] for r in results if r['backend']==mode}=={ready['boot_id']}
manifest=json.loads((BASE/'source-manifest.json').read_text())
for name,h in manifest['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
baseline=json.loads((BASE.parent/'catalog-single-20261026/host-before.json').read_text());captures=[]
for path in sorted(BASE.glob('*/host-endpoint.json')):
 h=json.loads(path.read_text());assert h['passed'] and h['capture']['complete'] and h['pins_verified'] and h['snapshot_listed']
 captures.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),tasks=len(h['qemu'][0]['tasks'])))
 for q in h['qemu']:q['tasks']=[{k:t[k] for k in ('tid','comm','affinity')} for t in q['tasks']]
 assert not collect.exploratory_check(baseline,h),path
assert len(captures)==88
recovery=json.loads((BASE/'recovery-final.stdout').read_text());assert recovery['passed'] and recovery['idle'] and recovery['taint']==0 and len(recovery['modules'])==73 and recovery['grubenv']=='next_entry=\n'
result=dict(passed=True,measured=42,strict_qualified=False,single_round=True,source_hashes=len(manifest['files']),optional_peak_unavailable=sum(r['peak_status']=='unavailable' for r in receipts),receipts=receipts,host_captures=captures,recovery_boot=recovery['boot_id'],archives=[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (BASE/'native-archive.stdout',archive)])
(BASE/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('receipts','host_captures','archives')}))
