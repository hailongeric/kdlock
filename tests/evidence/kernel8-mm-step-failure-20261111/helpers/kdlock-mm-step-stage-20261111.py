"""Stage frozen metadata for the authorized bounded VM syscall run."""
from pathlib import Path
import base64
import hashlib
import json
import subprocess
import time

BASE = Path('/tmp/kdlock-kernel8-mm-step-20261111-01')
FINAL = BASE / 'configuration-final-03'
OUT = BASE / 'stage-step-01'
GUEST = '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-mmap-step-input-0798c1ab-01'

assert not OUT.exists()
OUT.mkdir()
files = {p.name: p.read_bytes() for p in FINAL.iterdir() if p.is_file()}
supervisor = Path('/tmp/kdlock-kernel8-mm-prefix-supervisor-20261111-01.py').read_bytes()
assert hashlib.sha256(supervisor).hexdigest() == '09dc900987cec70b89ea60620ddd07c1493fa6c7dd2b4649201421b33c238ebc'
files['supervisor.py'] = supervisor
expected_config = '3c0655de113cdde76e86f238278604d2754013195e1037633300d7cfb93be0e1'
assert hashlib.sha256(files['host-config.json']).hexdigest() == expected_config
payload = {name: {'sha256': hashlib.sha256(raw).hexdigest(),
                  'data': base64.b64encode(raw).decode()} for name, raw in sorted(files.items())}
script = '''from pathlib import Path
import base64,datetime,hashlib,json,os,time
FILES = json.loads(PAYLOAD)
DEST = Path(GUEST_PATH)
def need(ok, message):
    if not ok: raise RuntimeError(message)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''): h.update(b)
    return h.hexdigest()
need(os.geteuid()==0, 'VM root required')
cfg=json.loads(base64.b64decode(FILES['host-config.json']['data']))
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
need(boot==cfg['boot_id'] and os.uname().release==cfg['release'] and
     Path('/proc/sys/kernel/tainted').read_text().strip()=='0', 'exact fresh boot required')
modules=Path('/proc/modules').read_text()
need(len(modules.splitlines())==1 and modules.split()[0]=='nls_iso8859_1', 'ordinary NLS-only state required')
need(not os.path.lexists(DEST) and DEST.parent.resolve(strict=True)==DEST.parent, 'fresh canonical input leaf required')
for p in (cfg['paths']['output'],str(DEST.parent/'mm-mmap-step-receipts-0798c1ab-01')):
    need(not os.path.lexists(p), 'fresh run/receipt leaves required')
for device in ('kd_mmap_api','kd_mmap_api_events','kd_mmap_jit','kd_rwsem_killable_fixture','kd_rwsem_runtime_fixture','kd_runtime_fixture','kd_rwsem_api'):
    need(not any((Path('/dev')/(device+s)).exists() for s in ('','_ctl','_events')), 'experimental device remains')
actors=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name)==os.getpid(): continue
    try:
        comm=(p/'comm').read_text().strip(); argv=(p/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')
        if comm=='mmap-userspace' or comm.startswith('kd-kill') or any(t in argv for t in ('tests/kernel/mmap_api/runner.py','tests/kernel/rwsem_killable/runner.py')): actors.append(int(p.name))
    except (FileNotFoundError,ProcessLookupError): pass
need(not actors, 'prior API actor remains')
need(os.statvfs('/').f_bavail*os.statvfs('/').f_frsize >= 1<<30, 'root floor')
need(os.statvfs(DEST.parent).f_bavail*os.statvfs(DEST.parent).f_frsize >= 4<<30, 'build floor')
pins={}
for name,p in cfg['paths'].items():
    if name in ('repo','output','jit_config','recovery'): continue
    path=Path(p); need(path.resolve(strict=True)==path, 'canonical pinned input required')
    pins[name]=sha(path); need(pins[name]==cfg['sha256'][name], 'pinned input differs: '+name)
state=json.loads(Path(cfg['paths']['source_state']).read_text()); manifest=json.loads(Path(cfg['paths']['source_manifest']).read_text()); repo=Path(cfg['paths']['repo'])
need(state['source_git_head']==cfg['repo_head'] and state['git_status']=='' and state['files']==len(manifest)==143, 'frozen source identity differs')
need({str(p.relative_to(repo)) for p in repo.rglob('*') if p.is_file()}==set(manifest), 'frozen source membership differs')
for name,row in manifest.items():
    p=repo/name; need(p.resolve(strict=True)==p and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'], 'frozen source bytes differ')
proof=json.loads(Path(cfg['paths']['gs_proof']).read_text()); need(proof['boot_id']==boot and proof['verified_for_running_kernel'] is True, 'fresh GS proof differs')
recovery=json.loads(base64.b64decode(FILES['recovery.json']['data'])); age=time.time()-datetime.datetime.fromisoformat(recovery['utc']).timestamp()
need(0<=age<=900, 'recovery receipt expired')
staged={}; DEST.mkdir(mode=0o700)
for name,item in FILES.items():
    need(Path(name).name==name, 'simple input filename required')
    raw=base64.b64decode(item['data'],validate=True); need(hashlib.sha256(raw).hexdigest()==item['sha256'], 'input transport differs')
    with (DEST/name).open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    os.chmod(DEST/name,0o600); need(sha(DEST/name)==item['sha256'], 'staged readback differs'); staged[name]=item['sha256']
fd=os.open(DEST,os.O_RDONLY|os.O_DIRECTORY); os.fsync(fd); os.close(fd)
print(json.dumps({'status':'FIVE_REGION_INPUT_STAGED_NO_PROFILE_LOADED','boot_id':boot,'taint':0,'modules':modules,'actors':actors,'frozen_source_files':len(manifest),'pins':pins,'recovery_age_seconds':age,'staged':staged},sort_keys=True))
'''.replace('PAYLOAD', repr(json.dumps(payload, sort_keys=True))).replace('GUEST_PATH', repr(GUEST))
raw = script.encode()
(OUT / 'stdin.py').write_bytes(raw)
argv = ['ssh', '-T', '-p', '2222', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        'root@10.176.26.71', 'python3', '-B', '-']
(OUT / 'command.json').write_text(json.dumps({'argv': argv, 'stdin': str(OUT / 'stdin.py'),
    'stdin_sha256': hashlib.sha256(raw).hexdigest(), 'timeout_seconds': 120}, indent=2)+'\n')
started = time.time()
with (OUT / 'result.json').open('xb') as stdout, (OUT / 'stderr').open('xb') as stderr:
    result = subprocess.run(argv, input=raw, stdout=stdout, stderr=stderr, timeout=120)
(OUT / 'return.json').write_text(json.dumps({'returncode': result.returncode,
    'elapsed_seconds': time.time()-started}, indent=2)+'\n')
assert result.returncode == 0, result.returncode
value=json.loads((OUT / 'result.json').read_text())
assert value['status']=='FIVE_REGION_INPUT_STAGED_NO_PROFILE_LOADED'
print(json.dumps({'status':value['status'],'returncode':result.returncode,
    'receipt_sha256':hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest(),
    'staged_files':len(value['staged']),'recovery_age_seconds':value['recovery_age_seconds']}))
