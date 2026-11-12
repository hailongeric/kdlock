from pathlib import Path
import hashlib,json,os,subprocess
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-mmap-step-input-0798c1ab-01')
expected=json.loads('{"admission.json": "547afb7c2d46d39a99ddf2b09a8ee02f5983ee193a3dafa197f4ac3a64b19403", "configuration-identities.json": "81e1d810bcec80993d415711814417be77ac4425c09ebb7f84eb170c140b626c", "host-config.json": "3c0655de113cdde76e86f238278604d2754013195e1037633300d7cfb93be0e1", "jit-config.bin": "e6b3a905e9cc0952adb3092f3334757cbf3e4ecbcd1efc5071c8b02831f3383b", "recovery.json": "900bda6369c6e805863058a8676764863156587b7a606087813847cd2eef6146", "source-scope.json": "a6cb7507f5c752cc941f61d04681d56c8ca010e30ac57cce9263f9e805360687", "supervisor.py": "09dc900987cec70b89ea60620ddd07c1493fa6c7dd2b4649201421b33c238ebc"}')
for name,h in expected.items():
    p=root/name
    assert p.resolve(strict=True)==p and hashlib.sha256(p.read_bytes()).hexdigest()==h,name
assert os.geteuid()==0
argv=['/usr/bin/python3','-B',str(root/'supervisor.py'),'--config-json',str(root/'host-config.json'),'--config-sha256',expected['host-config.json'],'--receipt','/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-mmap-step-receipts-0798c1ab-01']
result=subprocess.run(argv)
print(json.dumps({'supervisor_returncode':result.returncode,'signals_or_cleanup_by_wrapper':False}),flush=True)
raise SystemExit(result.returncode)
