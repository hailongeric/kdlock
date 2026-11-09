from pathlib import Path
import json,shlex,subprocess
local=Path('/tmp/kdlock-shape-4506f6e4-finalize');local.mkdir(exist_ok=False)
request=dict(boot=json.loads(Path('/tmp/kdlock-shape-4506f6e4-confirm-kd/reply.json').read_text()),
    preflight=json.loads(Path('/tmp/kdlock-shape-4506f6e4-preflight/reply.json').read_text()),
    freeze=json.loads(Path('/tmp/kdlock-shape-4506f6e4-freeze/transfer.stdout').read_text()))
code=r'''from pathlib import Path
import fcntl,importlib.util,json,os,sys
sys.dont_write_bytecode=True
r=json.loads(sys.stdin.buffer.read());root=Path(r['freeze']['root'])
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['boot']['boot_id']
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
spec=importlib.util.spec_from_file_location('shape_final_controller',root/'tests/kernel/mmap1_identity/delegated.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller);bench=controller.bench
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/shape-functional-4506f6e4-r2')
original_path=out/'result.json';original_hash=rt.digest(original_path);original=json.loads(original_path.read_text())
assert original['state']=='FUNCTIONAL_RETIREMENT_PENDING' and original['checks_passed'] and original['known_child_drain']
assert original['kernel_collection']['complete'] and not original['kernel_collection']['fault_detected']
assert not Path('/sys/module/kd_mmap1_identity').exists()
params=controller.PARAMETERS;expected=original['retirement_snapshot'];provider=Path(r['preflight']['provider'])
assert rt.digest(provider)==original['provider_sha256']==r['preflight']['provider_sha256']
assert params.joinpath('rwsem_provider_active').read_text().strip()=='N'
assert rt.status()==expected['source'] and expected['source']['frames']==expected['source']['writers']==0
assert rt.registry()==expected['registry'] and not bench.execution.device_writers()
assert rt.digest(bench.execution.NOTE)==expected['note_sha256']==bench.execution.module_note_sha256(provider)
assert bench.execution.syscall_shape_contract(rt.parameters(),True)==original['selected_policy']
result=dict(passed=False,drained=False,original_result_sha256=original_hash,
    source_commit=r['freeze']['source_commit'],before=dict(source=rt.status(),bindings=int(params.joinpath('rwsem_provider_bindings').read_text())))
def save():rt.write_json(out/'finalization.json',result)
assert not (out/'finalization.json').exists();save()
if result['before']['bindings']:
    spec=importlib.util.spec_from_file_location('shape_postrun',root/'bench/mmap1/postrun.py')
    postrun=importlib.util.module_from_spec(spec);spec.loader.exec_module(postrun)
    result['ordinary_cpu_progress']=postrun.progress(params,rt.status);save()
assert params.joinpath('rwsem_provider_bindings').read_text().strip()=='0'
assert rt.status()==expected['source'] and rt.registry()==expected['registry']
assert params.joinpath('service_progress').read_text().strip()=='total=0 shown=0'
with open('/dev/kd_dev','rb',buffering=0) as device:
    fcntl.ioctl(device,rt.RETIRE);result['retired']=rt.info(device.fileno())
assert result['retired']==dict(state=2,modules=0,frames=0,writers=0);save()
rt.command(['rmmod','kdlock_km'],out/'unload-selected.log',timeout=30);bench.idle()
assert rt.digest(original_path)==original_hash
result.update(passed=True,drained=True,final_idle=True,checks_passed=True,accepted=False,scored=False,delegation_proved=False)
save();print(json.dumps(result))
'''
p=subprocess.run(['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join([
    '/home/eric/vm/qemu-scripts/vm_ssh.sh','env PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -c '+shlex.quote(code)])],
    input=json.dumps(request).encode(),capture_output=True,timeout=75)
(local/'reply.json').write_bytes(p.stdout);(local/'stderr').write_bytes(p.stderr)
print('returncode',p.returncode);print(p.stdout.decode()[-3000:] if p.returncode==0 else p.stderr.decode()[-3500:]);raise SystemExit(p.returncode)
