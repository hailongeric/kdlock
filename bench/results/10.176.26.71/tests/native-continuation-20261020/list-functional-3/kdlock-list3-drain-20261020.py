"""Drain a stopped preparation failure; leave every original failure receipt intact."""
import fcntl,json,os,signal,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
root=Path('/root/host_fs/kdlock')
base=Path('/root/kdlock-evidence/10.176.26.71/tests/native-continuation-20261020/list-functional-3')
folder=base/'spin-list-prefetch-n16/list-prefetch-n16-t16-r00-direct-kdlock-adaptive'
sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
record=json.loads((folder/'session.json').read_text())
assert record['execution_status']=='PREPARATION_FAILED' and record['cleanup_error']=='translator has not exited'
assert json.loads((base/'tasks.json').read_text())['state']=='FAILED'
out=base/'post-failure-drain.json'
assert not out.exists()
receipt=dict(started_unix=time.time(),original_drained=record['drained'],steps=[],complete=False)
def save():out.write_text(json.dumps(receipt,indent=2)+'\n')
save()
for proc in Path('/proc').glob('[0-9]*'):
    try:assert (proc/'comm').read_text().strip()!='sc_worker',str(proc)
    except (FileNotFoundError,ProcessLookupError):pass
counts=json.loads(subprocess.check_output([root/'bench/spin_cacheline/client','--counts',
    '--workload','list-prefetch','--list-nodes','16'],timeout=30))
assert counts['active']==0 and rt.status()['frames']==0
receipt['counts']=counts
pid=record['daemon_pid'];proc=Path('/proc')/str(pid)
assert (proc/'comm').read_text().strip()=='daemon'
assert os.readlink(proc/'cwd')==str(folder/'workspace/daemon')
pidfd=os.pidfd_open(pid)
deadline=time.monotonic()+15
while rt.children(pid):
    if time.monotonic()>deadline:raise RuntimeError('translator did not finish naturally; no signal sent')
    time.sleep(.01)
# Stop only the failed session's coordinator, after the active translator has
# exited. A racing child retains its source lease and must finish before retire.
receipt['steps'].append(dict(action='SIGTERM coordinator after no children',pid=pid,unix=time.time()))
save()
signal.pidfd_send_signal(pidfd,signal.SIGTERM)
os.close(pidfd)
deadline=time.monotonic()+15
while (proc.exists() and (proc/'stat').read_text().split()[2]!='Z') or rt.status()['writers']:
    if time.monotonic()>deadline:raise RuntimeError('coordinator/writer has not exited; no unload')
    time.sleep(.05)
before=rt.status()
assert before['frames']==before['writers']==0
fd=os.open('/dev/kd_dev',os.O_RDONLY|os.O_CLOEXEC)
try:
    fcntl.ioctl(fd,rt.RETIRE)
    retired=rt.info(fd)
finally:os.close(fd)
assert retired==dict(state=2,modules=0,frames=0,writers=0)
receipt.update(before_retire=before,retired=retired)
save()
for module in ('spin_cacheline','kdlock_km'):
    result=subprocess.run(['rmmod',module],capture_output=True,text=True,timeout=15)
    receipt['steps'].append(dict(action='ordinary rmmod',module=module,returncode=result.returncode,
                                 stdout=result.stdout,stderr=result.stderr))
    save()
    assert result.returncode==0
rt.idle()
subprocess.run(['dmesg','--raw'],stdout=(base/'post-failure-dmesg.log').open('w'),check=True,timeout=15)
receipt.update(complete=True,final_idle=True,finished_unix=time.time())
save()
print(json.dumps(receipt))
