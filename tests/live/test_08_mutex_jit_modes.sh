#!/bin/bash
# test_08_mutex_jit_modes.sh - opt-in mutex JIT validation for nested mode 4,
# repeated hostcall mode 5, and GS JIT mode 11. Recovery VM only.
TEST_NAME="test_08_mutex_jit_modes"
source "$(dirname "$0")/../common.sh"

MODE4_ROLES=7
MODE4_ROLE_BASE=2147483648
MODE4_WORKLOAD=50000
MODE4_OOO="${KD_MUTEX_OOO:-0}"
if [ "$MODE4_OOO" != 0 ] &&
        { [ "$MODE4_OOO" != 1 ] || [ "${1:-all}" != 4 ]; }; then
    fail "$TEST_NAME" "KD_MUTEX_OOO=1 requires explicit mode 4"
    exit 1
fi
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
MODE5_QUOTA_THREADS=4

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

run_nested_mutex_contention() {
    local mode="$1"
    local out="$2"
    local -a pids=()
    local -a logs=()
    # The A executor (4) must sleep on B so its holder (1) can run on CPU 0.
    # Four queued roles share CPU 1 without changing the production node limit.
    local -a cpus=(1 0 1 0 0 1 1)
    local role pid status failed=0

    if ! python3 -c 'import os; assert {0, 1} <= os.sched_getaffinity(0)'; then
        fail "$TEST_NAME" "mode $mode requires CPUs 0 and 1"
        return 1
    fi
    for role in 0 1 2 3 4 5 6; do
        printf '%s\t%s\n' "$role" "${cpus[role]}"
    done > "$out/placements.tsv"
    : > "$out/statuses.tsv"

    # Both holders can yield at the workload barriers, even while retaining
    # their native mutexes. No test task reference or owner handoff is added.
    for role in 1 3; do
        logs[role]="$out/role-$role.log"
        timeout --kill-after=5s 60s taskset -c "${cpus[role]}" "$BENCH_BIN" \
            1 1 "$MODE4_WORKLOAD" 1 "$mode" \
            "$((MODE4_ROLE_BASE + role))" \
            >"${logs[role]}" 2>&1 &
        pids[role]=$!
    done
    sleep 0.1

    # A's direct waiter becomes the target's combiner. B's native holder waits
    # until that combiner actually contends on B before allowing progress.
    for role in 2 4 0 5 6; do
        logs[role]="$out/role-$role.log"
        timeout --kill-after=5s 60s taskset -c "${cpus[role]}" "$BENCH_BIN" \
            1 1 "$MODE4_WORKLOAD" 1 "$mode" \
            "$((MODE4_ROLE_BASE + role))" \
            >"${logs[role]}" 2>&1 &
        pids[role]=$!
    done

    for role in 0 1 2 3 4 5 6; do
        pid="${pids[role]}"
        if wait "$pid"; then
            status=0
        else
            status=$?
            failed=1
            info "mode $mode role $role failed:"
            tail -n 10 "${logs[role]}" || true
        fi
        printf '%s\t%s\n' "$role" "$status" >> "$out/statuses.tsv"
    done

    if [ "$failed" -ne 0 ]; then
        fail "$TEST_NAME" "mode $mode deterministic nested contention failed"
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

    # Keep this instrumented payload separate from preparation, pinned holders
    # and quota continuation. Its ioctl percentiles are not per-lock latency.
    local workload_log="${DAEMON_LOG}.workload.log"
    info "Evidence file: $workload_log"
    info "Evidence file: ${workload_log}.before.dmesg"
    info "Evidence file: ${workload_log}.after.dmesg"
    dmesg > "${workload_log}.before.dmesg" || return 1
    run_with_timeout 90 env KD_TEST_METRICS=1 "$BENCH_BIN" \
        "$MODE5_STRESS_THREADS" "$MODE5_STRESS_LOOPS" \
        "$MODE5_STRESS_WORKLOAD" 1 5 >"$workload_log" 2>&1 || {
        fail "$TEST_NAME" "mode 5 continuous hostcall JIT workload failed"
        return 1
    }
    dmesg > "${workload_log}.after.dmesg" || return 1
    return 0
}

# Keep this under mode 4, not another routine case. Its distinct native-B
# dependency complements (and cannot replace) the seven-role/two-CPU phase.
run_mode4_shared_b() {
    local out artifacts artifact lane role status failed=0
    local -a pids=() selected=()

    out=$(mktemp -d /tmp/kdlock-mutex-shared.XXXXXX) || return 1
    info "Evidence: $out"
    python3 -c 'import os; assert set(range(9)) <= os.sched_getaffinity(0)' || return 1
    clear_dmesg || return 1
    load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1 || return 1
    insmod "$KLOCK_DIR/klock_module.ko" mutex_shared=1 || return 1
    test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1 || return 1
    awk '$3 == "kd_shared_native" && $4 == "[klock_module]" {print $1}' \
        /proc/kallsyms > "$out/probe.txt" || return 1
    DAEMON_LOG="$out/daemon.log"
    start_daemon 2 || return 1
    for lane in 0 1; do
        run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 4 "$((lane + 8))" \
            > "$out/warm-$lane.log" 2>&1 || return 1
    done
    sleep 1
    for lane in 0 1; do
        run_with_timeout 30 "$BENCH_BIN" 1 12000 1 1 4 "$((lane + 8))" \
            > "$out/promote-$lane.log" 2>&1 || return 1
    done
    # B also becomes hot during serial promotion. Preserve its extra image;
    # select A entries by real source CALL returns, never artifact count/order.
    artifacts=$(wait_for_jit_artifact_count 3 60) || return 1
    while IFS= read -r artifact; do
        check_jit_artifacts "$artifact" || return 1
        check_complex_cs_artifact "$artifact" || return 1
        selected+=("$artifact")
    done <<< "$artifacts"
    # Reuse the device-layout observer; do not arm from file/log presence.
    PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$out" "$KLOCK_DIR/klock_module.ko" "${selected[@]}" <<'PY' || return 1
import json, subprocess, sys
from pathlib import Path
from mutex_signal_protocol import wait_ready
from mutex_stack_protocol import control_returns
out = Path(sys.argv[1])
published = [wait_ready(Path(p)) for p in sys.argv[3:]]
symbols = {row[2]: int(row[0], 16)
           for row in (line.split() for line in Path('/proc/kallsyms').read_text().splitlines())
           if len(row) == 4 and row[3] == '[klock_module]'}
roots, returns = [], []
for lane in range(2):
    name = f'kd_shared_cs{lane}'
    code = subprocess.check_output(['objdump', '-dr', f'--disassemble={name}', sys.argv[2]], text=True, timeout=10)
    (out / f'source-{lane}.asm').write_text(code)
    calls = control_returns(code, symbols[name], name)
    assert len(calls) == 2
    returns.extend(calls)
    matches = [p for p in published if int(p['entry'], 16) == calls[0]]
    assert len(matches) == 1
    roots.extend(matches)
assert len({p['entry'] for p in roots}) == 2
assert all(int(p['entry'], 16) in returns for p in published)
(out / 'published.json').write_text(json.dumps(roots, indent=2) + '\n')
(out / 'all-published.json').write_text(json.dumps(published, indent=2) + '\n')
(out / 'source-returns.json').write_text(json.dumps(returns) + '\n')
PY
    stop_daemon || return 1
    find "$DAEMON_DIR" -name jit.bin -print0 | sort -z | xargs -0 sha256sum \
        > "$out/images-before.sha256" || return 1
    printf '1\n' > /sys/module/klock_module/parameters/mutex_shared_armed || return 1
    : > "$out/statuses.tsv"
    : > "$out/placements.tsv"
    for role in 0 4 1 5 2 6 3 7 10; do
        local cpu=$role
        if [ "$role" = 10 ]; then cpu=8; fi
        printf '%s\t%s\n' "$role" "$cpu" >> "$out/placements.tsv" || return 1
        timeout --kill-after=5s 45s taskset -c "$cpu" "$BENCH_BIN" \
            1 1 1 1 4 "$role" > "$out/role-$role.log" 2>&1 &
        pids[role]=$!
    done
    for role in 0 4 1 5 2 6 3 7 10; do
        status=0
        wait "${pids[role]}" || status=$?
        printf '%s\t%s\n' "$role" "$status" >> "$out/statuses.tsv"
        if [ "$status" != 0 ]; then failed=1; fi
    done
    # A timed-out kernel caller may still own B. The shared cleanup's retire
    # operation must refuse busy state; never force unload or recycle its image.
    if [ "$failed" != 0 ]; then
        fail "$TEST_NAME" "shared-B caller failed; retain its role log"
        return 1
    fi
    find "$DAEMON_DIR" -name jit.bin -print0 | sort -z | xargs -0 sha256sum \
        > "$out/images-after.sha256" || return 1
    cmp "$out/images-before.sha256" "$out/images-after.sha256" || return 1
    unload_modules || return 1
    dmesg > "$out/final.log" || return 1
    python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" shared \
        --output "$out" || return 1
    check_mutex_jit_clean_stats 4 || return 1
    check_complex_cs_integrity 24005 1 || return 1
    check_dmesg_has "kd_exec invariant_failures=0" "shared-B frame invariants" || return 1
    check_dmesg_ok || return 1
    # The oracle requires both selected A images to execute. An extra B image
    # is a publication artifact, not an additional remote-B JIT requirement.
    (cd "$KDLOCK_DIR" && find daemon -path 'daemon/0x*' -type f -print0 |
        tar --null -T - -czf "$out/artifacts.tar.gz") || return 1
    info "  mode 4 shared native B: retained owner, native peer, next A JIT verified"
}

run_mode5_quota_contention() {
    local out="$1" holder status failed=0

    # Same-CPU progress is checked above. Quota needs a delegatable queue:
    # published waiters cannot schedule, so use distinct available CPUs rather
    # than depending on a local predecessor being suspended before acquisition.
    # Keep all five callers and require a real JIT quota exit plus owner ACK.
    if ! python3 -c 'import os; assert set(range(5)) <= os.sched_getaffinity(0)'; then
        fail "$TEST_NAME" "mode 5 quota requires CPUs 0-4"
        return 1
    fi
    dmesg > "$out/before-quota.log"
    printf '1\n' > /sys/module/klock_module/parameters/mode5_call_quota
    cat /sys/module/klock_module/parameters/mode5_call_quota > "$out/enabled.txt"
    [ "$(cat "$out/enabled.txt")" = Y ] || return 1
    timeout --kill-after=5s 90s taskset -c 0 "$BENCH_BIN" \
        1 1 "$MODE5_PINNED_HOLDER_WORKLOAD" 1 5 > "$out/holder.log" 2>&1 &
    holder=$!
    sleep 0.1
    if run_with_timeout 90 taskset -c 1-4 "$BENCH_BIN" \
        "$MODE5_QUOTA_THREADS" 1 "$MODE5_PINNED_WAITER_WORKLOAD" 1 5 \
        > "$out/waiters.log" 2>&1; then
        status=0
    else
        status=$?
        failed=1
    fi
    printf 'waiters\t%s\n' "$status" > "$out/statuses.tsv"
    if wait "$holder"; then
        status=0
    else
        status=$?
        failed=1
    fi
    printf 'holder\t%s\n' "$status" >> "$out/statuses.tsv"
    printf '0\n' > /sys/module/klock_module/parameters/mode5_call_quota
    cat /sys/module/klock_module/parameters/mode5_call_quota > "$out/disabled.txt"
    if [ "$failed" -ne 0 ] || [ "$(cat "$out/disabled.txt")" != N ]; then
        fail "$TEST_NAME" "mode 5 quota workload failed; retain both client logs"
        return 1
    fi
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
    check_mutex_origin_accounting || return 1
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
    local expected_cs_states=1
    local nested_out quota_out

    info "Testing mutex JIT mode $mode ($mode_name)..."
    clear_dmesg
    unload_modules

    sysctl -w kernel.randomize_va_space=0 >/dev/null 2>&1
    sysctl -w kernel.numa_balancing=0 >/dev/null 2>&1
    load_kdlock \
        target_process="$TARGET_PROCESS" mutex_jit=1 || {
        fail "$TEST_NAME" "mode $mode: loading kdlock_km failed"
        return 1
    }
    insmod "$KLOCK_DIR/klock_module.ko" mutex_nested_schedule="$((mode == 4))" || {
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
        check_complex_cs_artifact "$asm_dir" || return 1
        if [ "$mode" -eq 5 ]; then
            check_jit_hostcall_artifact "$asm_dir" "ktime_get" || return 1
            check_jit_hostcall_artifact "$asm_dir" "int_sqrt" || return 1
        fi
    done <<< "$artifacts"
    check_daemon_read_kernel_text "$DAEMON_LOG" || return 1

    delegate_count="$(dmesg | grep -c "begin delegate" || true)"
    write_count="$(jit_install_count)"
    target_count="$(grep -c '^Translation input: entry=0x' \
        "$DAEMON_LOG" || true)"
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
    write_count="$(jit_install_count)"
    target_count="$(grep -c '^Translation input: entry=0x' \
        "$DAEMON_LOG" || true)"

    if [ "$mode" -eq 4 ]; then
        nested_out="$(mktemp -d /tmp/kdlock-mutex-nested.XXXXXX)"
        info "Evidence: $nested_out"
        # Keep publication and requested/observed CPU identity with role logs.
        python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" ready \
            --artifact "$artifacts" --output "$nested_out/published.json" || return 1
        cat /sys/module/klock_module/parameters/mutex_nested_schedule \
            > "$nested_out/enabled.txt"
        if [ "$(cat "$nested_out/enabled.txt")" != Y ]; then
            fail "$TEST_NAME" "mode 4 scheduling observer is disabled"
            return 1
        fi
        if [ "$MODE4_OOO" = 1 ]; then
            printf '1\n' > /sys/module/klock_module/parameters/jit_mutex_ooo
        fi
        info "Running deterministic A/B nested contention..."
        run_nested_mutex_contention "$mode" "$nested_out" || return 1
    else
        quota_out="$(mktemp -d /tmp/kdlock-hostcall-quota.XXXXXX)"
        info "Evidence: $quota_out"
        python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" ready \
            --artifact "$artifacts" --output "$quota_out/published.json" || return 1
        info "Running repeated mode 5 hostcall contention..."
        run_mode5_hostcall_contention || return 1
        info "Running mode 5 pre-dispatch CALL quota continuation..."
        run_mode5_quota_contention "$quota_out" || return 1
        # Quota is not a callee-learning miss: the same registration must still
        # be NORMAL after all waiter suffixes and owner acknowledgements.
        python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" ready \
            --artifact "$artifacts" --output "$quota_out/published-after.json" || return 1
    fi
    sleep 1

    if [ "$mode" -eq 5 ]; then
        runtime_write_count="$(jit_install_count)"
        runtime_target_count="$(grep -c '^Translation input: entry=0x' \
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
        local jit_success nested_queued nested_jit

        dmesg > "$nested_out/final.log"
        python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" nested \
            --output "$nested_out" || return 1
        jit_success="$(get_dmesg_stat jit_success)"
        nested_queued="$(get_dmesg_stat nested_queued)"
        nested_jit="$(get_dmesg_stat nested_jit)"
        if [ -z "$jit_success" ] || [ "$jit_success" -lt 1 ]; then
            fail "$TEST_NAME" \
                "mode $mode: expected an outer JIT completion including native B, got ${jit_success:-missing}"
            return 1
        fi
        if [ -z "$nested_queued" ] || [ "$nested_queued" -lt 1 ] ||
           [ -z "$nested_jit" ] || [ "$nested_jit" -lt 1 ]; then
            fail "$TEST_NAME" \
                "mode $mode: nested B did not contend natively and resume JIT"
            return 1
        fi
        check_dmesg_stat_equals "jit_resume" "1" \
            "mode $mode: outer waiter did not resume exactly once" || return 1
        if [ "$MODE4_OOO" = 1 ]; then
            check_dmesg_has "kd_native stats: started=0 completed=0 unlocks=0" \
                "mode 4 OOO must complete entirely through JIT" || return 1
        fi
    else
        local jit_success jit_resume max_waiters

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

        dmesg > "$quota_out/final.log"
        python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" quota \
            --output "$quota_out" --artifact "$artifacts" || return 1
    fi
    check_mutex_jit_clean_stats "$mode" || return 1
    check_dmesg_has "kd_exec invariant_failures=0" \
        "mode $mode: execution-frame invariant failed" || return 1
    while IFS= read -r asm_dir; do
        check_jit_entry_executed "$asm_dir" || return 1
    done <<< "$artifacts"

    if [ "$mode" -eq 4 ]; then
        expected_counter=$((1 + 12000 + MODE4_ROLES + MODE4_OOO))
        expected_cs_states=2
    else
        expected_counter=$((1 + 12000 +
            MODE5_ROUNDS * MODE5_ROUND_THREADS * MODE5_ROUND_LOOPS +
            1 + MODE5_PINNED_THREADS * MODE5_PINNED_LOOPS +
            MODE5_STRESS_THREADS * MODE5_STRESS_LOOPS +
            1 + MODE5_QUOTA_THREADS))
    fi
    actual_counter="$(dmesg | sed -n \
        's/.*final counter: \([0-9][0-9]*\).*/\1/p' | tail -n 1)"
    if [ "$actual_counter" != "$expected_counter" ]; then
        fail "$TEST_NAME" \
            "mode $mode: counter mismatch, expected $expected_counter, got ${actual_counter:-missing}"
        return 1
    fi
    check_complex_cs_integrity "$expected_counter" "$expected_cs_states" || return 1

    if [ "$mode" -eq 5 ]; then
        local api_observations api_calls expected_calls

        # Normal JIT and quota-native suffixes must each consume one correct
        # full-width scalar result; the existing clock-call counts stay separate.
        check_dmesg_has "kd_scalar service: mode=5 calls=$expected_counter failures=0" \
            "mode 5 lost/repeated a scalar result or corrupted its 64-bit ABI" || return 1
        api_observations="$(dmesg | sed -n \
            's/.*mode5 api observations: \([0-9][0-9]*\).*/\1/p' |
            tail -n 1)"
        if [ "$api_observations" != "$expected_counter" ]; then
            fail "$TEST_NAME" \
                "mode 5: post-hostcall observation mismatch, expected $expected_counter, got ${api_observations:-missing}"
            return 1
        fi
        api_calls="$(dmesg | sed -n \
            's/.*mode5 api calls: \([0-9][0-9]*\).*/\1/p' | tail -n 1)"
        expected_calls=$((expected_counter + 16 * (1 + MODE5_QUOTA_THREADS)))
        if [ "$api_calls" != "$expected_calls" ]; then
            fail "$TEST_NAME" \
                "mode 5: repeated/skipped service call, expected $expected_calls, got ${api_calls:-missing}"
            return 1
        fi
        info "  mode 5: normal JIT returns and quota native suffixes both verified"
    fi

    info "  mode $mode translated execution passed"
    if [ "$mode" = 4 ] && [ "$MODE4_OOO" = 0 ]; then
        # start_daemon replaces workspaces. Preserve this independent phase's
        # images with its final dmesg before loading the shared-B session.
        (cd "$KDLOCK_DIR" && find daemon -path 'daemon/0x*' -type f -print0 |
            tar --null -T - -czf "$nested_out/artifacts.tar.gz") || return 1
        run_mode4_shared_b || return 1
    fi
    return 0
}

case "${1:-all}" in
4)
    run_jit_mode 4 "mutex-nested" 1 || exit 1
    ;;
5)
    run_jit_mode 5 "mutex-api-in-lock" 1 || exit 1
    ;;
11)
    bash "$KDLOCK_DIR/tests/live/test_24_gs_jit.sh" 11 || exit 1
    ;;
all)
    run_jit_mode 4 "mutex-nested" 1 || exit 1
    run_jit_mode 5 "mutex-api-in-lock" 1 || exit 1
    bash "$KDLOCK_DIR/tests/live/test_24_gs_jit.sh" 11 || exit 1
    ;;
*)
    fail "$TEST_NAME" "usage: $0 [4|5|11|all]"
    exit 1
    ;;
esac

pass "$TEST_NAME"
exit "$EXIT_CODE"
