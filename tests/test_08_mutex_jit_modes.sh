#!/bin/bash
# test_08_mutex_jit_modes.sh - opt-in mutex JIT validation for nested mode 4
# and API-in-critical-section mode 5. Run only in a recovery VM with a
# confirmed host-side snapshot.
TEST_NAME="test_08_mutex_jit_modes"
source "$(dirname "$0")/common.sh"

JIT_THREADS=4
JIT_LOOPS=1
JIT_WORKLOAD=1000000
MAX_ATTEMPTS=5
MODE4_ROLES=7
MODE4_ROLE_BASE=2147483648
MODE4_WORKLOAD=50000

build_all || exit 1

run_mode4_nested_contention() {
    local -a pids=()
    local -a logs=()
    local role pid failed=0

    if [ "$(nproc)" -lt "$MODE4_ROLES" ]; then
        fail "$TEST_NAME" "mode 4 requires at least $MODE4_ROLES online CPUs"
        return 1
    fi

    # Start the two holders first. Every process is pinned to a distinct CPU so
    # a scheduled parent execution frame cannot block the task that releases B.
    for role in 1 3; do
        logs[$role]="$(mktemp "/tmp/kdlock-mode4-role${role}.XXXXXX.log")"
        timeout --kill-after=5s 60s taskset -c "$role" "$BENCH_BIN" \
            1 1 "$MODE4_WORKLOAD" 1 4 \
            "$((MODE4_ROLE_BASE + role))" \
            >"${logs[$role]}" 2>&1 &
        pids[$role]=$!
    done
    sleep 0.1

    # Queue one direct waiter before the target on each lock, then queue a
    # trailing waiter. This makes the direct waiter combine the target instead
    # of merely handing the lock to it.
    for role in 2 4 0 5 6; do
        logs[$role]="$(mktemp "/tmp/kdlock-mode4-role${role}.XXXXXX.log")"
        timeout --kill-after=5s 60s taskset -c "$role" "$BENCH_BIN" \
            1 1 "$MODE4_WORKLOAD" 1 4 \
            "$((MODE4_ROLE_BASE + role))" \
            >"${logs[$role]}" 2>&1 &
        pids[$role]=$!
    done

    for role in 0 1 2 3 4 5 6; do
        pid="${pids[$role]}"
        if ! wait "$pid"; then
            failed=1
            info "mode 4 role $role failed:"
            tail -n 10 "${logs[$role]}" || true
        fi
    done
    for role in 0 1 2 3 4 5 6; do
        rm -f "${logs[$role]}"
    done

    if [ "$failed" -ne 0 ]; then
        fail "$TEST_NAME" "mode 4 deterministic nested contention failed"
        return 1
    fi
    return 0
}

run_jit_mode() {
    local mode="$1"
    local mode_name="$2"
    local expected_artifacts="$3"
    local attempt=0
    local artifacts asm_dir
    local delegate_count write_count target_count
    local expected_counter actual_counter

    info "Testing mutex JIT mode $mode ($mode_name)..."
    clear_dmesg
    unload_modules

    sysctl -w kernel.randomize_va_space=0 >/dev/null 2>&1
    sysctl -w kernel.numa_balancing=0 >/dev/null 2>&1
    insmod "$KM_DIR/kdlock_km.ko" \
        target_process="$TARGET_PROCESS" mutex_jit=1 || {
        fail "$TEST_NAME" "mode $mode: loading kdlock_km failed"
        return 1
    }
    insmod "$KLOCK_DIR/klock_module.ko" || {
        fail "$TEST_NAME" "mode $mode: loading klock_module failed"
        return 1
    }

    if [ "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" != "1" ]; then
        fail "$TEST_NAME" "mode $mode: mutex_jit is not enabled"
        return 1
    fi

    DAEMON_LOG="$(mktemp "/tmp/kdlock-test08-mode${mode}.XXXXXX.log")"
    start_daemon 2

    run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 "$mode" >/dev/null 2>&1 || {
        fail "$TEST_NAME" "mode $mode: warmup failed"
        return 1
    }
    sleep 1
    run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 "$mode" \
        >/dev/null 2>&1 || {
        fail "$TEST_NAME" "mode $mode: promotion workload failed"
        return 1
    }

    if ! artifacts="$(wait_for_jit_artifact_count "$expected_artifacts" 30)"; then
        fail "$TEST_NAME" \
            "mode $mode: expected $expected_artifacts complete JIT workspaces"
        return 1
    fi
    while IFS= read -r asm_dir; do
        check_jit_artifacts "$asm_dir" || return 1
    done <<< "$artifacts"
    check_daemon_read_kernel_text "$DAEMON_LOG" || return 1

    delegate_count="$(dmesg | grep -c "begin delegate" || true)"
    write_count="$(dmesg | grep -c "write to kernel" || true)"
    target_count="$(grep -c "^Targets: \['0x" "$DAEMON_LOG" || true)"
    if [ "$delegate_count" -lt "$expected_artifacts" ] ||
       [ "$write_count" -lt "$expected_artifacts" ] ||
       [ "$target_count" -lt "$expected_artifacts" ]; then
        fail "$TEST_NAME" \
            "mode $mode: incomplete promotion/translation evidence (delegate=$delegate_count write=$write_count targets=$target_count)"
        return 1
    fi

    if ! wait_for_jit_quiescence "$expected_artifacts" 20 2; then
        fail "$TEST_NAME" "mode $mode: JIT translation did not become quiet"
        return 1
    fi

    if [ "$mode" -eq 4 ]; then
        info "Running deterministic A/B nested contention..."
        run_mode4_nested_contention || return 1
        attempt=1
    else
        while [ "$attempt" -lt "$MAX_ATTEMPTS" ]; do
            attempt=$((attempt + 1))
            run_with_timeout 30 "$BENCH_BIN" \
                "$JIT_THREADS" "$JIT_LOOPS" "$JIT_WORKLOAD" 1 "$mode" \
                >/dev/null 2>&1 || {
                fail "$TEST_NAME" \
                    "mode $mode: contention attempt $attempt failed"
                return 1
            }
            sleep 1
            check_dmesg_ok || return 1
            check_dmesg_not_has "unexpected locked state" \
                "mode $mode: mutex state became inconsistent" || return 1
            if dmesg | grep "mutex JIT delegation ok" >/dev/null; then
                break
            fi
        done
    fi
    sleep 1

    stop_daemon
    check_dmesg_has "mutex JIT delegation ok" \
        "mode $mode: sandbox never completed a critical section" || return 1
    check_dmesg_not_has "unexpected locked state" \
        "mode $mode: mutex state became inconsistent" || return 1
    check_dmesg_ok || return 1

    unload_modules
    if [ "$mode" -eq 4 ]; then
        local jit_success nested_queued nested_remote

        jit_success="$(get_dmesg_stat jit_success)"
        nested_queued="$(get_dmesg_stat nested_queued)"
        nested_remote="$(get_dmesg_stat nested_remote)"
        if [ -z "$jit_success" ] || [ "$jit_success" -lt 2 ]; then
            fail "$TEST_NAME" \
                "mode 4: expected outer and inner JIT completions, got ${jit_success:-missing}"
            return 1
        fi
        if [ -z "$nested_queued" ] || [ "$nested_queued" -lt 1 ] ||
           [ -z "$nested_remote" ] || [ "$nested_remote" -lt 1 ]; then
            fail "$TEST_NAME" \
                "mode 4: nested B was not queued and remotely delegated"
            return 1
        fi
        check_dmesg_stat_equals "jit_not_ready" "0" \
            "mode 4: nested execution started before translation was ready" || return 1
        check_dmesg_stat_equals "jit_failure" "0" \
            "mode 4: translated nested critical section failed" || return 1
        check_dmesg_stat_equals "frame_failure" "0" \
            "mode 4: execution-frame invariant failed" || return 1
        check_dmesg_stat_equals "node_overflow" "0" \
            "mode 4: waiter node capacity was exhausted" || return 1
        check_dmesg_stat_equals "context_busy" "0" \
            "mode 4: a foreign task encountered a live execution context" || return 1
        check_dmesg_stat_equals "nested_abort_release" "0" \
            "mode 4: nested abort cleanup ran unexpectedly" || return 1
        check_dmesg_stat_equals "jit_resume" "1" \
            "mode 4: outer waiter did not resume exactly once" || return 1
        check_dmesg_stat_equals "active_waiters" "0" \
            "mode 4: mutex queue leaked active waiters" || return 1
        check_dmesg_stat_equals "reserved_nodes" "0" \
            "mode 4: mutex queue leaked reserved slots" || return 1
    else
        check_dmesg_stat_equals "jit_success" "1" \
            "mode $mode: expected exactly one sandbox completion" || return 1
    fi
    check_dmesg_has "kd_exec invariant_failures=0" \
        "mode $mode: execution-frame invariant failed" || return 1
    while IFS= read -r asm_dir; do
        check_jit_entry_executed "$asm_dir" || return 1
    done <<< "$artifacts"

    if [ "$mode" -eq 4 ]; then
        expected_counter=$((1 + 12000 + MODE4_ROLES))
    else
        expected_counter=$((1 + 12000 + JIT_THREADS * JIT_LOOPS * attempt))
    fi
    actual_counter="$(dmesg | sed -n \
        's/.*final counter: \([0-9][0-9]*\).*/\1/p' | tail -n 1)"
    if [ "$actual_counter" != "$expected_counter" ]; then
        fail "$TEST_NAME" \
            "mode $mode: counter mismatch, expected $expected_counter, got ${actual_counter:-missing}"
        return 1
    fi

    info "  mode $mode passed after $attempt contention attempt(s)"
    return 0
}

case "${1:-all}" in
4)
    run_jit_mode 4 "mutex-nested" 2 || exit 1
    ;;
5)
    run_jit_mode 5 "mutex-api-in-lock" 1 || exit 1
    ;;
all)
    run_jit_mode 4 "mutex-nested" 2 || exit 1
    run_jit_mode 5 "mutex-api-in-lock" 1 || exit 1
    ;;
*)
    fail "$TEST_NAME" "usage: $0 [4|5|all]"
    exit 1
    ;;
esac

pass "$TEST_NAME"
exit $EXIT_CODE
