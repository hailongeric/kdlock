from pathlib import Path
import hashlib,json,os,subprocess,time
p=Path('/tmp/kdlock-kernel8-aux-object-capture-controls-20261111-01');a=json.loads((p/'collection-command.json').read_text())['argv'];assert hashlib.sha256(Path(a[2]).read_bytes()).hexdigest()=='3cd38218bee1a01d9747deee866eba8122144ec6571634f86872ba3cc1f9890d';start=time.time()
with (p/'collection.stdout').open('xb') as out,(p/'collection.stderr').open('xb') as err:r=subprocess.run(a,stdout=out,stderr=err,timeout=240)
with (p/'collection-return.json').open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10));f.flush();os.fsync(f.fileno())
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
