from pathlib import Path
import json,runpy,shlex,subprocess

local=Path('/tmp/kdlock-shape-4506f6e4-functional-r2');local.mkdir(exist_ok=False)
request=dict(boot=json.loads(Path('/tmp/kdlock-shape-4506f6e4-confirm-kd/reply.json').read_text()),
    preflight=json.loads(Path('/tmp/kdlock-shape-4506f6e4-preflight/reply.json').read_text()),
    freeze=json.loads(Path('/tmp/kdlock-shape-4506f6e4-freeze/transfer.stdout').read_text()),
    probe=json.loads(Path('/tmp/kdlock-scaling-f9fdaa2a-preflight/reply.json').read_text()))
ssh=['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71']
capture=runpy.run_path('/tmp/kdlock-mm-actual-launch-third-20261103.py')['HOST_CAPTURE']
host=subprocess.run(ssh+['sudo -n taskset -c 63 python3 -'],input=capture.encode(),capture_output=True,timeout=60)
(local/'host.json').write_bytes(host.stdout);(local/'host.stderr').write_bytes(host.stderr)
assert host.returncode==0,host.stderr.decode()
h=json.loads(host.stdout);assert h['snapshot_listed'] and h['pins_verified'] and h['frequency_verified']
code=r'''from pathlib import Path
import fcntl,hashlib,importlib.util,json,os,select,subprocess,sys,time,traceback
sys.dont_write_bytecode=True
r=json.loads(sys.stdin.buffer.read());root=Path(r['freeze']['root']);p=r['preflight'];entries=[0xffffffff817b6f68,0xffffffff8181c73b]
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['boot']['boot_id']
assert r['boot']['verification']['running_build_id']=='5f2fce72a33480f6e79a79b374b21a0db377ecd1'
os.environ['PATH']=str(Path(sys.executable).parent)+':/usr/sbin:/usr/bin:/sbin:/bin'
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
spec=importlib.util.spec_from_file_location('shape_functional_controller',root/'tests/kernel/mmap1_identity/delegated.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller);bench=controller.bench
bench.idle()
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/shape-functional-4506f6e4-r2');out.mkdir(exist_ok=False)
provider=Path(p['provider']);probe=Path(r['probe']['probe'])
assert rt.digest(provider)==p['provider_sha256'] and rt.digest(probe)==r['probe']['probe_sha256']
binary=out/'arg_shape';rt.command(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',
    str(root/'tests/kernel/mmap1_identity/argument_fixture.c'),'-o',str(binary)],out/'fixture-build.log',timeout=30)
result=dict(schema=1,source_commit=r['freeze']['source_commit'],boot_id=r['boot']['boot_id'],passed=False,
    checks_passed=False,drained=False,accepted=False,scored=False,delegation_proved=False,translator_started=False,
    provider=p['provider'],provider_sha256=p['provider_sha256'],fixture_sha256=rt.digest(binary),cases=[],applications=[])
params=controller.PARAMETERS;loaded=False;observer_loaded=False;children=[]
def save():rt.write_json(out/'result.json',result)
def load(enabled):
    argv=['insmod',str(provider),'bench_quiet=1','bench_complete_probe=0','jit_timing=0','hotlock_stats=0',
        'service_cpus=0-61','rwsem_provider_demand=1','rwsem_provider_entries='+','.join(hex(x) for x in entries)]
    if enabled:argv.append('rwsem_provider_syscall_shape=1')
    rt.command(argv,out/('load-'+str(int(enabled))+'.log'),timeout=30)
    actual=rt.parameters();value=bench.execution.syscall_shape_contract(actual,enabled)
    assert value==dict(version=1,enabled=enabled)
    assert all((params/name).stat().st_mode&0o777==0o444 for name in bench.execution.SYSCALL_SHAPE_PARAMETERS)
    return value
def retire_now(log):
    assert params.joinpath('rwsem_provider_active').read_text().strip()=='N'
    assert params.joinpath('rwsem_provider_bindings').read_text().strip()=='0'
    assert rt.status()['frames']==rt.status()['writers']==0
    with open('/dev/kd_dev','rb',buffering=0) as device:
        fcntl.ioctl(device,rt.RETIRE);value=rt.info(device.fileno())
    assert value==dict(state=2,modules=0,frames=0,writers=0)
    rt.command(['rmmod','kdlock_km'],out/log,timeout=30);bench.idle();return value
def launch(argv,stdout,stderr,cpu):
    previous=os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0,{cpu});child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,
            stdin=subprocess.PIPE,text=True,start_new_session=True)
    finally:os.sched_setaffinity(0,previous)
    children.append(child);return child
fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC);os.lseek(fd,0,os.SEEK_END)
logs=out/'kernel-log';logs.mkdir();collector=bench.kernel_log.DiagnosticKernelLog(fd,logs,rt.FAULT,
    fault_check=rt.kernel_fault,max_bytes=64*1024**2);collector.start();save()
try:
    result['default_policy']=load(False);loaded=True
    result['default_retired']=retire_now('unload-default.log');loaded=False;save()
    result['selected_policy']=load(True);loaded=True
    params.joinpath('rwsem_provider_mode').write_text('prepare\n');params.joinpath('rwsem_provider_mode').write_text('activate\n')
    with (out/'fixture.stderr').open('w') as errors:
        child=launch([str(binary)],subprocess.PIPE,errors,0)
        stages=[('ready',set()),('anonymous64',set()),('file128',set()),('file128-unmapped',{entries[1]}),
                ('anonymous128',set(entries)),('anonymous128-unmapped',set(entries))]
        case_errors=[]
        for name,wanted in stages:
            assert select.select([child.stdout],[],[],10)[0], 'fixture checkpoint timeout; lifetime retained'
            line=child.stdout.readline().strip();assert line==name,(name,line)
            rows=rt.registry();observed={row['entry'] for row in rows}
            valid=observed==wanted and all(row['pid']==0 and row['status']==-1 and row['code']==row['generation']==0 and
                row['tgid']==child.pid and row['entry_abi']==2 and row['lock_kind']==2 for row in rows)
            result['cases'].append(dict(name=name,passed=valid,registry=rows,expected_entries=sorted(wanted)))
            if not valid:case_errors.append(name)
            save();child.stdin.write('next\n');child.stdin.flush()
        assert child.wait(timeout=20)==0
        assert not case_errors,case_errors
    params.joinpath('rwsem_provider_mode').write_text('deactivate\n')
    inputs_path=Path('/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kdscope1-mm-f7a84065-20261030/native-a/mmap1-prepare/inputs.json')
    assert rt.digest(inputs_path)=='beeb3e82481b881ba09d77667408f29fc37366b7fe5d987f3fd02af0c5ac4dc0'
    inputs=bench.inputs_from(inputs_path)
    provider_symbols=[int(line.split()[0],16) for line in Path('/proc/kallsyms').read_text().splitlines()
        if len(line.split())==4 and line.split()[2:]==['kd_rwsem_ops','[kdlock_km]']]
    assert len(provider_symbols)==1
    for model in ('threads','processes'):
        folder=out/model;folder.mkdir()
        rt.command(['insmod',str(probe),'target=mmap1_'+model,'pair_limit=0'],folder/'load-observer.log',timeout=30);observer_loaded=True
        params.joinpath('rwsem_provider_mode').write_text('activate\n')
        with (folder/'upstream.log').open('w') as log:
            started=time.monotonic_ns();child=launch(bench.argv(inputs['binaries'][model],2),log,subprocess.STDOUT,63)
            workers=None;deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                assert child.poll() is None,'application exited before warmup capture'
                try:workers=bench.capture_workers(child.pid,model,2,inputs['binaries'][model]);break
                except (rt.Failure,FileNotFoundError,ProcessLookupError):time.sleep(.05)
            assert workers is not None
            assert child.wait(timeout=30)==0
        assert all(bench.task_gone(worker) for worker in workers)
        output=bench.parse_output((folder/'upstream.log').read_text(),2)
        first,second=bytearray(controller.observer.SIZE),bytearray(controller.observer.SIZE)
        with open('/dev/kd_mmap1_identity','rb',buffering=0) as device:
            fcntl.ioctl(device,controller.observer.STOP,first,True);fcntl.ioctl(device,controller.observer.STOP,second,True)
        assert first==second
        snapshot=dict(controller.observer.decode(first),repeat_equal=True);rt.write_json(folder/'snapshot.json',snapshot)
        session=dict(passed=True,drained=True,scored=False,instrumentation='identity-kprobe',
            output=dict(output_valid=True,measured_samples=2),pid=child.pid,model=model,workers=2,workers_observed=workers)
        identity=controller.observer.validate(snapshot,session,'kd',os.sysconf('SC_CLK_TCK'),provider=provider_symbols[0])
        params.joinpath('rwsem_provider_mode').write_text('deactivate\n')
        rt.command(['rmmod','kd_mmap1_identity'],folder/'unload-observer.log',timeout=30);observer_loaded=False
        result['applications'].append(dict(model=model,passed=True,drained=True,scored=False,delegation_proved=False,
            local_untranslated=True,started_ns=started,finished_ns=time.monotonic_ns(),identity=identity,output=output))
        save()
    assert rt.status()['frames']==rt.status()['writers']==0 and not bench.execution.device_writers()
    assert all(row['status']==-1 and row['code']==row['generation']==0 for row in rt.registry())
    result['checks_passed']=True
except BaseException as error:
    result.update(error=repr(error),traceback=traceback.format_exc());save();raise
finally:
    if loaded:
        params.joinpath('rwsem_provider_mode').write_text('deactivate\n')
        result['known_child_drain']=all(child.poll() is not None for child in children)
        if result['known_child_drain'] and not observer_loaded and rt.status()['frames']==0:
            result.update(state='FUNCTIONAL_RETIREMENT_PENDING',retirement_snapshot=dict(source=rt.status(),registry=rt.registry(),
                note_sha256=rt.digest(bench.execution.NOTE),bindings=int(params.joinpath('rwsem_provider_bindings').read_text())))
        else:result['state']='LIVE_STATE_RETAINED'
    summary=collector.finish();result['kernel_collection']=summary
    if not collector.thread.is_alive():os.close(fd)
    if not summary['complete'] or summary['fault_detected']:result['checks_passed']=False
    save()
print(json.dumps(result))
'''
p=subprocess.run(ssh+[shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh',
    'env PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -c '+shlex.quote(code)])],
    input=json.dumps(request).encode(),capture_output=True,timeout=240)
(local/'reply.json').write_bytes(p.stdout);(local/'stderr').write_bytes(p.stderr)
print('returncode',p.returncode)
if p.returncode:print(p.stderr.decode()[-4000:])
else:
    result=json.loads(p.stdout);print('checks',result['checks_passed'],'cases',len(result['cases']),
        'models',[(row['model'],row['passed'],row['identity']['provider_routes']) for row in result['applications']],
        'state',result['state'],'snapshot',result.get('retirement_snapshot'))
raise SystemExit(p.returncode)
