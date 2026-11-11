#!/usr/bin/env python3
"""Run the two explicitly authorized immutable guest-receipt collections."""
import hashlib,json,os,subprocess,time
from pathlib import Path

HELPER=Path('/tmp/kdlock-rw-collect5.py')
assert hashlib.sha256(HELPER.read_bytes()).hexdigest()=='3cd38218bee1a01d9747deee866eba8122144ec6571634f86872ba3cc1f9890d'
LAUNCH=Path('/tmp/kdlock-reader-collection-launch-20261111-01')
LAUNCH.mkdir(mode=0o700)
BASE='/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f'
WORK='/mnt/kdlock-builds/kdlock-main-work'
common=['--max-files','10240','--max-paths','40960','--max-file-bytes','50331648',
        '--max-metadata-bytes','16777216','--inventory-seconds','90','--copy-seconds','180']
jobs=[('checkpoint','/tmp/kdlock-kernel5-checkpoint-collection-20261111-01','536870912',[
 ('overlay',BASE+'/receipts/overlay-kdrebuild5-rw-01'),
 ('install',BASE+'/receipts/install-kdrebuild5-rw-01'),
 ('postboot-initial',BASE+'/receipts/postboot-kdrebuild5-rw-01'),
 ('postboot-capacity',BASE+'/receipts/postboot-kdrebuild5-capacity-01'),
 ('postboot-learning-failed',BASE+'/receipts/postboot-kdrebuild5-learning-01'),
 ('postboot-learning-proof',BASE+'/receipts/postboot-kdrebuild5-learning-proof-01')]),
 ('recoveries','/tmp/kdlock-rw-recoveries-collection-01','268435456',[
 ('rwsem-capacity',WORK+'/kernel5-fixtures-e990fde3-rw-01/recovery-rwsem-capacity-01'),
 ('rwsem-learning',WORK+'/kernel5-fixtures-68a2e5ed-rw-01/recovery-rwsem-learning-01'),
 ('rwlock-native',WORK+'/kernel5-fixtures-e5b78520-rw-01/recovery-rwlock-native-01')])]
for label,output,total,trees in jobs:
 assert not Path(output).exists()
 argv=['python3',str(HELPER),'--output',output,*common,'--max-total-bytes',total]
 for name,path in trees:argv+=['--tree',name,path]
 root=LAUNCH/label;root.mkdir()
 (root/'collector.py').write_bytes(HELPER.read_bytes())
 (root/'command.json').write_text(json.dumps({'argv':argv,'started_unix':time.time(),'scope':'completed immutable guest receipts only; no host image or QEMU access'},indent=2)+'\n')
 start=time.monotonic()
 with (root/'stdout.log').open('xb') as out,(root/'stderr.log').open('xb') as err:
  result=subprocess.run(argv,stdout=out,stderr=err)
  out.flush();err.flush();os.fsync(out.fileno());os.fsync(err.fileno())
 receipt={'returncode':result.returncode,'elapsed_seconds':time.monotonic()-start,'output':output,'launch_receipts':str(root)}
 for name in ['stdout.log','stderr.log','command.json','collector.py']:
  b=(root/name).read_bytes();receipt[name]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
 (root/'result.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 print(json.dumps(receipt,sort_keys=True),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
