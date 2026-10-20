#!/bin/sh
# Source-host orchestration. The bounded VM supervisor never kills a timed-out
# caller. Capture the host endpoint immediately, even if the diagnostic fails.
set -u
cd /home/eric/vm/vm-shared/kdlock || exit 1
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 2222 root@10.176.26.71 \
  'cd /root/host_fs/kdlock && PATH=/root/kdlock-translation-venv-20261019/bin:$PATH PYTHONDONTWRITEBYTECODE=1 LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z python3 -u -' \
  > /tmp/kdlock-latency-run-1-console.log 2>&1 <<'PY'
import hashlib, json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'bench/spin_cacheline'))
import bench_runtime as rt
base = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-latency-20261021')
inputs = base/'inputs-3/inputs.json'
state = json.loads((inputs.parent/'state.json').read_text())
digest = hashlib.sha256(inputs.read_bytes()).hexdigest()
assert state['complete'] and state['idle'] and state['manifest_sha256'] == digest
program = Path('/tmp/kdlock-latency-run-1.py')
assert not program.exists()
shutil.copyfile(inputs.parent/'tools/latency_run.py', program)
command = [sys.executable, program, '--inputs', inputs, '--inputs-sha256', digest,
           '--output', base/'run-1', '--host-state', '/tmp/kdlock-latency-host-before-3.json',
           '--source-commit', '0cc479beb2c4ecb5b755d9881ca5a340fb58424a',
           '--budget-seconds', '3600']
# Keep this open supervisor log outside the evidence base inspected for writers.
log = Path('/tmp/kdlock-latency-run-1-supervision.log')
try:
    print(rt.command(command, log, timeout=3900), end='', flush=True)
except BaseException:
    print(log.read_text(), end='', flush=True)
    raise
PY
run_status=$?
ssh -o BatchMode=yes -o ConnectTimeout=10 eric@10.176.26.71 \
  'timeout 30 sudo -n python3 -' \
  < bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py \
  > /tmp/kdlock-latency-host-after-1.json
capture_status=$?
printf '{"supervisor_ssh_exit":%d,"host_capture_exit":%d}\n' "$run_status" "$capture_status" \
  > /tmp/kdlock-latency-launch-1-exit.json
if [ "$run_status" -ne 0 ]; then
  exit "$run_status"
fi
exit "$capture_status"
