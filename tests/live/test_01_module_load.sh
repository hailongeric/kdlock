#!/bin/bash
# Current provider/device lifecycle only. Actual JIT is verified by the direct
# runner; loading the retired transparent-hook workload would not prove it.
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ "$PWD" == /root/host_fs/kdlock && "$EUID" == 0 ]]
[[ "${KDLOCK_RECOVERY_CONFIRMED:-}" == 1 ]]
python3 - <<'PY'
import sys
sys.path.insert(0, 'bench/spin_cacheline')
import bench_runtime
bench_runtime.idle()
PY
timeout 120 python3 bench/spin_cacheline/kernel_identity.py
# Default SELFTEST=0 and unchanged kernel; KDIR is the verified build above.
timeout 120 make -C kernel_module KDIR=/root/linux-6.1.159-kdclobber2 W=1 KDLOCK_SELFTEST=0
loaded=0
cleanup() {
    if (( loaded )); then
        # Preserve the module and evidence if retirement cannot finish.
        timeout 20 python3 disassem/device_session.py retire && timeout 20 rmmod kdlock_km
    fi
}
trap cleanup EXIT
timeout 20 insmod kernel_module/kdlock_km.ko
loaded=1
[[ -c /dev/kd_dev ]]
timeout 20 python3 disassem/device_session.py capabilities
timeout 20 python3 disassem/device_session.py status
cleanup
loaded=0
[[ ! -e /dev/kd_dev && ! -e /sys/module/kdlock_km ]]
echo 'PASS: current provider/device lifecycle (JIT=0)'
