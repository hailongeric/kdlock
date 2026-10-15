#!/bin/bash
set -euo pipefail
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONDONTWRITEBYTECODE=1 LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=mutex-numa-c01-rerun-20261015
export KD_MUTEX_RERUN=/root/kdlock-evidence/10.176.26.71/bench/mutex-numa-c01-rerun-20261015

python3 - <<'PY'
import hashlib,json,os,tarfile
from pathlib import Path
out=Path(os.environ['KD_MUTEX_RERUN'])
identity=json.loads((out/'source-identity.json').read_text())
archive=out/'source-5b50a4a.tar'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==identity['archive_sha256']
assert not any((out/'source').iterdir())
before=json.loads((out/'control/guest-before.json').read_text())
assert before['passed'] and before['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
boot=json.loads((out/'control/boot-policy.json').read_text())
assert boot['boot_id']==before['boot_id'] and boot['method']=='live_pv_ops_two_function_pointers'
host=json.loads((out/'control/host-before.json').read_text())
assert host['passed'] and host['created'] and host['snapshot_tag']==os.environ['KDLOCK_SNAPSHOT_TAG']
with tarfile.open(archive) as tf:
    for item in tf.getmembers():
        assert not Path(item.name).is_absolute() and '..' not in Path(item.name).parts
        assert item.isfile() or item.isdir(), item.name
    tf.extractall(out/'source')
for name,digest in identity['manifest'].items():
    assert hashlib.sha256((out/'source'/name).read_bytes()).hexdigest()==digest,name
(out/'control/source-before.json').write_text(json.dumps(dict(passed=True,commit=identity['commit'],files=len(identity['manifest']),archive_sha256=identity['archive_sha256']),indent=2)+'\n')
print('Verified committed source, idle-boot receipt and new recovery snapshot.',flush=True)
PY

set +e
unshare --mount --fork bash -se <<'KD_NAMESPACE'
set -euo pipefail
mount --make-rprivate /
mount --bind "$KD_MUTEX_RERUN/source" /root/host_fs/kdlock
cd /root/host_fs/kdlock

args=(--mutex-implementation owned-v1 --owned-mutex-cabi --owned-mutex-reuse-spins 32
      --owned-mutex-origin-spin --owned-mutex-numa --mutex-acceptance adaptive-performance
      --workload cacheline --cachelines 1
      --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60
      --cpus 0-59 --collector-cpu 63
      --backends native tclock kdlock --repeats 3 --duration-ms 2000
      --peak-window-ms 300 --peak-settle-ms 300 --sample-ms 10
      --kernel-source /root/linux-6.1.159-kdclobber2
      --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919
      --output "$KD_MUTEX_RERUN/matrix")
python3 bench/tclock_compare/run_mutex.py "${args[@]}" --dry-run > "$KD_MUTEX_RERUN/control/plan.json"
python3 - <<'PY'
import json,os,sys
from pathlib import Path
sys.path.insert(0,'bench/tclock_compare')
import run
run.idle()
out=Path(os.environ['KD_MUTEX_RERUN'])
plan=json.loads((out/'control/plan.json').read_text())
threads=[*range(1,9),*range(12,61,4)]
arms=['native','tclock','kdlock']
assert [(r['threads'],r['repeat'],r['arm']) for r in plan]==[(n,i,a) for n in threads for i in range(3) for a in (arms[::-1] if i%2 else arms)]
assert len(plan)==189 and all(not r['collector_shared'] for r in plan)
assert all(r['owned_mutex_origin_spin'] and r['owned_mutex_numa'] and r['entry_abi']==4 and r['owned_mutex_reuse_spins']==32 for r in plan if r['arm']=='kdlock')
print('Plan verified: 189 sessions, three arms, requested 21 worker counts, separate collector.',flush=True)
PY

timeout --kill-after=10s 7200s python3 bench/tclock_compare/run_mutex.py "${args[@]}" > "$KD_MUTEX_RERUN/runner.log" 2>&1

python3 - <<'PY'
import hashlib,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,'bench/tclock_compare')
import run
run.idle()
out=Path(os.environ['KD_MUTEX_RERUN'])
matrix=out/'matrix'
identity=json.loads((out/'source-identity.json').read_text())
for name,digest in identity['manifest'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
sources=json.loads((matrix/'source-sha256.json').read_text())
assert run.source_state()==sources
for name,digest in json.loads((matrix/'binary-sha256.json').read_text()).items():
    assert run.digest(Path(name))==digest,name
modules=[line.split()[0] for line in Path('/proc/modules').read_text().splitlines() if line.startswith(('kd','tc','spin_cacheline','mutex_cacheline','rwlock','rwsem'))]
assert not modules,modules
kernel=subprocess.check_output(['dmesg'],text=True)
(out/'control/kernel-final.log').write_text(kernel)
assert not run.runtime.FAULT.search(kernel),'kernel fault at final drain'
result=dict(passed=True,idle=True,project_modules=modules,source_unchanged=True,binaries_unchanged=True,
    committed_files=len(identity['manifest']),source_files=len(sources),online_cpus=Path('/sys/devices/system/cpu/online').read_text().strip(),
    preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    kernel_faults=False)
(out/'control/guest-final.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
PY
KD_NAMESPACE
status=$?
printf '%s\n' "$status" > "$KD_MUTEX_RERUN/exit-status.txt"
exit "$status"
