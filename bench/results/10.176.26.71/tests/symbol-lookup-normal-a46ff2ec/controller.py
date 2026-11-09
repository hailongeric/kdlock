"""380G10 controller for one read-only metadata comparison on the guest."""
from pathlib import Path
import ast
import base64
import hashlib
import json
import shlex
import subprocess

local = Path('/tmp/kdlock-symbol-lookup-normal-a46ff2ec')
local.mkdir(exist_ok=False)
helper_path = Path('/tmp/kdlock-symbol-lookup-normal-profile.py')
helper = helper_path.read_bytes()
ast.parse(helper, filename=str(helper_path))
verification_path = Path('/tmp/kdlock-shape-4506f6e4-confirm-normal/reply.json')
verification = json.loads(verification_path.read_text())
manifest = json.loads(Path('/tmp/kdlock-shape-4506f6e4-freeze/source-sha256.json').read_text())
selected = [name for name in manifest if name.startswith(('disassem/', 'include/', 'tests/protocols/'))]
selected.extend(name for name in manifest if name.startswith('bench/spin_cacheline/') and name.endswith('.py'))
request = dict(root='/root/kdlock-inputs/shape-4506f6e4',
    output='/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/symbol-lookup-normal-a46ff2ec',
    boot_id=verification['boot_id'], build_id=verification['verification']['running_build_id'],
    verification_receipt_sha256=hashlib.sha256(verification_path.read_bytes()).hexdigest(),
    source_commit='4506f6e46394133e439f68a04d6fde38aea0885f',
    files={name:manifest[name] for name in sorted(set(selected))},
    helper_sha256=hashlib.sha256(helper).hexdigest())
(local/'helper-as-run.py').write_bytes(helper)
(local/'request.json').write_text(json.dumps(request,indent=2)+'\n')
(local/'normal-verification.json').write_bytes(verification_path.read_bytes())
transfer = dict(request=request, helper=base64.b64encode(helper).decode())
code = '''from pathlib import Path
import base64, hashlib, io, json, os, sys
sys.dont_write_bytecode=True
value=json.loads(sys.stdin.buffer.read())
request=value['request']; helper=base64.b64decode(value['helper'])
assert hashlib.sha256(helper).hexdigest()==request['helper_sha256']
os.environ['PATH']='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin:/usr/sbin:/usr/bin:/sbin:/bin'
sys.stdin=io.TextIOWrapper(io.BytesIO(json.dumps(request).encode()), encoding='utf-8')
exec(compile(helper, '<symbol-lookup-profile>', 'exec'), {'__name__':'__main__'})
out=Path(request['output'])
(out/'helper-as-run.py').write_bytes(helper)
(out/'request.json').write_text(json.dumps(request,indent=2)+'\\n')
'''
command = ['ssh', '-oBatchMode=yes', '-oConnectTimeout=10', 'eric@10.176.26.71',
    shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh',
        'env PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -c '+shlex.quote(code)])]
(local/'command.json').write_text(json.dumps(command,indent=2)+'\n')
try:
    process = subprocess.run(command,input=json.dumps(transfer).encode(),capture_output=True,timeout=120)
except subprocess.TimeoutExpired as error:
    (local/'stdout').write_bytes(error.stdout or b'')
    (local/'stderr').write_bytes(error.stderr or b'')
    (local/'controller-status.json').write_text(json.dumps(dict(completed=False, timeout=120))+'\n')
    raise
(local/'reply.json').write_bytes(process.stdout)
(local/'stderr').write_bytes(process.stderr)
(local/'controller-status.json').write_text(json.dumps(dict(completed=True,returncode=process.returncode))+'\n')
assert process.returncode == 0, process.stderr.decode()
result = json.loads(process.stdout)
assert result['passed'] and result['final_idle']
print(json.dumps({name:result[name] for name in ('passed','kernel_release','boot_id','identical_requests','observed_table_stable','observed_modules_stable','final_idle')}))
for name in ('original','snapshot'):
    arm = result[name]
    print(json.dumps({key:arm[key] for key in ('kind','wall_ns','user_ns','system_ns','lookup_count','open_attempts','snapshot_symbols','requested_counts','maxrss_kib_before','maxrss_kib_after')}))
