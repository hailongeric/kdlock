"""Stream-check a sealed evidence tarball; optionally extract regular files only."""
from pathlib import Path,PurePosixPath
import argparse,gzip,hashlib,json,tarfile,os
p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--extract',type=Path);a=p.parse_args()
run='mutex-legacy-compat-20261017T122742Z';files={};links={};metadata={};seen=set()
if a.extract:a.extract.mkdir(parents=True,exist_ok=False)
with tarfile.open(a.archive,'r|gz') as tar:
 for item in tar:
  assert item.name not in seen,item.name
  seen.add(item.name)
  parts=PurePosixPath(item.name).parts
  assert parts and parts[0]==run and '..' not in parts and not item.name.startswith('/'),item.name
  rel='/'.join(parts[1:])
  if item.isdir():continue
  if item.issym():links[rel]=item.linkname;continue
  assert item.isfile(),item.name
  data=tar.extractfile(item);h=hashlib.sha256();size=0;payload=[];out=None
  if a.extract:
   dest=a.extract/rel;dest.parent.mkdir(parents=True,exist_ok=True);out=dest.open('xb')
  try:
   for chunk in iter(lambda:data.read(1<<20),b''):
    h.update(chunk);size+=len(chunk)
    if rel in ('MANIFEST.json','SEAL.json'):payload.append(chunk)
    if out:out.write(chunk)
  finally:
   if out:out.close()
  assert size==item.size,item.name
  if a.extract:os.chmod(dest,item.mode)
  if rel in ('MANIFEST.json','SEAL.json'):metadata[rel]=(b''.join(payload),h.hexdigest())
  else:files[rel]=dict(sha256=h.hexdigest(),bytes=size,mode=item.mode)
manifest=json.loads(metadata['MANIFEST.json'][0]);seal=json.loads(metadata['SEAL.json'][0])
assert files==manifest['files'] and links==manifest['symlinks']
assert seal['manifest_sha256']==metadata['MANIFEST.json'][1]
print(json.dumps(dict(status='PASS',regular_files=len(files),symlinks=len(links),manifest_sha256=metadata['MANIFEST.json'][1],accepted=seal['accepted']),indent=2))
