#!/bin/sh
# Sole source-host supervisor; deadlines never kill an active guest caller.
set -u
cd /home/eric/vm/vm-shared/kdlock || exit 1
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 2222 root@10.176.26.71 \
 'cd /root/host_fs/kdlock && PATH=/root/kdlock-translation-venv-20261019/bin:$PATH PYTHONDONTWRITEBYTECODE=1 LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z python3 -u -' \
 > /tmp/kdlock-pipecap-run-2-console.log 2>&1 <<'PY'
import hashlib, shutil, sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'bench/spin_cacheline'))
import bench_runtime as rt
source=Path.cwd()/'bench/mutex_api_compare/pipecap_causal.py'
program=Path('/tmp/kdlock-pipecap-run-2.py')
assert not program.exists()
shutil.copyfile(source,program)
assert hashlib.sha256(program.read_bytes()).digest()==hashlib.sha256(source.read_bytes()).digest()
command=[sys.executable,program,'--prepared',
 '/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2',
 '--output','/root/kdlock-evidence/10.176.26.71/bench/pipecap-causal-20261021/run-2',
 '--host-state','/tmp/kdlock-pipecap-host-before-4.json',
 '--source-commit','6c90e7adbae6e3e4ba19ff01c1803e6969b1fff7']
log=Path('/tmp/kdlock-pipecap-run-2-supervision.log')
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
 > /tmp/kdlock-pipecap-host-after-2.json
capture_status=$?
printf '{"supervisor_ssh_exit":%d,"host_capture_exit":%d}\n' "$run_status" "$capture_status" \
 > /tmp/kdlock-pipecap-launch-2-exit.json
if [ "$run_status" -ne 0 ]; then exit "$run_status"; fi
exit "$capture_status"
