import pathlib,json,os,termios,subprocess
P=pathlib.Path;D=P('/mnt/kdlock-builds2/main-spin-migration-20261117');receipt=json.loads((D/'migration-receipt.json').read_text())
assert receipt['verified_entries']==416
assert os.uname().release=='7.0.0-38-kdrebuild16'
assert P('/proc/sys/kernel/random/boot_id').read_text().strip()==receipt['boot']
assert P('/proc/modules').read_text()==receipt['modules']
left=[str(p) for pattern in ['main-spin-migration-20261117-part-*','main-spin-migration-delta-0*'] for p in P('/var/lib/kdlock-run').glob(pattern)];assert not left,left
fd=os.open('/dev/ttyS0',os.O_RDWR|os.O_NOCTTY);speed=termios.tcgetattr(fd)[4:6];os.close(fd);assert speed==[9600,9600]
w=[s for s in subprocess.check_output(['dmesg'],text=True).splitlines() if 'soft lockup' in s or 'BUG:' in s]
print(json.dumps({'verified_entries':416,'temporary_chunks':left,'kernel':os.uname().release,'boot':receipt['boot'],'modules_unchanged':True,'serial_speed':speed,'warnings':w,'directory':str(D)}))
