from pathlib import Path
import json,subprocess
p=Path('/tmp/kdlock-kernel8-killable-cycle-recovery-20261111-01');a=json.loads((p/'collection-argv.json').read_text())
with (p/'collection.stdout').open('xb') as out,(p/'collection.stderr').open('xb') as err:r=subprocess.run(a,stdout=out,stderr=err,timeout=360)
(p/'collection-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10));print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
