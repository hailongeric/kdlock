import base64,hashlib,json,subprocess,sys,time
from pathlib import Path
phase=sys.argv[1];assert phase in {'reboot','post-normal'}
out=Path('/tmp/kdlock-return5-readers-01')
if phase=='reboot':out.mkdir(exist_ok=False)
raw=Path('/tmp/kdlock-main-return-normal-after-kdrebuild5-readers.py').read_bytes();pin=hashlib.sha256(raw).hexdigest()
helper='/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/receipts/return-normal5-readers-helper-01/return-normal.py'
args=[helper,phase]
if phase=='reboot':
 for family,sha in [('rwlock','1eabd219a39e5d781081b59f89a603eed2c220b19fc39570b8cf2474daad90a1'),('spin','5dc8e3a6208a5a64aa812f7eb8bb5de90dbc3bbe8b491ad7581433691a7aaf02'),('mutex','4a1cece6922e82d403352486c35a2b66299af5884765682e3b3b610a7ee261b5')]:
  args+=['--'+family+'-controller','/mnt/kdlock-builds/kdlock-main-work/kernel5-fixtures-09834f09-rw-01/live-'+family+'-receipts-01/result.json','--'+family+'-controller-sha256',sha]
code='import ast,base64,hashlib,os,pathlib,runpy,sys\nraw=base64.b64decode('+repr(base64.b64encode(raw).decode())+')\nassert hashlib.sha256(raw).hexdigest()=='+repr(pin)+'\nast.parse(raw)\np=pathlib.Path('+repr(helper)+')\n'
if phase=='reboot':code+='p.parent.mkdir(mode=0o700,exist_ok=False)\nwith p.open("xb") as f:f.write(raw);f.flush();os.fsync(f.fileno())\n'
code+='assert p.read_bytes()==raw\nsys.argv='+repr(args)+'\nrunpy.run_path(str(p),run_name="__main__")\n'
a=['ssh','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=8','root@10.176.26.71','timeout 150 python3 -']
start=time.time();x=subprocess.run(a,input=code.encode(),capture_output=True,timeout=170)
(out/(phase+'.stdout')).write_bytes(x.stdout);(out/(phase+'.stderr')).write_bytes(x.stderr);(out/(phase+'-controller.json')).write_text(json.dumps({'argv':a,'script_sha256':hashlib.sha256(code.encode()).hexdigest(),'helper_sha256':pin,'returncode':x.returncode,'started_unix':start,'finished_unix':time.time()},indent=2)+'\n')
print(phase,'returncode',x.returncode);print(x.stdout.decode()[-2200:]);print(x.stderr.decode()[-2200:]);raise SystemExit(x.returncode)
