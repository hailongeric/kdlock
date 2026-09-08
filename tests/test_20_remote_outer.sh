#!/bin/bash
# Recovery-only remote ancestor unlock with an independent owner dependency.
TEST_NAME="test_20_remote_outer"
source "$(dirname "$0")/common.sh"

stage=${1:-1}
native_owner=${KD_REMOTE_NATIVE_OWNER:-0}
renamed=${KD_NATIVE_RENAME:-0}
depth=${KD_REMOTE_DEPTH:-2}
reverse=${KD_REMOTE_REVERSE:-0}
cross_numa=${KD_REMOTE_CROSS_NUMA:-0}
test "${KDLOCK_RECOVERY_CONFIRMED:-0}" = 1
[[ $stage =~ ^[1234]$ && $native_owner =~ ^[01]$ && $renamed =~ ^[01]$ ]]
[[ $depth =~ ^[23]$ && $reverse =~ ^[01]$ ]]
[[ $cross_numa =~ ^[01]$ ]]
test "$stage:$renamed" != 1:1
if test "$depth" = 2; then
    test "$stage" != 4
    test "$reverse" = 0
fi
grep -Eq '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt
test -z "$(lsmod | grep -E '^(kdlock_km|klock_module) ')"
if pgrep -x 'klock_test|daemon|kd_native|kd_renamed'; then
    exit 1
fi
out=$(mktemp -d /tmp/kdlock-remote-outer-stage"$stage".XXXXXX)
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"
finish() {
    local status=$?
    trap - EXIT
    stop_daemon
    if pgrep -x 'klock_test|kd_native|kd_renamed' >/dev/null; then
        fail "$TEST_NAME" "callers remain; retain modules for recovery"
        status=1
    else
        unload_modules
    fi
    dmesg > "$out/dmesg.log"
    (cd "$KDLOCK_DIR"
     find daemon -path 'daemon/0x*' -type f -print0 |
         tar --null -T - -czf "$out/artifacts.tar.gz")
    printf '%s\n' "$status" > "$out/exit-status"
    exit "$status"
}
trap finish EXIT
placement_output=$(PYTHONPATH="$KDLOCK_DIR/tests" python3 - \
    "$depth" "${KD_REMOTE_CPUS:-}" "$cross_numa" "$out/placement.json" <<'PY'
import json, sys
from pathlib import Path
from remote_outer_protocol import capture_placement

placement = capture_placement(sys.argv[2], int(sys.argv[1]), bool(int(sys.argv[3])))
Path(sys.argv[4]).write_text(json.dumps(placement, indent=2, sort_keys=True) + "\n")
print(",".join(map(str, placement["role_cpus"])))
PY
)
IFS=, read -r -a role_cpus <<< "$placement_output"
info "Role CPUs: $placement_output; require_cross_numa=$cross_numa"
build_all
unload_modules
clear_dmesg
resume_stage=3
test "$stage" != 1 || resume_stage=0
insmod "$KM_DIR/kdlock_km.ko" target_process="$TARGET_PROCESS" mutex_jit=1
insmod "$KLOCK_DIR/klock_module.ko" native_resume_stage="$resume_stage"
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
start_daemon 2
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 1 > "$out/warmup.log"
sleep 1
run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 1 > "$out/promotion.log"
if test "$depth" = 3; then
    # Global warmup is over: a pause after C's first sample marks it cold.
    run_with_timeout 30 "$BENCH_BIN" 1 12001 10 1 8 11 > "$out/c-promotion.log"
fi
for role in 0 2 4; do
    run_with_timeout 10 "$BENCH_BIN" 1 1 10 1 8 "$role" >> "$out/registration.log"
done
artifact_output=$(wait_for_jit_artifact_count "$((depth + 4))" 30)
mapfile -t asm_dirs <<< "$artifact_output"
for asm_dir in "${asm_dirs[@]}"; do
    check_jit_artifacts "$asm_dir"
    PYTHONPATH="$KDLOCK_DIR/tests" python3 -c '
import json, sys
from mutex_signal_protocol import wait_ready
print(json.dumps(wait_ready(sys.argv[1], lock_kind=1)))
' "$asm_dir" >> "$out/published.jsonl"
done
sleep 1
check_daemon_read_kernel_text "$DAEMON_LOG"
check_dmesg_has "$JIT_INSTALL_PATTERN"
stop_daemon
printf '%s\n' "$stage" > /sys/module/klock_module/parameters/remote_spin_ooo
printf '%s\n' "$native_owner" > /sys/module/klock_module/parameters/remote_spin_native_owner
printf '%s\n' "$renamed" > /sys/module/klock_module/parameters/native_resume_rename
printf '%s\n' "$((depth - 2))" > /sys/module/klock_module/parameters/remote_spin_deep
printf '%s\n' "$reverse" > /sys/module/klock_module/parameters/remote_spin_reverse
pids=()
roles=(1 2 5 3 4 6 0 7 8)
test "$depth" = 2 || roles=(10 11 12 "${roles[@]}" 13)
test "$native_owner" = 0 || roles=(9 "${roles[@]}")
for role in "${roles[@]}"; do
    role_comm=$TARGET_PROCESS
    test "$role" != 9 || role_comm=kd_native
    timeout --kill-after=5s 60s env KD_TEST_COMM="$role_comm" \
        taskset -c "${role_cpus[$role]}" "$BENCH_BIN" 1 1 50000 1 8 "$((2147483648 + role))" \
        > "$out/role-$role.log" 2>&1 &
    pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
    wait "$pid" || failed=1
done
test "$failed" = 0
check_any_jit_entry_executed "${asm_dirs[@]}"
unload_modules
check_complex_cs_integrity "$((12014 + native_owner + 12007 * (depth - 2)))" "$depth"
records=12003
test "$stage" != 1 || records=0
check_dmesg_has "kd_resume records: requests=$records failures=0"
check_dmesg_has 'kd_spin oracle: inside=0 overlaps=0 origin_missing=0 context_failures=0'
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_has 'kd_spin diag invariant_failures=0'
check_dmesg_not_has 'JIT retry\|abort release\|non-continuable exit\|jit_disabled=1'
check_dmesg_ok
dmesg > "$out/protocol.log"
options=(--placement "$out/placement.json")
test "$depth" = 2 || options+=(--depth 3)
test "$reverse" = 0 || options+=(--reverse)
test "$native_owner" = 0 || options+=(--native-owner)
test "$renamed" = 0 || options+=(--renamed)
python3 "$KDLOCK_DIR/tests/remote_outer_protocol.py" "$out/protocol.log" "$stage" "${options[@]}"
pass "$TEST_NAME stage=$stage depth=$depth reverse=$reverse native_owner=$native_owner rename=$renamed cross_numa=$cross_numa"
