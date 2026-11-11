from pathlib import Path
import datetime,hashlib,json,subprocess,time
p=Path('/tmp/kdlock-kernel8-offroot-20261111-01')
argv=['ssh','-T','-p','22','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71','sudo','-n','python3','/home/eric/vm/vm-shared/kdlock/bench/basic/capture_host.py','--snapshot','kdlock-builddisk-clean-20261031']
(p/'recovery-command.json').write_text(json.dumps({'argv':argv,'timeout_seconds':45},indent=2)+'\n')
start=time.time()
with (p/'host-recovery.json').open('xb') as out,(p/'host-recovery.stderr').open('xb') as err:r=subprocess.run(argv,stdout=out,stderr=err,timeout=45)
(p/'host-recovery-result.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-start},indent=2)+'\n')
if r.returncode:raise SystemExit(r.returncode)
c=json.loads((p/'host-recovery.json').read_text());assert c['pins_verified'] and c['frequency_verified'] and c['snapshot_listed'] and c['capture_script_sha256']=='e9417457c4d33eea2a84f70af0ed2839ce5b07abbd4dd70bb84ea66fdaf9bb74'
assert 'kdlock-builddisk-clean-20261031' in c['snapshots'].split('List of snapshots present on all disks:',1)[1].split('List of partial',1)[0]
script="import datetime,json,os; p='/home/eric/vm';s=os.statvfs(p);print(json.dumps({'path':p,'realpath':os.path.realpath(p),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'host_free_bytes':s.f_bavail*s.f_frsize,'total':s.f_blocks*s.f_frsize}))\n"
argv=['ssh','-T','-p','22','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71','python3','-B','-'];(p/'space-command.json').write_text(json.dumps({'argv':argv,'stdin':script,'timeout_seconds':20},indent=2)+'\n')
with (p/'host-space.json').open('xb') as out,(p/'host-space.stderr').open('xb') as err:r=subprocess.run(argv,input=script.encode(),stdout=out,stderr=err,timeout=20)
if r.returncode:raise SystemExit(r.returncode)
v=json.loads((p/'host-space.json').read_text());assert v['host_free_bytes']>=48*1024**3 and v['path']==v['realpath']=='/home/eric/vm'
raw=(json.dumps({'capture':c,'headroom':v},sort_keys=True,indent=2)+'\n').encode();(p/'full-recovery.json').write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
a=json.loads((p/'proposed-argv.json').read_text());a[a.index('--recovery-sha')+1]=digest;(p/'actual-argv.json').write_text(json.dumps(a,indent=2)+'\n')
print(json.dumps({'recovery_sha256':digest,'captured_utc':c['captured_utc'],'host_free_bytes':v['host_free_bytes'],'argv_sha256':hashlib.sha256((p/'actual-argv.json').read_bytes()).hexdigest()}))
