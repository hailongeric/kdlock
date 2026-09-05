#!/bin/bash
# Recovery-only: ordinary CALL miss must continue, never replay partial stores.
TEST_NAME="test_10_native_resume"
source "$(dirname "$0")/common.sh"

if [ "${KDLOCK_RECOVERY_CONFIRMED:-0}" != 1 ]; then
    fail "$TEST_NAME" "confirm a recovery snapshot with KDLOCK_RECOVERY_CONFIRMED=1"
    exit 1
fi
mode="${1:-0}"
stage="${2:-1}"
pinned="${KD_NATIVE_PINNED:-0}"
renamed="${KD_NATIVE_RENAME:-0}"
mixed="${KD_NATIVE_MIXED:-0}"
if [ "$mixed" != 0 ] && { [ "$mixed" != 1 ] || [ "$mode:$stage:$pinned:$renamed" != 3:1:0:0 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_MIXED=1 requires unpinned mode 3 stage 1 without rename"
    exit 1
fi
if [ "$renamed" != 0 ] && { [ "$renamed" != 1 ] || { [ "$mode" != 3 ] && [ "$mode" != 4 ]; }; }; then
    fail "$TEST_NAME" "KD_NATIVE_RENAME=1 requires mutex mode 3 or 4"
    exit 1
fi
if [ "$pinned" != 0 ] && { [ "$pinned" != 1 ] || [ "$mode:$stage" != 3:1 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_PINNED=1 requires mode 3 stage 1"
    exit 1
fi
case "$mode:$stage" in
    0:1|3:1|1:2|1:3|4:2|4:3|8:2|8:3) ;;
    *) fail "$TEST_NAME" "use mode 0/3 stage 1 or mode 1/4/8 stage 2/3"; exit 1 ;;
esac
out="$(mktemp -d "/tmp/kdlock-native-mode${mode}-stage${stage}.XXXXXX")"
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"

retain_and_cleanup() {
    local status=$?
    stop_daemon
    # A blocked kernel caller may still own a continuation. Do not force unload.
    if ! pgrep -x klock_test >/dev/null; then
        unload_modules
    fi
    dmesg > "$out/dmesg.log"
    find "$DAEMON_DIR" -path '*/0x*' -type f -print0 |
        sort -z | xargs -0 -r sha256sum > "$out/artifacts.sha256"
    (cd "$KDLOCK_DIR"
     find daemon -path 'daemon/0x*' -type f -print0 |
         tar --null -T - -czf "$out/artifacts.tar.gz")
    printf '%s\n' "$status" > "$out/exit-status"
}
trap retain_and_cleanup EXIT

build_all
unload_modules
clear_dmesg
insmod "$KM_DIR/kdlock_km.ko" target_process="$TARGET_PROCESS" mutex_jit=1
insmod "$KLOCK_DIR/klock_module.ko" native_resume_stage="$stage"
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
probe_ip="$(awk '$3 == "kd_resume_native_probe" { print $1 }' /proc/kallsyms)"
test -n "$probe_ip"
{
    date --iso-8601=seconds
    uname -a
    printf 'mode=%s stage=%s mutex_jit=1 pinned=%s rename=%s mixed=%s\n' \
        "$mode" "$stage" "$pinned" "$renamed" "$mixed"
} > "$out/environment.log"
start_daemon 2

promotion_mode="$mode"
artifacts=1
threads=8
states=1
operations=12009
requests=12009
case "$mode" in
    1) artifacts=2 ;;
    8) promotion_mode=1; artifacts=6 ;;
esac
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 "$promotion_mode" > "$out/warmup.log"
sleep 1
run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 "$promotion_mode" > "$out/promotion.log"
if [ "$mode" = 8 ]; then
    for role in 0 2 4; do
        run_with_timeout 10 "$BENCH_BIN" 1 1 10 1 8 "$role" >> "$out/registration.log"
    done
fi
artifact_output="$(wait_for_jit_artifact_count "$artifacts" 30)"
mapfile -t asm_dirs <<< "$artifact_output"
for asm_dir in "${asm_dirs[@]}"; do
    check_jit_artifacts "$asm_dir"
done
sleep 1
check_daemon_read_kernel_text "$DAEMON_LOG"
check_dmesg_has "$JIT_INSTALL_PATTERN"
stop_daemon
if [ "$renamed" = 1 ]; then
    printf '1\n' > /sys/module/klock_module/parameters/native_resume_rename
fi

if [ "$pinned" = 1 ]; then
    timeout --kill-after=5s 90s taskset -c 0 "$BENCH_BIN" \
        1 1 200000000 1 3 > "$out/holder.log" 2>&1 &
    holder=$!
    sleep 0.1
    run_with_timeout 90 taskset -c 1 "$BENCH_BIN" \
        4 1 1000000 1 3 > "$out/workload.log"
    wait "$holder"
    operations=12006
    requests=12006
elif [ "$mode" = 4 ]; then
    # A's delegation queue contends on native B, pinned to separate CPUs.
    pids=()
    for role in 1 3 2 4 0 5 6; do
        timeout --kill-after=5s 60s taskset -c "$role" "$BENCH_BIN" \
            1 1 50000 1 4 "$((2147483648 + role))" \
            > "$out/role-$role.log" 2>&1 &
        pids+=("$!")
    done
    failed=0
    for pid in "${pids[@]}"; do
        wait "$pid" || failed=1
    done
    test "$failed" = 0
    operations=12008
    requests=12002
    states=2
elif [ "$mode" = 8 ]; then
    run_with_timeout 60 "$BENCH_BIN" 9 1 50000 1 8 2147483648 > "$out/workload.log"
    operations=12013
    requests=12003
    states=2
elif [ "$mixed" = 1 ]; then
    run_with_timeout 60 env KD_TEST_MIXED=1 "$BENCH_BIN" \
        "$threads" 1 1000000 1 "$mode" > "$out/workload.log"
else
    run_with_timeout 60 "$BENCH_BIN" "$threads" 1 1000000 1 "$mode" > "$out/workload.log"
fi

unload_modules
check_dmesg_ok
check_any_jit_entry_executed "${asm_dirs[@]}"
check_complex_cs_integrity "$operations" "$states"
check_dmesg_has "kd_resume records: requests=$requests failures=0"
check_dmesg_has 'kd_native stats: started=[1-9][0-9]* completed=[1-9][0-9]*'
check_dmesg_has "kd_native begin:.* ip=$probe_ip "
if [ "$pinned" = 1 ]; then
    check_dmesg_has 'kd_native begin:.*mutex=1 cpu=1'
fi
started="$(dmesg | sed -n 's/.*kd_native stats: started=\([0-9]*\).*/\1/p' | tail -1)"
completed="$(dmesg | sed -n 's/.*kd_native stats:.*completed=\([0-9]*\).*/\1/p' | tail -1)"
test "$started" = "$completed"
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_not_has 'JIT retry\|abort release\|non-continuable exit'
if [ "$mode" = 3 ] || [ "$mode" = 4 ]; then
    check_mutex_origin_accounting
    if [ "$renamed" = 1 ]; then
        check_dmesg_has 'task_reroutes=[1-9][0-9]*'
    fi
    check_dmesg_stat_equals active_waiters 0
    check_dmesg_stat_equals reserved_nodes 0
    check_dmesg_stat_equals jit_failure 0
    check_dmesg_stat_equals frame_failure 0
else
    check_dmesg_has 'kd_spin diag invariant_failures=0'
    check_dmesg_has 'kd_spin diag overflow=0'
fi
if [ "$stage" = 3 ] && [ "$mode" = 8 ]; then
    # Both B and its suspended parent A must join the native handoff chain.
    test "$started" -ge 2
    test "$(dmesg | sed -n 's/.*kd_native begin:.*outer=\([0-9a-f]*\).*/\1/p' | sort -u | wc -l)" -ge 2
fi
pass "$TEST_NAME mode=$mode stage=$stage native=$started records=$requests"
