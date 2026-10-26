import json,os,runpy,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
root=Path('/root/host_fs/kdlock')
sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
r=dict(release=os.uname().release,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),cmdline=Path('/proc/cmdline').read_text().strip(),modules=sorted(x.split()[0] for x in Path('/proc/modules').read_text().splitlines()),taint=int(Path('/proc/sys/kernel/tainted').read_text()),online=Path('/sys/devices/system/cpu/online').read_text().strip(),preempt=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),idle=True)
p=subprocess.Popen(['grub-editenv','/boot/grub/grubenv','list'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
out,err=p.communicate(timeout=10)
assert p.returncode==0 and not err
r['grubenv']=out.decode()
print(json.dumps(r),flush=True)
