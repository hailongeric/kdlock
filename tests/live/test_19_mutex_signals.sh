#!/bin/bash
# Native signal cancellation while the combiner retains L for a JIT continuation.
TEST_NAME=test_19_mutex_signals
source "$(dirname "$0")/../common.sh"
probe=${1:-1}
cpus=${KD_SIGNAL_CPUS:-0,1,2,3,4,5}
comm=${KD_SIGNAL_COMM:-kd_native}
race=${KD_SIGNAL_RACE:-0}
handoff=${KD_SIGNAL_HANDOFF:-0}
controls=()
case "$race:$handoff" in
    0:0) ;;
    1:0) controls+=(--race) ;;
    1:1) controls+=(--race --handoff) ;;
    *) fail "$TEST_NAME" 'race/handoff must be 0/1, handoff requires race'; exit 1 ;;
esac
case "$probe" in 1|2|3|4) ;; *) fail "$TEST_NAME" 'use probe 1..4'; exit 1 ;; esac
test "${KDLOCK_RECOVERY_CONFIRMED:-0}" = 1 || {
    fail "$TEST_NAME" 'confirm a recovery snapshot'; exit 1;
}
grep -Eq '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt
test -z "$(lsmod | grep -E '^(kdlock_km|klock_module) ')"
if pgrep -x 'klock_test|kd_native|kd_renamed|daemon' >/dev/null; then
    fail "$TEST_NAME" 'existing callers must drain before this test'
    exit 1
fi
out=$(mktemp -d /tmp/kdlock-mutex-signals.XXXXXX)
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"
cleanup() {
    local status=$?
    stop_daemon
    if ! pgrep -x 'klock_test|kd_native|kd_renamed' >/dev/null; then
        unload_modules
    else
        fail "$TEST_NAME" 'live callers remain; retain modules for recovery'
        status=1
    fi
    dmesg > "$out/dmesg.log"
    printf '%s\n' "$status" > "$out/exit-status"
}
trap cleanup EXIT
build_all
gcc -O2 -Wall -Wextra -Werror "$KDLOCK_DIR/tests/clients/mutex_signal_client.c" -o "$out/client"
clear_dmesg
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1
insmod "$KLOCK_DIR/klock_module.ko" native_resume_stage=1 mutex_signal_probe="$probe" \
    mutex_signal_race="$race" mutex_signal_handoff="$handoff"
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
probe_ip=$(awk '$3 == "kd_resume_native_probe" && $4 == "[klock_module]" { print $1 }' /proc/kallsyms)
test -n "$probe_ip"
start_daemon 2
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 3 > "$out/warmup.log"
run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 3 > "$out/promotion.log"
artifact=$(wait_for_jit_artifacts 30)
check_jit_artifacts "$artifact"
check_daemon_read_kernel_text "$DAEMON_LOG"
run_with_timeout 35 python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" ready \
    --artifact "$artifact" --output "$out/ready.json"
stop_daemon
run_with_timeout 100 python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" run \
    --bench "$BENCH_BIN" --client "$out/client" --probe "$probe" \
    --cpus "$cpus" --comm "$comm" --output "$out" "${controls[@]}" \
    --race-us "${KD_SIGNAL_RACE_US:-0}" --expect "${KD_SIGNAL_EXPECT:-either}"
unload_modules
dmesg > "$out/dmesg.log"
check_any_jit_entry_executed "$artifact"
python3 "$KDLOCK_DIR/tests/protocols/mutex_signal_protocol.py" validate --dmesg "$out/dmesg.log" \
    --identities "$out/identities.json" --probe-ip "$probe_ip" --result "$out/operations"
check_dmesg_ok
check_complex_cs_integrity "$(cat "$out/operations")" 1
check_dmesg_has 'kd_resume records: requests=12005 failures=0'
check_dmesg_has 'kd_mutex oracle: inside=0 overlaps=0'
check_mutex_origin_accounting
for stat in active_waiters reserved_nodes frame_failure jit_failure; do
    check_dmesg_stat_equals "$stat" 0
done
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_not_has 'kd_signal error:'
pass "$TEST_NAME probe=$probe comm=$comm cpus=$cpus race=$race handoff=$handoff mutex_jit=1 translated prefix executed"
