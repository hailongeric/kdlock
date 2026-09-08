#!/bin/bash
# Real full-shadow queue-head regression; never part of the default suite.
TEST_NAME="test_13_spin_shadow_capacity"
source "$(dirname "$0")/common.sh"

if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 ]]; then
    fail "$TEST_NAME" "confirm a recoverable guest snapshot first"
    exit 1
fi
if pgrep -x 'daemon|klock_test|kd_shadow_[0-2]' >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no active kdlock workers, daemon or modules"
    exit 1
fi

EVIDENCE=$(mktemp -d /tmp/kdlock-spin-shadow-kernel.XXXXXX)
CPUS=${KD_SELFTEST_CPUS:-0,1,2}
loaded=0
info "Evidence: $EVIDENCE"

cleanup() {
    local status=$?
    trap - EXIT
    if pgrep -x 'kd_shadow_[0-2]' >/dev/null; then
        fail "$TEST_NAME" "kernel workers have not drained; retain module and use VM recovery"
        exit 1
    fi
    if [[ $loaded == 1 ]]; then
        rmmod kdlock_km || status=1
    fi
    # Kbuild tracks the changed command-line define and rebuilds normal objects.
    make -C "$KM_DIR" KDLOCK_SELFTEST=0 W=1 -j8 >"$EVIDENCE/build-default.log" 2>&1 || status=1
    exit "$status"
}
trap cleanup EXIT

make -C "$KM_DIR" KDLOCK_SELFTEST=1 W=1 -j8 >"$EVIDENCE/build-selftest.log" 2>&1
cp "$KM_DIR/kdlock_km.ko" "$EVIDENCE/kdlock-selftest.ko"
clear_dmesg
timeout --kill-after=10s 45s insmod "$KM_DIR/kdlock_km.ko" \
    target_process=kd_shadow_unused spin_selftest_cpus="$CPUS"
loaded=1
check_dmesg_has 'kd kernel module init' || exit 1
rmmod kdlock_km
loaded=0
dmesg >"$EVIDENCE/dmesg.log"

rounds=$(grep -c "kd_spin selftest: round=.* cpus=$CPUS held=8 precheck=1 acquired=3 observed=1 value=3 failures=0" "$EVIDENCE/dmesg.log" || true)
if [[ $rounds != 8 ]]; then
    fail "$TEST_NAME" "expected eight complete kernel rounds, got $rounds"
    exit 1
fi
check_dmesg_stat_equals waiters 0 || exit 1
check_dmesg_stat_equals combiner 0 || exit 1
check_dmesg_stat_equals jit_success 0 || exit 1
check_dmesg_has 'kd_spin diag invariant_failures=0' || exit 1
check_dmesg_has 'kd_exec invariant_failures=0' || exit 1
check_dmesg_not_has 'selftest error:\|WARNING:\|\[KD_JIT\]\[ERROR\]' || exit 1
check_dmesg_ok || exit 1
pass "$TEST_NAME cpus=$CPUS rounds=$rounds held=8 real-queue=1 JIT=0"
