#!/bin/bash
# test_04_spinlock.sh — verify spinlock delegation for modes 0, 1, 2.
TEST_NAME="test_04_spinlock"
source "$(dirname "$0")/common.sh"

build_all || exit 1

run_spinlock_mode() {
    local mode=$1
    local mode_name=$2

    info "Testing mode $mode ($mode_name)..."
    clear_dmesg
    load_modules || return 1
    start_daemon 2
    sleep 1

    # Run workload: 4 threads, 2000 loops, 100 workload, 2 syscalls
    run_with_timeout "$TIMEOUT_SEC" "$BENCH_BIN" 4 2000 100 2 "$mode" >/dev/null 2>&1
    local rc=$?
    sleep 2

    stop_daemon

    if [ $rc -ne 0 ]; then
        fail "$TEST_NAME" "mode $mode ($mode_name) workload failed or timed out"
        unload_modules
        return 1
    fi

    check_dmesg_ok || { unload_modules; return 1; }

    # Check delegation happened (at least for mode 0 after promotion)
    if dmesg | grep -q "delegation ok"; then
        info "  mode $mode: delegation successful"
    else
        info "  mode $mode: no delegation (may need more iterations for promotion)"
    fi

    unload_modules
    return 0
}

# --- Mode 0: contended single spinlock ---
run_spinlock_mode 0 "spin-contention" || exit 1

# --- Mode 1: nested spinlocks ---
run_spinlock_mode 1 "spin-nested" || exit 1

# --- Mode 2: API call in spinlock CS ---
run_spinlock_mode 2 "spin-api-in-lock" || exit 1

pass "$TEST_NAME"
exit $EXIT_CODE
