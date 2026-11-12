from pathlib import Path
import json,subprocess,time
p=Path('/tmp/kdlock-kernel8-mm-step-20261111-01/repeat-controls');deadline=time.monotonic()+240
script="from pathlib import Path;import json,os;print(json.dumps({'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':Path('/proc/sys/kernel/tainted').read_text().strip()}))"
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=5','root@10.176.26.71','python3','-B','-'];(p/'reconnect-command.json').write_text(json.dumps({'argv':a,'stdin':script,'total_seconds':240,'per_attempt_seconds':10,'read_only':True},indent=2)+chr(10));n=0
while time.monotonic()<deadline:
 n+=1;start=time.time()
 with (p/('reconnect-%03d.stdout'%n)).open('xb') as out,(p/('reconnect-%03d.stderr'%n)).open('xb') as err:
  c=subprocess.Popen(a,stdin=subprocess.PIPE,stdout=out,stderr=err);c.stdin.write(script.encode());c.stdin.close()
  try:code=c.wait(timeout=min(10,max(1,deadline-time.monotonic())))
  except subprocess.TimeoutExpired:
   (p/'reconnect-pending.json').write_text(json.dumps({'pid':c.pid,'attempt':n,'status':'READ_CHILD_RETAINED'})+chr(10));raise
 stderr=(p/('reconnect-%03d.stderr'%n)).read_text();(p/('reconnect-%03d.return.json'%n)).write_text(json.dumps({'returncode':code,'elapsed_seconds':time.time()-start},indent=2)+chr(10))
 if any(x in stderr for x in ('Permission denied','Operation not permitted','Access denied')):raise RuntimeError('access denial; stop: '+stderr)
 if code==0:
  v=json.loads((p/('reconnect-%03d.stdout'%n)).read_text())
  if v['boot']!='2ae5991e-d024-48ac-9f86-24a0a8910172':
   (p/'reconnected-identity.json').write_text(json.dumps(v,indent=2)+chr(10));assert v['release']=='7.0.0-38-kdrebuild8' and v['taint']=='0',v;print(json.dumps({'status':'RECONNECTED','attempts':n,'identity':v}));break
 time.sleep(min(5,max(0,deadline-time.monotonic())))
else:raise RuntimeError('bounded read-only reconnect expired; no reboot retry')
