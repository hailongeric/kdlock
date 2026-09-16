#!/bin/bash
# test_07_mutex_jit.sh — opt-in repeated mutex JIT delegation and contention
# validation.
#
# Select this diagnostic explicitly (--case mode-3); daily mutex regression
# uses nested and hostcall cases. All live suites require recovery confirmation.
TEST_NAME="test_07_mutex_jit"
source "$(dirname "$0")/../common.sh"

JIT_ROUNDS="${KD_MUTEX_JIT_ROUNDS:-32}"
ROUND_THREADS=4
ROUND_LOOPS=1
ROUND_WORKLOAD="${KD_MUTEX_JIT_ROUND_WORKLOAD:-1000000}"
PINNED_THREADS=4
PINNED_LOOPS=1
PINNED_HOLDER_WORKLOAD="${KD_MUTEX_JIT_PINNED_HOLDER_WORKLOAD:-200000000}"
PINNED_WAITER_WORKLOAD="${KD_MUTEX_JIT_PINNED_WAITER_WORKLOAD:-1000000}"
STRESS_THREADS="${KD_MUTEX_JIT_STRESS_THREADS:-8}"
STRESS_LOOPS="${KD_MUTEX_JIT_STRESS_LOOPS:-100}"
STRESS_WORKLOAD="${KD_MUTEX_JIT_STRESS_WORKLOAD:-100000}"
MIN_JIT_SUCCESSES="${KD_MUTEX_JIT_MIN_SUCCESSES:-}"

for value in "$JIT_ROUNDS" "$ROUND_WORKLOAD" "$PINNED_HOLDER_WORKLOAD" \
             "$PINNED_WAITER_WORKLOAD" "$STRESS_THREADS" "$STRESS_LOOPS" \
             "$STRESS_WORKLOAD"; do
    case "$value" in
        ''|*[!0-9]*)
            fail "$TEST_NAME" "stress parameters must be non-negative integers"
            exit 1
            ;;
    esac
done
if [ "$JIT_ROUNDS" -lt 1 ] || [ "$ROUND_WORKLOAD" -lt 1 ] ||
   [ "$PINNED_HOLDER_WORKLOAD" -lt 1 ] ||
   [ "$PINNED_WAITER_WORKLOAD" -lt 1 ] ||
   [ "$STRESS_THREADS" -lt 2 ] || [ "$STRESS_LOOPS" -lt 1 ] ||
   [ "$STRESS_WORKLOAD" -lt 1 ]; then
    fail "$TEST_NAME" "stress rounds, threads, loops, and workloads must be positive"
    exit 1
fi
if [ -z "$MIN_JIT_SUCCESSES" ]; then
    MIN_JIT_SUCCESSES=$((JIT_ROUNDS / 2))
else
    case "$MIN_JIT_SUCCESSES" in
        *[!0-9]*)
            fail "$TEST_NAME" "minimum JIT successes must be an integer"
            exit 1
            ;;
    esac
fi
if [ "$MIN_JIT_SUCCESSES" -lt 1 ]; then
    MIN_JIT_SUCCESSES=1
fi

info "Building components..."
build_all || exit 1

clear_dmesg
unload_modules

sysctl -w kernel.randomize_va_space=0 >/dev/null 2>&1
sysctl -w kernel.numa_balancing=0 >/dev/null 2>&1
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1 || {
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

# Prime kd_hotlock_record's 1e9-cycle startup window.
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
check_complex_cs_artifact "$asm_dir" || exit 1
# Files precede device upload, and the final-chunk log precedes its copy. Wait
# for this exact mutex entry's published state before starting any JIT waiter.
# This uses the existing protocol observer, not a sleep or execution-proof proxy.
python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" ready \
    --artifact "$asm_dir" --output "${DAEMON_LOG%.log}.published.json" || {
    fail "$TEST_NAME" "mutex JIT entry was not published before workload"
    exit 1
}
check_dmesg_has "$JIT_INSTALL_PATTERN" "daemon did not install mutex JIT code" || exit 1
wait_for_jit_quiescence 1 20 2 || {
    fail "$TEST_NAME" "mutex translation did not become quiet"
    exit 1
}

# Recreate the deterministic owner/three-waiter topology repeatedly. One long
# critical section gives the remaining workers time to queue, exercising node
# reuse, completion publication, and post-unlock register resume on every round.
for ((round = 1; round <= JIT_ROUNDS; round++)); do
    run_with_timeout 20 "$BENCH_BIN" \
        "$ROUND_THREADS" "$ROUND_LOOPS" "$ROUND_WORKLOAD" 1 3 \
        >/dev/null 2>&1 || {
        fail "$TEST_NAME" "JIT delegation round $round failed"
        exit 1
    }
done

# The holder and each busy waiter have separate CPUs. A waiter no longer
# schedules to admit another target task on its origin CPU while delegated.
timeout --kill-after=5s 90s taskset -c 0 "$BENCH_BIN" \
    1 1 "$PINNED_HOLDER_WORKLOAD" 1 3 >/dev/null 2>&1 &
pinned_holder_pid=$!
sleep 0.1
pinned_waiters=()
for ((cpu = 1; cpu <= PINNED_THREADS; cpu++)); do
    timeout --kill-after=5s 90s taskset -c "$cpu" "$BENCH_BIN" \
        1 "$PINNED_LOOPS" "$PINNED_WAITER_WORKLOAD" 1 3 >/dev/null 2>&1 &
    pinned_waiters+=("$!")
done
pinned_failed=0
for pid in "${pinned_waiters[@]}"; do
    wait "$pid" || pinned_failed=1
done
if [ "$pinned_failed" != 0 ]; then
    wait "$pinned_holder_pid" || true
    fail "$TEST_NAME" "pinned busy-wait workload failed"
    exit 1
fi
if ! wait "$pinned_holder_pid"; then
    fail "$TEST_NAME" "pinned mutex holder failed"
    exit 1
fi

# Keep the same translated entry hot across repeated lock/unlock cycles. This
# catches queue corruption that isolated one-shot runs cannot expose.
run_with_timeout 90 "$BENCH_BIN" \
    "$STRESS_THREADS" "$STRESS_LOOPS" "$STRESS_WORKLOAD" 1 3 \
    >/dev/null 2>&1 || {
    fail "$TEST_NAME" "continuous JIT contention workload failed"
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

jit_success="$(get_dmesg_stat jit_success)"
jit_resume="$(get_dmesg_stat jit_resume)"
if [ -z "$jit_success" ] || [ "$jit_success" -lt "$MIN_JIT_SUCCESSES" ]; then
    fail "$TEST_NAME" \
        "expected at least $MIN_JIT_SUCCESSES JIT completions, got ${jit_success:-missing}"
    exit 1
fi
if [ "$jit_resume" != "$jit_success" ]; then
    fail "$TEST_NAME" \
        "completed/resumed waiter mismatch: success=$jit_success resume=${jit_resume:-missing}"
    exit 1
fi
check_dmesg_stat_equals "jit_not_ready" "0" \
    "JIT workload ran before translation was ready" || exit 1
check_dmesg_stat_equals "jit_failure" "0" \
    "translated mutex critical section failed" || exit 1
check_dmesg_stat_equals "frame_failure" "0" \
    "mutex JIT execution-frame invariant failed" || exit 1
check_dmesg_stat_equals "node_overflow" "0" \
    "mutex waiter node capacity was exhausted" || exit 1
check_dmesg_stat_equals "context_busy" "0" \
    "a foreign task encountered a live execution context" || exit 1
check_dmesg_stat_equals "nested_abort_release" "0" \
    "mode 3 unexpectedly used nested abort cleanup" || exit 1
check_dmesg_stat_equals "active_waiters" "0" \
    "mutex queue leaked active waiters" || exit 1
check_dmesg_stat_equals "reserved_nodes" "0" \
    "mutex queue leaked reserved waiter slots" || exit 1
check_dmesg_has "kd_exec invariant_failures=0" \
    "execution-frame invariant failed" || exit 1
check_jit_entry_executed "$asm_dir" || exit 1

expected_counter=$((1 + 12000 +
    JIT_ROUNDS * ROUND_THREADS * ROUND_LOOPS +
    1 + PINNED_THREADS * PINNED_LOOPS +
    STRESS_THREADS * STRESS_LOOPS))
actual_counter=$(dmesg | sed -n 's/.*final counter: \([0-9][0-9]*\).*/\1/p' | tail -n 1)
if [ "$actual_counter" != "$expected_counter" ]; then
    fail "$TEST_NAME" \
        "counter mismatch after JIT: expected $expected_counter, got ${actual_counter:-missing}"
    exit 1
fi
check_complex_cs_integrity "$expected_counter" 1 || exit 1
check_mutex_origin_accounting || exit 1

check_dmesg_ok || exit 1

info "JIT completions verified: $jit_success"
pass "$TEST_NAME"
exit "$EXIT_CODE"
