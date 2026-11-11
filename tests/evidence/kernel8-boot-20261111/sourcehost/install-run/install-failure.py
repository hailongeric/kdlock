from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-install-run-20261111-01');v=json.loads((p/'install-failure-command.json').read_text())
with (p/'install-failure-metadata.json').open('xb') as out,(p/'install-failure-metadata.stderr').open('xb') as err:r=subprocess.run(v['argv'],input=v['stdin'].encode(),stdout=out,stderr=err,timeout=v['timeout_seconds'])
if r.returncode:raise SystemExit(r.returncode)
v=json.loads((p/'install-failure-metadata.json').read_text());d=p/'install-failure';d.mkdir()
for n,row in v.pop('files').items():
 b=base64.b64decode(row['data']);assert hashlib.sha256(b).hexdigest()==row['sha256'];(d/n).write_bytes(b)
v['failure']=json.loads((d/'install-failure.json').read_text());v['driver_stderr']=(d/'driver-stderr').read_text();v['grub_log']=(d/'install-grub-installed.log').read_text();print(json.dumps(v,indent=2))
