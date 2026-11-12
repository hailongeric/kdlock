"""Recover the preserved, confirmed panicked guest with one QEMU reset."""
from pathlib import Path
import hashlib, json, subprocess, time

BASE = Path('/tmp/kdlock-kernel8-mm-step-20261111-01')
saved = BASE / 'failure-snapshot-01/result.json'
assert hashlib.sha256(saved.read_bytes()).hexdigest() == '3f70a450f32108043cbf2a13c7193709ca376558a89bf96a2611bd6885255b75'
assert json.loads(saved.read_text())['status'] == 'FAILED_VM_SNAPSHOT_PRESERVED_ON_ALL_THREE_DISKS'
OUT = BASE / 'recovery-reset-01'
assert not OUT.exists()
OUT.mkdir()
raw = br'''from pathlib import Path
import datetime, hashlib, json, os, socket
assert os.readlink('/proc/257489/exe') == '/usr/bin/qemu-system-x86_64'
assert Path('/etc/hostname').read_text().strip() == 'Super-Server'
serial = Path('/tmp/qemu-serial.log')
with serial.open('rb') as f:
 f.seek(max(0, serial.stat().st_size - 1048576)); tail = f.read()
assert b'Kernel panic - not syncing: Oopsed too often' in tail
result = {'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'commands':[], 'serial_tail_sha256':hashlib.sha256(tail).hexdigest(), 'ordinary_drain':False, 'reason':'Confirmed kernel panic; failed state preserved on three disks before reset'}
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(15); s.connect('/tmp/qemu-monitor.sock')
def prompt():
 data = b''
 while b'(qemu) ' not in data:
  part = s.recv(65536)
  if not part: raise RuntimeError('monitor closed')
  data += part
  assert len(data) <= 1048576
 return data.decode(errors='replace')
def command(text):
 s.sendall((text+'\n').encode()); reply=prompt(); result['commands'].append({'command':text,'output':reply}); return reply
result['greeting']=prompt()
names=['kd-mm-step-failed-20261111-01','linux70-kdlock1-clean-20261027']
for drive in ['drive_system','drive_data1','drive_kdlock_builds2']:
 reply=command('info block -v '+drive)
 assert all(name in reply for name in names)
assert 'No active jobs' in command('info block-jobs')
command('info status')
reply=command('system_reset')
assert 'Error' not in reply and 'error:' not in reply
result['status']='ONE_QEMU_RESET_ISSUED_AFTER_FAILURE_SNAPSHOT'
result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
s.close()
print(json.dumps(result,sort_keys=True))
'''
(OUT/'recover.py').write_bytes(raw)
argv=['ssh','-T','-p','22','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71','sudo','-n','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin_sha256':hashlib.sha256(raw).hexdigest(),'scope':'One reset after confirmed kernel panic and preserved failure state; no snapshot restoration or drain claim'},indent=2)+'\n')
started=time.time()
with (OUT/'result.json').open('xb') as stdout, (OUT/'stderr').open('xb') as stderr:
 child=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,start_new_session=True)
 (OUT/'dispatch.json').write_text(json.dumps({'pid':child.pid,'started_unix':started},indent=2)+'\n')
 child.stdin.write(raw);child.stdin.close()
 try:code=child.wait(timeout=60)
 except subprocess.TimeoutExpired:code=None
(OUT/'return.json').write_text(json.dumps({'returncode':code,'elapsed_seconds':time.time()-started,'signals_sent':False},indent=2)+'\n')
assert code==0,code
result=json.loads((OUT/'result.json').read_text())
print(json.dumps({'status':result['status'],'receipt_sha256':hashlib.sha256((OUT/'result.json').read_bytes()).hexdigest(),'ordinary_drain':False}))
