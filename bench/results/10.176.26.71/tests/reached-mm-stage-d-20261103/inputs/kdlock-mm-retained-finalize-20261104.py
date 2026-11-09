from pathlib import Path
import json, runpy, shlex, subprocess, sys

configuration = json.loads(Path(sys.argv[1]).read_text())
destination = Path(configuration['local_output'])
destination.mkdir(exist_ok=False)
host_code=runpy.run_path('/tmp/kdlock-mm-actual-launch-third-20261103.py')['HOST_CAPTURE']
host=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71','sudo -n taskset -c 63 python3 -'],input=host_code.encode(),capture_output=True,timeout=60)
(destination/'host.json').write_bytes(host.stdout);(destination/'host.stderr').write_bytes(host.stderr)
assert host.returncode==0,host.stderr.decode()
observed=json.loads(host.stdout);assert observed['snapshot_listed'] and observed['pins_verified'] and observed['frequency_verified']
code = r'''from pathlib import Path
import argparse,fcntl,importlib.util,json,os,shutil,subprocess,sys,traceback
c=json.loads(sys.stdin.readline())
sys.dont_write_bytecode=True
os.environ['PATH']='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin:/usr/sbin:/usr/bin:/sbin:/bin'
os.sched_setaffinity(0,set(range(64)))
root=Path(c['root']);case=Path(c['case']);model=case/c['model']
spec=importlib.util.spec_from_file_location('retained_mm_controller',root/'tests/kernel/mmap1_identity/delegated.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
rt=d.rt;out=Path(c['output']);out.mkdir(exist_ok=False)
result=dict(passed=False,scored=False,accepted=False,original_failure_preserved=True,
    source_commit=c['source_commit'],boot_id=c['boot'],model=c['model'],case=str(case))
def reference(p):return dict(path=str(p),sha256=rt.digest(p))
def live():
    p=d.PARAMETERS
    assert (p/'rwsem_provider_active').read_text().strip()=='N'
    assert (p/'rwsem_provider_mode').read_text().strip()=='inactive'
    assert (p/'rwsem_provider_bindings').read_text().strip()=='0'
    source=rt.status();assert source==dict(state=0,modules=0,frames=0,writers=0),source
    stats=d.bench.execution.reached_observations()
    assert stats['active']==stats['unsupported']==0 and stats['roots']==stats['completions']>0
    return dict(source=source,reached=stats)
collector=fd=None
try:
    original=json.loads((case/'result.json').read_text())
    assert original['runtime_source_commit']==c['source_commit'] and original['boot_id']==c['boot']
    assert original['models'][c['model']]['error']=="Failure('provider bindings and execution frames drain did not complete; live state retained')"
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot']
    args=argparse.Namespace(mode='kd',boot_id=c['boot'],kernel_variant='kdscope5-log16-kd',
        kernel_source=Path('/mnt/kdlock-builds2/linux-7.0.0-38-kdscope5/build'),
        kernel_baseline=Path('/root/kdlock-kernel-baselines/linux70-kdscope5-log16-kd-20261103'),
        captured_runtime_policy=original['kernel_identity']['runtime_policy'],execution_mode='reached',
        sites=Path(original['sites']['path']),sites_sha256=original['sites']['sha256'],
        source_state=root/'source-state.json',source_manifest=root/'source-sha256.json',
        source_state_sha256=c['state_sha256'],source_manifest_sha256=c['manifest_sha256'],
        source_commit=c['source_commit'])
    d.bench.verify_boot(args);os.sched_setaffinity(0,{63});d.source_manifest(args)
    audit=d.site_audit(args,original['kernel_binding'])
    binaries=json.loads((case/'binary-sha256.json').read_text())
    for row in binaries.values():assert rt.digest(Path(row['path']))==row['sha256']
    provider=Path(binaries['provider']['path'])
    assert rt.digest(d.bench.execution.NOTE)==d.bench.execution.module_note_sha256(provider)
    assert binaries['provider']['sha256']==original['models'][c['model']]['execution_session']['provider_sha256']
    result['before']=live()
    fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC);os.lseek(fd,0,os.SEEK_END)
    collector=d.bench.kernel_log.DiagnosticKernelLog(fd,out,rt.FAULT,
        fault_check=rt.kernel_fault,max_bytes=64*1024**2)
    collector.start()
    application=json.loads((model/'application/result.json').read_text())
    lifecycle=json.loads((model/'lifecycle-log/result.json').read_text())
    for row in (application['kernel_log_collection'],lifecycle):
        assert row['complete'] and row['errors']==0 and not row['fault_detected']
        assert row['bytes']==Path(row['log']).stat().st_size
    assert application['passed'] and application['drained'] and application['returncode']==0
    assert all(d.bench.task_gone(row) for row in application['workers_observed'])
    assert rt.digest(Path(application['kernel_log_collection']['log']))==application['kernel_log_collection']['sha256']
    snapshot=json.loads((model/'snapshot.json').read_text())
    decoded=d.observer.decode((model/'snapshot.bin').read_bytes());assert dict(decoded,repeat_equal=True)==snapshot
    symbols=[int(line.split()[0],16) for line in Path('/proc/kallsyms').read_text().splitlines()
        if len(line.split())==4 and line.split()[2:]==['kd_rwsem_ops','[kdlock_km]']]
    assert len(symbols)==1 and symbols[0]>0
    messages=(model/'application/kernel.log').read_text()
    assert 'kd_service event=local_image ' not in messages and 'kd_service unsupported continuation:' not in messages
    proof=d.observer.validate_delegated(snapshot,application,os.sysconf('SC_CLK_TCK'),messages,audit['entry_sites'],symbols[0])
    controller=d.Controller.__new__(d.Controller);controller.args=args;controller.audit=audit
    proof['service_transactions']=controller.validate_services(proof,[],messages,snapshot)
    proof['syscall_pairs']=d.pairs.validate((model/'lifecycle-log/kernel.log').read_text(),snapshot,proof,audit['entry_sites'],8)
    result['continuation_criterion']=d.require_observed_continuation(proof)
    rt.write_json(out/'delegated-proof.json',proof)
    result['proof']=reference(out/'delegated-proof.json')
    result['application']=reference(model/'application/result.json')
    result['lifecycle']=reference(model/'lifecycle-log/result.json')
    result['original_failed_result']=reference(case/'result.json')
    result['before_retire']=live();assert result['before']==result['before_retire']
    with open('/dev/kd_dev','rb',buffering=0) as device:
        fcntl.ioctl(device,rt.RETIRE)
        result['retired']=rt.info(device.fileno())
    assert result['retired']==dict(state=2,modules=0,frames=0,writers=0)
    for name in ('kd_mmap1_identity','kdlock_km'):
        run=subprocess.run(['rmmod',name],capture_output=True,text=True,timeout=30)
        (out/(name+'-unload.log')).write_text(run.stdout+run.stderr)
        assert run.returncode==0,(name,run.stderr)
    d.bench.idle()
    result['free_root_bytes']=shutil.disk_usage('/').free
    result.update(passed=True,drained=True,final_idle=True,
        completed_requests=proof['completed_request_count'],downgraded_read_tails=proof['downgraded_read_tails'],
        syscall_pairs=proof['syscall_pairs']['completed_pairs'])
except BaseException as error:
    result.update(error=repr(error),traceback=traceback.format_exc())
finally:
    if collector is not None:
        capture=collector.finish();result['kernel_log_collection']=capture
        if not capture['complete'] or capture['fault_detected']:result['passed']=False
        if not collector.thread.is_alive():os.close(fd)
    rt.write_json(out/'result.json',result)
    print(json.dumps(result),flush=True)
sys.exit(0 if result['passed'] else 1)
'''
env = 'env PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=kdlock-builddisk-clean-20261031 KDLOCK_PRIVATE_SOURCE_STATE_SHA256=' + configuration['state_sha256']
env += ' KDLOCK_PRIVATE_SOURCE_MANIFEST_SHA256=' + configuration['manifest_sha256']
env += ' /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -'
command = ['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',
           shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh',env])]
remote = "import json\nc=json.loads(" + repr(json.dumps(configuration)) + ")\n"
# Configuration is supplied as the first line consumed by the program.
program = code.replace("c=json.loads(sys.stdin.readline())", "c=" + repr(configuration))
run = subprocess.run(command,input=program.encode(),capture_output=True,timeout=240)
(destination/'reply.json').write_bytes(run.stdout)
(destination/'stderr').write_bytes(run.stderr)
assert run.returncode==0,(run.returncode,run.stderr.decode(),run.stdout.decode()[-1500:])
result=json.loads(run.stdout)
print(json.dumps({key:result.get(key) for key in ('passed','drained','completed_requests','downgraded_read_tails','syscall_pairs','continuation_criterion','retired','final_idle')}))
