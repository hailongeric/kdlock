import datetime, hashlib, json, os, runpy, shutil, subprocess, sys
from pathlib import Path
sys.dont_write_bytecode = True
r = json.load(sys.stdin)
root = Path('/root/host_fs/kdlock')
sys.path.insert(0, str(root / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
runpy.run_path(str(root / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
assert os.uname().release == '6.1.159-kdclobber2'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == r['recovery_boot']
def modules():
    return sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
def command(argv):
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    out, err = p.communicate(timeout=30)
    return dict(argv=argv, pid=p.pid, returncode=p.returncode, stdout=out.decode(), stderr=err.decode(), completion_unconfirmed=False)
expected = sorted(r['expected_modules'])
assert set(modules()) <= set(expected)
missing = sorted(set(expected) - set(modules()))
assert missing == ['nfnetlink', 'tls'], missing
restored = []
for name in missing:
    row = command(['modprobe', name])
    restored.append(row)
    assert row['returncode'] == 0, row
assert modules() == expected
identity = kernel_identity.check(Path('/root/linux-6.1.159-kdclobber2'), Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919'))
assert identity['ok'] and identity['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
grub = command(['grub-editenv', '/boot/grub/grubenv', 'list'])
assert grub['returncode'] == 0 and grub['stdout'] == 'next_entry=\n'
assert 'set default="' + r['recovery_default'] + '"' in Path('/boot/grub/grub.cfg').read_text()
dmesg = command(['dmesg'])
assert dmesg['returncode'] == 0 and not rt.FAULT.search(dmesg['stdout'])
runpy.run_path(str(root / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
taint = int(Path('/proc/sys/kernel/tainted').read_text())
assert taint == 0
print(json.dumps(dict(passed=True, captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    release=os.uname().release, boot_id=r['recovery_boot'], kernel_identity=identity,
    cmdline=Path('/proc/cmdline').read_text().strip(), modules=modules(), restored=restored,
    taint=taint, grubenv=grub['stdout'], recovery_default=r['recovery_default'], idle=True,
    preempt=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
    online=Path('/sys/devices/system/cpu/online').read_text().strip(), dmesg=dmesg,
    free_bytes={p:shutil.disk_usage(p).free for p in ('/', '/mnt/kdlock-builds', '/dev/shm')})), flush=True)
