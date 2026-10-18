#!/bin/bash
set -euo pipefail
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONDONTWRITEBYTECODE=1 LC_ALL=C
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=workloads-20261015T172603Z
export KD_WORKLOAD_OUT=/root/kdlock-evidence/10.176.26.71/bench/workloads-20261015T180603Z
set +e
unshare --mount --fork bash -se <<'KD_NAMESPACE'
set -euo pipefail
mount --make-rprivate /
mount --bind "$KD_WORKLOAD_OUT/source" /root/host_fs/kdlock
cd /root/host_fs/kdlock
python3 "$KD_WORKLOAD_OUT/driver.py"
KD_NAMESPACE
status=$?
printf '%s\n' "$status" > "$KD_WORKLOAD_OUT/exit-status.txt"
exit "$status"
