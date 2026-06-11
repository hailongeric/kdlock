#!/bin/bash
# common.sh — shared utilities for kdlock test scripts.
# Source this file from each test: source "$(dirname "$0")/common.sh"

set -euo pipefail

KDLOCK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KM_DIR="$KDLOCK_DIR/kernel_module"
KLOCK_DIR="$KDLOCK_DIR/klock_module"
DAEMON_DIR="$KDLOCK_DIR/daemon"
BENCH_DIR="$KDLOCK_DIR/bench"
BENCH_BIN="$BENCH_DIR/klock_test"

TARGET_PROCESS="klock_test"
TIMEOUT_SEC=30

# --- Output helpers ---

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1: $2"; EXIT_CODE=1; }
info() { echo "  [INFO] $1"; }

EXIT_CODE=0

# --- Build ---

build_all() {
    make -C "$KM_DIR" -j"$(nproc)" >/dev/null 2>&1 || { fail "$TEST_NAME" "kernel module build failed"; return 1; }
    make -C "$KLOCK_DIR" -j"$(nproc)" >/dev/null 2>&1 || { fail "$TEST_NAME" "klock_module build failed"; return 1; }
    make -C "$DAEMON_DIR" >/dev/null 2>&1 || true
    if [ ! -f "$BENCH_BIN" ]; then
        gcc -Iinclude "$BENCH_DIR/klock_test.c" -o "$BENCH_BIN" -lpthread 2>/dev/null || true
    fi
}

# --- Module management ---

load_modules() {
    local target="${1:-$TARGET_PROCESS}"
    rmmod klock_module 2>/dev/null || true
    rmmod kdlock_km 2>/dev/null || true
    sleep 0.2

    sysctl -w kernel.randomize_va_space=0 >/dev/null 2>&1
    sysctl -w kernel.numa_balancing=0 >/dev/null 2>&1

    insmod "$KM_DIR/kdlock_km.ko" target_process="$target" || { fail "$TEST_NAME" "insmod kdlock_km failed"; return 1; }
    insmod "$KLOCK_DIR/klock_module.ko" || { fail "$TEST_NAME" "insmod klock_module failed"; return 1; }
}

unload_modules() {
    rmmod klock_module 2>/dev/null || true
    sleep 0.1
    rmmod kdlock_km 2>/dev/null || true
    sleep 0.1
}

# --- Daemon management ---

start_daemon() {
    local mode="${1:-2}"
    cd "$DAEMON_DIR"
    rm -rf 0x* 2>/dev/null || true
    ./daemon --mode "$mode" --quiet &
    DAEMON_PID=$!
    cd "$KDLOCK_DIR"
    sleep 0.5
}

stop_daemon() {
    if [ -n "${DAEMON_PID:-}" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        kill "$DAEMON_PID" 2>/dev/null || true
        wait "$DAEMON_PID" 2>/dev/null || true
    fi
    DAEMON_PID=""
}

# --- Run with timeout ---

run_with_timeout() {
    local timeout="${1:-$TIMEOUT_SEC}"
    shift
    timeout "$timeout" "$@"
    local rc=$?
    if [ $rc -eq 124 ]; then
        fail "$TEST_NAME" "command timed out after ${timeout}s: $*"
        return 1
    fi
    return $rc
}

# --- dmesg checks ---

clear_dmesg() {
    dmesg -C
}

check_dmesg_ok() {
    local bad
    bad=$(dmesg | grep -ci "BUG:\|panic\|double fault\|soft lockup\|unable to handle" || true)
    if [ "$bad" -gt 0 ]; then
        fail "$TEST_NAME" "dmesg contains errors:"
        dmesg | grep -i "BUG:\|panic\|double fault\|soft lockup\|unable to handle" | tail -5
        return 1
    fi
    return 0
}

check_dmesg_has() {
    local pattern="$1"
    local msg="${2:-expected pattern '$pattern' in dmesg}"
    if ! dmesg | grep -q "$pattern"; then
        fail "$TEST_NAME" "$msg"
        return 1
    fi
    return 0
}

check_dmesg_not_has() {
    local pattern="$1"
    local msg="${2:-unexpected pattern '$pattern' in dmesg}"
    if dmesg | grep -q "$pattern"; then
        fail "$TEST_NAME" "$msg"
        dmesg | grep "$pattern" | tail -3
        return 1
    fi
    return 0
}

# --- Cleanup trap ---

cleanup() {
    stop_daemon
    unload_modules
}
trap cleanup EXIT
