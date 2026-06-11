#!/bin/bash
# test_03_hotlock.sh — verify hot-lock promotion state machine.
# The lock address must be hit 10000 times within the time window
# for count_uaddr_cnt to promote it to DELEGATE state.
TEST_NAME="test_03_hotlock"
source "$(dirname "$0")/common.sh"

build_all || exit 1
clear_dmesg
load_modules || exit 1

# --- Test 1: run enough iterations to trigger promotion ---
# 4 threads × 5000 loops = 20000 hits on the same lock address
# The hot-lock promotion requires 10000 hits within a time window.
info "Running workload to trigger hot-lock promotion..."
run_with_timeout 15 "$BENCH_BIN" 4 5000 10 1 0 >/dev/null 2>&1 || true
sleep 1

check_dmesg_has "begin delegate" "hot-lock promotion did not trigger" || exit 1
info "Hot-lock promoted to DELEGATE state"

# --- Test 2: verify no crash during promotion ---
check_dmesg_ok || exit 1
info "No kernel errors during promotion"

pass "$TEST_NAME"
exit $EXIT_CODE
