from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-reboot-20261111-01');v=json.loads((p/'pre-reboot-command.json').read_text())
with (p/'pre-reboot.json').open('xb') as out,(p/'pre-reboot.stderr').open('xb') as err:r=subprocess.run(v['argv'],input=v['stdin'].encode(),stdout=out,stderr=err,timeout=v['timeout_seconds'])
if r.returncode:raise SystemExit(r.returncode)
v=json.loads((p/'pre-reboot.json').read_text());b=base64.b64decode(v.pop('arm_data'));assert hashlib.sha256(b).hexdigest()==v['arm_sha256'];(p/'arm-result.json').write_bytes(b);print(json.dumps(v))
