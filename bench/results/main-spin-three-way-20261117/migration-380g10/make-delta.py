from pathlib import Path
import tarfile,zlib,json,hashlib,base64,gzip
R=Path('/tmp/kdlock-380g10-migration-20261117');raw=(R/'migration.tar.gz').read_bytes();count=36;prefix=raw[:count*131072];base=zlib.decompressobj(31).decompress(prefix)
index={hashlib.sha256(base[i:i+512]).digest():i for i in range(0,len(base)-511,512)}
literals=[];literal_index={};files=[];dirs=[]
with tarfile.open(R/'migration.tar.gz') as t:
 for m in t:
  if m.isdir():dirs.append([m.name,m.mode]);continue
  if m.issym():files.append({'name':m.name,'link':m.linkname});continue
  assert m.isfile(),m
  data=t.extractfile(m).read();ops=[]
  for i in range(0,len(data),512):
   b=data[i:i+512].ljust(512,b'\0');h=hashlib.sha256(b).digest();off=index.get(h)
   if off is not None:assert base[off:off+512]==b;ops.append(off+1)
   else:
    if h not in literal_index:literal_index[h]=len(literals);literals.append(base64.b64encode(b).decode())
    ops.append(-literal_index[h]-1)
  files.append({'name':m.name,'mode':m.mode,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'ops':ops})
package={'prefix_parts':count,'prefix_sha256':hashlib.sha256(prefix).hexdigest(),'base_sha256':hashlib.sha256(base).hexdigest(),'files':files,'dirs':dirs,'literals':literals}
blob=gzip.compress(json.dumps(package,separators=(',',':')).encode(),mtime=0)
(R/'delta.json.gz').write_bytes(blob)
print({'prefix_bytes':len(prefix),'base_bytes':len(base),'literal_blocks':len(literals),'delta_bytes':len(blob),'files':len(files),'sha256':hashlib.sha256(blob).hexdigest()})
