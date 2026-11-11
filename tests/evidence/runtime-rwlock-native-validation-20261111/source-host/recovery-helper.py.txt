import hashlib,json,os,pathlib,stat,subprocess,time
W=pathlib.Path('/mnt/kdlock-builds/kdlock-main-work/kernel5-fixtures-e5b78520-rw-01')
O=W/'recovery-rwlock-native-01'
M='kd_rwlock_runtime_fixture'
BOOT='b827f92c-254a-4cd3-a989-c6ea32c74605'
PINS={'live-rwlock-01/result.json': '8c3dfcfc87215e2827621cdfa66745bce92fb7cf2434d85215c0354931db052d', 'live-rwlock-receipts-01/result.json': '0d49a3883d69ee35c33c5a6a1b1afd6bb4777eafe69984952589187d9d28720e'}
def need(v,m):
 if not v:raise RuntimeError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def save(n,b):
 with (O/n).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def status(fd,n):
 os.lseek(fd,0,os.SEEK_SET);b=os.read(fd,16384);save(n,b);return dict(x.split('=',1) for x in b.decode().split())
def tasks():
 rows=[]
 for p in pathlib.Path('/proc').iterdir():
  if not p.name.isdecimal():continue
  try:
   c=(p/'comm').read_text().strip()
   if c.startswith(('kd-fixture/','kd-scene/','kd-reader/')):rows.append({'pid':int(p.name),'comm':c,'stat':(p/'stat').read_text()})
  except FileNotFoundError:pass
 return rows
need(os.geteuid()==0 and os.uname().release=='7.0.0-38-kdrebuild5' and pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT,'kernel identity differs')
need(pathlib.Path('/proc/sys/kernel/tainted').read_text().strip()=='12288','taint differs')
for rel,pin in PINS.items():
 p=W/rel;s=p.lstat();need(stat.S_ISREG(s.st_mode) and s.st_size<2097152 and sha(p.read_bytes())==pin,'failed input differs '+rel)
f=json.loads((W/'live-rwlock-01/result.json').read_text());c=json.loads((W/'live-rwlock-receipts-01/result.json').read_text())
need(f['status']=='failed_or_incomplete' and c['status']=='FAILED_OR_INCOMPLETE' and c['returncode']==1,'original disposition differs')
need(f['wire_log']['reservations']==0 and not (W/'live-rwlock-01/source-export.bin').exists() and not f.get('compiler_cycles'),'source channel or producer existed')
need(f['observation_records']==653 and f['observation_overflow']==0,'observation count differs')
need(not O.exists() and pathlib.Path('/sys/module',M).is_dir(),'recovery/module differs')
O.mkdir(mode=0o700);r={'status':'PREPARED','started_unix':time.time(),'pins':PINS,'exchanges':[]};fd=-1
try:
 save('tasks-before.json',(json.dumps(tasks(),indent=2)+'\n').encode())
 before=subprocess.run(['dmesg','--color=never'],check=True,capture_output=True,timeout=15).stdout;save('dmesg-before.txt',before)
 fd=os.open('/dev/'+M+'_ctl',os.O_RDWR|os.O_CLOEXEC)
 s=status(fd,'fixture-before.txt')
 need(all(s.get(k)==v for k,v in {'workers':'5','finished':'5','locks_clear':'1','runtime':'1','errors':'0','core_errors':'0','origin_errors':'0','events':'653','overflow':'0'}.items()),'finished native scene differs')
 need(len(tasks())==5,'native joined task count differs')
 for command in [b'stop\n',b'destroy\n']:
  need(os.write(fd,command)==len(command),'ordinary control refused')
  r['exchanges'].append(command.decode().strip());s=status(fd,'fixture-after-'+command.decode().strip()+'.txt')
  need(s.get('workers')=='0' and s.get('locks_clear')=='1','workers/locks did not drain')
  if command==b'destroy\n':need(s.get('runtime')=='0','runtime not destroyed')
 os.close(fd);fd=-1
 x=subprocess.run(['/usr/sbin/rmmod',M],capture_output=True,timeout=20);save('rmmod.stdout',x.stdout);save('rmmod.stderr',x.stderr);r['rmmod_returncode']=x.returncode;need(x.returncode==0,'ordinary unload refused')
 need(not pathlib.Path('/sys/module',M).exists() and not list(pathlib.Path('/dev').glob(M+'*')) and not tasks(),'module/devices/workers remain')
 after=subprocess.run(['dmesg','--color=never'],check=True,capture_output=True,timeout=15).stdout;save('dmesg-after.txt',after);need(after==before,'dmesg changed')
 need(pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT and pathlib.Path('/proc/sys/kernel/tainted').read_text().strip()=='12288','identity changed')
 r.update(status='ORDINARY_NATIVE_ONLY_RECOVERY_COMPLETE',dmesg_unchanged=True,unloaded=True,source_exported=False,compiler_cycles=0,wire_reservations=0)
except BaseException as e:
 r.update(status='FAILED_RETAIN_STATE',error=repr(e));raise
finally:
 if fd>=0:os.close(fd)
 r['finished_unix']=time.time();save('result.json',(json.dumps(r,indent=2,sort_keys=True)+'\n').encode());print(json.dumps(r),flush=True)
