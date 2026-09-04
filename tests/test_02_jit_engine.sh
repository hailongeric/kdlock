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

# --- Test 2: trigger exe_add after hot-lock promotion ---
# count_uaddr_cnt() ignores the first 1e9 TSC cycles after the first observed
# lock. Prime that timer before the real workload, otherwise this test can pass
# through the original spinlock path and never allocate an exe entry.
info "Priming hot-lock timer..."
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 0 >/dev/null 2>&1 || true
sleep 1

info "Running single-thread spinlock workload to trigger exe_add..."
run_with_timeout 20 "$BENCH_BIN" 1 12000 10 1 0 >/dev/null 2>&1 || true
sleep 0.5

check_dmesg_has "exe added" "kd_exe_add was not triggered" || exit 1
info "kd_exe_add triggered"

# --- Test 3: daemon reads kernel text, translates, and writes back ---
info "Starting daemon for translation..."
DAEMON_LOG="$(mktemp /tmp/kdlock-test02-daemon.XXXXXX.log)"
start_daemon 2

# The daemon polls /dev/kd_dev and translates the UNINIT entry created above.
# Do not run the same lock again after write-back here: that would execute the
# translated spinlock critical section and belongs in the spinlock integration
# tests, not this pipeline smoke test.
if ! asm_dir="$(wait_for_jit_artifacts 20)"; then
    fail "$TEST_NAME" "daemon did not produce complete JIT artifacts"
    exit 1
fi

check_daemon_read_kernel_text "$DAEMON_LOG" || exit 1
info "Daemon read kernel text for translation"

check_jit_artifacts "$asm_dir" || exit 1

check_dmesg_has "write to kernel" "daemon did not write JIT back" || exit 1
info "Daemon wrote JIT binary back to kernel"

stop_daemon
check_dmesg_ok || exit 1

pass "$TEST_NAME"
exit $EXIT_CODE
