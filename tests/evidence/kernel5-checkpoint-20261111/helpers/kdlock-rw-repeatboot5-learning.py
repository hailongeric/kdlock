import hashlib,json,subprocess,time
from pathlib import Path
out=Path('/tmp/kdlock-rw-repeatboot5-learning-01');out.mkdir(exist_ok=False)
saved=Path('/tmp/kdlock-host-image-size-20261111-01/host-stdout.jsonl').read_bytes()
metadata=json.loads(saved.splitlines()[0])['data']
assert any(x['command']=='info snapshots' and 'kdlock-builddisk-clean-20261031' in x['output'].split('List of partial')[0] for x in metadata['hmp'])
assert any(x['command']=='info block' and all(n in x['output'] for n in ['drive_system','drive_data1','drive_kdlock_builds2']) for x in metadata['hmp'])
(out/'recovery-saved-host-metadata.jsonl').write_bytes(saved)
(out/'recovery-source.json').write_text(json.dumps({'source':'/tmp/kdlock-host-image-size-20261111-01/host-stdout.jsonl','sha256':hashlib.sha256(saved).hexdigest(),'scope':'Already captured live monitor proof before ordinary image-lock refusal; no second host/image access.'},indent=2)+'\n')
code='''import hashlib,json,os,pathlib,subprocess
assert os.uname().release=='7.0.0-38-kdrebuild5' and pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='9336b735-78f0-4f9c-9d9e-f04677f8d6bc'
assert pathlib.Path('/proc/sys/kernel/tainted').read_text().strip()=='12288'
assert not list(pathlib.Path('/dev').glob('kd*')) and not list(pathlib.Path('/sys/module').glob('kd_*fixture*'))
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdecimal():continue
 try:
  c=(p/'comm').read_text().strip()
  assert not c.startswith(('kd-fixture','kd-reader','kd-scene','gcc','cc1')) and c not in {'make','ld','as','objtool'},c
 except FileNotFoundError:pass
cfg=pathlib.Path('/boot/grub/grub.cfg').read_text();assert 'set default="gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdlock1-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961"' in cfg
entry='gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>gnulinux-7.0.0-38-kdrebuild5-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961'
assert cfg.count("'"+entry.split('>')[1]+"'")==1
subprocess.run(['grub-reboot',entry],check=True,timeout=15)
r=subprocess.run(['grub-editenv','/boot/grub/grubenv','list'],check=True,capture_output=True,text=True,timeout=15);assert 'next_entry='+entry in r.stdout.splitlines()
assert pathlib.Path('/boot/grub/grub.cfg').read_text()==cfg
print(json.dumps({'before_boot':'9336b735-78f0-4f9c-9d9e-f04677f8d6bc','normal_default_preserved':True,'grubenv':r.stdout}),flush=True)
subprocess.run(['sync'],check=True,timeout=15);subprocess.run(['systemctl','reboot'],check=True,timeout=10)
'''
a=['ssh','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=8','root@10.176.26.71','timeout 55 python3 -'];x=subprocess.run(a,input=code.encode(),capture_output=True,timeout=65);(out/'reboot.stdout').write_bytes(x.stdout);(out/'reboot.stderr').write_bytes(x.stderr);(out/'reboot-command.json').write_text(json.dumps({'argv':a,'returncode':x.returncode,'script_sha256':hashlib.sha256(code.encode()).hexdigest(),'unix':time.time()},indent=2)+'\n');print(x.returncode,x.stdout.decode(),x.stderr.decode());assert x.returncode==0
