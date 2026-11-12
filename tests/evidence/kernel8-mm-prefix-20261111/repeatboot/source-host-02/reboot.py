from pathlib import Path
import hashlib,json,os,subprocess,time
p=Path('/tmp/kdlock-kernel8-repeatboot-run-20261111-02');arm=(p/'actual-arm-result.json').read_bytes();assert hashlib.sha256(arm).hexdigest()=='0bc262c07e7e8f73aa4019231eafe4e804f3c9c98a7254f055714abd221e54bd';r=json.loads(arm);assert r['status']=='REPEAT_ONESHOT_ARM_COMPLETE' and r['grub_after']['environment']['next_entry']=='kdlock-kdrebuild8-api-01'
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','/usr/bin/systemctl','reboot','--no-wall'];start=time.time()
def put(n,v):
 with (p/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
put('reboot-command.json',{'argv':a,'timeout_seconds':30,'arm_sha256':'0bc262c07e7e8f73aa4019231eafe4e804f3c9c98a7254f055714abd221e54bd','old_boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','dispatch_count':1})
with (p/'reboot.stdout').open('xb') as out,(p/'reboot.stderr').open('xb') as err:
 child=subprocess.Popen(a,stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True);put('reboot-dispatch.json',{'pid':child.pid})
 try:code=child.wait(timeout=30)
 except subprocess.TimeoutExpired:put('reboot-return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('reboot-return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'returncode':code}));raise SystemExit(code)
