#!/bin/bash
# Ticket/native-reference component test; legacy queue/JIT routing is unchanged.
TEST_NAME="test_16_spin_entry"
source "$(dirname "$0")/common.sh"

if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 ]]; then
    fail "$TEST_NAME" "confirm a recoverable guest snapshot first"
    exit 1
fi
if pgrep -x 'daemon|klock_test|kd_entry_[0-1]|kd_gate_[0-3]|kd_shadow_[0-2]' >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no kdlock modules or workers"
    exit 1
fi

EVIDENCE=$(mktemp -d /tmp/kdlock-spin-entry-kernel.XXXXXX)
CPUS=${KD_ENTRY_CPUS:-0,1}
loaded=0
info "Evidence: $EVIDENCE"

cleanup() {
    local status=$?
    trap - EXIT
    if pgrep -x 'kd_entry_[0-1]|kd_gate_[0-3]|kd_shadow_[0-2]' >/dev/null; then
        fail "$TEST_NAME" "workers have not drained; retain module and use VM recovery"
        exit 1
    fi
    if [[ $loaded == 1 ]]; then
        rmmod kdlock_km || status=1
    fi
    dmesg >"$EVIDENCE/dmesg.log"
    make -C "$KM_DIR" KDLOCK_SELFTEST=0 W=1 -j8 >"$EVIDENCE/build-default.log" 2>&1 || status=1
    exit "$status"
}
trap cleanup EXIT

make -C "$KM_DIR" KDLOCK_SELFTEST=1 W=1 -j8 >"$EVIDENCE/build-selftest.log" 2>&1
cp "$KM_DIR/kdlock_km.ko" "$EVIDENCE/kdlock-selftest.ko"
clear_dmesg
timeout --kill-after=10s 60s insmod "$KM_DIR/kdlock_km.ko" \
    target_process=kd_entry_unused spin_entry_selftest=1 spin_entry_cpus="$CPUS"
loaded=1
check_dmesg_has "kd_spin entry selftest: cpus=$CPUS capacity=32 notifications=2 retained_pin=1 retained_b=1 failures=0 JIT=0" || exit 1
rmmod kdlock_km
loaded=0
dmesg >"$EVIDENCE/dmesg.log"
check_dmesg_has 'kd_spin diag invariant_failures=0' || exit 1
check_dmesg_has 'kd_exec invariant_failures=0' || exit 1
check_dmesg_not_has 'selftest error:\|WARNING:\|scheduling while atomic\|exited with preempt_count' || exit 1
check_dmesg_ok || exit 1
pass "$TEST_NAME cpus=$CPUS capacity=32 native-refs=2 retained-pin=1 JIT=0"
