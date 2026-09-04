#!/bin/bash
# test_07a_mutex_jit_smoke.sh — opt-in smoke confirmation of one real mutex
# JIT sandbox completion.
#
# This stays out of run_all.sh. It loads mutex_jit=1, forces a single
# translation, then runs one bounded 4-thread contention pass to confirm a
# single sandbox completion and exact counter accounting.
TEST_NAME="test_07a_mutex_jit_smoke"
source "$(dirname "$0")/common.sh"

SMOKE_THREADS=4
SMOKE_LOOPS=1
SMOKE_WORKLOAD=1000000

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

DAEMON_LOG="$(mktemp /tmp/kdlock-test07a-daemon.XXXXXX.log)"
start_daemon 2

# Prime the hot-lock timer, then force translation without contention.
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 3 >/dev/null 2>&1 || {
    fail "$TEST_NAME" "warmup failed"
    exit 1
}
sleep 1
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
check_complex_cs_artifact "$asm_dir" || exit 1
check_dmesg_has "$JIT_INSTALL_PATTERN" "daemon did not install mutex JIT code" || exit 1

# The benchmark start barrier releases all workers together. A long single CS
# keeps the owner active until three waiters queue, which gives the combiner
# exactly one waiter with a successor to execute through the sandbox.
run_with_timeout 20 "$BENCH_BIN" \
    "$SMOKE_THREADS" "$SMOKE_LOOPS" "$SMOKE_WORKLOAD" 1 3 \
    >/dev/null 2>&1 || {
    fail "$TEST_NAME" "smoke contention workload failed"
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

check_dmesg_stat_equals "jit_success" "1" \
    "smoke test should complete exactly one mutex sandbox" || exit 1

expected_counter=$((1 + 12000 + SMOKE_THREADS * SMOKE_LOOPS))
actual_counter="$(dmesg | sed -n 's/.*final counter: \([0-9][0-9]*\).*/\1/p' | tail -n 1)"
if [ "$actual_counter" != "$expected_counter" ]; then
    fail "$TEST_NAME" \
        "counter mismatch after smoke test: expected $expected_counter, got ${actual_counter:-missing}"
    exit 1
fi
check_complex_cs_integrity "$expected_counter" 1 || exit 1

check_dmesg_ok || exit 1

pass "$TEST_NAME"
exit "$EXIT_CODE"
