#!/bin/bash
# Native-L/private-word component test; not legacy spin JIT interoperability.
TEST_NAME="test_15_spin_native_gate"
source "$(dirname "$0")/../common.sh"

if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 ]]; then
    fail "$TEST_NAME" "confirm a recoverable guest snapshot first"
    exit 1
fi
if pgrep -x 'daemon|klock_test|kd_gate_[0-3]|kd_shadow_[0-2]' >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no kdlock modules or workers"
    exit 1
fi

EVIDENCE=$(mktemp -d /tmp/kdlock-spin-gate-kernel.XXXXXX)
CPUS=${KD_GATE_CPUS:-0,1,2,3}
loaded=0
info "Evidence: $EVIDENCE"

cleanup() {
    local status=$?
    trap - EXIT
    if pgrep -x 'kd_gate_[0-3]|kd_shadow_[0-2]' >/dev/null; then
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
load_kdlock --timeout 60 \
    target_process=kd_gate_unused spin_gate_selftest=1 spin_gate_cpus="$CPUS"
loaded=1
check_dmesg_has "kd_spin gate selftest: cpus=$CPUS sequences=2 native_waits=2 loops=128 operations=516 native_while_gate_held=1 failures=0" || exit 1
rmmod kdlock_km
loaded=0
dmesg >"$EVIDENCE/dmesg.log"
check_dmesg_has 'kd_spin diag invariant_failures=0' || exit 1
check_dmesg_has 'kd_exec invariant_failures=0' || exit 1
check_dmesg_not_has 'selftest error:\|WARNING:\|scheduling while atomic\|exited with preempt_count' || exit 1
check_dmesg_ok || exit 1
pass "$TEST_NAME cpus=$CPUS native-L=1 private-word=1 operations=516 JIT=0"
