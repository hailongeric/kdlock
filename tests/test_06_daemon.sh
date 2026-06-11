#!/bin/bash
# test_06_daemon.sh — verify daemon translation pipeline end-to-end.
TEST_NAME="test_06_daemon"
source "$(dirname "$0")/common.sh"

build_all || exit 1
clear_dmesg
load_modules || exit 1

# --- Test 1: daemon starts and creates workspace ---
info "Starting daemon..."
start_daemon 2
sleep 1

# Trigger exe_add so daemon has something to translate
run_with_timeout 10 "$BENCH_BIN" 2 500 10 1 0 >/dev/null 2>&1 || true
sleep 3

# Check daemon created workspace directories (0x... pattern)
if ls "$DAEMON_DIR"/0x* >/dev/null 2>&1; then
    info "Daemon created workspace directories"
else
    fail "$TEST_NAME" "daemon did not create workspace directories"
    exit 1
fi

# --- Test 2: JIT binary written back ---
check_dmesg_has "write to kernel" "daemon did not write JIT back" || exit 1
info "JIT binary written to kernel"

# --- Test 3: clean stop ---
stop_daemon
info "Daemon stopped cleanly"

# --- Test 4: workspace can be cleaned ---
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
