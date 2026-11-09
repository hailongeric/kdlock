from pathlib import Path
import hashlib
import json
import shlex
import subprocess

out=Path('/tmp/kdlock-core-symbols-26337db1-compiler');out.mkdir(exist_ok=False)
child=Path('/tmp/kdlock-core-symbols-26337db1-compiler-child.py').read_bytes()
guest=Path('/tmp/kdlock-core-symbols-26337db1-compiler-guest.py').read_bytes()
request=dict(candidate=json.loads(Path('/tmp/kdlock-core-symbols-26337db1-freeze/transfer.stdout').read_text()),
 boot=json.loads(Path('/tmp/kdlock-core-symbols-26337db1-confirm-native/reply.json').read_text()),
 provider=json.loads(Path('/tmp/kdlock-shape-4506f6e4-preflight/reply.json').read_text()),
 child_hex=child.hex(),child_sha256=hashlib.sha256(child).hexdigest())
(out/'compiler-child.py').write_bytes(child);(out/'compiler-guest.py').write_bytes(guest)
(out/'request.json').write_text(json.dumps({key:value for key,value in request.items() if key!='child_hex'},indent=2)+'\n')
code=guest.decode()
command=['ssh','-oBatchMode=yes','-oConnectTimeout=10','eric@10.176.26.71',shlex.join([
 '/home/eric/vm/qemu-scripts/vm_ssh.sh','env PYTHONDONTWRITEBYTECODE=1 /mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3 -c '+shlex.quote(code)])]
try:
 p=subprocess.run(command,input=json.dumps(request).encode(),capture_output=True,timeout=780)
except subprocess.TimeoutExpired as error:
 (out/'stdout').write_bytes(error.stdout or b'');(out/'stderr').write_bytes(error.stderr or b'')
 (out/'controller-status.json').write_text(json.dumps(dict(completed=False,timeout=780))+'\n')
 raise
(out/'reply.json').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
(out/'controller-status.json').write_text(json.dumps(dict(completed=True,returncode=p.returncode))+'\n')
assert p.returncode==0,p.stderr.decode()
r=json.loads(p.stdout)
for pair in r['pairs']:
 print(pair['name'],'artifacts_identical',pair['artifacts_identical'],'lookups_identical',pair['lookup_results_identical'],'coverage_identical',pair['coverage_identical'])
 for arm in pair['arms']:
  print(json.dumps({key:arm[key] for key in ('kind','returncode','wall_ns','user_ns','system_ns','maxrss_kib')}),
   json.dumps({key:arm['telemetry'][key] for key in ('lookup_count','symbol_opens','core_reused')}))
print('passed',r['passed'],'retirement',r['retirement'],'final_idle',r['final_idle'])
