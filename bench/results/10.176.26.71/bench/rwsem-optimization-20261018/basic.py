import hashlib, json, os, subprocess, time
from pathlib import Path

root = Path('/root/host_fs/kdlock')
out = Path('/mnt/kdlock-builds/rwsem-opt-20261018/final-basic')
out.mkdir(exist_ok=False)
source = out / 'source'
hashes = {}
for folder in ('include', 'daemon', 'tests/unit'):
    for p in (root / folder).rglob('*'):
        rel = p.relative_to(root)
        if (not p.is_file() or any(x.startswith('.') or x == '__pycache__' for x in rel.parts)
                or (p.suffix not in ('.c', '.h', '.inc', '.S', '.def', '.py') and p.name != 'Makefile')):
            continue
        data = p.read_bytes()
        dest = source / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        hashes[str(rel)] = hashlib.sha256(data).hexdigest()
(out / 'source-sha256.json').write_text(json.dumps(hashes, indent=2)+'\n')
argv = ['make', '-C', 'tests/unit', 'run']
start = time.monotonic()
with (out / 'basic.log').open('wb') as log:
    result = subprocess.run(argv, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=180)
(out / 'result.json').write_text(json.dumps(dict(command=argv, returncode=result.returncode,
    seconds=time.monotonic()-start), indent=2)+'\n')
print((out / 'basic.log').read_text(), flush=True)
raise SystemExit(result.returncode)
