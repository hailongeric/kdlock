import hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/receipts/repeat-kdrebuild4-db7-20261111-01')
old='84e4ba94-b616-4b65-9efe-820921f36c16'
review='07ca30d9ddbd129f91f5e606fe1dc3cb579958623cd46a27e157541b7a271aeb'
arm_bytes=(root/'arm-complete.json').read_bytes(); arm=json.loads(arm_bytes)
assert arm['status']=='COMPLETE' and arm['phase']=='arm' and arm['review_sha256']==review
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()==old
assert os.uname().release=='7.0.0-38-kdrebuild4'
assert pathlib.Path('/proc/sys/kernel/tainted').read_text().strip()=='12288'
assert not list(pathlib.Path('/dev').glob('kd*'))
assert not any(any(x in row.split()[0].lower() for x in ('kdlock','kd_','komb','tclock')) for row in pathlib.Path('/proc/modules').read_text().splitlines())
assert hashlib.sha256(pathlib.Path('/boot/grub/grub.cfg').read_bytes()).hexdigest()=='9797117f0ac48ebd8122a39b38716c3f7dd5c86c59ced0ead048389ae086f9a1'
env=subprocess.run(['grub-editenv','/boot/grub/grubenv','list'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15).stdout.decode()
assert dict(x.split('=',1) for x in env.splitlines() if '=' in x)==json.loads((root/'arm-after.json').read_text())['environment']
def save(name,value):
 with (root/name).open('x') as f:
  json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
argv=['systemctl','reboot'];started=time.time()
save('reboot-command.json',{'argv':argv,'old_boot_id':old,'arm_sha256':hashlib.sha256(arm_bytes).hexdigest(),'review_sha256':review,'unix':started,'timeout_seconds':30,'ordinary_reboot_only':True})
try:
 r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
 save('reboot-result.json',{'argv':argv,'returncode':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace'),'unix':time.time(),'elapsed_seconds':time.time()-started})
 raise SystemExit(r.returncode)
except subprocess.TimeoutExpired as e:
 save('reboot-uncertain.json',{'argv':argv,'error':repr(e),'unix':time.time(),'no_retry':True})
 raise
