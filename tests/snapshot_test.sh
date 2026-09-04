#!/bin/bash
# snapshot_test.sh — run integration tests with QEMU snapshot for fast recovery.
#
# This script creates a QEMU snapshot before loading modules, then runs
# the specified test. If the VM crashes, you can restore in ~2 seconds.
#
# Usage:
#   bash tests/snapshot_test.sh [test_mode]
#
# test_mode: 0-5 (default: 3 = mutex contention)
#
# Prerequisites:
#   - VM must be started with a qcow2 disk (not raw) to support snapshots
#   - QEMU monitor accessible via: socat - UNIX-CONNECT:/tmp/qemu-monitor.sock
#     OR via Ctrl-A + C in the serial console
#
# Recovery after crash:
#   From host: echo "loadvm pre_test" | socat - UNIX-CONNECT:/tmp/qemu-monitor.sock
#   Or in QEMU monitor (Ctrl-A C): loadvm pre_test

set -uo pipefail

KDLOCK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MONITOR_SOCK="/tmp/qemu-monitor.sock"
TEST_MODE="${1:-3}"
THREADS=4
LOOPS=1000
WORKLOAD=50
SYSCALLS=2
TIMEOUT=20

info() { echo "[snapshot_test] $1"; }
fail() { echo "[FAIL] $1"; }

send_monitor_cmd() {
    if [ -S "$MONITOR_SOCK" ]; then
        echo "$1" | socat - UNIX-CONNECT:"$MONITOR_SOCK" 2>/dev/null
        return $?
    else
        info "Monitor socket not found at $MONITOR_SOCK"
        info "To use snapshots, start QEMU with: -monitor unix:$MONITOR_SOCK,server,nowait"
        info "Or manually run in QEMU monitor: $1"
        return 1
    fi
}

# --- Step 1: Save snapshot ---
info "Saving VM snapshot 'pre_test'..."
if send_monitor_cmd "savevm pre_test"; then
    info "Snapshot saved. If the VM crashes, restore with:"
    info "  echo 'loadvm pre_test' | socat - UNIX-CONNECT:$MONITOR_SOCK"
else
    info "Could not save snapshot (monitor not connected)."
    info "Continuing without snapshot protection."
fi

# --- Step 2: Build ---
info "Building modules..."
cd "$KDLOCK_DIR"
make -C kernel_module -j"$(nproc)" >/dev/null 2>&1 || { fail "build failed"; exit 1; }
make -C klock_module -j"$(nproc)" >/dev/null 2>&1 || { fail "klock build failed"; exit 1; }
if [ ! -f bench/klock_test ]; then
    gcc -Iinclude bench/klock_test.c -o bench/klock_test -lpthread 2>/dev/null
fi

# --- Step 3: Load modules ---
info "Loading modules..."
dmesg -C
rmmod klock_module 2>/dev/null || true
rmmod kdlock_km 2>/dev/null || true
sleep 0.2
sysctl -w kernel.randomize_va_space=0 >/dev/null 2>&1
sysctl -w kernel.numa_balancing=0 >/dev/null 2>&1
insmod kernel_module/kdlock_km.ko target_process="klock_test" || { fail "insmod failed"; exit 1; }
insmod klock_module/klock_module.ko || { fail "insmod klock failed"; exit 1; }

# --- Step 4: Start daemon ---
info "Starting daemon..."
cd daemon
rm -rf 0x* 2>/dev/null || true
./daemon --mode 2 --quiet &
DAEMON_PID=$!
cd "$KDLOCK_DIR"
sleep 1

# --- Step 5: Run test with timeout ---
info "Running test mode $TEST_MODE ($THREADS threads, $LOOPS loops)..."
info "If the VM hangs for >${TIMEOUT}s, it will be killed."
timeout "$TIMEOUT" ./bench/klock_test "$THREADS" "$LOOPS" "$WORKLOAD" "$SYSCALLS" "$TEST_MODE" >/dev/null 2>&1
RC=$?

# --- Step 6: Stop daemon ---
kill "$DAEMON_PID" 2>/dev/null; wait "$DAEMON_PID" 2>/dev/null || true

# --- Step 7: Check result ---
if [ $RC -eq 124 ]; then
    fail "Test timed out! VM may be hung."
    info "Check dmesg for errors:"
    dmesg | grep -i "BUG:\|panic\|double fault\|lockup" | tail -5
    info ""
    info "To restore: echo 'loadvm pre_test' | socat - UNIX-CONNECT:$MONITOR_SOCK"
    exit 1
elif [ $RC -ne 0 ]; then
    fail "Test exited with code $RC"
    dmesg | tail -10
    exit 1
fi

# --- Step 8: Verify dmesg ---
if dmesg | grep -i "BUG:\|panic\|double fault\|soft lockup" >/dev/null; then
    fail "Kernel errors detected!"
    dmesg | grep -i "BUG:\|panic\|double fault\|soft lockup" | tail -5
    exit 1
fi

# --- Step 9: Unload ---
rmmod klock_module 2>/dev/null
rmmod kdlock_km 2>/dev/null

# --- Step 10: Report ---
info "═══════════════════════════════"
info "[PASS] mode $TEST_MODE completed without errors"
if dmesg | grep "delegation ok" >/dev/null; then
    count=$(dmesg | grep -c "delegation ok")
    info "Delegation succeeded $count times"
fi
info "═══════════════════════════════"

# Delete snapshot on success (optional)
# send_monitor_cmd "delvm pre_test"
