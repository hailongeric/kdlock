from pathlib import Path
import json,shlex,subprocess
out=Path('/tmp/kdlock-shape-4506f6e4-preflight');out.mkdir(exist_ok=False)
r=json.loads(Path('/tmp/kdlock-shape-4506f6e4-freeze/transfer.stdout').read_text())
code=r'''from pathlib import Path
import json,os,runpy,shutil,subprocess,sys
sys.dont_write_bytecode=True
r=json.loads(sys.stdin.buffer.read());root=Path(r['root'])
assert os.uname().release=='7.0.0-38-kdlock1'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='3da48c0e-7596-469a-bfea-45122dfd4d81'
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
from provider.prepare import prepare
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle)
assert rt.digest(root/'source-state.json')==r['source_state_sha256']
assert rt.digest(root/'source-sha256.json')==r['source_manifest_sha256']
manifest=json.loads((root/'source-sha256.json').read_text())
def verify():
 for name,wanted in manifest.items():assert rt.digest(root/name)==wanted,name
verify()
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/shape-preflight-4506f6e4');out.mkdir(exist_ok=False)
(out/'temporary').mkdir()
py='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(out/'temporary'))
result=dict(source_commit=r['source_commit'],root=str(root),selected_image_capacity=128,
 default_image_capacity=64,units=[],no_module_load=True,no_reboot=True,no_timing=True,
 original_retention_unchanged=True,boot_id='3da48c0e-7596-469a-bfea-45122dfd4d81')
def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
save()
for index,name in enumerate(('bench/test_mmap1_demand.py','bench/test_mmap1.py','bench/test_mmap1_delegated.py','bench/test_mmap1_image_point.py','mutex/test_rwsem_api.py','bench/test_mmap1_campaign.py')):
 argv=['taskset','-c','63',py,str(root/'tests/unit/run.py'),name]
 p=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=180)
 log=out/('unit-'+str(index)+'.log');log.write_text(p.stdout+p.stderr)
 result['units'].append(dict(test=name,argv=argv,returncode=p.returncode,log=str(log),tail=(p.stdout+p.stderr)[-2200:]))
 save();assert p.returncode==0 and '[SKIP]' not in p.stdout+p.stderr,result['units'][-1]
provider=out/'provider';prepared=prepare(provider,root)
(out/'preparation.json').write_text(json.dumps(prepared,indent=2)+'\n')
argv=['taskset','-c','0-63','make','-C',str(provider/'kernel_module'),
 'KDIR=/mnt/kdlock-builds2/linux-7.0.0-38-kdscope5/build','W=1','-j8',
 'KDLOCK_SELFTEST=0','KDLOCK_NUMA=1','KDLOCK_SPIN_BATCH=1024','KDLOCK_JIT_IMAGES=128','UBSAN_SANITIZE=n']
p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=240)
(out/'build.log').write_text(p.stdout+p.stderr);result['build']=dict(argv=argv,returncode=p.returncode);save()
assert p.returncode==0,p.stderr[-2000:]
module=provider/'kernel_module/kdlock_km.ko'
params=subprocess.check_output(['modinfo','-p',module],text=True,timeout=10)
(out/'parameters.txt').write_text(params);names={line.split(':',1)[0] for line in params.splitlines()}
assert {'bench_quiet','bench_complete_probe','rwsem_provider_demand','jit_timing','service_trace','service_cpus','jit_image_usage','rwsem_provider_entries','rwsem_provider_syscall_shape','rwsem_provider_syscall_shape_version'}<=names
result.update(provider=str(module),provider_sha256=rt.digest(module),
 preparation_kind=prepared['kind'],preparation_sha256=rt.digest(out/'preparation.json'),required_parameters_present=True)
build=out/'daemon-tree';build.mkdir()
shutil.copytree(root/'daemon',build/'daemon');shutil.copytree(root/'include',build/'include')
argv=['taskset','-c','63','make','-C',str(build/'daemon'),'CFLAGS=-O2 -Wall -Wextra -Werror']
p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=90)
(out/'daemon-build.log').write_text(p.stdout+p.stderr);result['daemon_build']=dict(argv=argv,returncode=p.returncode);save()
assert p.returncode==0,p.stderr[-2000:]
result.update(daemon=str(build/'daemon/daemon'),daemon_sha256=rt.digest(build/'daemon/daemon'))
idle(root,rt.idle);verify();result.update(passed=True,final_idle=True,frozen_inputs_unchanged=True);save();print(json.dumps(result))
'''
p=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh',
 'env PYTHONDONTWRITEBYTECODE=1 python3 -c '+shlex.quote(code)])],input=json.dumps(r).encode(),capture_output=True,timeout=950)
(out/'reply.json').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
print('returncode',p.returncode)
if p.returncode==0:
 d=json.loads(p.stdout)
 for row in d['units']:print(row['test'],row['returncode'],row['tail'][-800:])
 print('provider build',d['build']['returncode'],'daemon build',d['daemon_build']['returncode'],'passed',d['passed'],'idle',d['final_idle'])
else:print(p.stderr.decode()[-3000:])
raise SystemExit(p.returncode)
