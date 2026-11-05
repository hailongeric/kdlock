from pathlib import Path
import json
import shlex
import subprocess

out=Path('/tmp/kdlock-core-symbols-26337db1-baseline-check');out.mkdir(exist_ok=False)
code='''from pathlib import Path
import json,os,runpy,subprocess,sys
sys.dont_write_bytecode=True
root=Path('/root/kdlock-inputs/shape-4506f6e4')
assert os.uname().release=='7.0.0-38-kdlock1'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='1ed38b4b-301c-4c76-a2a1-eb4b9f1bd93e'
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle)
candidate=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/core-symbols-26337db1-units')
record=json.loads((candidate/'result.json').read_text())
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/core-symbols-26337db1-baseline-check');out.mkdir(exist_ok=False)
py='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PATH=str(Path(py).parent)+':/usr/sbin:/usr/bin:/sbin:/bin')
argv=['taskset','-c','63',py,str(root/'tests/unit/run.py'),'admission/test_context_policy.py']
p=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=180)
log=out/'baseline-context.log';log.write_text(p.stdout+p.stderr)
result=dict(candidate=record,baseline=dict(argv=argv,returncode=p.returncode,log=str(log),log_sha256=rt.digest(log),output=p.stdout+p.stderr))
result['candidate_logs']={path.name:path.read_text() for path in candidate.glob('unit-*.log')}
idle(root,rt.idle);result['final_idle']=True
(out/'result.json').write_text(json.dumps(result,indent=2)+'\\n')
print(json.dumps(result))
'''
p=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join([
 '/home/eric/vm/qemu-scripts/vm_ssh.sh','env PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -c '+shlex.quote(code)])],
 capture_output=True,timeout=230)
(out/'reply.json').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
assert p.returncode==0,p.stderr.decode()
r=json.loads(p.stdout)
for row in r['candidate']['units']:print(row['test'],row['returncode'],row['tail'][-500:])
print('baseline context returncode',r['baseline']['returncode'],r['baseline']['output'][-2200:])
print('final_idle',r['final_idle'])
