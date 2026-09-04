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
    gcc -I"$KDLOCK_DIR/include" "$BENCH_DIR/klock_test.c" \
        -o "$BENCH_BIN" -lpthread 2>/dev/null || {
        fail "$TEST_NAME" "benchmark build failed"
        return 1
    }
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
    if [ -n "${DAEMON_LOG:-}" ]; then
        setsid ./daemon --mode "$mode" --quiet >"$DAEMON_LOG" 2>&1 &
    else
        setsid ./daemon --mode "$mode" --quiet &
    fi
    DAEMON_PID=$!
    cd "$KDLOCK_DIR"
    sleep 0.5
}

stop_daemon() {
    if [ -n "${DAEMON_PID:-}" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        kill -- "-$DAEMON_PID" 2>/dev/null || kill "$DAEMON_PID" 2>/dev/null || true
        wait "$DAEMON_PID" 2>/dev/null || true
    fi
    DAEMON_PID=""
}

# --- Run with timeout ---

run_with_timeout() {
    local timeout="${1:-$TIMEOUT_SEC}"
    shift
    timeout --kill-after=5s "$timeout" "$@"
    local rc=$?
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
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

get_dmesg_stat() {
    local key="$1"

    dmesg | sed -n "s/.*${key}=\\([0-9][0-9]*\\).*/\\1/p" | tail -n 1
}

check_dmesg_stat_equals() {
    local key="$1"
    local expected="$2"
    local msg="${3:-expected ${key}=${expected}}"
    local actual

    actual="$(get_dmesg_stat "$key")"
    if [ "$actual" != "$expected" ]; then
        fail "$TEST_NAME" "$msg (got ${actual:-missing})"
        return 1
    fi
    return 0
}

# --- JIT translation artifact checks ---

find_jit_asm_dir() {
    find "$DAEMON_DIR" -mindepth 3 -maxdepth 3 -type d -name asm 2>/dev/null | sort | head -n 1
}

wait_for_jit_artifacts() {
    local timeout="${1:-20}"
    local deadline=$((SECONDS + timeout))
    local asm_dir

    while [ "$SECONDS" -lt "$deadline" ]; do
        asm_dir="$(find_jit_asm_dir || true)"
        if [ -n "$asm_dir" ] &&
           [ -s "$asm_dir/jit.S" ] &&
           [ -s "$asm_dir/jit.bin" ] &&
           [ -s "$asm_dir/bin.txt" ]; then
            printf '%s\n' "$asm_dir"
            return 0
        fi
        sleep 0.2
    done
    return 1
}

wait_for_jit_artifact_count() {
    local expected="$1"
    local timeout="${2:-30}"
    local deadline=$((SECONDS + timeout))
    local complete asm_dir
    local -a asm_dirs

    while [ "$SECONDS" -lt "$deadline" ]; do
        mapfile -t asm_dirs < <(
            find "$DAEMON_DIR" -mindepth 3 -maxdepth 3 -type d -name asm \
                2>/dev/null | sort
        )
        if [ "${#asm_dirs[@]}" -ge "$expected" ]; then
            complete=1
            for asm_dir in "${asm_dirs[@]}"; do
                if [ ! -s "$asm_dir/jit.S" ] ||
                   [ ! -s "$asm_dir/jit.bin" ] ||
                   [ ! -s "$asm_dir/bin.txt" ]; then
                    complete=0
                    break
                fi
            done
            if [ "$complete" -eq 1 ]; then
                printf '%s\n' "${asm_dirs[@]}"
                return 0
            fi
        fi
        sleep 0.2
    done
    return 1
}

wait_for_jit_quiescence() {
    local min_artifacts="$1"
    local timeout="${2:-30}"
    local quiet="${3:-2}"
    local deadline=$((SECONDS + timeout))
    local stable_since=0
    local last_writes=""
    local writes artifacts

    while [ "$SECONDS" -lt "$deadline" ]; do
        writes="$(dmesg | grep -c "write to kernel" || true)"
        artifacts="$(find "$DAEMON_DIR" -mindepth 4 -maxdepth 4 -type f \
            -name jit.bin -size +127c 2>/dev/null | wc -l)"
        if [ "$artifacts" -ge "$min_artifacts" ]; then
            if [ "$writes" = "$last_writes" ]; then
                if [ "$stable_since" -eq 0 ]; then
                    stable_since=$SECONDS
                elif [ $((SECONDS - stable_since)) -ge "$quiet" ]; then
                    return 0
                fi
            else
                last_writes="$writes"
                stable_since=0
            fi
        fi
        sleep 0.2
    done
    return 1
}

check_daemon_read_kernel_text() {
    local log_file="$1"

    if [ ! -s "$log_file" ]; then
        fail "$TEST_NAME" "daemon log is missing or empty"
        return 1
    fi
    if ! grep -q "Targets: \\['0x" "$log_file"; then
        fail "$TEST_NAME" "daemon did not log translation targets"
        return 1
    fi
    if ! grep -Eq "^\\['0x[0-9a-f]+" "$log_file"; then
        fail "$TEST_NAME" "daemon did not log bytes read from kernel text"
        return 1
    fi
    return 0
}

check_jit_artifacts() {
    local asm_dir="$1"
    local tgid_dir rip_dir entry bin_size

    if [ -z "$asm_dir" ] || [ ! -d "$asm_dir" ]; then
        fail "$TEST_NAME" "JIT asm workspace not found"
        return 1
    fi

    tgid_dir="$(dirname "$asm_dir")"
    rip_dir="$(basename "$(dirname "$tgid_dir")")"
    entry="${rip_dir#0x}"

    if [ "$entry" = "$rip_dir" ] || [ -z "$entry" ]; then
        fail "$TEST_NAME" "cannot derive entry RIP from workspace $asm_dir"
        return 1
    fi
    if ! [ -s "$asm_dir/jit.S" ] ||
       ! [ -s "$asm_dir/jit.bin" ] ||
       ! [ -s "$asm_dir/bin.txt" ]; then
        fail "$TEST_NAME" "JIT workspace is missing jit.S, jit.bin, or bin.txt"
        return 1
    fi

    if ! grep -Eq "J(MP|Z)[[:space:]]+loc_${entry}\\b" "$asm_dir/jit.S"; then
        fail "$TEST_NAME" "jit.S does not dispatch to entry label loc_${entry}"
        return 1
    fi
    if ! grep -Eq "^loc_${entry}:" "$asm_dir/jit.S"; then
        fail "$TEST_NAME" "jit.S does not define entry label loc_${entry}"
        return 1
    fi
    if ! grep -Eq "JMP[[:space:]]+(exit|ij_failed|comp_syscall|inst_limit)" "$asm_dir/jit.S"; then
        fail "$TEST_NAME" "jit.S does not contain sandbox exit/miss paths"
        return 1
    fi

    bin_size="$(stat -c '%s' "$asm_dir/jit.bin")"
    if [ "$bin_size" -lt 128 ]; then
        fail "$TEST_NAME" "jit.bin is unexpectedly small: ${bin_size} bytes"
        return 1
    fi
    if ! grep -Eq "^[[:space:]]*[0-9a-f]+:" "$asm_dir/bin.txt"; then
        fail "$TEST_NAME" "bin.txt does not contain objdump disassembly"
        return 1
    fi

    info "JIT artifacts verified for entry 0x$entry (${bin_size} bytes)"
    return 0
}

# --- Cleanup trap ---

cleanup() {
    stop_daemon
    unload_modules
}
trap cleanup EXIT
