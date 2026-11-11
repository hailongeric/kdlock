from pathlib import Path
import json,subprocess
p=Path('/tmp/kdlock-kernel8-install-finalize-20261111-01');v=json.loads((p/'origin-pins-command.json').read_text())
with (p/'origin-pins.json').open('xb') as out,(p/'origin-pins.stderr').open('xb') as err:r=subprocess.run(v['argv'],input=v['stdin'].encode(),stdout=out,stderr=err,timeout=v['timeout_seconds'])
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
