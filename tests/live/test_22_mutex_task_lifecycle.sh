#!/bin/bash
# Real task-record/RCU and owner ACK probe, not a generated-code execution gate.
TEST_NAME="test_22_mutex_task_lifecycle"
source "$(dirname "$0")/../common.sh"

if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 ]]; then
    fail "$TEST_NAME" "confirm a recoverable guest snapshot first"
    exit 1
fi
WORKERS='daemon|klock_test|kd_mtask_[0-2]|kd_entry_[0-1]|kd_gate_[0-3]|kd_shadow_[0-2]'
if pgrep -x "$WORKERS" >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no kdlock modules or workers"
    exit 1
fi

EVIDENCE=$(mktemp -d /tmp/kdlock-mutex-task-kernel.XXXXXX)
CPUS=${KD_MUTEX_TASK_CPUS:-0,1,2}
if [[ ! $CPUS =~ ^[0-9]+,[0-9]+,[0-9]+$ ]]; then
    fail "$TEST_NAME" "KD_MUTEX_TASK_CPUS must name three distinct online CPUs"
    exit 1
fi
info "Evidence: $EVIDENCE"

cleanup() {
    local status=$?
    trap - EXIT
    if pgrep -x "$WORKERS" >/dev/null; then
        fail "$TEST_NAME" "workers have not drained; retain module and use VM recovery"
        exit 1
    fi
    if lsmod | grep '^kdlock_km ' >/dev/null; then
        rmmod kdlock_km || status=1
    fi
    dmesg >"$EVIDENCE/dmesg.log"
    make -C "$KM_DIR" KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8 \
        >"$EVIDENCE/build-default.log" 2>&1 || status=1
    exit "$status"
}
trap cleanup EXIT

make -C "$KM_DIR" KDLOCK_SELFTEST=1 KDLOCK_NUMA=0 W=1 -j8 \
    >"$EVIDENCE/build-selftest.log" 2>&1
cp "$KM_DIR/kdlock_km.ko" "$EVIDENCE/kdlock-selftest.ko"
clear_dmesg
load_kdlock --timeout 60 \
    target_process=kd_mtask_unused mutex_task_selftest=1 mutex_task_cpus="$CPUS"
check_dmesg_has "kd_mutex task selftest: cpus=$CPUS orders=2 acks=4 deferred_frees=2 failures=0 JIT=0"
for order in B-A A-B; do
    check_dmesg_has "kd_mutex task selftest round: order=$order acks=2 deferred_frees=1 failures=0 JIT=0"
done
rmmod kdlock_km
check_dmesg_has 'kd_mutex tasks: active_tasks=0 task_alloc_failure=2 task_reroutes=4'
check_dmesg_has 'kd_native stats: started=2 completed=2 unlocks=4'
check_dmesg_has 'kd_exec invariant_failures=0'
check_dmesg_not_has 'selftest error:\|WARNING:\|scheduling while atomic\|exited with preempt_count'
check_dmesg_not_has 'JIT body witness:\|install JIT chunk:'
check_dmesg_ok
pass "$TEST_NAME cpus=$CPUS real-RCU=2 owner-ACKs=4 JIT=0"
