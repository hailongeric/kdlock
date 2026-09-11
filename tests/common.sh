#!/bin/bash
# common.sh — shared utilities for kdlock test scripts.
# Source this file from each test: source "$(dirname "$0")/common.sh"
# Driver library, not an interactive startup file: ROOT depends on $0 and the
# EXIT trap stops its daemon and retires/unloads modules. start_daemon replaces
# generated 0x* workspaces, so preserve evidence and drain the previous session.

set -euo pipefail

KDLOCK_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KM_DIR="$KDLOCK_DIR/kernel_module"
KLOCK_DIR="$KDLOCK_DIR/klock_module"
DAEMON_DIR="$KDLOCK_DIR/daemon"
BENCH_DIR="$KDLOCK_DIR/bench"
BENCH_BIN="$BENCH_DIR/klock_test"

TARGET_PROCESS="klock_test"
TIMEOUT_SEC=30
JIT_INSTALL_PATTERN='install JIT chunk:.*status=0'

# --- Output helpers ---

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1: $2"; EXIT_CODE=1; }
info() { echo "  [INFO] $1"; }

# Sourced test scripts read this shared result accumulator.
# shellcheck disable=SC2034
EXIT_CODE=0

# --- Build ---

build_all() {
    make -C "$KM_DIR" -j"$(nproc)" >/dev/null 2>&1 || {
        fail "$TEST_NAME" "kernel module build failed"
        return 1
    }
    make -C "$KLOCK_DIR" -j"$(nproc)" >/dev/null 2>&1 || {
        fail "$TEST_NAME" "klock_module build failed"
        return 1
    }
    make -C "$DAEMON_DIR" >/dev/null 2>&1 || {
        fail "$TEST_NAME" "daemon build failed"
        return 1
    }
    gcc -I"$KDLOCK_DIR/include" "$BENCH_DIR/klock_test.c" \
        -o "$BENCH_BIN" -lpthread 2>/dev/null || {
        fail "$TEST_NAME" "benchmark build failed"
        return 1
    }
}

# --- Module management ---

load_modules() {
    local target="${1:-$TARGET_PROCESS}"
    unload_modules || return 1
    sleep 0.2

    sysctl -w kernel.randomize_va_space=0 >/dev/null 2>&1
    sysctl -w kernel.numa_balancing=0 >/dev/null 2>&1

    insmod "$KM_DIR/kdlock_km.ko" target_process="$target" || { fail "$TEST_NAME" "insmod kdlock_km failed"; return 1; }
    insmod "$KLOCK_DIR/klock_module.ko" || { fail "$TEST_NAME" "insmod klock_module failed"; return 1; }
}

unload_modules() {
    # Pins can form a reverse source/provider dependency. Close admission and
    # retire them only after callers/translators drain; never force either exit.
    if [ -d /sys/module/kdlock_km ]; then
        python3 "$KDLOCK_DIR/disassem/device_session.py" retire || {
            fail "$TEST_NAME" "source retirement failed; retain modules for diagnosis"
            return 1
        }
    fi
    if [ -d /sys/module/klock_module ]; then
        rmmod klock_module || return 1
    fi
    sleep 0.1
    if [ -d /sys/module/kdlock_km ]; then
        rmmod kdlock_km || return 1
    fi
    sleep 0.1
}

# --- Daemon management ---

start_daemon() {
    local mode="${1:-2}"
    cd "$DAEMON_DIR"
    rm -rf 0x* 2>/dev/null || true
    if [ -n "${DAEMON_LOG:-}" ]; then
        # The runner collects this after drain, also when an oracle fails.
        # Announce only this log, never scan unrelated temporary files.
        info "Evidence file: $DAEMON_LOG"
        KD_JIT_BODY_WITNESS=1 setsid ./daemon --mode "$mode" --quiet >"$DAEMON_LOG" 2>&1 &
    else
        KD_JIT_BODY_WITNESS=1 setsid ./daemon --mode "$mode" --quiet &
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

jit_install_count() {
    dmesg | grep -c "$JIT_INSTALL_PATTERN" || true
}

check_dmesg_has() {
    local pattern="$1"
    local msg="${2:-expected pattern $pattern in dmesg}"
    # Do not use grep -q here. With pipefail and a large kernel log, grep can
    # exit on the first match and make dmesg fail with SIGPIPE.
    if ! dmesg | grep "$pattern" >/dev/null; then
        fail "$TEST_NAME" "$msg"
        return 1
    fi
    return 0
}

check_dmesg_not_has() {
    local pattern="$1"
    local msg="${2:-unexpected pattern $pattern in dmesg}"
    if dmesg | grep "$pattern" >/dev/null; then
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

# Call after module unload, when all physical acquisitions must be released.
check_mutex_origin_accounting() {
    local acquired released
    acquired="$(get_dmesg_stat origin_acquires)"
    released="$(get_dmesg_stat origin_releases)"
    if [ -z "$acquired" ] || [ "$acquired" != "$released" ]; then
        fail "$TEST_NAME" "native owner imbalance: acquire=$acquired release=$released"
        return 1
    fi
    check_dmesg_stat_equals active_tasks 0 || return 1
    check_dmesg_stat_equals task_alloc_failure "${1:-0}" || return 1
    check_dmesg_has 'kd_mutex oracle: inside=0 overlaps=0' || return 1
}

check_complex_cs_integrity() {
    local expected_operations="$1"
    local expected_active_states="${2:-}"
    local line operations active_states failures

    line="$(dmesg | sed -n '/kd_cs integrity:/p' | tail -n 1)"
    operations="$(printf '%s\n' "$line" | sed -n \
        's/.*operations=\([0-9][0-9]*\).*/\1/p')"
    active_states="$(printf '%s\n' "$line" | sed -n \
        's/.*active_states=\([0-9][0-9]*\).*/\1/p')"
    failures="$(printf '%s\n' "$line" | sed -n \
        's/.*failures=\([0-9][0-9]*\).*/\1/p')"

    if [ -z "$operations" ] || [ -z "$active_states" ] ||
       [ -z "$failures" ]; then
        fail "$TEST_NAME" "complex critical-section integrity report is missing"
        return 1
    fi
    if [ "$operations" != "$expected_operations" ]; then
        fail "$TEST_NAME" \
            "complex critical-section operation mismatch: expected $expected_operations, got $operations"
        return 1
    fi
    if [ "$expected_operations" -gt 0 ] && [ "$active_states" -eq 0 ]; then
        fail "$TEST_NAME" "complex critical-section state was never updated"
        return 1
    fi
    if [ -n "$expected_active_states" ] &&
       [ "$active_states" != "$expected_active_states" ]; then
        fail "$TEST_NAME" \
            "complex critical-section active-state mismatch: expected $expected_active_states, got $active_states"
        return 1
    fi
    if [ "$failures" != "0" ]; then
        fail "$TEST_NAME" "complex critical-section state validation failed"
        dmesg | grep "kd_cs .*mismatch\|kd_cs integrity limit" | tail -n 8 || true
        return 1
    fi

    check_dmesg_has 'kd_spin oracle: inside=0 overlaps=0 origin_missing=0 context_failures=0' || return 1
    info "Complex critical section verified: $operations transitions across $active_states state(s)"
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
        writes="$(jit_install_count)"
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
    if ! grep -Eq \
            '^Translation input: entry=0x[0-9a-f]+ targets=[1-9][0-9]* regions=[1-9][0-9]* bytes=[1-9][0-9]*$' \
            "$log_file"; then
        fail "$TEST_NAME" "daemon did not confirm reading kernel text"
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

check_complex_cs_artifact() {
    local asm_dir="$1"
    local code

    code="$(awk '
        /^[[:space:]]*\/\*/ { in_comment = 1; next }
        /^[[:space:]]*\*\// { in_comment = 0; next }
        !in_comment { print }
    ' "$asm_dir/jit.S")"

    if ! printf '%s\n' "$code" |
            grep -Ei 'AND[[:space:]]+[^,]+,[[:space:]]+0x3' >/dev/null; then
        fail "$TEST_NAME" \
            "jit.S does not execute the complex critical-section lane selector"
        return 1
    fi
    if ! printf '%s\n' "$code" |
            grep -E 'JZ[[:space:]]+loc_' >/dev/null; then
        fail "$TEST_NAME" \
            "jit.S does not execute the complex critical-section branch"
        return 1
    fi
    if ! printf '%s\n' "$code" | grep -E 'ROL[[:space:]]+' >/dev/null ||
       ! printf '%s\n' "$code" | grep -E 'IMUL[[:space:]]+' >/dev/null; then
        fail "$TEST_NAME" \
            "jit.S is missing complex rotate or multiply operations"
        return 1
    fi
    if ! printf '%s\n' "$code" |
            grep -E 'QWORD PTR \[[^]]*0x8[[:space:]]*\*[[:space:]]*R' \
                >/dev/null; then
        fail "$TEST_NAME" \
            "jit.S is missing complex indexed state access"
        return 1
    fi

    info "Complex critical-section instructions verified in $asm_dir"
    return 0
}

check_jit_hostcall_artifact() {
    local asm_dir="$1"
    local symbol="$2"
    local stub label target

    stub="$(awk -v symbol="$symbol" '
        $0 ~ "KD_HOSTCALL.*symbol=" symbol { capture = 1 }
        capture { print }
        capture && /JMP[[:space:]]+exit/ { exit }
    ' "$asm_dir/jit.S")"
    if [ -z "$stub" ]; then
        fail "$TEST_NAME" \
            "jit.S has no named hostcall stub for $symbol"
        return 1
    fi
    if ! printf '%s\n' "$stub" |
            grep -E "MOV[[:space:]]+Stack_IJ,[[:space:]]+0x5" >/dev/null; then
        fail "$TEST_NAME" \
            "$symbol stub does not use KD_EXE_HOSTCALL"
        return 1
    fi
    if printf '%s\n' "$stub" |
            grep -E "LEA[[:space:]]+R13,.*R13[[:space:]]*\+[[:space:]]*0x8" \
                >/dev/null; then
        fail "$TEST_NAME" \
            "$symbol hostcall stub discards its virtual return address"
        return 1
    fi

    label="$(printf '%s\n' "$stub" | sed -n \
        's/^loc_\([0-9a-f][0-9a-f]*\):$/\1/p' | head -n 1)"
    if [ -z "$label" ]; then
        fail "$TEST_NAME" "cannot derive $symbol hostcall target"
        return 1
    fi
    target="$(printf '%s' "$label" | tr '[:upper:]' '[:lower:]')"
    if [ -s "$asm_dir/callee_table.txt" ] &&
            grep -Eiq "^(0x)?${target}$" "$asm_dir/callee_table.txt"; then
        fail "$TEST_NAME" \
            "$symbol hostcall leaked into callee_table.txt"
        return 1
    fi

    info "Hostcall artifact verified for $symbol at 0x$target"
    return 0
}

jit_entry_from_asm_dir() {
    local asm_dir="$1"
    local tgid_dir rip_dir entry

    tgid_dir="$(dirname "$asm_dir")"
    rip_dir="$(basename "$(dirname "$tgid_dir")")"
    entry="${rip_dir#0x}"
    if [ "$entry" = "$rip_dir" ] || [ -z "$entry" ]; then
        return 1
    fi
    printf '%s\n' "$entry"
}

jit_entry_was_executed() {
    local asm_dir="$1"
    local entry

    entry="$(jit_entry_from_asm_dir "$asm_dir")" || return 1
    dmesg | grep -E \
        "JIT body witness: entry=${entry} lock=[0-9a-f]+ body=1([[:space:]]|$)" \
        >/dev/null
}

jit_entry_was_executed_for_lock() {
    local lock_addr="$1"
    local asm_dir="$2"
    local entry

    entry="$(jit_entry_from_asm_dir "$asm_dir")" || return 1
    dmesg | grep -E \
        "JIT body witness: entry=${entry} lock=${lock_addr} body=1([[:space:]]|$)" \
        >/dev/null
}

check_jit_entry_executed() {
    local asm_dir="$1"
    local entry

    entry="$(jit_entry_from_asm_dir "$asm_dir")" || {
        fail "$TEST_NAME" "cannot derive runtime entry RIP from $asm_dir"
        return 1
    }
    if ! jit_entry_was_executed "$asm_dir"; then
        fail "$TEST_NAME" \
            "translated entry 0x$entry has no returned generated-body witness"
        return 1
    fi
    info "Runtime execution verified for translated entry 0x$entry"
    return 0
}

check_any_jit_entry_executed() {
    local asm_dir entry

    for asm_dir in "$@"; do
        if jit_entry_was_executed "$asm_dir"; then
            entry="$(jit_entry_from_asm_dir "$asm_dir")"
            info "Runtime execution verified for translated entry 0x$entry"
            return 0
        fi
    done
    fail "$TEST_NAME" "none of the installed entries has a returned generated-body witness"
    return 1
}

check_any_jit_entry_executed_for_lock() {
    local lock_addr="$1"
    local asm_dir entry

    shift
    for asm_dir in "$@"; do
        if jit_entry_was_executed_for_lock "$lock_addr" "$asm_dir"; then
            entry="$(jit_entry_from_asm_dir "$asm_dir")"
            info "Runtime execution verified for lock $lock_addr at translated entry 0x$entry"
            return 0
        fi
    done
    fail "$TEST_NAME" \
        "lock $lock_addr has no matching generated-body witness"
    return 1
}

# --- Cleanup trap ---

cleanup() {
    stop_daemon
    unload_modules
}
trap cleanup EXIT
