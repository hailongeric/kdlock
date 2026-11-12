from pathlib import Path
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
