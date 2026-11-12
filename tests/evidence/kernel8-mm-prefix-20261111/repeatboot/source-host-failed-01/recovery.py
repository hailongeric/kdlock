from pathlib import Path
import hashlib,json,subprocess,time,datetime
p=Path('/tmp/kdlock-kernel8-repeatboot-run-20261111-01');helper=Path('/tmp/kdlock-kernel6-preflight-20261111-01/host-read.py')
assert hashlib.sha256(helper.read_bytes()).hexdigest()=='05936f37e7ba3ae185b04c14ccfc87d3de74b429626329842ac1d10c585949b2'
a=['ssh','-T','-p','22','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71','sudo','-n','python3','-B','-']
with (p/'recovery-command.json').open('x') as f:json.dump({'argv':a,'stdin':str(helper),'stdin_sha256':'05936f37e7ba3ae185b04c14ccfc87d3de74b429626329842ac1d10c585949b2','timeout_seconds':60},f,indent=2);f.write(chr(10))
start=time.time()
with (p/'recovery.json').open('xb') as out,(p/'recovery.stderr').open('xb') as err:r=subprocess.run(a,input=helper.read_bytes(),stdout=out,stderr=err,timeout=60)
with (p/'recovery-return.json').open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10))
assert r.returncode==0
proof=json.loads((p/'recovery.json').read_text());assert proof['hostname']=='Super-Server' and proof['pid']==257489 and proof['exe']=='/usr/bin/qemu-system-x86_64'
images=['/home/eric/vm/qemu-disks/ubuntu22.04.img','/home/eric/vm/qemu-disks/sda.qcow2','/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2']
assert [v['path'] for v in proof['images']]==images
assert all(v['path']==v['realpath'] and v['open_fds'] and v['host_available']>=8*1024**3 for v in proof['images'])
commands={v['command']:v['output'] for v in proof['hmp']};assert 'VM status: running' in commands['info status']
for label in ('drive_system','drive_data1','drive_kdlock_builds2'):assert 'kdlock-builddisk-clean-20261031' in commands['info block -v '+label]
assert 'kdlock-builddisk-clean-20261031' in commands['info snapshots']
assert 0<=time.time()-datetime.datetime.fromisoformat(proof['utc']).timestamp()<900
sha=hashlib.sha256((p/'recovery.json').read_bytes()).hexdigest();print(json.dumps({'returncode':r.returncode,'recovery_sha256':sha,'utc':proof['utc']}))
