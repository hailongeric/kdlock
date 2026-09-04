#!/bin/bash
# test_06_daemon.sh — verify daemon translation pipeline end-to-end.
TEST_NAME="test_06_daemon"
source "$(dirname "$0")/common.sh"

build_all || exit 1
clear_dmesg
load_modules || exit 1

# --- Test 1: create an UNINIT exe entry for the daemon to translate ---
# Prime the hot-lock timer first; otherwise the short workload can stay on the
# original lock path.
info "Priming hot-lock timer..."
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 0 >/dev/null 2>&1 || true
sleep 1

run_with_timeout 20 "$BENCH_BIN" 1 12000 10 1 0 >/dev/null 2>&1 || true

check_dmesg_has "exe added" "kd_exe_add was not triggered" || exit 1

# --- Test 2: daemon starts and creates workspace ---
info "Starting daemon..."
DAEMON_LOG="$(mktemp /tmp/kdlock-test06-daemon.XXXXXX.log)"
start_daemon 2
if ! asm_dir="$(wait_for_jit_artifacts 20)"; then
    fail "$TEST_NAME" "daemon did not produce complete JIT artifacts"
    exit 1
fi

# Check daemon created workspace directories (0x... pattern)
if ls "$DAEMON_DIR"/0x* >/dev/null 2>&1; then
    info "Daemon created workspace directories"
else
    fail "$TEST_NAME" "daemon did not create workspace directories"
    exit 1
fi

# --- Test 3: JIT translation artifacts and write-back ---
check_daemon_read_kernel_text "$DAEMON_LOG" || exit 1
check_jit_artifacts "$asm_dir" || exit 1
check_dmesg_has "write to kernel" "daemon did not write JIT back" || exit 1
info "JIT binary written to kernel"

# --- Test 4: clean stop ---
stop_daemon
info "Daemon stopped cleanly"

# --- Test 5: workspace can be cleaned ---
rm -rf "$DAEMON_DIR"/0x* 2>/dev/null
if ! ls "$DAEMON_DIR"/0x* >/dev/null 2>&1; then
    info "Workspace cleaned"
else
    fail "$TEST_NAME" "workspace cleanup failed"
    exit 1
fi

check_dmesg_ok || exit 1

pass "$TEST_NAME"
exit $EXIT_CODE
