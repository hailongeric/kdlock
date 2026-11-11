import hashlib,json,subprocess,time
from pathlib import Path
out=Path('/tmp/kdlock-kernel4-db7-live-collection-20261111-01')
index=json.loads((out/'guest-index.json').read_text())
leaf='/mnt/kdlock-builds/kdlock-main-work/kernel4-fixtures-db7d7d6e-01a1bc4f'
groups=('live-spin-output','live-spin-controller','live-mutex-output','live-mutex-controller','module-build-receipts')
singles=[row['source_path'] for row in index['files'] if '/' not in row['path']]
paths=[leaf+'/'+name for name in groups]+singles
args=['scp','-r','-P','2222','-o','BatchMode=yes','-o','ConnectTimeout=10']+['root@10.176.26.71:'+name for name in paths]+[str(out)+'/']
record={'argv':args,'started_unix':time.time(),'observer_seconds':90}
with (out/'copy.stdout').open('xb') as stdout,(out/'copy.stderr').open('xb') as stderr:
 child=subprocess.Popen(args,stdout=stdout,stderr=stderr,start_new_session=True)
 record['pid']=child.pid
 try:record['returncode']=child.wait(timeout=90)
 except subprocess.TimeoutExpired:record.update(returncode=None,child_retained=True)
record['finished_unix']=time.time()
with (out/'copy-command.json').open('x') as stream:json.dump(record,stream,indent=2);stream.write('\n')
assert record['returncode']==0,record
for row in index['files']:
 p=out/row['path'];assert not p.is_symlink();data=p.read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],row['path']
summary={'files':index['count'],'bytes':index['bytes'],'index_sha256':hashlib.sha256((out/'guest-index.json').read_bytes()).hexdigest(),'copy_returncode':record['returncode'],'all_hashes_verified':True}
with (out/'verification.json').open('x') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
print(json.dumps(summary))
