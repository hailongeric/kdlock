#!/bin/sh
# Sole source-host supervisor; deadlines never kill an active guest caller.
set -u
cd /home/eric/vm/vm-shared/kdlock || exit 1
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 2222 root@10.176.26.71 \
 'cd /root/host_fs/kdlock && PATH=/root/kdlock-translation-venv-20261019/bin:$PATH PYTHONDONTWRITEBYTECODE=1 LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z python3 -u -' \
 > /tmp/kdlock-recovery-followup-run-1-console.log 2>&1 <<'PY'
import hashlib, shutil, sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'bench/spin_cacheline'))
import bench_runtime as rt
source=Path.cwd()/'bench/mutex_api_compare/recovery_replay.py'
program=Path('/tmp/kdlock-recovery-followup-run-1.py')
assert not program.exists()
shutil.copyfile(source,program)
assert hashlib.sha256(program.read_bytes()).digest()==hashlib.sha256(source.read_bytes()).digest()
command=[sys.executable,program,'--prepared',
 '/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2',
 '--output','/root/kdlock-evidence/10.176.26.71/bench/mutex-recovery-followup-20261021/run-1',
 '--host-state','/tmp/kdlock-recovery-followup-host-before-run.json',
 '--transition','/root/kdlock-evidence/10.176.26.71/bench/mutex-recovery-followup-20261021/transition-1/result.json',
 '--transition-sha256','81280a1655854fead9e64c4ee752275a32eef3c3f30ce09d27b71a89621a1ca1',
 '--source-commit','0d65f89aff5030224e7e324add0f8e9f2d3d5dd5']
log=Path('/tmp/kdlock-recovery-followup-run-1-supervision.log')
try:
 print(rt.command(command,log,timeout=2700),end='',flush=True)
except BaseException:
 print(log.read_text(),end='',flush=True)
 raise
PY
run_status=$?
ssh -o BatchMode=yes -o ConnectTimeout=10 eric@10.176.26.71 \
 'timeout 30 sudo -n python3 -' \
 < bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py \
 > /tmp/kdlock-recovery-followup-host-after-1.json
capture_status=$?
printf '{"supervisor_ssh_exit":%d,"host_capture_exit":%d}\n' "$run_status" "$capture_status" \
 > /tmp/kdlock-recovery-followup-launch-1-exit.json
if [ "$run_status" -ne 0 ]; then exit "$run_status"; fi
exit "$capture_status"
