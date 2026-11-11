from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-install-run-20261111-01');v=json.loads((p/'small-receipts-command.json').read_text())
with (p/'small-receipts.json').open('xb') as out,(p/'small-receipts.stderr').open('xb') as err:r=subprocess.run(v['argv'],input=v['stdin'].encode(),stdout=out,stderr=err,timeout=v['timeout_seconds'])
if r.returncode:raise SystemExit(r.returncode)
v=json.loads((p/'small-receipts.json').read_text());d=p/'small-receipts';d.mkdir()
for n,x in v.pop('files').items():
 raw=base64.b64decode(x['data']);assert hashlib.sha256(raw).hexdigest()==x['sha256'];(d/n).write_bytes(raw)
print(json.dumps({'phase_receipts':{n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in ('stage-complete.json','check-complete.json')},'budget':json.loads((d/'root-budget.json').read_text()),'limited':json.loads((d/'limited-stage.json').read_text()),'grub':v},indent=2))
