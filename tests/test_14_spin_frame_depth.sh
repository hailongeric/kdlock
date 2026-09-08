#!/bin/bash
# Natural nested combiners, not a synthetic frame/count injection.
TEST_NAME=test_14_spin_frame_depth
source "$(dirname "$0")/common.sh"
depth=${1:-2}
forced=${KD_CHAIN_FORCE_PROMOTION:-0}
numa=${KD_CHAIN_NUMA:-0}
buffered=${KD_CHAIN_TRACE_BUFFERED:-0}
probe=${KD_CHAIN_PROBE_FRAMES:-0}
nodes=${KD_CHAIN_TRACE_NODES:-0}
defer_levels=${KD_CHAIN_DEFER_LEVELS:-}
defer_count=${KD_CHAIN_DEFER_COUNT:-1}
defer_mask=0
if [[ $numa != 0 && $numa != 1 ]]; then
    fail "$TEST_NAME" "KD_CHAIN_NUMA must be 0 or 1"
    exit 1
fi
if [[ ! $buffered =~ ^[01]$ || ( $buffered == 1 && $numa != 1 ) ]]; then
    fail "$TEST_NAME" "KD_CHAIN_TRACE_BUFFERED must be 0/1; buffering requires NUMA=1"
    exit 1
fi
if [[ $forced != 0 && $forced != 1 ]]; then
    fail "$TEST_NAME" "KD_CHAIN_FORCE_PROMOTION must be 0 or 1"
    exit 1
fi
if [[ $probe != 0 && $probe != 1 ]]; then
    fail "$TEST_NAME" "KD_CHAIN_PROBE_FRAMES must be 0 or 1"
    exit 1
fi
if [[ $nodes != 0 && $nodes != 1 ]]; then
    fail "$TEST_NAME" "KD_CHAIN_TRACE_NODES must be 0 or 1"
    exit 1
fi
if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 || ! $depth =~ ^[1-8]$ ]]; then
    fail "$TEST_NAME" "require recovery confirmation and depth 1..8"
    exit 1
fi
if [[ ! $defer_count =~ ^[1-3]$ ||
      ( -z $defer_levels && $defer_count != 1 ) ||
      ( -n $defer_levels && ( $buffered != 1 || ! $defer_levels =~ ^[0-7](,[0-7])*$ ) ) ]]; then
    fail "$TEST_NAME" "KD_CHAIN_DEFER_LEVELS requires buffering and sorted unique levels; COUNT=1..3"
    exit 1
fi
IFS=, read -r -a levels <<< "$defer_levels"
previous=-1
for level in "${levels[@]}"; do
    if ((level <= previous || level >= depth)); then
        fail "$TEST_NAME" "KD_CHAIN_DEFER_LEVELS requires sorted unique levels below depth"
        exit 1
    fi
    defer_mask=$((defer_mask | (1 << level)))
    previous=$level
done
if pgrep -x 'daemon|klock_test|kd_shadow_[0-2]' >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no active kdlock workers or modules"
    exit 1
fi
grep -E '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt
out=$(mktemp -d "/tmp/kdlock-spin-frames-${depth}.XXXXXX")
info "Evidence: $out"
protocol="$KDLOCK_DIR/tests/spin_frame_protocol.py"
capture_args=()
[[ $buffered == 0 ]] || capture_args+=(--buffered)
[[ $probe == 0 ]] || capture_args+=(--probe-frames)
[[ -z $defer_levels ]] || capture_args+=(--defer-levels "$defer_levels" --defer-count "$defer_count")
python3 "$protocol" capture "$depth" "$numa" "${capture_args[@]}" > "$out/placement.json"
node_protocol="$KDLOCK_DIR/tests/spin_node_protocol.py"
python3 "$node_protocol" profile "$nodes" physical > "$out/node-profile.json"
control=$(python3 "$protocol" control "$out/placement.json")
DAEMON_LOG="$out/daemon.log"
cleanup() {
    local status=$?
    trap - EXIT
    stop_daemon
    if pgrep -x 'klock_test|kd_shadow_[0-2]' >/dev/null; then
        fail "$TEST_NAME" "workers remain; retain code and use VM recovery"
        status=1
    else
        unload_modules
        make -C "$KM_DIR" KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8 > "$out/build-default.log" 2>&1 || status=1
    fi
    dmesg > "$out/dmesg.log"
    (cd "$KDLOCK_DIR"
     find daemon -path 'daemon/0x*' -type f -print0 |
         tar --null -T - -czf "$out/artifacts.tar.gz")
    printf '%s\n' "$status" > "$out/exit-status"
    exit "$status"
}
trap cleanup EXIT
build_all
make -C "$KM_DIR" KDLOCK_SELFTEST=1 KDLOCK_NUMA="$numa" W=1 -j8 > "$out/build-selftest.log" 2>&1
cp "$KM_DIR/kdlock_km.ko" "$out/kdlock-selftest.ko"
cp "$KM_DIR/.kd_spinlock.o.cmd" "$out/spin-build.cmd"
if [[ $numa == 1 ]]; then
    grep -Fq -- '-DNUMA_AWARE' "$out/spin-build.cmd"
elif grep -Fq -- '-DNUMA_AWARE' "$out/spin-build.cmd"; then
    fail "$TEST_NAME" "NUMA-off test has NUMA-on object code"
    exit 1
fi
clear_dmesg
module_args=()
[[ $buffered == 0 ]] || module_args+=(spin_selftest_deferred_buffered=1)
[[ $probe == 0 ]] || module_args+=(spin_selftest_probe_frames=1)
[[ $nodes == 0 ]] || module_args+=(spin_selftest_trace_nodes=1)
insmod "$KM_DIR/kdlock_km.ko" target_process="$TARGET_PROCESS" mutex_jit=0 spin_selftest_trace_frames=1 "${module_args[@]}"
[[ $nodes == 0 ]] || test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_trace_nodes)" = Y
insmod "$KLOCK_DIR/klock_module.ko" spin_chain_depth="$depth" \
    spin_chain_defer="$defer_mask" spin_chain_defer_count="$defer_count"
start_daemon 2
for ((i=0; i<depth; i++)); do
    run_with_timeout 10 taskset -c "$((1+i))" "$BENCH_BIN" 1 1 1 1 8 "$i" >> "$out/warmup.log"
done
sleep 1
if [[ $forced == 1 ]]; then
    # Isolate frame execution from the global adaptive sampling heuristic.
    # Queue shape, requests, registers and all frame counts remain real.
    for ((i=0; i<depth; i++)); do
        addr=$(dmesg | sed -n "s/.*kd_chain lock: index=$i addr=\([0-9a-f]*\)$/\1/p")
        test -n "$addr"
        printf '0x%s\n' "$addr" > /sys/module/kdlock_km/parameters/spin_selftest_promote
    done
fi
for ((i=0; i<depth; i++)); do
    run_with_timeout 30 taskset -c "$((1+i))" "$BENCH_BIN" 1 12000 1 1 8 "$i" >> "$out/promotion.log"
done
artifact_output=$(wait_for_jit_artifact_count 2 30)
mapfile -t asm_dirs <<< "$artifact_output"
for dir in "${asm_dirs[@]}"; do
    check_jit_artifacts "$dir"
    check_complex_cs_artifact "$dir"
done
wait_for_jit_quiescence 2 30 1
stop_daemon
check_daemon_read_kernel_text "$DAEMON_LOG"
dmesg > "$out/before-chain.log"
python3 - "$out/before-chain.log" "$depth" "$forced" <<'PY'
import re, sys
from pathlib import Path
log = Path(sys.argv[1]).read_text()
locks = dict(re.findall(r'kd_chain lock: index=(\d+) addr=([0-9a-f]+)', log))
for i in range(int(sys.argv[2])):
    expected = (f'kd_hotlock selftest promote: lock={locks[str(i)]}'
                if sys.argv[3] == '1' else f'uaddr {locks[str(i)]} begin delegate')
    assert expected in log, f'lock {i} never promoted'
assert 'kd_frame trace:' not in log
PY
taskset -pc "$control" "$$" > "$out/controller-affinity.log"
python3 - "$control" "$$" "$out/controller.json" <<'PY'
import json, os, sys
from pathlib import Path
cpu = int(sys.argv[1])
affinity = sorted(os.sched_getaffinity(0))
assert affinity == [cpu], affinity
Path(sys.argv[3]).write_text(json.dumps({"pid": int(sys.argv[2]), "cpu": cpu, "affinity": affinity}) + "\n")
PY
if [[ $buffered == 1 ]]; then
    test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_deferred_buffered)" = Y
    addresses=()
    for ((i=0; i<depth; i++)); do
        addr=$(sed -n "s/.*kd_chain lock: index=$i addr=\([0-9a-f]*\)$/\1/p" "$out/before-chain.log")
        test -n "$addr"
        addresses+=("0x$addr")
    done
    (IFS=,; printf '%s\n' "${addresses[*]}") > /sys/module/kdlock_km/parameters/spin_selftest_deferred_locks
fi
printf '1\n' > /sys/module/klock_module/parameters/spin_chain_armed
pids=()
spawn() {
    local role=$1 cpu=$2
    timeout --kill-after=5s 45s taskset -c "$cpu" "$BENCH_BIN" 1 1 1 1 8 "$role" \
        > "$out/role-$role.log" 2>&1 &
    pids+=("$!")
}
for ((i=0; i<depth; i++)); do spawn "$((20+i))" "$((20+i))"; done
spawn 9 19
spawn 8 0
for ((i=0; i<depth; i++)); do
    spawn "$i" "$((1+i))"
    spawn "$((10+i))" "$((10+i))"
done
if [[ -n $defer_levels ]]; then
    role_output=$(python3 "$protocol" followers "$out/placement.json")
    while read -r role cpu; do spawn "$role" "$cpu"; done <<< "$role_output"
    ready=0
    for level in "${levels[@]}"; do
        python3 "$protocol" gate "$out/placement.json" "$level" > "$out/linked-$level.json"
        ready=$((ready | (1 << level)))
        printf '%s\n' "$ready" > /sys/module/klock_module/parameters/spin_chain_defer_ready
    done
fi
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
test "$failed" = 0
test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
rmmod klock_module
rmmod kdlock_km
dmesg > "$out/dmesg.log"
check_dmesg_ok
check_dmesg_not_has 'kd_chain timeout:\|WARNING:\|\[KD_JIT\]\[ERROR\]'
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_has 'kd_spin diag invariant_failures=0'
check_dmesg_has 'kd_spin diag overflow=0'
check_dmesg_stat_equals waiters 0
lock_ip=$(awk '$3 == "_raw_spin_lock" {print $1}' /proc/kallsyms)
test -n "$lock_ip"
python3 "$protocol" validate "$out" "$DAEMON_DIR" "$lock_ip" | tee "$out/protocol.log"
python3 "$node_protocol" validate "$out/dmesg.log" "$out/placement.json" "$out/node-profile.json" | tee "$out/node-protocol.json"
check_any_jit_entry_executed "${asm_dirs[@]}"
pass "$TEST_NAME depth=$depth actual-frames=$depth numa=$numa buffered=$buffered defer=${defer_levels:-none} count=$defer_count JIT=1"
