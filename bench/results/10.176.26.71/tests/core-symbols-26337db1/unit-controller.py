from pathlib import Path
import json
import shlex
import subprocess

out=Path('/tmp/kdlock-core-symbols-26337db1-units')
out.mkdir(exist_ok=False)
request=json.loads(Path('/tmp/kdlock-core-symbols-26337db1-freeze/transfer.stdout').read_text())
code='''from pathlib import Path
import json,os,runpy,shutil,subprocess,sys
sys.dont_write_bytecode=True
r=json.loads(sys.stdin.buffer.read());root=Path(r['root'])
assert os.uname().release=='7.0.0-38-kdlock1'
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='1ed38b4b-301c-4c76-a2a1-eb4b9f1bd93e'
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle)
assert rt.digest(root/'source-state.json')==r['source_state_sha256']
assert rt.digest(root/'source-sha256.json')==r['source_manifest_sha256']
manifest=json.loads((root/'source-sha256.json').read_text())
def verify():
 for name,wanted in manifest.items():assert rt.digest(root/name)==wanted,name
verify()
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/core-symbols-26337db1-units');out.mkdir(exist_ok=False)
(out/'temporary').mkdir()
py='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(out/'temporary'),PATH=str(Path(py).parent)+':/usr/sbin:/usr/bin:/sbin:/bin')
result=dict(source=r,boot_id=boot,release=os.uname().release,units=[],passed=False,no_module_load=True,no_reboot=True)
def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\\n')
try:
 for index,name in enumerate(('admission/test_kernel_symbols.py','codegen/test_jit_diagnostics.py','admission/test_context_policy.py')):
  argv=['taskset','-c','63',py,str(root/'tests/unit/run.py'),name]
  p=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=180)
  log=out/('unit-'+str(index)+'.log');log.write_text(p.stdout+p.stderr)
  result['units'].append(dict(test=name,argv=argv,returncode=p.returncode,log=str(log),log_sha256=rt.digest(log),tail=(p.stdout+p.stderr)[-2000:]))
  save();assert p.returncode==0 and '[SKIP]' not in p.stdout+p.stderr,result['units'][-1]
 idle(root,rt.idle);verify();result.update(passed=True,final_idle=True,frozen_inputs_unchanged=True)
finally:
 save()
print(json.dumps(result))
'''
p=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join([
 '/home/eric/vm/qemu-scripts/vm_ssh.sh','env PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -c '+shlex.quote(code)])],
 input=json.dumps(request).encode(),capture_output=True,timeout=600)
(out/'reply.json').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
(out/'controller-status.json').write_text(json.dumps(dict(returncode=p.returncode))+'\n')
assert p.returncode==0,p.stderr.decode()
r=json.loads(p.stdout)
for row in r['units']:print(row['test'],row['returncode'],row['tail'])
print('passed',r['passed'],'final_idle',r['final_idle'])
