from pathlib import Path
import json,subprocess,time
p=Path('/tmp/kdlock-kernel8-mm-provider-build-de76da8a-01');a=json.loads((p/'collection-command.json').read_text())['argv'];start=time.time()
with (p/'collection.stdout').open('xb') as out,(p/'collection.stderr').open('xb') as err:r=subprocess.run(a,stdout=out,stderr=err,timeout=360)
with (p/'collection-return.json').open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10))
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
