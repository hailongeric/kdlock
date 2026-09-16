#!/bin/bash
# Original and delegated callers must contend on the same Linux mutex.
TEST_NAME=test_11_mutex_native_protocol
source "$(dirname "$0")/../common.sh"
jit="${1:-1}"
if [[ "$jit" != 0 && "$jit" != 1 ]]; then
    fail "$TEST_NAME" "usage: $0 [0|1]"
    exit 1
fi
if [[ "$jit" = 1 && "${KDLOCK_RECOVERY_CONFIRMED:-0}" != 1 ]]; then
    fail "$TEST_NAME" "set KDLOCK_RECOVERY_CONFIRMED=1 in a recovery VM"
    exit 1
fi
out="$(mktemp -d /tmp/kdlock-native-protocol.XXXXXX)"
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
    if [[ "$jit" = 1 ]]; then
        (cd "$KDLOCK_DIR"
         find daemon -path 'daemon/0x*' -type f -print0 |
             tar --null -T - -czf "$out/artifacts.tar.gz")
    fi
}
trap cleanup EXIT
build_all
unload_modules
clear_dmesg
load_kdlock target_process="$TARGET_PROCESS" mutex_jit="$jit"
insmod "$KLOCK_DIR/klock_module.ko"
if [[ "$jit" = 1 ]]; then
    start_daemon 2
fi
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 3 > "$out/warmup.log"
sleep 1
run_with_timeout 60 env KD_TEST_MIXED=1 "$BENCH_BIN" \
    8 100 1000 1 3 > "$out/before-promotion.log"
# Keep non-target callers active while target acquisitions cross promotion.
timeout --kill-after=5s 60s env KD_TEST_COMM=kd_native "$BENCH_BIN" \
    2 1000 10000 1 3 > "$out/during-promotion.log" 2>&1 &
native=$!
run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 3 > "$out/promotion.log"
wait "$native"
if [[ "$jit" = 1 ]]; then
    artifact="$(wait_for_jit_artifacts 30)"
    check_jit_artifacts "$artifact"
    wait_for_jit_quiescence 1 20 2
    printf '1\n' > /sys/module/kdlock_km/parameters/mutex_task_fail_once
fi
run_with_timeout 90 env KD_TEST_MIXED=1 "$BENCH_BIN" \
    8 500 10000 1 3 > "$out/after-promotion.log"

# Eight target waiters share four slots. Unqueued overflow callers must still
# acquire the original mutex, and their task records must not leak.
timeout --kill-after=5s 60s taskset -c 0 "$BENCH_BIN" \
    1 1 200000000 1 3 > "$out/holder.log" 2>&1 &
holder=$!
sleep 0.1
run_with_timeout 60 taskset -c 1 "$BENCH_BIN" \
    8 1 1000000 1 3 > "$out/oversubscribed.log"
wait "$holder"
stop_daemon
unload_modules
check_dmesg_ok
check_complex_cs_integrity 18810 1
check_mutex_origin_accounting "$jit"
if [[ "$jit" = 1 ]]; then
    check_any_jit_entry_executed "$artifact"
    check_dmesg_has 'jit_success=[1-9][0-9]*'
    check_dmesg_has 'node_overflow=[1-9][0-9]*'
else
    check_dmesg_stat_equals jit_success 0
fi
check_dmesg_stat_equals active_waiters 0
check_dmesg_stat_equals reserved_nodes 0
check_dmesg_stat_equals frame_failure 0
pass "$TEST_NAME mutex_jit=$jit"
