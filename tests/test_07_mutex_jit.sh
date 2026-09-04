#!/bin/bash
# test_07_mutex_jit.sh — opt-in bounded confirmation of mutex JIT sandbox
# execution.
#
# This is intentionally excluded from run_all.sh because mutex_jit=1 executes
# translated kernel critical sections and can crash the guest while under
# development.
TEST_NAME="test_07_mutex_jit"
source "$(dirname "$0")/common.sh"

info "Building components..."
build_all || exit 1

clear_dmesg
unload_modules

sysctl -w kernel.randomize_va_space=0 >/dev/null 2>&1
sysctl -w kernel.numa_balancing=0 >/dev/null 2>&1
insmod "$KM_DIR/kdlock_km.ko" target_process="$TARGET_PROCESS" mutex_jit=1 || {
    fail "$TEST_NAME" "insmod kdlock_km with mutex_jit=1 failed"
    exit 1
}
insmod "$KLOCK_DIR/klock_module.ko" || {
    fail "$TEST_NAME" "insmod klock_module failed"
    exit 1
}

if [ "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" != "1" ]; then
    fail "$TEST_NAME" "mutex_jit module parameter is not enabled"
    exit 1
fi

DAEMON_LOG="$(mktemp /tmp/kdlock-test07-daemon.XXXXXX.log)"
start_daemon 2

# Prime count_uaddr_cnt's 1e9-cycle startup window.
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 3 >/dev/null 2>&1 || {
    fail "$TEST_NAME" "warmup failed"
    exit 1
}
sleep 1

# Promote and translate the mutex without contention, so no waiter executes
# JIT code before the daemon has written a complete sandbox back.
run_with_timeout 20 "$BENCH_BIN" 1 12000 10 1 3 >/dev/null 2>&1 || {
    fail "$TEST_NAME" "promotion workload failed"
    exit 1
}

check_dmesg_has "begin delegate" "mutex was not promoted" || exit 1
if ! asm_dir="$(wait_for_jit_artifacts 20)"; then
    fail "$TEST_NAME" "daemon did not produce complete mutex JIT artifacts"
    exit 1
fi
check_daemon_read_kernel_text "$DAEMON_LOG" || exit 1
check_jit_artifacts "$asm_dir" || exit 1
check_dmesg_has "write to kernel" "daemon did not install mutex JIT code" || exit 1

# Now introduce a bounded amount of contention. A passing run must contain an
# actual KD_EXE_RUN_TO_UNLOCK completion, not merely a successful translation.
run_with_timeout 20 "$BENCH_BIN" 4 500 1000 1 3 >/dev/null 2>&1 || {
    fail "$TEST_NAME" "JIT contention workload failed"
    exit 1
}
sleep 1
stop_daemon

check_dmesg_has "mutex JIT delegation ok" \
    "sandbox never completed a mutex critical section" || exit 1
check_dmesg_ok || exit 1
check_dmesg_not_has "unexpected locked state" \
    "mutex state became inconsistent after JIT execution" || exit 1

unload_modules

check_dmesg_has "jit_success=[1-9][0-9]*" \
    "mutex JIT success counter remained zero" || exit 1

expected_counter=$((1 + 12000 + 4 * 500))
actual_counter=$(dmesg | sed -n 's/.*final counter: \([0-9][0-9]*\).*/\1/p' | tail -n 1)
if [ "$actual_counter" != "$expected_counter" ]; then
    fail "$TEST_NAME" \
        "counter mismatch after JIT: expected $expected_counter, got ${actual_counter:-missing}"
    exit 1
fi

check_dmesg_ok || exit 1

pass "$TEST_NAME"
exit $EXIT_CODE
