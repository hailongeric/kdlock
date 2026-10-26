
import datetime,json,os,shutil,subprocess
from pathlib import Path

import os
from pathlib import Path
skip={os.getpid()}
parent=os.getppid()
while parent>1 and parent not in skip:
    skip.add(parent)
    try: parent=int(Path('/proc',str(parent),'stat').read_text().rsplit(')',1)[1].split()[1])
    except (OSError,ValueError,IndexError): break
processes=[];open_project=[];scan_errors=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name) in skip: continue
    try:
        args=p.joinpath('cmdline').read_bytes().split(b'\0')
        argv=[x.decode(errors='replace') for x in args if x]
        comm=p.joinpath('comm').read_text().strip()
        if not argv: continue
        project=any(s in ' '.join(argv).lower() for s in ('kdlock','kd_mmap','bench/mmap','bench/mutex','kernel_module','tests/kernel'))
        build=comm in ('make','gmake','ninja','gcc','cc1','cc1plus','ld','ld.bfd','insmod','rmmod','kd_daemon')
        if project or build:
            processes.append({'pid':int(p.name),'comm':comm,'argv':argv[:8]})
        for fd in p.joinpath('fd').iterdir():
            try: target=os.readlink(fd)
            except FileNotFoundError: continue
            if target.startswith(('/root/host_fs/kdlock/','/root/kdlock-evidence/')):
                open_project.append({'pid':int(p.name),'fd':fd.name,'target':target})
    except (FileNotFoundError,ProcessLookupError): continue
    except PermissionError as e: scan_errors.append(str(e))

result=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),uid=os.geteuid(),release=os.uname().release,
 boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),cmdline=Path('/proc/cmdline').read_text().strip(),
 modules=sorted(x.split()[0] for x in Path('/proc/modules').read_text().splitlines()),
 taint=int(Path('/proc/sys/kernel/tainted').read_text()),online=Path('/sys/devices/system/cpu/online').read_text().strip(),
 preempt=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
 grubenv=subprocess.check_output(['grub-editenv','list'],text=True,timeout=10),
 filesystems={p:dict(zip(('total','used','free'),shutil.disk_usage(p))) for p in ('/','/mnt/kdlock-builds','/dev/shm')},
 recovery_source=str(Path('/root/linux-6.1.159-kdclobber2').resolve()),project_processes=processes,open_project_files=open_project,scan_errors=scan_errors,
 dmesg=subprocess.check_output(['dmesg'],text=True,timeout=10))
print(json.dumps(result),flush=True)
