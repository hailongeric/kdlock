"""Preserve saved failed-run evidence with lossless stored/raw hash records."""
from pathlib import Path
import gzip,hashlib,json,subprocess

REPO=Path('/home/eric/vm/vm-shared/kdlock-main')
DEST=REPO/'tests/evidence/kernel8-mm-step-failure-20261111'
assert not DEST.exists()
DEST.mkdir()
rows=[]
def digest(data):return hashlib.sha256(data).hexdigest()
def copy(source,relative):
 source=Path(source);assert source.is_file() and not source.is_symlink()
 before=source.stat();raw=source.read_bytes();after=source.stat()
 assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 compressed=len(raw)>=65536 and source.suffix not in ('.gz','.o','.elf','.ko')
 name=str(relative)+('.gz' if compressed else '')
 target=DEST/name;assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True)
 stored=gzip.compress(raw,compresslevel=6,mtime=0) if compressed else raw
 with target.open('xb') as f:f.write(stored)
 actual=target.read_bytes();assert (gzip.decompress(actual) if compressed else actual)==raw
 rows.append({'source':str(source),'path':name,'raw_bytes':len(raw),'raw_sha256':digest(raw),'stored_bytes':len(stored),'stored_sha256':digest(stored),'gzip':compressed})
def tree(source,prefix):
 source=Path(source)
 for p in sorted(source.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():copy(p,Path(prefix)/p.relative_to(source))
tree('/tmp/kdlock-kernel8-mm-step-20261111-01','controls')
tree('/tmp/kdlock-kernel8-mm-step-collection-20261111-01','collections/failed')
tree('/tmp/kdlock-kernel8-mm-step-collection-20261111-02','collections/recovered')
for p in sorted(Path('/tmp').glob('kdlock-mm-step*.py')):copy(p,Path('helpers')/p.name)
for name in ['kdlock-kernel8-mm-prefix-supervisor-20261111-01.py','kdlock-kernel8-mm-step-acquire-refusal-review-20261111.md','kdlock-mutex-cohort-await-independent-review-20261111.md','kdlock-mutex-cohort-await-fix-20261111.patch']:
 copy(Path('/tmp')/name,Path('review')/name)
copy('/tmp/kdlock-kernel8-aux-object-capture-collection-20261111-02/payload/capture/20-instructions.stdout','review/jit-object-instructions.stdout')
copy(__file__,'archive.py')
before=subprocess.check_output(['git','-C',str(REPO),'show','6e486ece^:kernel/mutex.c'])
after=subprocess.check_output(['git','-C',str(REPO),'show','6e486ece:kernel/mutex.c'])
assert digest(before)=='949ed7175a6f68fc6e91ac3ef84742e4f631fc159809dab0bc23f342d81ecbc0'
assert digest(after)=='014b4a9cfb4609eb8a1e49cc14e715302b13060dc641519a7e68b22a7e515564'
(DEST/'source-fix').mkdir()
(DEST/'source-fix/mutex-before.c').write_bytes(before)
(DEST/'source-fix/mutex-after.c').write_bytes(after)
(DEST/'source-fix/commit.txt').write_bytes(subprocess.check_output(['git','-C',str(REPO),'show','--format=fuller','--stat','6e486ece']))
index={'format':'kdlock.lossless-archive.v1','scope':'Failed five-region mmap prefix attempt and reset recovery; no ordinary drain or successful final workload verdict','files':rows,'raw_bytes':sum(r['raw_bytes'] for r in rows),'stored_bytes':sum(r['stored_bytes'] for r in rows),'omitted_files':[]}
(DEST/'copy-index.json').write_text(json.dumps(index,indent=2,sort_keys=True)+'\n')
print(json.dumps({'destination':str(DEST),'copied_files':len(rows),'raw_bytes':index['raw_bytes'],'stored_bytes':index['stored_bytes']}))
