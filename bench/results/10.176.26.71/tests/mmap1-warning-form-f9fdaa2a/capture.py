from pathlib import Path
import json,runpy,shlex,subprocess

out=Path('/tmp/kdlock-frontier-f9fdaa2a-capture');out.mkdir(exist_ok=False)
boot=json.loads(Path('/tmp/kdlock-frontier-f9fdaa2a-confirm-kd/reply.json').read_text())
preflight=json.loads(Path('/tmp/kdlock-scaling-f9fdaa2a-preflight/reply.json').read_text())
capture=runpy.run_path('/tmp/kdlock-mm-actual-launch-third-20261103.py')['HOST_CAPTURE']
ssh=['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71']
host=subprocess.run(ssh+['sudo -n taskset -c 63 python3 -'],input=capture.encode(),capture_output=True,timeout=60)
(out/'host.json').write_bytes(host.stdout);(out/'host.stderr').write_bytes(host.stderr)
assert host.returncode==0,host.stderr.decode()
h=json.loads(host.stdout);assert h['snapshot_listed'] and h['pins_verified'] and h['frequency_verified']
code=r'''from pathlib import Path
import fcntl,hashlib,json,os,runpy,sys,traceback
sys.dont_write_bytecode=True
r=json.loads(sys.stdin.buffer.read());root=Path('/root/kdlock-inputs/scaling-f9fdaa2a')
assert os.uname().release=='7.0.0-38-kdscope5'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['boot']['boot_id']
assert r['boot']['verification']['running_build_id']=='5f2fce72a33480f6e79a79b374b21a0db377ecd1'
sys.path.insert(0,str(root/'bench/spin_cacheline'));sys.path.insert(0,str(root/'disassem'))
import bench_runtime as rt,device_session,memread
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle)
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/frontier-bytes-f9fdaa2a');out.mkdir(exist_ok=False)
p=r['preflight'];provider=Path(p['provider']);assert rt.digest(provider)==p['provider_sha256']
result=dict(passed=False,drained=False,kind='bounded instruction reproduction; no application execution',
    boot_id=r['boot']['boot_id'],build_id=r['boot']['verification']['running_build_id'],
    provider_source_commit=p['provider_source_commit'],provider_sha256=p['provider_sha256'],
    previous_campaign_bytes_not_retained=True,address=0xffffffff81817f57,size=15)
def save():rt.write_json(out/'result.json',result)
save();loaded=False
try:
    rt.command(['insmod',str(provider),'bench_quiet=1','bench_complete_probe=0','jit_timing=0',
        'hotlock_stats=0','service_cpus=0-61','rwsem_provider_demand=1',
        'rwsem_provider_entries=0xffffffff817b6f68,0xffffffff8181c73b'],out/'load.log',timeout=30)
    loaded=True
    params=Path('/sys/module/kdlock_km/parameters')
    assert params.joinpath('rwsem_provider_active').read_text().strip()=='N'
    assert params.joinpath('rwsem_provider_bindings').read_text().strip()=='0'
    with device_session.session():
        result['leased_source']=device_session.info(device_session.require())
        data=memread.read_kernel_addr_data(result['address'],result['size'])
        assert data is not None and len(data)==result['size']
        (out/'instruction.bin').write_bytes(data)
        result.update(bytes_hex=data.hex(),bytes_sha256=hashlib.sha256(data).hexdigest())
    from miasm.arch.x86.arch import mn_x86
    try:
        instruction=mn_x86.dis(data,64)
        result['decoder']=dict(decoded=True,name=instruction.name,length=instruction.l,text=str(instruction))
    except Exception as error:
        result['decoder']=dict(decoded=False,error_type=type(error).__name__,error=str(error))
    result['after_reader']=rt.status();save()
    assert result['after_reader']['frames']==result['after_reader']['writers']==0
    assert params.joinpath('rwsem_provider_bindings').read_text().strip()=='0'
    assert params.joinpath('service_progress').read_text().strip()=='total=0 shown=0'
    with open('/dev/kd_dev','rb',buffering=0) as device:
        fcntl.ioctl(device,rt.RETIRE);result['retired']=rt.info(device.fileno())
    assert result['retired']==dict(state=2,modules=0,frames=0,writers=0)
    rt.command(['rmmod','kdlock_km'],out/'unload.log',timeout=30);loaded=False
    idle(root,rt.idle);result.update(passed=True,drained=True,final_idle=True)
except BaseException as error:
    result.update(error=repr(error),traceback=traceback.format_exc(),provider_still_loaded=loaded);save();raise
finally:save()
print(json.dumps(result))
'''
p=subprocess.run(ssh+[shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh',
    'env PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -c '+shlex.quote(code)])],
    input=json.dumps(dict(boot=boot,preflight=preflight)).encode(),capture_output=True,timeout=120)
(out/'reply.json').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
print('returncode',p.returncode)
print(p.stdout.decode()[-3500:] if p.returncode==0 else p.stderr.decode()[-3500:])
raise SystemExit(p.returncode)
