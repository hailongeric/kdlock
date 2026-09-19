#!/bin/bash
# Execute nested GS read/write/RMW/current probes through real spin/mutex JIT.
# One worker per origin CPU avoids overlapping probe storage outside the locks.
TEST_NAME="test_24_gs_jit"
source "$(dirname "$0")/../common.sh"

if [ "${KDLOCK_RECOVERY_CONFIRMED:-0}" != 1 ]; then
    fail "$TEST_NAME" "confirm a recoverable VM with KDLOCK_RECOVERY_CONFIRMED=1"
    exit 1
fi
mode="${1:-10}"
case "$mode" in
    10) kind=spin; lock_kind=1; expected_artifacts=2 ;;
    11) kind=mutex; lock_kind=2; expected_artifacts=1 ;;
    *) fail "$TEST_NAME" "use mode 10 (spin) or 11 (mutex)"; exit 1 ;;
esac
out="$(mktemp -d "/tmp/kdlock-gs-mode${mode}.XXXXXX")"
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"
cleanup() {
    local status=$?
    stop_daemon
    if ! pgrep -x klock_test >/dev/null; then
        unload_modules
    fi
    dmesg > "$out/dmesg.log"
    printf '%s\n' "$status" > "$out/exit-status"
}
trap cleanup EXIT

build_all
unload_modules
clear_dmesg
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1
insmod "$KLOCK_DIR/klock_module.ko"
start_daemon 2
run_with_timeout 10 taskset -c 0 "$BENCH_BIN" 1 1 1 1 "$mode" 0 > "$out/warmup.log"
run_with_timeout 30 taskset -c 0 "$BENCH_BIN" 1 12000 10 1 "$mode" 0 > "$out/promotion.log"
artifact_output=$(wait_for_jit_artifact_count "$expected_artifacts" 60)
mapfile -t asm_dirs <<< "$artifact_output"
check_daemon_read_kernel_text "$DAEMON_LOG"
for asm_dir in "${asm_dirs[@]}"; do
    check_jit_artifacts "$asm_dir"
    # Every published entry must include the probe, not just a native CALL exit.
    grep -q 'Stack_RGS' "$asm_dir/jit.S"
    grep -q 'Stack_RCT' "$asm_dir/jit.S"
    PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$asm_dir" "$lock_kind" <<'PY'
import json, sys
from mutex_signal_protocol import wait_ready
print(json.dumps(wait_ready(sys.argv[1], lock_kind=int(sys.argv[2]))))
PY
done > "$out/publication.log"
wait_for_jit_quiescence "$expected_artifacts" 30 2

# Separate origin CPUs are part of the busy-wait contract. The real mutex
# owner and any task needed for progress must be able to run on another CPU.
pids=()
for cpu in 0 1 2 3; do
    timeout --kill-after=5s 60s taskset -c "$cpu" "$BENCH_BIN" \
        1 32 1000000 1 "$mode" 0 > "$out/cpu-$cpu.log" 2>&1 &
    pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
    wait "$pid" || failed=1
done
test "$failed" = 0
stop_daemon
check_any_jit_entry_executed "${asm_dirs[@]}"
# Preserve generated instructions and binary hashes before the next session.
(cd "$KDLOCK_DIR" && find daemon -path 'daemon/0x*' -type f -print0 |
    tar --null -T - -czf "$out/artifacts.tar.gz")
unload_modules
check_dmesg_ok
check_dmesg_has "kd_gs $kind stats: attempts=12129 successes=12129 failures=0"
check_complex_cs_integrity 12129 1
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_not_has 'kd_native begin:'
if [ "$kind" = mutex ]; then
    check_mutex_origin_accounting
    success=$(get_dmesg_stat jit_success)
    test "${success:-0}" -gt 0
    check_dmesg_stat_equals jit_resume "$success"
    check_dmesg_stat_equals jit_failure 0
    check_dmesg_stat_equals frame_failure 0
    check_dmesg_stat_equals active_waiters 0
    check_dmesg_stat_equals reserved_nodes 0
else
    check_dmesg_has 'kd_spin lock stats:.*jit_success=[1-9]'
    check_dmesg_has 'kd_spin diag invariant_failures=0'
    check_dmesg_has 'kd_spin diag overflow=0'
    check_dmesg_not_has 'kd_spin lock stats:.*waiters=[1-9]'
fi
pass "$TEST_NAME mode=$mode GS read/write/RMW/current with real JIT"
