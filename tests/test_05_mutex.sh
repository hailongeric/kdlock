#!/bin/bash
# test_05_mutex.sh — verify mutex delegation protocol for modes 3, 4, 5.
# By default kdlock_km loads with mutex_jit=0, so this validates queueing,
# combiner handoff, fallback, and count management without executing the
# experimental mutex JIT sandbox. Key checks: no double fault, no soft lockup,
# count doesn't leak across runs.
TEST_NAME="test_05_mutex"
source "$(dirname "$0")/common.sh"

build_all || exit 1

run_mutex_mode() {
    local mode=$1
    local mode_name=$2
    local runs="${3:-1}"

    info "Testing mode $mode ($mode_name), $runs run(s)..."
    clear_dmesg
    load_modules || return 1
    start_daemon 2

    # count_uaddr_cnt() intentionally ignores the first 1e9 TSC cycles after
    # the first observed lock. Prime that timer, then wait before the real
    # workload; otherwise a short test can pass without entering kd_mutex.
    run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 "$mode" >/dev/null 2>&1 || {
        fail "$TEST_NAME" "mode $mode warmup failed"
        stop_daemon; unload_modules; return 1
    }
    sleep 1

    for i in $(seq 1 "$runs"); do
        info "  run $i/$runs..."
        # 4 * 5000 acquisitions exceed the 10000-hit promotion threshold and
        # leave enough operations to exercise the kd_mutex slowpath/handoff.
        run_with_timeout "$TIMEOUT_SEC" "$BENCH_BIN" 4 5000 10 1 "$mode" >/dev/null 2>&1
        local rc=$?
        if [ $rc -ne 0 ]; then
            fail "$TEST_NAME" "mode $mode run $i timed out or failed"
            stop_daemon; unload_modules; return 1
        fi
        sleep 1
    done

    stop_daemon

    check_dmesg_has "begin delegate" \
        "mode $mode never promoted its mutex to kdlock" || { unload_modules; return 1; }
    check_dmesg_has "exe added" \
        "mode $mode did not enter the kd_mutex execution path" || { unload_modules; return 1; }

    # Critical: no double fault or lockup
    check_dmesg_not_has "double fault" "double fault detected in mode $mode" || { unload_modules; return 1; }
    check_dmesg_not_has "soft lockup" "soft lockup detected in mode $mode" || { unload_modules; return 1; }
    check_dmesg_not_has "shadow stack ptr is NULL" "shadow stack corruption in mode $mode" || { unload_modules; return 1; }
    check_dmesg_ok || { unload_modules; return 1; }

    unload_modules

    check_dmesg_has "kd_mutex stats: slowpath=[1-9][0-9]*" \
        "mode $mode never entered the kd_mutex slowpath" || return 1
    check_dmesg_has "combiner=[1-9][0-9]*" \
        "mode $mode never elected a mutex combiner" || return 1
    check_dmesg_has "handoff=[1-9][0-9]*" \
        "mode $mode never handed a mutex to a waiter" || return 1
    info "  mode $mode: promotion, slowpath, combiner, and handoff verified"
    return 0
}

# --- Mode 3: contended single mutex ---
# Run TWICE to verify count doesn't leak between runs
run_mutex_mode 3 "mutex-contention" 2 || exit 1

# --- Mode 4: nested mutexes ---
run_mutex_mode 4 "mutex-nested" 1 || exit 1

# --- Mode 5: API call in mutex CS ---
run_mutex_mode 5 "mutex-api-in-lock" 1 || exit 1

pass "$TEST_NAME"
exit $EXIT_CODE
