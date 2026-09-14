#!/bin/bash
# Private kdlock S and native callers must all exclude each other through L.
TEST_NAME=test_17_spin_native_protocol
source "$(dirname "$0")/common.sh"
if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 ]]; then
    fail "$TEST_NAME" "require recovery confirmation"
    exit 1
fi
if pgrep -x 'daemon|klock_test|kd_native' >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no active kdlock workers or modules"
    exit 1
fi
out=$(mktemp -d /tmp/kdlock-spin-native-protocol.XXXXXX)
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"
cleanup() {
    local status=$?
    trap - EXIT
    stop_daemon
    if pgrep -x 'klock_test|kd_native' >/dev/null; then
        fail "$TEST_NAME" "workers remain; retain code and use VM recovery"
        status=1
    else
        unload_modules
    fi
    dmesg > "$out/dmesg.log"
    (cd "$KDLOCK_DIR"
     find daemon -path 'daemon/0x*' -type f -print0 |
         tar --null -T - -czf "$out/artifacts.tar.gz")
    printf '%s\n' "$status" > "$out/exit-status"
    exit "$status"
}
trap cleanup EXIT
build_all
clear_dmesg
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=0
insmod "$KLOCK_DIR/klock_module.ko"
start_daemon 2
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 0 > "$out/warmup.log"
sleep 1
run_with_timeout 60 env KD_TEST_MIXED=1 "$BENCH_BIN" \
    8 100 1000 1 0 > "$out/before-promotion.log"
# This overlaps workloads, not a deterministic promotion/rename witness.
timeout --kill-after=5s 60s env KD_TEST_COMM=kd_native "$BENCH_BIN" \
    2 1000 10000 1 0 > "$out/during-promotion.log" 2>&1 &
native=$!
run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 0 > "$out/promotion.log"
wait "$native"
artifact=$(wait_for_jit_artifacts 30)
check_jit_artifacts "$artifact"
check_complex_cs_artifact "$artifact"
wait_for_jit_quiescence 1 20 2
run_with_timeout 90 env KD_TEST_MIXED=1 "$BENCH_BIN" \
    8 500 10000 1 0 > "$out/after-promotion.log"
stop_daemon
unload_modules || exit 1
check_dmesg_ok
check_dmesg_not_has 'WARNING:\|\[KD_JIT\]\[ERROR\]'
check_complex_cs_integrity 18801 1
check_any_jit_entry_executed "$artifact"
check_dmesg_has 'jit_success=[1-9][0-9]*'
check_dmesg_has 'kd_spin oracle: inside=0 overlaps=0 origin_missing=0 context_failures=0 irqsave=600 bh=600 trylock=600'
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_has 'kd_spin diag invariant_failures=0'
check_dmesg_has 'kd_spin diag overflow=0'
check_dmesg_stat_equals waiters 0
check_dmesg_not_has 'kd_native begin:'
pass "$TEST_NAME JIT=1 native-L/private-S"
