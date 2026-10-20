#!/bin/sh
# Source-host orchestration only. The VM supervisor bounds its wait without
# killing a timed-out caller; no later test is launched by this script.
set -u
cd /home/eric/vm/vm-shared/kdlock || exit 1
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 2222 root@10.176.26.71 \
  'cd /root/host_fs/kdlock && PATH=/root/kdlock-translation-venv-20261019/bin:$PATH PYTHONDONTWRITEBYTECODE=1 LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z python3 -u -' \
  > /tmp/kdlock-admission-3-console.log 2>&1 <<'PY'
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path.cwd()/'bench/spin_cacheline'))
import bench_runtime as rt
command = [sys.executable, 'bench/rwlock_compare/admission.py', 'run',
           '--mode', 'diagnostic',
           '--output', '/root/kdlock-evidence/10.176.26.71/bench/nano-rwlock-diagnosis-20261021/admission-3',
           '--host-state', '/tmp/kdlock-admission-host-before-2.json']
log = Path('/root/kdlock-evidence/10.176.26.71/bench/nano-rwlock-diagnosis-20261021/admission-3-supervision.log')
try:
    print(rt.command(command, log, timeout=1800), end='')
except BaseException:
    print(log.read_text(), end='', flush=True)
    raise
PY
run_status=$?
ssh -o BatchMode=yes -o ConnectTimeout=10 eric@10.176.26.71 \
  'timeout 30 sudo -n python3 -' \
  < bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py \
  > /tmp/kdlock-admission-host-after-3.json
capture_status=$?
printf '{"supervisor_ssh_exit":%d,"host_capture_exit":%d}\n' "$run_status" "$capture_status" \
  > /tmp/kdlock-admission-launch-3-exit.json
if [ "$run_status" -ne 0 ]; then
  exit "$run_status"
fi
exit "$capture_status"
