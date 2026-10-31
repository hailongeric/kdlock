"""Launch one hash-bound guest step from a retained JSON specification."""
import argparse,hashlib,json,shlex,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
data=a.spec.read_bytes();s=json.loads(data);a.output.mkdir(parents=True,exist_ok=False)
(a.output/'spec.json').write_bytes(data)
def ssh(argv):return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71',shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh',shlex.join(argv)])]
verify='import hashlib,pathlib,sys; assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()==sys.argv[2]'
c=subprocess.run(ssh(['python3','-c',verify,s['script'],s['script_sha256']]),capture_output=True,timeout=30);assert c.returncode==0,c.stderr
python='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
argv=['env','-u','KERNELRELEASE','-u','KBUILD_OUTPUT','PYTHONDONTWRITEBYTECODE=1','LC_ALL=C',
 'PATH='+str(Path(python).parent)+':/usr/sbin:/usr/bin:/sbin:/bin',
 'KDLOCK_RECOVERY_CONFIRMED=1','KDLOCK_SNAPSHOT_TAG=kdlock-builddisk-clean-20261031',
 'taskset','-c',s.get('affinity','0-63'),python,s['script'],*s['argv']]
r=dict(transport_completed=False,started=time.time(),spec_sha256=hashlib.sha256(data).hexdigest(),argv=argv,
       guest_result=s['result'],child_completion_unknown=True)
def save():(a.output/'owner.json').write_text(json.dumps(r,indent=2)+'\n')
save()
with(a.output/'stdout').open('xb')as stdout,(a.output/'stderr').open('xb')as stderr:
 c=subprocess.Popen(ssh(argv),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True);r['pid']=c.pid;save()
 try:rc=c.wait(timeout=s['timeout'])
 except subprocess.TimeoutExpired:r['timeout']=True;save();raise
r.update(returncode=rc,finished=time.time(),child_completion_unknown=False);save()
c=subprocess.run(ssh(['cat',s['result']]),capture_output=True,timeout=30)
(a.output/'result.json').write_bytes(c.stdout);assert c.returncode==0,c.stderr
result=json.loads(c.stdout)
r.update(transport_completed=True,result_sha256=hashlib.sha256(c.stdout).hexdigest(),
         step_passed=result.get(s.get('success_key','passed'))is True,
         step_state=result.get('state'),step_error=result.get('error'))
save();print(json.dumps(r,indent=2));assert rc==0 and r['step_passed']
