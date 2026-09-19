#!/bin/bash
# One fresh native-with-hooks/JIT session for paired_benchmark.py. This is not
# a daily regression: identical ordinary CS preparation/measurement parameters
# arrive through the existing runner's explicit, sanitized case environment.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "$ROOT" != /root/host_fs/kdlock ] || [ "$(id -u)" != 0 ] ||
   [ "${KDLOCK_RECOVERY_CONFIRMED:-}" != 1 ]; then
    printf '%s\n' 'Recovery guest root and explicit snapshot confirmation required' >&2
    exit 1
fi
case "${KD_BENCH_ARM:-}" in
    native) target=kd_unused ;;
    jit) target=klock_test ;;
    *) exit 1 ;;
esac
case "${KD_BENCH_JIT_TIMING:-0}" in
    0|1) jit_timing="${KD_BENCH_JIT_TIMING:-0}" ;;
    *) exit 1 ;;
esac
python3 -c 'import sys; sys.path.insert(0, "tests"); import regression; regression.check_idle()'
TEST_NAME=benchmark_arm
source "$(dirname "$0")/../common.sh"
out="$(mktemp -d /tmp/kdlock-benchmark-arm.XXXXXX)"
info "Evidence: $out"
build_all
clear_dmesg
# Keep each native/JIT pair under identical opt-in observation. The read-only
# parameter cannot be toggled while old invocations are still being counted.
load_modules "$target" mutex_jit=1 "jit_timing=$jit_timing"
# Both arms begin with a new provider/source session. Only drained generated
# workspaces may be removed; old images are not native-arm execution evidence.
rm -rf "$DAEMON_DIR"/0x*
python3 "$ROOT/tests/tools/paired_benchmark.py" arm init "$out"
DAEMON_LOG="$out/daemon.log"
if [ "$KD_BENCH_ARM" = jit ]; then
    # Observe translation separately from the prepared ioctl payload; this
    # does not turn daemon polling/settling time into code-generation time.
    start_daemon per-tgid --metrics
fi
python3 "$ROOT/tests/tools/paired_benchmark.py" arm warmup "$out"
# CPU admission requires frequency; do not expire the lock window by idling.
python3 "$ROOT/tests/tools/paired_benchmark.py" arm promotion "$out"
if [ "$KD_BENCH_ARM" = jit ]; then
    artifacts="$(wait_for_jit_artifact_count 1 30)"
    check_jit_artifacts "$artifacts"
    check_complex_cs_artifact "$artifacts"
    check_jit_hostcall_artifact "$artifacts" ktime_get
    check_jit_hostcall_artifact "$artifacts" int_sqrt
    check_daemon_read_kernel_text "$DAEMON_LOG"
    wait_for_jit_quiescence 1 20 2
    stop_daemon
fi
# Equal post-preparation settling, not a claim of identical cache/thermal state.
# Publication additionally requires zero active writer/frame counts.
sleep 2
python3 "$ROOT/tests/tools/paired_benchmark.py" arm before "$out"
dmesg > "$out/before.dmesg"
python3 "$ROOT/tests/tools/paired_benchmark.py" arm measure "$out"
dmesg > "$out/after.dmesg"
python3 "$ROOT/tests/tools/paired_benchmark.py" arm after "$out"
unload_modules
dmesg > "$out/final.log"
check_dmesg_ok
check_mutex_origin_accounting
check_dmesg_has 'kd_spin oracle: inside=0 overlaps=0 origin_missing=0 context_failures=0'
python3 "$ROOT/tests/tools/paired_benchmark.py" arm finish "$out"
