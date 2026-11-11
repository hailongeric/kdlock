from pathlib import Path
import hashlib,json,os,subprocess,time
args=['/usr/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/install-finalize-helpers-01/postboot.py', '--output', '/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/postboot-kdrebuild8-api-01', '--timeout', '120', '--max-command-bytes', '33554432', '--max-notes-bytes', '1048576'];helper=Path(args[2]);assert hashlib.sha256(helper.read_bytes()).hexdigest()=='7ba6bd53f6d281715f21dfdb11280cde751fc3bb6a471f5f33f40274c32146a7';assert os.uname().release=='7.0.0-38-kdrebuild8' and Path('/proc/sys/kernel/tainted').read_text().strip()=='0'
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/postboot-driver-api-01');d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
put('command.json',{'argv':args,'helper_sha256':'7ba6bd53f6d281715f21dfdb11280cde751fc3bb6a471f5f33f40274c32146a7'});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid,'unix':time.time()});print(json.dumps({'event':'DISPATCHED','pid':child.pid,'driver':str(d)}),flush=True)
 try:code=child.wait(timeout=240)
 except subprocess.TimeoutExpired:put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code,'driver':str(d)}),flush=True);raise SystemExit(code)
