#!/bin/bash
# test_04_spinlock.sh — verify spinlock translation and delegation modes.
TEST_NAME="test_04_spinlock"
source "$(dirname "$0")/common.sh"

build_all || exit 1

run_spinlock_mode() {
    local mode=$1
    local mode_name=$2
    local expected_artifacts expected_locks expected_counter actual_counter
    local artifact_output
    local artifact_timeout=20
    local diag_count nested_diag_count
    local jit_writes_before=0 jit_writes_after=0
    local -a asm_dirs
    local exec_threads=8
    local exec_loops=1
    local exec_workload=1000000
    local exec_syscount=1
    local exec_role_base=0
    local warmup_threads=1
    local promotion_threads=1
    local promotion_loops=12000
    local promotion_mode=$mode
    local registration_calls=0
    local nested_registration_role=0
    local expected_cs_states=1
    local mode8_not_ready="${KD_MODE8_NOT_READY:-0}"
    local abort_inject="${KD_SPIN_ABORT_INJECT:-0}"
    local jit_fault_kind="${KD_JIT_FAULT_KIND:-0}"
    local abort_expected=0

    if [ "$abort_inject" -eq 1 ] || [ "$jit_fault_kind" -ne 0 ]; then
        abort_expected=1
    fi

    if [ "$abort_expected" -eq 1 ]; then
        fail "$TEST_NAME" \
            "legacy synthetic aborts are fail-stop; use test_10_native_resume.sh for recoverable CALL misses"
        return 1
    fi

    if [ "$abort_expected" -eq 1 ]; then
        if [ "$mode" -ne 9 ] &&
                ! { [ "$mode" -eq 8 ] && [ "$mode8_not_ready" -eq 1 ]; }; then
            fail "$TEST_NAME" \
                "abort injection requires mode 9, or mode 8 with KD_MODE8_NOT_READY=1"
            return 1
        fi
    fi
    if [ "$jit_fault_kind" -lt 0 ] || [ "$jit_fault_kind" -gt 3 ]; then
        fail "$TEST_NAME" "KD_JIT_FAULT_KIND must be 0, 1, 2, or 3"
        return 1
    fi

    case "$mode" in
        0|2) expected_artifacts=1 ;;
        1|7) expected_artifacts=2 ;;
        6) expected_artifacts=3 ;;
        8)
            expected_artifacts=6
            # Six serial translations now include guarded A/B/C CFG analysis.
            # Bound initialization separately; do not relax execution/oracle gates.
            artifact_timeout=90
            warmup_threads=2
            promotion_mode=1
            registration_calls=3
            exec_threads=9
            exec_role_base=2147483648
            exec_workload=50000
            expected_cs_states=2
            if [ "$mode" -eq 8 ] && [ "$mode8_not_ready" -eq 1 ]; then
                expected_artifacts=5
                nested_registration_role=1073741824
            fi
            ;;
        9)
            expected_artifacts=2
            exec_threads=5
            exec_role_base=2147483648
            exec_workload=50000
            expected_cs_states=2
            ;;
        *) expected_artifacts=1 ;;
    esac
    expected_locks=$expected_artifacts
    if [ "$mode" -eq 8 ]; then
        expected_locks=2
    fi

    DAEMON_LOG="$(mktemp "/tmp/kdlock-test04-mode${mode}.XXXXXX.log")"

    info "Testing mode $mode ($mode_name)..."
    clear_dmesg
    load_modules || return 1
    start_daemon 2

    info "  Priming hot-lock timer..."
    run_with_timeout 10 "$BENCH_BIN" \
        "$warmup_threads" 1 1 1 "$mode" >/dev/null 2>&1 || {
        fail "$TEST_NAME" "mode $mode ($mode_name) warmup failed"
        stop_daemon
        unload_modules
        return 1
    }
    sleep 1

    info "  Promoting and translating..."
    run_with_timeout 20 "$BENCH_BIN" \
        "$promotion_threads" "$promotion_loops" 10 1 "$promotion_mode" \
        >/dev/null 2>&1 || {
        fail "$TEST_NAME" "mode $mode ($mode_name) promotion workload failed"
        stop_daemon
        unload_modules
        return 1
    }

    if [ "$registration_calls" -gt 0 ]; then
        info "  Registering translated entry points without contention..."
        run_with_timeout 10 "$BENCH_BIN" 1 1 10 1 "$mode" \
            "$nested_registration_role" \
            >/dev/null 2>&1 || {
            fail "$TEST_NAME" "mode $mode nested entry registration failed"
            stop_daemon
            unload_modules
            return 1
        }
        run_with_timeout 10 "$BENCH_BIN" 1 1 10 1 "$mode" 2 \
            >/dev/null 2>&1 || {
            fail "$TEST_NAME" "mode $mode direct entry registration failed"
            stop_daemon
            unload_modules
            return 1
        }
        run_with_timeout 10 "$BENCH_BIN" 1 1 10 1 "$mode" 4 \
            >/dev/null 2>&1 || {
            fail "$TEST_NAME" "mode $mode outer entry registration failed"
            stop_daemon
            unload_modules
            return 1
        }
    fi

    check_dmesg_has "begin delegate" \
        "mode $mode ($mode_name) did not promote its spinlock" || {
        stop_daemon
        unload_modules
        return 1
    }

    local artifact_started=$SECONDS
    if ! artifact_output="$(wait_for_jit_artifact_count "$expected_artifacts" "$artifact_timeout")"; then
        fail "$TEST_NAME" \
            "mode $mode ($mode_name) incomplete JIT artifacts after ${artifact_timeout}s (daemon: $DAEMON_LOG)"
        stop_daemon
        unload_modules
        return 1
    fi
    mapfile -t asm_dirs <<< "$artifact_output"
    info "  JIT artifacts ready after $((SECONDS - artifact_started))s (limit ${artifact_timeout}s)"

    check_daemon_read_kernel_text "$DAEMON_LOG" || {
        stop_daemon
        unload_modules
        return 1
    }
    for asm_dir in "${asm_dirs[@]}"; do
        check_jit_artifacts "$asm_dir" || {
            stop_daemon
            unload_modules
            return 1
        }
        check_complex_cs_artifact "$asm_dir" || return 1
        if [ "$mode" -eq 2 ]; then
            check_jit_hostcall_artifact "$asm_dir" "ktime_get" || {
                stop_daemon
                unload_modules
                return 1
            }
            check_jit_hostcall_artifact "$asm_dir" "int_sqrt" || return 1
        fi
    done
    check_dmesg_has "$JIT_INSTALL_PATTERN" \
        "mode $mode ($mode_name) did not write JIT code back" || {
        stop_daemon
        unload_modules
        return 1
    }
    if [ "$mode" -eq 2 ]; then
        jit_writes_before="$(jit_install_count)"
    fi

    if [ "$abort_inject" -eq 1 ]; then
        info "  Injecting one failure after nested B acquisition..."
        echo 1 > /sys/module/kdlock_km/parameters/spin_jit_fail_after_nested_lock
    elif [ "$jit_fault_kind" -ne 0 ]; then
        info "  Injecting JIT runtime fault kind $jit_fault_kind after nested B acquisition..."
        echo "$jit_fault_kind" > \
            /sys/module/kdlock_km/parameters/jit_hl_fault_after_known_call
        stop_daemon
    fi

    info "  Running translated workload..."
    # Measure only the prepared payload, not promotion/translation. Keep the
    # kernel witness/oracle gates: ioctl timings alone never establish JIT.
    local workload_log="${DAEMON_LOG}.workload.log"
    info "Evidence file: $workload_log"
    info "Evidence file: ${workload_log}.before.dmesg"
    info "Evidence file: ${workload_log}.after.dmesg"
    dmesg > "${workload_log}.before.dmesg" || return 1
    run_with_timeout "$TIMEOUT_SEC" env KD_TEST_METRICS=1 "$BENCH_BIN" \
        "$exec_threads" "$exec_loops" "$exec_workload" "$exec_syscount" \
        "$mode" "$exec_role_base" \
        >"$workload_log" 2>&1 || {
        fail "$TEST_NAME" "mode $mode ($mode_name) translated workload failed or timed out"
        stop_daemon
        unload_modules
        return 1
    }
    dmesg > "${workload_log}.after.dmesg" || return 1
    sleep 2

    if [ "$mode" -eq 2 ]; then
        jit_writes_after="$(jit_install_count)"
        if [ "$jit_writes_after" != "$jit_writes_before" ]; then
            fail "$TEST_NAME" \
                "mode 2 hostcall triggered runtime JIT recompilation"
            stop_daemon
            unload_modules
            return 1
        fi
    fi

    stop_daemon
    unload_modules

    check_dmesg_ok || return 1
    check_dmesg_has "kd_spin diag overflow=0" \
        "spinlock diagnostic table overflowed" || return 1
    check_dmesg_has "kd_spin diag invariant_failures=0" \
        "spinlock delegation invariant failed" || return 1
    check_dmesg_has "kd_exec invariant_failures=0" \
        "execution-frame invariant failed" || return 1

    local diag_lines jit_lock
    diag_lines="$(dmesg | grep -E "kd_spin lock stats:" || true)"
    if [ -z "$diag_lines" ]; then
        fail "$TEST_NAME" \
            "mode $mode ($mode_name) missing spinlock delegation statistics"
        return 1
    fi
    if [ "$mode" -eq 0 ] || [ "$mode" -eq 1 ]; then
        jit_lock="$(printf '%s\n' "$diag_lines" | sed -n \
            's/.*lock=\([0-9a-f]*\) depth=1 .*jit_success=[1-9][0-9]*.*/\1/p' | \
            head -n 1)"
        if [ -z "$jit_lock" ]; then
            fail "$TEST_NAME" \
                "mode $mode has no depth-1 lock with JIT completion evidence"
            return 1
        fi
        check_any_jit_entry_executed_for_lock \
            "$jit_lock" "${asm_dirs[@]}" || return 1
    else
        check_any_jit_entry_executed "${asm_dirs[@]}" || return 1
    fi
    if printf '%s\n' "$diag_lines" | grep -Eq "waiters=[1-9][0-9]*"; then
        fail "$TEST_NAME" "mode $mode leaked queued spinlock waiters"
        printf '%s\n' "$diag_lines"
        return 1
    fi
    case "$mode" in
        0|2)
            if ! printf '%s\n' "$diag_lines" |
                    grep -Eq "jit_success=[1-9][0-9]*"; then
                fail "$TEST_NAME" \
                    "mode $mode ($mode_name) missing per-lock JIT diagnostics"
                return 1
            fi
            ;;
        1|6|7|8|9)
            diag_count="$(printf '%s\n' "$diag_lines" | sed '/^$/d' | wc -l)"
            if [ "$diag_count" -ne "$expected_locks" ]; then
                fail "$TEST_NAME" \
                    "mode $mode expected diagnostics for $expected_locks locks"
                printf '%s\n' "$diag_lines"
                return 1
            fi
            if [ "$abort_expected" -eq 0 ]; then
                if [ "$mode" -eq 7 ]; then
                    if ! printf '%s\n' "$diag_lines" |
                            grep -Eq "jit_success=[1-9][0-9]*"; then
                        fail "$TEST_NAME" \
                            "mode 7 has no JIT success evidence"
                        return 1
                    fi
                elif ! printf '%s\n' "$diag_lines" |
                        grep -Eq "depth=1 .*jit_success=[1-9][0-9]*"; then
                    fail "$TEST_NAME" \
                        "mode $mode outer lock has no JIT success evidence"
                    return 1
                fi
            fi
            nested_diag_count="$(printf '%s\n' "$diag_lines" | awk \
                '/nested_lock=[1-9][0-9]*.*nested_unlock=[1-9][0-9]*.*native_fallback=0/ { count++ } END { print count + 0 }')"
            if [ "$nested_diag_count" -ne "$((expected_locks - 1))" ]; then
                fail "$TEST_NAME" \
                    "mode $mode inner locks were not delegated without native fallback"
                printf '%s\n' "$diag_lines"
                return 1
            fi
            ;;
    esac

    if [ "$mode" -eq 7 ] && ! printf '%s\n' "$diag_lines" |
            grep -Eq "ooo_unlock=[1-9][0-9]*"; then
        fail "$TEST_NAME" \
            "mode 7 did not exercise the translated out-of-order unlock path"
        printf '%s\n' "$diag_lines"
        return 1
    fi

    if [ "$mode" -eq 8 ] &&
            [ "$mode8_not_ready" -eq 0 ] &&
            ! printf '%s\n' "$diag_lines" |
            grep -Eq "slowpath=[1-9][0-9]*.*combiner=[1-9][0-9]*.*jit_success=[1-9][0-9]*.*nested_lock=[1-9][0-9]*.*nested_remote=[1-9][0-9]*"; then
        fail "$TEST_NAME" \
            "mode $mode did not remotely execute a nested B waiter through JIT"
        printf '%s\n' "$diag_lines"
        return 1
    fi

    if [ "$mode" -eq 8 ] && [ "$mode8_not_ready" -eq 1 ] &&
            ! printf '%s\n' "$diag_lines" |
            grep -Eq "jit_not_ready=[1-9][0-9]*.*nested_lock=[1-9][0-9]*.*nested_unlock=[1-9][0-9]*.*native_fallback=0"; then
        fail "$TEST_NAME" \
            "mode 8 did not safely hand off an untranslated nested waiter"
        printf '%s\n' "$diag_lines"
        return 1
    fi

    if [ "$abort_expected" -eq 1 ]; then
        if [ "$abort_inject" -eq 1 ]; then
            check_dmesg_has "spin JIT injected failure after nested lock" \
                "mode $mode did not execute the requested nested-lock fault" || return 1
        else
            check_dmesg_has "JIT injected runtime fault: kind=$jit_fault_kind" \
                "mode $mode did not execute JIT fault kind $jit_fault_kind" || return 1
        fi
        check_dmesg_has "spin JIT abort cleanup:.*released=1" \
            "mode $mode did not release B through the abort cleanup path" || return 1
        if [ "$mode" -eq 8 ]; then
            check_dmesg_has "spin JIT abort release:.*kind=2" \
                "mode 8 did not clean up B as a queue owner" || return 1
        fi
        check_dmesg_has "spin JIT retry resume:" \
            "mode $mode did not resume at the saved A critical-section entry" || return 1
        if ! printf '%s\n' "$diag_lines" |
                grep -Eq "native_fallback=[1-9][0-9]*.*jit_disabled=1"; then
            fail "$TEST_NAME" \
                "mode $mode did not disable JIT and drain A through native handoff"
            printf '%s\n' "$diag_lines"
            return 1
        fi
    fi

    expected_counter=$((warmup_threads +
        promotion_threads * promotion_loops +
        registration_calls +
        exec_threads * exec_loops))
    actual_counter="$(dmesg | sed -n 's/.*final counter: \([0-9][0-9]*\).*/\1/p' | tail -n 1)"
    if [ "$actual_counter" != "$expected_counter" ]; then
        fail "$TEST_NAME" \
            "mode $mode ($mode_name) counter mismatch: expected $expected_counter, got ${actual_counter:-missing}"
        return 1
    fi
    check_complex_cs_integrity "$expected_counter" "$expected_cs_states" || return 1

    if [ "$mode" -eq 2 ]; then
        local hostcall_stats hostcall_exits hostcall_executed
        local hostcall_resumed hostcall_rejected hostcall_failed hostcall_limit
        local api_observations jit_completions

        hostcall_stats="$(dmesg | sed -n '/kd_hostcall stats:/p' | tail -n 1)"
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
                [ "$hostcall_resumed" != "$hostcall_exits" ]; then
            fail "$TEST_NAME" \
                "mode 2 did not complete every hostcall exit/execute/resume cycle"
            printf '%s\n' "$hostcall_stats"
            return 1
        fi
        if [ "$hostcall_rejected" != "0" ] ||
                [ "$hostcall_failed" != "0" ] ||
                [ "$hostcall_limit" != "0" ]; then
            fail "$TEST_NAME" "mode 2 hostcall diagnostics reported a failure"
            printf '%s\n' "$hostcall_stats"
            return 1
        fi

        # Each completed translated CS must return from both named services;
        # a native-only scalar suffix cannot masquerade as full JIT success.
        jit_completions="$(printf '%s\n' "$diag_lines" | awk '{
            for (i = 1; i <= NF; i++)
                if ($i ~ /^jit_success=/) { split($i, value, "="); total += value[2] }
        } END { print total + 0 }')"
        if [ "$hostcall_executed" -ne "$((2 * jit_completions))" ]; then
            fail "$TEST_NAME" "mode 2 did not return from two services per JIT completion"
            return 1
        fi
        check_dmesg_has "kd_scalar service: mode=2 calls=$expected_counter failures=0" \
            "mode 2 lost/repeated a scalar result or corrupted its 64-bit ABI" || return 1

        api_observations="$(dmesg | sed -n \
            's/.*mode2 api observations: \([0-9][0-9]*\).*/\1/p' |
            tail -n 1)"
        if [ "$api_observations" != "$expected_counter" ]; then
            fail "$TEST_NAME" \
                "mode 2 post-hostcall observation mismatch: expected $expected_counter, got ${api_observations:-missing}"
            return 1
        fi
        info "  mode 2 hostcalls: exits=$hostcall_exits, all resumed"
    fi

    info "  mode $mode: delegation and translated execution verified"
    return 0
}

run_selected_mode() {
    case "$1" in
        0) run_spinlock_mode 0 "spin-contention" ;;
        1) run_spinlock_mode 1 "spin-nested" ;;
        2) run_spinlock_mode 2 "spin-api-in-lock" ;;
        6) run_spinlock_mode 6 "spin-deep-nested" ;;
        7) run_spinlock_mode 7 "spin-ooo-nested" ;;
        8) run_spinlock_mode 8 "spin-inner-contention" ;;
        9) run_spinlock_mode 9 "spin-abort-recovery" ;;
        10) bash "$KDLOCK_DIR/tests/test_12_context_native_only.sh" 10 ;;
        *)
            fail "$TEST_NAME" "unsupported spinlock mode: $1"
            return 1
            ;;
    esac
}

if [ "$#" -eq 0 ]; then
    set -- 0 1 2 6 7 8
fi
for mode in "$@"; do
    run_selected_mode "$mode" || exit 1
    # Keep the established mode-8 CFG/native-register workload intact. Its
    # second joined phase adds independent logical roots, not a basic smoke.
    if [ "$mode" = 8 ] && [ "${KD_MODE8_NOT_READY:-0}" = 0 ]; then
        first_phase=$(mktemp -d /tmp/kdlock-mode8-first.XXXXXX)
        info "Evidence: $first_phase"
        dmesg > "$first_phase/protocol.log"
        # The next daemon clears generated workspaces and dmesg. Preserve this
        # completed phase first, rather than retaining only its PASS message.
        (cd "$KDLOCK_DIR"
         find daemon -path 'daemon/0x*' -type f -print0 |
             tar --null -T - -czf "$first_phase/artifacts.tar.gz")
        bash "$KDLOCK_DIR/tests/test_20_remote_outer.sh" multi || exit 1
        # Keep pure remote completion distinct from quota/native relay: the
        # latter must pause B's batch and then execute its other root in JIT.
        bash "$KDLOCK_DIR/tests/test_20_remote_outer.sh" multi quota || exit 1
    fi
done

pass "$TEST_NAME"
exit "$EXIT_CODE"
