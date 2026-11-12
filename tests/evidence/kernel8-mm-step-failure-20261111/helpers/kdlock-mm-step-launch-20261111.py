"""Observe one authorized unchanged syscall run without failure cleanup."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

BASE=Path('/tmp/kdlock-kernel8-mm-step-20261111-01')
OUT=BASE/'run-step-01'
assert not OUT.exists()
OUT.mkdir()
stage=json.loads((BASE/'stage-step-01/result.json').read_text())
assert stage['status']=='FIVE_REGION_INPUT_STAGED_NO_PROFILE_LOADED'
expected=stage['staged']
assert expected['host-config.json']=='3c0655de113cdde76e86f238278604d2754013195e1037633300d7cfb93be0e1'
script='''from pathlib import Path
import hashlib,json,os,subprocess
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-mmap-step-input-0798c1ab-01')
expected=json.loads(EXPECTED)
for name,h in expected.items():
    p=root/name
    assert p.resolve(strict=True)==p and hashlib.sha256(p.read_bytes()).hexdigest()==h,name
assert os.geteuid()==0
argv=['/usr/bin/python3','-B',str(root/'supervisor.py'),'--config-json',str(root/'host-config.json'),'--config-sha256',expected['host-config.json'],'--receipt','/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-mmap-step-receipts-0798c1ab-01']
result=subprocess.run(argv)
print(json.dumps({'supervisor_returncode':result.returncode,'signals_or_cleanup_by_wrapper':False}),flush=True)
raise SystemExit(result.returncode)
'''.replace('EXPECTED',repr(json.dumps(expected,sort_keys=True)))
raw=script.encode();(OUT/'stdin.py').write_bytes(raw)
argv=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin':str(OUT/'stdin.py'),
    'stdin_sha256':hashlib.sha256(raw).hexdigest(),'observer_seconds':650,
    'signals_or_cleanup_on_observer_timeout':False},indent=2)+'\n')
started=time.time()
with (OUT/'stdout').open('xb') as stdout,(OUT/'stderr').open('xb') as stderr:
    child=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True)
    (OUT/'dispatch.json').write_text(json.dumps({'pid':child.pid,'process_group':os.getpgid(child.pid),
        'started_unix':started,'single_dispatch':True},indent=2)+'\n')
    child.stdin.write(raw);child.stdin.close()
    try:
        code=child.wait(timeout=650)
        record={'returncode':code,'elapsed_seconds':time.time()-started,'signals_or_cleanup':False}
    except subprocess.TimeoutExpired:
        record={'returncode':None,'elapsed_seconds':time.time()-started,'signals_or_cleanup':False,
                'status':'SOURCE_HOST_OBSERVER_TIMEOUT_EXISTING_SSH_RETAINED','pid':child.pid}
(OUT/'return.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
if record['returncode'] is not None:
    print((OUT/'stdout').read_text()[-8192:])
raise SystemExit(0 if record['returncode']==0 else 1)
