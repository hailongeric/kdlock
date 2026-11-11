from pathlib import Path
import hashlib,json,subprocess,time
p=Path('/tmp/kdlock-kernel8-host-checks-20261111-01');helper=Path('/tmp/kdlock-rw-collect5.py');assert hashlib.sha256(helper.read_bytes()).hexdigest()=='3cd38218bee1a01d9747deee866eba8122144ec6571634f86872ba3cc1f9890d'
argv=json.loads((p/'collection-argv.json').read_text());start=time.time()
with (p/'collection.stdout').open('xb') as out,(p/'collection.stderr').open('xb') as err:r=subprocess.run(argv,stdout=out,stderr=err,timeout=330)
(p/'collection-return.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-start},indent=2)+'\n');print(json.dumps({'returncode':r.returncode,'output':argv[argv.index('--output')+1]}));raise SystemExit(r.returncode)
