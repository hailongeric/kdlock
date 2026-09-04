#!/bin/bash
# test_03_hotlock.sh — verify hot-lock promotion state machine.
# The lock address must be hit 10000 times within the time window
# for kd_hotlock_record() to promote it to DELEGATE state.
TEST_NAME="test_03_hotlock"
source "$(dirname "$0")/common.sh"

build_all || exit 1
clear_dmesg
load_modules || exit 1

# --- Test 1: run enough iterations to trigger promotion ---
# 1 thread × 12000 loops = 12000 hits on the same lock address
# The hot-lock promotion requires 10000 hits within a time window.
# kd_hotlock_record() ignores the first 1e9 TSC cycles after the first observed
# lock, so prime that timer and wait before the real workload.
info "Priming hot-lock timer..."
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 0 >/dev/null 2>&1 || true
sleep 1

info "Running workload to trigger hot-lock promotion..."
run_with_timeout 20 "$BENCH_BIN" 1 12000 10 1 0 >/dev/null 2>&1 || true
sleep 1

check_dmesg_has "begin delegate" "hot-lock promotion did not trigger" || exit 1
info "Hot-lock promoted to DELEGATE state"

# --- Test 2: verify no crash during promotion ---
check_dmesg_ok || exit 1
info "No kernel errors during promotion"

pass "$TEST_NAME"
exit "$EXIT_CODE"
