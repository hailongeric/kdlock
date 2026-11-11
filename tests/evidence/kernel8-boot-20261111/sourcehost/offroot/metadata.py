from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-offroot-20261111-01');v=json.loads((p/'metadata-command.json').read_text())
with (p/'metadata.json').open('xb') as out,(p/'metadata.stderr').open('xb') as err:r=subprocess.run(v['argv'],input=v['stdin'].encode(),stdout=out,stderr=err,timeout=v['timeout_seconds'])
if r.returncode:raise SystemExit(r.returncode)
v=json.loads((p/'metadata.json').read_text());b=base64.b64decode(v.pop('base64'));assert hashlib.sha256(b).hexdigest()==v['sha256'];(p/'result.json').write_bytes(b);print(json.dumps(v))
