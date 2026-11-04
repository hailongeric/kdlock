from pathlib import Path
import json,shlex,subprocess
out=Path('/tmp/kdlock-reached-mm-jit-far-units-20261103');out.mkdir(exist_ok=False)
host_code=__import__('runpy').run_path('/tmp/kdlock-mm-actual-launch-third-20261103.py')['HOST_CAPTURE']
host=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71','sudo -n taskset -c 63 python3 -'],input=host_code.encode(),capture_output=True,timeout=60)
(out/'host.json').write_bytes(host.stdout);(out/'host.stderr').write_bytes(host.stderr);assert host.returncode==0,host.stderr.decode()
h=json.loads(host.stdout);assert h['snapshot_listed'] and h['pins_verified'] and h['frequency_verified']
code=r'''from pathlib import Path
import json,os,runpy,subprocess,sys
sys.dont_write_bytecode=True
root=Path('/root/kdlock-inputs/reached-mm-jit-far-383e830f-20261103');py='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reached-mm-jit-far-units-20261103');out.mkdir(exist_ok=False)
env=dict(os.environ,KDLOCK_RECOVERY_CONFIRMED='1',KDLOCK_SNAPSHOT_TAG='kdlock-builddisk-clean-20261031',PYTHONDONTWRITEBYTECODE='1',PATH=str(Path(py).parent)+':'+os.environ.get('PATH',''),KDLOCK_PRIVATE_SOURCE_MANIFEST_SHA256='9c90d2b1360cac0d7456a474a1221926adffc316105257d41c8efde7f4daa013',KDLOCK_PRIVATE_SOURCE_STATE_SHA256='bae0db407d668c67465006ed550058169a9ce4dd099f06196cc5ac49f20b222b')
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
result=dict(source_commit='383e830f4c7ac01f8edf9cec05d6c5b91aee8d8f',units=[])
fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK)
os.lseek(fd,0,os.SEEK_END)
try:
 try: result['kmsg_readv_bytes']=os.readv(fd,[bytearray(1<<20)])
 except BlockingIOError:result['kmsg_readv_bytes']=0
 result['kmsg_readv_supported']=True
finally:os.close(fd)
for args in [['execution/test_reached_jit.py'], ['bench/test_mmap1_delegated.py','-v']]:
 r=subprocess.run(['taskset','-c','63',py,str(root/'tests/unit/run.py'),*args],cwd=root,env=env,capture_output=True,text=True,timeout=180)
 log='unit-'+str(len(result['units']))+'.log';(out/log).write_text(r.stdout+r.stderr)
 result['units'].append(dict(args=args,returncode=r.returncode,log=log,tail=(r.stdout+r.stderr)[-8000:]));(out/'result.json').write_text(json.dumps(result,indent=2))
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
if all(x['returncode']==0 for x in result['units']):
 command=[py,str(root/'tests/kernel/jit_continuation/run.py'),'--output',str(out/'cold'),'--family','rwsem','--mode','killable','--execution-mode','reached','--cpus','0-7','--iterations','32','--warmup-iterations','1','--phase-timeout','30','--kernel-variant','kdscope5-kd','--kernel-source','/mnt/kdlock-builds2/linux-7.0.0-38-kdscope5/build','--kernel-baseline','/root/kdlock-kernel-baselines/linux70-kdscope5-kd-20261103']
 r=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=600)
 (out/'cold-runner.log').write_text(r.stdout+r.stderr)
 result.update(cold_returncode=r.returncode,cold_stdout=r.stdout,cold_stderr=r.stderr,cold_result=json.loads((out/'cold/result.json').read_text()) if (out/'cold/result.json').exists() else None)
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](root,rt.idle)
result.update(passed=all(x['returncode']==0 for x in result['units']) and result.get('cold_returncode')==0,final_idle=True)
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
'''
r=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh','env PYTHONDONTWRITEBYTECODE=1 python3 -'])],input=code.encode(),capture_output=True,timeout=1000)
(out/'reply.json').write_bytes(r.stdout);(out/'remote.stderr').write_bytes(r.stderr)
assert r.returncode==0,r.stderr.decode();d=json.loads(r.stdout)
for row in d['units']:print(row['args'],row['returncode'],row['tail'][-300:])
print('resident',d.get('cold_returncode'),(d.get('cold_result') or {}).get('fixture'));assert d['passed'];print('PASS; saved',out/'reply.json')
