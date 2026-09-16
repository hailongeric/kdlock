#!/bin/bash
# Recovery-only: one logical waiter across four to eight actual executors.
TEST_NAME=test_21_remote_depth
source "$(dirname "$0")/../common.sh"
depth=${1:-4}
stage=${2:-1}
owner=${KD_DEEP_NATIVE_OWNER:-0}
reverse=${KD_DEEP_REVERSE:-0}
renamed=${KD_NATIVE_RENAME:-0}
cross=${KD_DEEP_CROSS_NUMA:-0}
defer=${KD_DEEP_DEFER_LAYER:-}
defer_count=${KD_DEEP_DEFER_COUNT:-1}
nodes=${KD_DEEP_TRACE_NODES:-0}
refusal=${KD_DEEP_REFUSAL:-0}
refusal_numa=${KD_DEEP_REFUSAL_NUMA:-0}
readmit=${KD_DEEP_READMIT:-0}
readmit_layer=${KD_DEEP_READMIT_LAYER:-3}
waiter_exit=${KD_DEEP_WAITER_EXIT:-0}
[[ $waiter_exit =~ ^[01]$ ]]
# Only the existing all-ancestors-unlocked case can delay its root without
# withholding an owner ACK. Keep this opt-in out of other remote schedules.
if [[ $waiter_exit == 1 ]]; then
    test "$depth:$stage:$owner:$reverse:$renamed:$cross:$readmit:$refusal:$nodes" = 4:3:1:1:1:1:0:0:0
    test -z "$defer"
fi
[[ $readmit =~ ^[012]$ ]]
[[ $readmit_layer =~ ^[123]$ ]]
if [[ $readmit != 0 ]]; then
    test "$depth:$stage:$renamed:$refusal:$refusal_numa" = 4:1:0:0:0
    test -z "$defer"
    test -n "${KD_DEEP_CPUS:-}"
else
    test "$readmit_layer" = 3
fi
[[ $refusal =~ ^[012]$ && $refusal_numa =~ ^[01]$ ]]
if [[ $refusal != 0 ]]; then
    test "$depth:$stage:$renamed" = 4:1:0
    test -z "$defer"
else
    test "$refusal_numa" = 0
fi
[[ $nodes =~ ^[01]$ ]]
test "${KDLOCK_RECOVERY_CONFIRMED:-0}" = 1
[[ $depth =~ ^[4-8]$ && $stage =~ ^[1-5]$ ]]
[[ $owner =~ ^[01]$ && $reverse =~ ^[01]$ && $renamed =~ ^[01]$ && $cross =~ ^[01]$ ]]
[[ $defer_count =~ ^[1-8]$ ]]
test "$stage:$renamed" != 1:1
test "$stage:$depth" != 1:8
test "$stage" != 5 || test "$depth" = 8
if [[ -n $defer ]]; then
    [[ $defer =~ ^[0-7]$ ]] && ((defer < depth))
    test -n "${KD_DEEP_CPUS:-}"
else
    test "$defer_count" = 1
fi
test "$TARGET_PROCESS" = klock_test
grep -Eq '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt
test -z "$(lsmod | grep -E '^(kdlock_km|klock_module) ')"
if pgrep -x 'klock_test|daemon|kd_native|kd_renamed'; then exit 1; fi
out=$(mktemp -d /tmp/kdlock-remote-depth-"$depth"-"$stage".XXXXXX)
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"
finish() {
    local rc=$?
    trap - EXIT
    stop_daemon
    if pgrep -x 'klock_test|kd_native|kd_renamed' >/dev/null; then
        fail "$TEST_NAME" 'callers remain; retain modules for recovery'
        rc=1
    else
        unload_modules
        if [[ -n $defer || $nodes == 1 || $refusal != 0 || $readmit != 0 || $waiter_exit == 1 ]]; then
            make -C "$KM_DIR" KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8 > "$out/build-default.log" 2>&1 || rc=1
        fi
    fi
    dmesg > "$out/dmesg.log"
    (cd "$KDLOCK_DIR"
     find daemon -path 'daemon/0x*' -type f -print0 |
         tar --null -T - -czf "$out/artifacts.tar.gz")
    printf '%s\n' "$rc" > "$out/exit-status"
    exit "$rc"
}
trap finish EXIT
placement=$(PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - \
    "$depth" "${KD_DEEP_CPUS:-}" "$cross" "$out/placement.json" "$defer" "$defer_count" "$readmit" "$readmit_layer" <<'PY'
import json, sys
from pathlib import Path
from remote_depth_protocol import capture_placement

p = capture_placement(sys.argv[2], int(sys.argv[1]), bool(int(sys.argv[3])),
                      int(sys.argv[5]) if sys.argv[5] else None, int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8]))
Path(sys.argv[4]).write_text(json.dumps(p, indent=2, sort_keys=True) + "\n")
print(",".join(map(str, p["role_cpus"])))
PY
)
IFS=, read -r -a cpus <<< "$placement"
node_protocol="$KDLOCK_DIR/tests/protocols/spin_node_protocol.py"
python3 "$node_protocol" profile "$nodes" remote > "$out/node-profile.json"
info "Role CPUs: $placement; cross_numa=$cross"
control=$(PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$out/placement.json" <<'PY'
import json, sys
from remote_depth_protocol import select_control_cpu
with open(sys.argv[1]) as source:
    print(select_control_cpu(json.load(source)))
PY
)
build_all
parameters=(remote_chain_depth="$depth")
if [[ -n $defer || $nodes == 1 || $refusal != 0 || $readmit != 0 || $waiter_exit == 1 ]]; then
    numa=$refusal_numa
    [[ -z $defer ]] || numa=1
    [[ $readmit == 0 ]] || numa=1
    make -C "$KM_DIR" KDLOCK_SELFTEST=1 KDLOCK_NUMA="$numa" W=1 -j8 > "$out/build-selftest.log" 2>&1
    cp "$KM_DIR/.kd_spinlock.o.cmd" "$out/spin-build.cmd"
    cp "$KM_DIR/kdlock_km.ko" "$out/kdlock-selftest.ko"
fi
if [[ -n $defer ]]; then
    grep -F -- '-DNUMA_AWARE' "$out/spin-build.cmd" > /dev/null
    strings "$KM_DIR/kdlock_km.ko" | grep -F 'kd_defer append:' > /dev/null
    strings "$KM_DIR/kdlock_km.ko" | grep -F 'kd_defer splice:' > /dev/null
    strings "$KM_DIR/kdlock_km.ko" | grep -F 'kd_defer restore:' > /dev/null
    parameters+=(remote_chain_defer="$((defer+1))")
    parameters+=(remote_chain_defer_count="$defer_count")
fi
[[ $readmit == 0 ]] || parameters+=(remote_chain_readmit=1 remote_chain_readmit_layer="$readmit_layer")
clear_dmesg
module_args=()
[[ $nodes == 0 ]] || module_args+=(spin_selftest_trace_nodes=1)
[[ $refusal == 0 ]] || module_args+=(spin_selftest_refusal="$refusal")
[[ $readmit == 0 ]] || module_args+=(spin_selftest_readmit="$readmit")
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1 "${module_args[@]}"
[[ $nodes == 0 ]] || test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_trace_nodes)" = Y
[[ $refusal == 0 ]] || test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_refusal)" = "$refusal"
[[ $readmit == 0 ]] || test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_readmit)" = "$readmit"
insmod "$KLOCK_DIR/klock_module.ko" "${parameters[@]}"
if [[ $readmit != 0 ]]; then
    test "$(cat /sys/module/klock_module/parameters/remote_chain_readmit)" = Y
    test "$(cat /sys/module/klock_module/parameters/remote_chain_readmit_layer)" = "$readmit_layer"
fi
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
start_daemon 2
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 8 3 > "$out/warmup.log"
sleep 1
for ((i=0; i<depth; i++)); do
    loops=12001
    test "$i" != 0 || loops=12000
    run_with_timeout 30 "$BENCH_BIN" 1 "$loops" 1 1 8 "$((3+4*i))" >> "$out/promotion.log"
done
run_with_timeout 15 "$BENCH_BIN" 1 1 1 1 8 0 > "$out/registration.log"
artifact_output=$(wait_for_jit_artifact_count "$((depth+1))" 120)
mapfile -t asm_dirs <<< "$artifact_output"
for dir in "${asm_dirs[@]}"; do
    check_jit_artifacts "$dir"
    PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 -c '
import json, sys
from mutex_signal_protocol import wait_ready
print(json.dumps(wait_ready(sys.argv[1], lock_kind=1)))
' "$dir" >> "$out/published.jsonl"
done
check_daemon_read_kernel_text "$DAEMON_LOG"
check_dmesg_has "$JIT_INSTALL_PATTERN"
stop_daemon
# Voluntary-preemption workers can otherwise starve the userspace release gate.
taskset -pc "$control" "$$" > "$out/controller-affinity.log"
python3 - "$control" "$out/controller.json" <<'PY'
import json, os, sys
from pathlib import Path
cpu = int(sys.argv[1])
affinity = sorted(os.sched_getaffinity(0))
assert affinity == [cpu]
Path(sys.argv[2]).write_text(json.dumps({"pid": os.getppid(), "cpu": cpu, "affinity": affinity}) + "\n")
PY
if [[ -n $defer ]]; then
    addr=$(dmesg | sed -n "s/.*kd_deep lock: index=$defer addr=\([0-9a-f]*\)$/\1/p")
    test -n "$addr"
    printf '0x%s\n' "$addr" > /sys/module/kdlock_km/parameters/spin_selftest_deferred_lock
fi
if [[ $waiter_exit == 1 ]]; then
    addr=$(dmesg | sed -n 's/.*kd_deep lock: index=0 addr=\([0-9a-f]*\)$/\1/p')
    test -n "$addr"
    printf '0x%s\n' "$addr" > /sys/module/kdlock_km/parameters/spin_selftest_exit_lock
    python3 - "$addr" > "$out/exit-gate.json" <<'PY'
import json, sys
from pathlib import Path
value = int(Path('/sys/module/kdlock_km/parameters/spin_selftest_exit_lock').read_text())
assert value == int(sys.argv[1], 16)
print(json.dumps({"root_lock": hex(value), "waiter_exit": True}))
PY
fi
if [[ $refusal != 0 ]]; then
    addr=$(dmesg | sed -n 's/.*kd_deep lock: index=3 addr=\([0-9a-f]*\)$/\1/p')
    test -n "$addr"
    printf '0x%s\n' "$addr" > /sys/module/kdlock_km/parameters/spin_selftest_refusal_lock
fi
if [[ $readmit != 0 ]]; then
    addr=$(dmesg | sed -n "s/.*kd_deep lock: index=$readmit_layer addr=\([0-9a-f]*\)$/\1/p")
    test -n "$addr"
    printf '0x%s\n' "$addr" > /sys/module/kdlock_km/parameters/spin_selftest_readmit_lock
    printf '0x%s\n' "$addr" > /sys/module/kdlock_km/parameters/spin_selftest_deferred_lock
fi
printf '%s\n' "$reverse" > /sys/module/klock_module/parameters/remote_chain_reverse
printf '%s\n' "$renamed" > /sys/module/klock_module/parameters/native_resume_rename
printf '%s\n' "$stage" > /sys/module/klock_module/parameters/remote_chain_stage
pids=()
spawn() {
    local role=$1 comm=$TARGET_PROCESS
    if test "$role:$owner" = 1:1; then comm=kd_native; fi
    timeout --kill-after=5s 60s env KD_TEST_COMM="$comm" taskset -c "${cpus[$role]}" \
        "$BENCH_BIN" 1 1 1 1 8 "$role" > "$out/role-$role.log" 2>&1 &
    pids+=("$!")
}
spawn 1
for ((i=depth-1; i>=0; i--)); do
    spawn "$((2+4*i))"
    spawn "$((3+4*i))"
    spawn "$((4+4*i))"
    spawn "$((5+4*i))"
done
if [[ -n $defer ]]; then
    for ((i=0; i<defer_count; i++)); do spawn "$((2+4*depth+i))"; done
fi
if [[ $readmit != 0 ]]; then spawn 18; spawn 19; fi
spawn 0
if [[ -n $defer || $readmit != 0 ]]; then
    PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$out/placement.json" > "$out/linked.json" <<'PY'
import json, sys
from remote_depth_protocol import wait_deferred_link
with open(sys.argv[1]) as source:
    print(json.dumps(wait_deferred_link(json.load(source)), sort_keys=True))
PY
    gate=remote_chain_defer_ready
    [[ $readmit == 0 ]] || gate=remote_chain_readmit_ready
    printf '1\n' > "/sys/module/klock_module/parameters/$gate"
fi
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
test "$failed" = 0
check_any_jit_entry_executed "${asm_dirs[@]}"
unload_modules
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_has 'kd_spin diag invariant_failures=0'
check_dmesg_not_has 'JIT retry\|abort release\|non-continuable exit\|kd_deep timeout:'
# RUN_ERROR deliberately disables only the rejected lock; the oracle checks
# that exact address and rejects any other disabled lock.
[[ $refusal == 2 ]] || check_dmesg_not_has 'jit_disabled=1'
check_dmesg_ok
dmesg > "$out/protocol.log"
lock_ip=$(awk '$3 == "_raw_spin_lock" {print $1}' /proc/kallsyms)
options=(--lock-ip "$lock_ip")
[[ $waiter_exit == 0 ]] || options+=(--waiter-exit)
[[ $refusal == 0 ]] || options+=(--refusal "$refusal")
test "$owner" = 0 || options+=(--native-owner)
test "$reverse" = 0 || options+=(--reverse)
test "$renamed" = 0 || options+=(--renamed)
python3 "$KDLOCK_DIR/tests/protocols/remote_depth_protocol.py" "$out/protocol.log" \
    "$out/placement.json" "$stage" "${options[@]}"
python3 "$node_protocol" validate "$out/protocol.log" "$out/placement.json" "$out/node-profile.json" | tee "$out/node-protocol.json"
pass "$TEST_NAME depth=$depth stage=$stage owner=$owner reverse=$reverse rename=$renamed defer=${defer:-none} count=$defer_count refusal=$refusal refusal_numa=$refusal_numa readmit=$readmit readmit_layer=$readmit_layer waiter_exit=$waiter_exit"
