#!/bin/bash
# test_05_mutex.sh - mutex_jit=0 must use Linux mutexes even after promotion.
TEST_NAME="test_05_mutex"
source "$(dirname "$0")/common.sh"

build_all || exit 1

run_mutex_mode() {
    local mode=$1
    local mode_name=$2
    local runs="${3:-1}"
    local expected_operations=$((1 + runs * 4 * 5000))

    info "Testing mode $mode ($mode_name), $runs run(s)..."
    clear_dmesg
    load_modules || return 1
    start_daemon 2

    # kd_hotlock_record() intentionally ignores the first 1e9 TSC cycles after
    # the first observed lock. Prime that timer, then wait before the real
    # workload; the workload must cross promotion while staying on the native path.
    run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 "$mode" >/dev/null 2>&1 || {
        fail "$TEST_NAME" "mode $mode warmup failed"
        stop_daemon; unload_modules; return 1
    }
    sleep 1

    for i in $(seq 1 "$runs"); do
        info "  run $i/$runs..."
        # 4 * 5000 acquisitions exceed the 10000-hit promotion threshold and
        # leave enough operations to verify native execution after promotion.
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
    # Critical: no double fault or lockup
    check_dmesg_not_has "double fault" "double fault detected in mode $mode" || { unload_modules; return 1; }
    check_dmesg_not_has "soft lockup" "soft lockup detected in mode $mode" || { unload_modules; return 1; }
    check_dmesg_not_has "shadow stack ptr is NULL" "shadow stack corruption in mode $mode" || { unload_modules; return 1; }
    check_dmesg_ok || { unload_modules; return 1; }

    unload_modules

    check_complex_cs_integrity "$expected_operations" 1 || return 1

    check_dmesg_stat_equals slowpath 0 || return 1
    check_dmesg_stat_equals jit_success 0 || return 1
    check_mutex_origin_accounting || return 1
    info "  mode $mode: promoted locks still use native mutexes with JIT disabled"
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
exit "$EXIT_CODE"
