from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-postboot-run-20261111-01');v=json.loads((p/'actual-proof-command.json').read_text())
with (p/'actual-proof.json').open('xb') as out,(p/'actual-proof.stderr').open('xb') as err:r=subprocess.run(v['argv'],input=v['stdin'].encode(),stdout=out,stderr=err,timeout=v['timeout_seconds'])
if r.returncode:raise SystemExit(r.returncode)
v=json.loads((p/'actual-proof.json').read_text());files=v.pop('files');digests={}
for n,x in files.items():
 b=base64.b64decode(x['data']);assert hashlib.sha256(b).hexdigest()==x['sha256'];(p/('guest-'+n)).write_bytes(b);digests[n]=x['sha256']
r=json.loads((p/'guest-result.json').read_text());v['guest_sha256']=digests;v['outer_return_sha256']=hashlib.sha256((p/'result.json').read_bytes()).hexdigest();v['postboot_phase']=r['phase'];v['build_id']=r['running_build_id'];print(json.dumps(v))
