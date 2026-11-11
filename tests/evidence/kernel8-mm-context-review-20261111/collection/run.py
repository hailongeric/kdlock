from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-mm-context-20261111-01');v=json.loads((p/'command.json').read_text())
with (p/'raw.json').open('xb') as out,(p/'stderr').open('xb') as err:r=subprocess.run(v['argv'],input=(p/'stdin.py').read_bytes(),stdout=out,stderr=err,timeout=v['timeout_seconds'])
if r.returncode:raise SystemExit(r.returncode)
v=json.loads((p/'raw.json').read_text());d=p/'export';d.mkdir();index=[]
for n,x in v['source_files'].items():
 b=base64.b64decode(x.pop('data'));assert hashlib.sha256(b).hexdigest()==x['sha256'];q=d/'source'/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b);index.append({'path':str(q.relative_to(d)),'bytes':len(b),'sha256':x['sha256']})
for n,x in v['disassembly'].items():
 b=base64.b64decode(x.pop('stdout'));assert hashlib.sha256(b).hexdigest()==x['stdout_sha256'];q=d/'disassembly'/(n+'.txt');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b);(q.with_suffix('.stderr')).write_bytes(base64.b64decode(x.pop('stderr')));index.append({'path':str(q.relative_to(d)),'bytes':len(b),'sha256':x['stdout_sha256']})
(p/'manifest.json').write_text(json.dumps(v,indent=2,sort_keys=True)+chr(10));(p/'copy-index.json').write_text(json.dumps(index,indent=2,sort_keys=True)+chr(10));print(json.dumps({'source_files':v['source_file_count'],'symbols':v['symbol_count'],'bytes':v['payload_bytes'],'manifest_sha256':hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest(),'index_sha256':hashlib.sha256((p/'copy-index.json').read_bytes()).hexdigest(),'output':str(d)}))
