#!/bin/bash
# test_08_mutex_jit_modes.sh - opt-in mutex JIT validation for nested mode 4
# and repeated hostcall mode 5. Run only in a recovery VM with a confirmed
# host-side snapshot.
TEST_NAME="test_08_mutex_jit_modes"
source "$(dirname "$0")/common.sh"

MODE4_ROLES=7
MODE4_ROLE_BASE=2147483648
MODE4_WORKLOAD=50000
MODE5_ROUNDS="${KD_MUTEX_HOSTCALL_JIT_ROUNDS:-16}"
MODE5_ROUND_THREADS=4
MODE5_ROUND_LOOPS=1
MODE5_ROUND_WORKLOAD="${KD_MUTEX_HOSTCALL_JIT_ROUND_WORKLOAD:-1000000}"
MODE5_PINNED_THREADS=4
MODE5_PINNED_LOOPS=1
MODE5_PINNED_HOLDER_WORKLOAD="${KD_MUTEX_HOSTCALL_JIT_PINNED_HOLDER_WORKLOAD:-200000000}"
MODE5_PINNED_WAITER_WORKLOAD="${KD_MUTEX_HOSTCALL_JIT_PINNED_WAITER_WORKLOAD:-1000000}"
MODE5_STRESS_THREADS="${KD_MUTEX_HOSTCALL_JIT_STRESS_THREADS:-8}"
MODE5_STRESS_LOOPS="${KD_MUTEX_HOSTCALL_JIT_STRESS_LOOPS:-64}"
MODE5_STRESS_WORKLOAD="${KD_MUTEX_HOSTCALL_JIT_STRESS_WORKLOAD:-100000}"
MODE5_MIN_JIT_SUCCESSES="${KD_MUTEX_HOSTCALL_JIT_MIN_SUCCESSES:-}"

for value in "$MODE5_ROUNDS" "$MODE5_ROUND_WORKLOAD" \
             "$MODE5_PINNED_HOLDER_WORKLOAD" \
             "$MODE5_PINNED_WAITER_WORKLOAD" "$MODE5_STRESS_THREADS" \
             "$MODE5_STRESS_LOOPS" "$MODE5_STRESS_WORKLOAD"; do
    case "$value" in
        ''|*[!0-9]*)
            fail "$TEST_NAME" \
                "mode 5 stress parameters must be non-negative integers"
            exit 1
            ;;
    esac
done
if [ "$MODE5_ROUNDS" -lt 1 ] || [ "$MODE5_ROUND_WORKLOAD" -lt 1 ] ||
   [ "$MODE5_PINNED_HOLDER_WORKLOAD" -lt 1 ] ||
   [ "$MODE5_PINNED_WAITER_WORKLOAD" -lt 1 ] ||
   [ "$MODE5_STRESS_THREADS" -lt 2 ] || [ "$MODE5_STRESS_LOOPS" -lt 1 ] ||
   [ "$MODE5_STRESS_WORKLOAD" -lt 1 ]; then
    fail "$TEST_NAME" \
        "mode 5 stress rounds, threads, loops, and workloads must be positive"
    exit 1
fi
if [ -z "$MODE5_MIN_JIT_SUCCESSES" ]; then
    MODE5_MIN_JIT_SUCCESSES=$((MODE5_ROUNDS / 2))
else
    case "$MODE5_MIN_JIT_SUCCESSES" in
        *[!0-9]*)
            fail "$TEST_NAME" \
                "mode 5 minimum JIT successes must be an integer"
            exit 1
            ;;
    esac
fi
if [ "$MODE5_MIN_JIT_SUCCESSES" -lt 2 ]; then
    MODE5_MIN_JIT_SUCCESSES=2
fi

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

run_mode5_hostcall_contention() {
    local round pinned_holder_pid

    # Repeated owner/waiter topologies prove that the same artifact can leave
    # the sandbox, execute the native service, and resume more than once.
    for ((round = 1; round <= MODE5_ROUNDS; round++)); do
        run_with_timeout 20 "$BENCH_BIN" \
            "$MODE5_ROUND_THREADS" "$MODE5_ROUND_LOOPS" \
            "$MODE5_ROUND_WORKLOAD" 1 5 >/dev/null 2>&1 || {
            fail "$TEST_NAME" "mode 5 hostcall JIT round $round failed"
            return 1
        }
    done

    if [ "$(nproc)" -lt 2 ]; then
        fail "$TEST_NAME" "mode 5 requires at least two online CPUs"
        return 1
    fi

    # Hold the mutex on CPU 0 while several waiters share CPU 1. Every remotely
    # completed waiter must retain its own stack and resume after mutex_unlock.
    timeout --kill-after=5s 90s taskset -c 0 "$BENCH_BIN" \
        1 1 "$MODE5_PINNED_HOLDER_WORKLOAD" 1 5 >/dev/null 2>&1 &
    pinned_holder_pid=$!
    sleep 0.1
    run_with_timeout 90 taskset -c 1 "$BENCH_BIN" \
        "$MODE5_PINNED_THREADS" "$MODE5_PINNED_LOOPS" \
        "$MODE5_PINNED_WAITER_WORKLOAD" 1 5 >/dev/null 2>&1 || {
        kill "$pinned_holder_pid" 2>/dev/null || true
        wait "$pinned_holder_pid" 2>/dev/null || true
        fail "$TEST_NAME" "mode 5 same-CPU waiter workload failed"
        return 1
    }
    if ! wait "$pinned_holder_pid"; then
        fail "$TEST_NAME" "mode 5 pinned mutex holder failed"
        return 1
    fi

    run_with_timeout 90 "$BENCH_BIN" \
        "$MODE5_STRESS_THREADS" "$MODE5_STRESS_LOOPS" \
        "$MODE5_STRESS_WORKLOAD" 1 5 >/dev/null 2>&1 || {
        fail "$TEST_NAME" "mode 5 continuous hostcall JIT workload failed"
        return 1
    }
    return 0
}

check_mutex_jit_clean_stats() {
    local mode="$1"

    check_dmesg_stat_equals "jit_not_ready" "0" \
        "mode $mode: execution started before translation was ready" || return 1
    check_dmesg_stat_equals "jit_failure" "0" \
        "mode $mode: translated mutex critical section failed" || return 1
    check_dmesg_stat_equals "frame_failure" "0" \
        "mode $mode: execution-frame invariant failed" || return 1
    check_dmesg_stat_equals "node_overflow" "0" \
        "mode $mode: waiter node capacity was exhausted" || return 1
    check_dmesg_stat_equals "context_busy" "0" \
        "mode $mode: foreign task encountered a live execution context" || return 1
    check_dmesg_stat_equals "nested_abort_release" "0" \
        "mode $mode: nested abort cleanup ran unexpectedly" || return 1
    check_dmesg_stat_equals "active_waiters" "0" \
        "mode $mode: mutex queue leaked active waiters" || return 1
    check_dmesg_stat_equals "reserved_nodes" "0" \
        "mode $mode: mutex queue leaked reserved slots" || return 1
}

run_jit_mode() {
    local mode="$1"
    local mode_name="$2"
    local expected_artifacts="$3"
    local artifacts asm_dir
    local delegate_count write_count target_count
    local runtime_write_count runtime_target_count
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
        if [ "$mode" -eq 5 ]; then
            check_jit_hostcall_artifact "$asm_dir" "ktime_get" || return 1
        fi
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
    write_count="$(dmesg | grep -c "write to kernel" || true)"
    target_count="$(grep -c "^Targets: \['0x" "$DAEMON_LOG" || true)"

    if [ "$mode" -eq 4 ]; then
        info "Running deterministic A/B nested contention..."
        run_mode4_nested_contention || return 1
    else
        info "Running repeated mode 5 hostcall contention..."
        run_mode5_hostcall_contention || return 1
    fi
    sleep 1

    if [ "$mode" -eq 5 ]; then
        runtime_write_count="$(dmesg | grep -c "write to kernel" || true)"
        runtime_target_count="$(grep -c "^Targets: \['0x" \
            "$DAEMON_LOG" || true)"
        if [ "$runtime_write_count" != "$write_count" ] ||
           [ "$runtime_target_count" != "$target_count" ]; then
            fail "$TEST_NAME" \
                "mode 5 hostcall triggered runtime JIT recompilation (writes $write_count->$runtime_write_count, targets $target_count->$runtime_target_count)"
            return 1
        fi
    fi

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
        check_dmesg_stat_equals "jit_resume" "1" \
            "mode 4: outer waiter did not resume exactly once" || return 1
    else
        local jit_success jit_resume max_waiters
        local hostcall_stats hostcall_exits hostcall_executed
        local hostcall_resumed hostcall_rejected hostcall_failed hostcall_limit

        jit_success="$(get_dmesg_stat jit_success)"
        jit_resume="$(get_dmesg_stat jit_resume)"
        max_waiters="$(get_dmesg_stat max_waiters)"
        if [ -z "$jit_success" ] ||
           [ "$jit_success" -lt "$MODE5_MIN_JIT_SUCCESSES" ]; then
            fail "$TEST_NAME" \
                "mode 5: expected at least $MODE5_MIN_JIT_SUCCESSES JIT completions, got ${jit_success:-missing}"
            return 1
        fi
        if [ "$jit_resume" != "$jit_success" ]; then
            fail "$TEST_NAME" \
                "mode 5: waiter resume mismatch, success=$jit_success resume=${jit_resume:-missing}"
            return 1
        fi
        if [ -z "$max_waiters" ] || [ "$max_waiters" -lt 2 ]; then
            fail "$TEST_NAME" \
                "mode 5: workload did not form a contended mutex queue"
            return 1
        fi

        hostcall_stats="$(dmesg | sed -n \
            '/kd_hostcall stats:/p' | tail -n 1)"
        hostcall_exits="$(printf '%s\n' "$hostcall_stats" | sed -n \
            's/.*exits=\([0-9][0-9]*\).*/\1/p')"
        hostcall_executed="$(printf '%s\n' "$hostcall_stats" | sed -n \
            's/.*executed=\([0-9][0-9]*\).*/\1/p')"
        hostcall_resumed="$(printf '%s\n' "$hostcall_stats" | sed -n \
            's/.*resumed=\([0-9][0-9]*\).*/\1/p')"
        hostcall_rejected="$(printf '%s\n' "$hostcall_stats" | sed -n \
            's/.*rejected=\([0-9][0-9]*\).*/\1/p')"
        hostcall_failed="$(printf '%s\n' "$hostcall_stats" | sed -n \
            's/.*failed=\([0-9][0-9]*\).*/\1/p')"
        hostcall_limit="$(printf '%s\n' "$hostcall_stats" | sed -n \
            's/.*limit=\([0-9][0-9]*\).*/\1/p')"
        if [ -z "$hostcall_exits" ] || [ "$hostcall_exits" -eq 0 ] ||
           [ "$hostcall_executed" != "$hostcall_exits" ] ||
           [ "$hostcall_resumed" != "$hostcall_exits" ] ||
           [ "$hostcall_exits" != "$jit_success" ]; then
            fail "$TEST_NAME" \
                "mode 5: hostcall/JIT accounting mismatch (jit=$jit_success, $hostcall_stats)"
            return 1
        fi
        if [ "$hostcall_rejected" != "0" ] ||
           [ "$hostcall_failed" != "0" ] ||
           [ "$hostcall_limit" != "0" ]; then
            fail "$TEST_NAME" \
                "mode 5: hostcall diagnostics reported a failure"
            printf '%s\n' "$hostcall_stats"
            return 1
        fi
    fi
    check_mutex_jit_clean_stats "$mode" || return 1
    check_dmesg_has "kd_exec invariant_failures=0" \
        "mode $mode: execution-frame invariant failed" || return 1
    while IFS= read -r asm_dir; do
        check_jit_entry_executed "$asm_dir" || return 1
    done <<< "$artifacts"

    if [ "$mode" -eq 4 ]; then
        expected_counter=$((1 + 12000 + MODE4_ROLES))
    else
        expected_counter=$((1 + 12000 +
            MODE5_ROUNDS * MODE5_ROUND_THREADS * MODE5_ROUND_LOOPS +
            1 + MODE5_PINNED_THREADS * MODE5_PINNED_LOOPS +
            MODE5_STRESS_THREADS * MODE5_STRESS_LOOPS))
    fi
    actual_counter="$(dmesg | sed -n \
        's/.*final counter: \([0-9][0-9]*\).*/\1/p' | tail -n 1)"
    if [ "$actual_counter" != "$expected_counter" ]; then
        fail "$TEST_NAME" \
            "mode $mode: counter mismatch, expected $expected_counter, got ${actual_counter:-missing}"
        return 1
    fi

    if [ "$mode" -eq 5 ]; then
        local api_observations

        api_observations="$(dmesg | sed -n \
            's/.*mode5 api observations: \([0-9][0-9]*\).*/\1/p' |
            tail -n 1)"
        if [ "$api_observations" != "$expected_counter" ]; then
            fail "$TEST_NAME" \
                "mode 5: post-hostcall observation mismatch, expected $expected_counter, got ${api_observations:-missing}"
            return 1
        fi
        info "  mode 5 hostcalls: $jit_success exits executed and resumed"
    fi

    info "  mode $mode translated execution passed"
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
