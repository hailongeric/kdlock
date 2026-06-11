#!/bin/bash
# test_02_jit_engine.sh — verify JIT engine initialization and daemon write-back.
TEST_NAME="test_02_jit_engine"
source "$(dirname "$0")/common.sh"

build_all || exit 1
clear_dmesg
load_modules || exit 1

# --- Test 1: end_point dynamic resolution ---
check_dmesg_has "end_point\[0\]" "end_point[0] not resolved" || exit 1
check_dmesg_has "end_point\[1\]" "end_point[1] (mutex_unlock) not resolved" || exit 1
info "end_point resolved for spin_unlock and mutex_unlock"

# --- Test 2: trigger exe_add via a short workload ---
info "Running short spinlock workload to trigger exe_add..."
run_with_timeout 10 "$BENCH_BIN" 2 100 10 1 0 >/dev/null 2>&1 || true
sleep 0.5

check_dmesg_has "exe added" "kd_exe_add was not triggered" || exit 1
info "kd_exe_add triggered"

# --- Test 3: daemon translates and writes back ---
info "Starting daemon for translation..."
start_daemon 2
sleep 3

# Run workload again so daemon picks up UNINIT entries
run_with_timeout 10 "$BENCH_BIN" 2 100 10 1 0 >/dev/null 2>&1 || true
sleep 3

check_dmesg_has "write to kernel" "daemon did not write JIT back" || exit 1
info "Daemon wrote JIT binary back to kernel"

stop_daemon
check_dmesg_ok || exit 1

pass "$TEST_NAME"
exit $EXIT_CODE
