#!/bin/bash
# Recovery-only: ordinary/pending-lock CALL exits must not replay partial stores.
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
policy_completion="${KD_NATIVE_POLICY_COMPLETION:-0}"
pending_contended="${KD_NATIVE_PENDING_CONTENDED:-0}"
shadow_capacity="${KD_NATIVE_SHADOW_CAPACITY:-0}"
virtual_resource="${KD_NATIVE_VIRTUAL_RESOURCE:-0}"
waiter_signal="${KD_NATIVE_WAITER_SIGNAL:-0}"
waiter_api="${KD_NATIVE_WAITER_API:-0}"
waiter_race="${KD_NATIVE_WAITER_RACE:-0}"
waiter_race_us="${KD_NATIVE_WAITER_RACE_US:-0}"
waiter_expect="${KD_NATIVE_WAITER_EXPECT:-either}"
ooo="${KD_NATIVE_OOO:-0}"
dependency="${KD_NATIVE_OOO_DEPENDENCY:-0}"
registers="${KD_NATIVE_REGISTERS:-0}"
native_control="${KD_NATIVE_CONTROL:-0}"
source_module="${KD_NATIVE_SOURCE_MODULE:-0}"
stack_change="${KD_NATIVE_STACK_CHANGE:-0}"
shared_cpu="${KD_NATIVE_SHARED_CPU:-0}"
gate_pressure="${KD_NATIVE_GATE_PRESSURE:-0}"
spin_acquired="${KD_NATIVE_SPIN_ACQUIRED:-0}"
source_loaded=0
# A validated post-B checkpoint uses the existing nested workload, but must
# not replace an ordinary CALL/register probe or a PENDING resource refusal.
case "$spin_acquired" in
    0|1|2) ;;
    *) fail "$TEST_NAME" "KD_NATIVE_SPIN_ACQUIRED must be 0, 1 or 2"; exit 1 ;;
esac
if [ "$spin_acquired" != 0 ]; then
    if [ "$mode:$stage" != 1:3 ]; then
        fail "$TEST_NAME" "spin acquired requires mode 1 stage 3"
        exit 1
    fi
    for flag in pinned renamed mixed policy_completion pending_contended shadow_capacity \
        virtual_resource ooo dependency registers native_control source_module stack_change \
        shared_cpu gate_pressure waiter_signal waiter_api waiter_race; do
        if [ "${!flag}" != 0 ]; then
            fail "$TEST_NAME" "spin acquired cannot combine with $flag"
            exit 1
        fi
    done
    if [ "$spin_acquired" = 2 ]; then
        python3 -c 'import os; assert {0, 1, 2, 3, 4, 6, 8} <= os.sched_getaffinity(0)'
    fi
fi
# Gate-map pressure only extends the real ticket case. It must not silently
# change another native/register/signal workload or its capacity premise.
case "$gate_pressure" in
    0|1) ;;
    *) fail "$TEST_NAME" "KD_NATIVE_GATE_PRESSURE must be 0 or 1"; exit 1 ;;
esac
if [ "$gate_pressure" = 1 ]; then
    test "$mode:$stage:$virtual_resource:$pending_contended" = 8:4:3:1 || exit 1
    python3 -c 'import os; assert set(range(9, 19)) <= os.sched_getaffinity(0)'
fi
# Reuse the pending-B gate with A's owner, waiter and trailer sharing CPU 4.
# Keep signal/stack/resource perturbations separate from this scheduling test.
case "$shared_cpu" in
    0|1) ;;
    *) fail "$TEST_NAME" "KD_NATIVE_SHARED_CPU must be 0 or 1"; exit 1 ;;
esac
if [ "$shared_cpu" = 1 ]; then
    if [ "$mode:$stage:$pending_contended" != 4:4:1 ]; then
        fail "$TEST_NAME" "shared CPU requires mode 4 stage 4 with pending contention"
        exit 1
    fi
    for flag in pinned renamed mixed policy_completion shadow_capacity virtual_resource \
        ooo dependency registers native_control source_module stack_change waiter_signal waiter_api waiter_race; do
        if [ "${!flag}" != 0 ]; then
            fail "$TEST_NAME" "shared CPU cannot combine with $flag"
            exit 1
        fi
    done
fi
# Deliver the original pure-native register control without a /tmp helper.
# It is opt-in and cannot silently replace a requested JIT continuation gate.
case "$native_control:$registers:$mode:$stage" in
    0:*|1:1:0:1|1:1:3:1) ;;
    *) fail "$TEST_NAME" "KD_NATIVE_CONTROL=1 requires registers=1, mode 0/3 stage 1"; exit 1 ;;
esac
# A real shared-stack write is a completed-control boundary, not a PENDING
# resource injection, ordinary CALL miss, signal cancellation or depth probe.
if [ "$stack_change" != 0 ] && { [ "$stack_change" != 1 ] ||
        [ "$mode:$stage:$pending_contended:$pinned:$renamed:$mixed:$policy_completion:$shadow_capacity:$virtual_resource:$ooo:$dependency:$registers:$source_module:$waiter_signal:$waiter_api:$waiter_race" != 4:4:1:0:0:0:0:0:0:0:0:0:0:0:0:0 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_STACK_CHANGE=1 requires plain mode 4 stage 4 with native B contention"
    exit 1
fi
# The second source extends the learned-depth case, not ordinary/signal modes.
if [ "$source_module" != 0 ] && { [ "$source_module" != 1 ] ||
        [ "$mode:$stage:$pinned:$renamed:$mixed:$policy_completion:$pending_contended:$shadow_capacity:$virtual_resource:$ooo:$dependency:$registers" != 4:5:0:0:0:0:0:0:0:0:0:0 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_SOURCE_MODULE=1 requires plain mode 4 stage 5"
    exit 1
fi
if [ -d /sys/module/kd_depth_source ]; then
    fail "$TEST_NAME" "a previous source helper remains; inspect before another session"
    exit 1
fi
# API selection changes native B's return contract, not kdlock's lock controls.
# Only the matching real signal may cancel each opt-in native acquisition.
case "$waiter_api:$waiter_signal" in
    0:0|0:9|0:10|1:10|2:9) ;;
    *) fail "$TEST_NAME" "waiter API 1 requires SIGUSR1, API 2 requires SIGKILL"; exit 1 ;;
esac
# Keep the release race distinct from forced cancellation. Its return is an
# observed native API result; neither an offset nor the expected result sets it.
case "$waiter_race:$waiter_api" in
    0:*)
        if [ "$waiter_race_us:$waiter_expect" != 0:either ]; then
            fail "$TEST_NAME" "waiter race offsets/expectations require KD_NATIVE_WAITER_RACE=1"
            exit 1
        fi ;;
    1:1|1:2) ;;
    *) fail "$TEST_NAME" "waiter race requires cancellable API 1 or 2"; exit 1 ;;
esac
case "$waiter_expect" in
    either|acquired|cancelled) ;;
    *) fail "$TEST_NAME" "waiter expectation must be either/acquired/cancelled"; exit 1 ;;
esac
if [ "$waiter_race" = 1 ]; then
    python3 -c 'import sys; assert -50000 <= int(sys.argv[1]) <= 50000' "$waiter_race_us"
fi
# The signalled participant is the single-task native B waiter, not a native
# peer or timeout supervisor. Keep all other perturbations out of this case.
if [ "$waiter_signal" != 0 ]; then
    case "$waiter_signal" in
        9|10) ;;
        *) fail "$TEST_NAME" "KD_NATIVE_WAITER_SIGNAL must be 0, 9 or 10"; exit 1 ;;
    esac
    if [ "$mode:$stage:$pending_contended:$pinned:$renamed:$mixed:$policy_completion:$shadow_capacity:$virtual_resource:$ooo:$dependency:$registers" != 4:4:1:0:0:0:0:0:0:0:0:0 ]; then
        fail "$TEST_NAME" "waiter signal requires plain mode 4 stage 4 with pending contention"
        exit 1
    fi
fi
# Reuse the independent B owner/pending topology, but reach the real virtual
# ticket cancellation branches instead of the earlier jit_fail_pending_lock.
if [ "$virtual_resource" != 0 ]; then
    case "$virtual_resource" in
        1|2|3) ;;
        *) fail "$TEST_NAME" "KD_NATIVE_VIRTUAL_RESOURCE must be 0, 1, 2 or 3"; exit 1 ;;
    esac
    if [ "$mode:$stage:$pending_contended:$pinned:$renamed:$mixed:$policy_completion:$shadow_capacity:$ooo:$dependency:$registers" != 8:4:1:0:0:0:0:0:0:0:0 ]; then
        fail "$TEST_NAME" "virtual resource refusal requires plain mode 8 stage 4 with pending contention"
        exit 1
    fi
fi
selftest=0
if [ "$shadow_capacity" = 1 ] || [ "$virtual_resource" != 0 ]; then
    selftest=1
fi
if [ "$registers" != 0 ]; then
    case "$registers:$mode:$stage" in
        1:0:1|1:3:1|1:1:2|1:1:3|1:4:2|1:4:3|1:8:2|1:8:3) ;;
        *) fail "$TEST_NAME" "KD_NATIVE_REGISTERS=1 requires an ordinary CALL-miss mode/stage"; exit 1 ;;
    esac
    if [ "$pinned:$renamed:$mixed:$policy_completion:$pending_contended:$shadow_capacity:$ooo:$dependency" != 0:0:0:0:0:0:0:0 ]; then
        fail "$TEST_NAME" "register probe requires an unmodified ordinary CALL-miss case"
        exit 1
    fi
fi
if [ "$dependency" != 0 ] && { { [ "$dependency" != 1 ] && [ "$dependency" != 2 ]; } ||
        { [ "$mode:$stage:$ooo" != 4:3:3 ] && [ "$mode:$stage:$ooo" != 1:3:3 ]; }; }; then
    fail "$TEST_NAME" "KD_NATIVE_OOO_DEPENDENCY=1/2 requires mode 1/4 stage 3 OOO=3"
    exit 1
fi
if [ "$ooo" != 0 ] && { { [ "$ooo" != 1 ] && [ "$ooo" != 2 ] && [ "$ooo" != 3 ]; } ||
        { [ "$mode:$stage" != 1:3 ] && [ "$mode:$stage" != 4:3 ]; } ||
        [ "$pinned:$mixed:$policy_completion:$pending_contended:$shadow_capacity" != 0:0:0:0:0 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_OOO=1/2/3 requires mode 1/4 stage 3, optionally rename"
    exit 1
fi
if [ "$shadow_capacity" != 0 ] && { [ "$shadow_capacity" != 1 ] ||
        [ "$mode:$stage:$pinned:$renamed:$mixed:$policy_completion:$pending_contended" != 1:4:0:0:0:0:0 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_SHADOW_CAPACITY=1 requires plain mode 1 stage 4"
    exit 1
fi
if [ "$shadow_capacity" = 1 ] &&
        ! grep -Eq '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt; then
    fail "$TEST_NAME" "shadow-pressure fixture requires verified none/voluntary preemption"
    exit 1
fi
if [ "$pending_contended" != 0 ] && { [ "$pending_contended" != 1 ] ||
        { [ "$mode:$stage:$pinned:$mixed:$policy_completion" != 4:4:0:0:0 ] &&
          [ "$mode:$stage:$pinned:$mixed:$policy_completion" != 8:4:0:0:0 ]; }; }; then
    fail "$TEST_NAME" "KD_NATIVE_PENDING_CONTENDED=1 requires mode 4/8 stage 4"
    exit 1
fi
if [ "$mode:$stage" = 8:4 ]; then
    test "$pending_contended" = 1 || {
        fail "$TEST_NAME" "mode 8 stage 4 requires KD_NATIVE_PENDING_CONTENDED=1"
        exit 1
    }
    grep -Eq '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt
    python3 -c 'import os; assert {0, 1, 2, 3, 4, 6, 8} <= os.sched_getaffinity(0)'
    python3 - <<'PY'
import os, re
from pathlib import Path
kernel = Path(os.environ.get("KDIR", f"/lib/modules/{os.uname().release}/build"))
pv = (kernel / "kernel/locking/qspinlock_paravirt.h").read_text()
assert "#define_Q_SLOW_VAL(3U<<_Q_LOCKED_OFFSET)" in re.sub(r"\s+", "", pv)
PY
fi
if [ "$policy_completion" != 0 ] && { [ "$policy_completion" != 1 ] ||
        { [ "$mode:$stage" != 0:1 ] && [ "$mode:$stage" != 3:1 ]; } ||
        [ "$pinned:$renamed:$mixed" != 0:0:0 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_POLICY_COMPLETION=1 requires plain mode 0/3 stage 1"
    exit 1
fi
if [ "$mixed" != 0 ] && { [ "$mixed" != 1 ] || [ "$mode:$stage:$pinned:$renamed" != 3:1:0:0 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_MIXED=1 requires unpinned mode 3 stage 1 without rename"
    exit 1
fi
if [ "$renamed" != 0 ] && [ "$renamed" != 1 ]; then
    fail "$TEST_NAME" "KD_NATIVE_RENAME must be 0 or 1"
    exit 1
fi
if [ "$pinned" != 0 ] && { [ "$pinned" != 1 ] || [ "$mode:$stage" != 3:1 ]; }; then
    fail "$TEST_NAME" "KD_NATIVE_PINNED=1 requires mode 3 stage 1"
    exit 1
fi
case "$mode:$stage" in
    0:1|3:1|1:2|1:3|1:4|4:2|4:3|4:4|4:5|8:2|8:3|8:4) ;;
    *) fail "$TEST_NAME" "use mode 0/3 stage 1, mode 1/4/8 stage 2/3/4, or mode 4 stage 5"; exit 1 ;;
esac
out="$(mktemp -d "/tmp/kdlock-native-mode${mode}-stage${stage}.XXXXXX")"
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"

retain_and_cleanup() {
    local status=$?
    trap - EXIT
    if { [ "$policy_completion" = 1 ] || [ "$stage" = 5 ]; } && [ -n "${DAEMON_PID:-}" ]; then
        kill -CONT -- "-$DAEMON_PID" 2>/dev/null || true
    fi
    stop_daemon
    # A blocked kernel caller may still own a continuation. Do not force unload.
    if ! pgrep -x 'klock_test|kd_native|kd_shadow_[0-2]' >/dev/null; then
        unload_modules
        if [ "$source_loaded" = 1 ] && [ -d /sys/module/kd_depth_source ]; then
            rmmod kd_depth_source || status=1
        fi
        # Do not leave ordinary tests linked against this optional source.
        if [ "$source_module" = 1 ]; then
            make -C "$KLOCK_DIR" KDLOCK_SOURCE_HELPER=0 W=1 -j8 > "$out/build-default-source.log" 2>&1 || status=1
        fi
        if [ "$selftest" = 1 ]; then
            make -C "$KM_DIR" KDLOCK_SELFTEST=0 W=1 -j8 > "$out/build-default.log" 2>&1 || status=1
        fi
    elif [ "$selftest" = 1 ]; then
        fail "$TEST_NAME" "workers remain active; retain test module for VM recovery"
        status=1
    fi
    dmesg > "$out/dmesg.log"
    find "$DAEMON_DIR" -path '*/0x*' -type f -print0 |
        sort -z | xargs -0 -r sha256sum > "$out/artifacts.sha256"
    (cd "$KDLOCK_DIR"
     find daemon -path 'daemon/0x*' -type f -print0 |
         tar --null -T - -czf "$out/artifacts.tar.gz")
    printf '%s\n' "$status" > "$out/exit-status"
    exit "$status"
}
trap retain_and_cleanup EXIT

if [ "$native_control" = 1 ] && { pgrep -x 'klock_test|daemon|kd_native|kd_renamed' >/dev/null ||
        grep -Eq '^(kdlock_km|klock_module) ' /proc/modules; }; then
    fail "$TEST_NAME" "native control requires an idle guest session"
    # Do not let this test's cleanup retire an unrelated existing session.
    trap - EXIT
    exit 1
fi
build_all
if [ "$source_module" = 1 ]; then
    make -C "$KLOCK_DIR" KDLOCK_SOURCE_HELPER=1 W=1 -j8 > "$out/build-source.log" 2>&1
    cp "$KLOCK_DIR/klock_module.ko" "$out/klock-source.ko"
    cp "$KLOCK_DIR/kd_depth_source.ko" "$out/kd_depth_source.ko"
fi
if [ "$waiter_signal" != 0 ]; then
    gcc -O2 -Wall -Wextra -Werror "$KDLOCK_DIR/tests/mutex_signal_client.c" -o "$out/signal-client"
fi
unload_modules
clear_dmesg
module_args=()
if [ "$selftest" = 1 ]; then
    make -C "$KM_DIR" KDLOCK_SELFTEST=1 W=1 -j8 > "$out/build-selftest.log" 2>&1
    cp "$KM_DIR/kdlock_km.ko" "$out/kdlock-selftest.ko"
    module_args+=(spin_selftest_fill_shadow="$shadow_capacity"
        spin_selftest_virtual_refusal="$virtual_resource")
fi
module_target="$TARGET_PROCESS"
if [ "$native_control" = 1 ]; then module_target=kd_unused; fi
load_kdlock target_process="$module_target" mutex_jit=1 "${module_args[@]}"
if [ "$source_module" = 1 ]; then
    insmod "$KLOCK_DIR/kd_depth_source.ko"
    source_loaded=1
fi
insmod "$KLOCK_DIR/klock_module.ko" native_resume_stage="$stage" \
    native_acquired_queue="$((spin_acquired == 2))" \
    native_pending_contended="$pending_contended" native_resume_registers="$registers" \
    native_waiter_signal="$waiter_signal" native_waiter_api="$waiter_api" \
    native_waiter_race="$waiter_race" native_stack_change="$stack_change" \
    native_ticket_pressure="$((virtual_resource == 3))" native_gate_pressure="$gate_pressure"
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
if [ "$shadow_capacity" = 1 ]; then
    shadow_outer="$(awk '$3 == "nested_lock_a" && $4 == "[klock_module]" { print $1 }' /proc/kallsyms)"
    shadow_inner="$(awk '$3 == "nested_lock_b" && $4 == "[klock_module]" { print $1 }' /proc/kallsyms)"
    test -n "$shadow_outer"
    test -n "$shadow_inner"
fi
probe_symbol=kd_resume_native_probe
if [ "$registers" = 1 ]; then
    probe_symbol=kd_resume_register_capture
fi
probe_ip="$(awk -v name="$probe_symbol" '$3 == name && $4 == "[klock_module]" { print $1 }' /proc/kallsyms)"
test -n "$probe_ip"
if [ "$spin_acquired" != 0 ]; then
    acquired_outer=$(awk '$3 == "nested_lock_a" && $4 == "[klock_module]" {print $1}' /proc/kallsyms)
    acquired_inner=$(awk '$3 == "nested_lock_b" && $4 == "[klock_module]" {print $1}' /proc/kallsyms)
    acquired_target=$(awk '$3 == "_raw_spin_lock" {print $1}' /proc/kallsyms)
    test -n "$acquired_outer" && test -n "$acquired_inner" && test -n "$acquired_target"
fi
if [ "$ooo" != 0 ]; then
    ooo_kind=spin
    ooo_symbol=nested_lock
    ooo_records=8
    if [ "$mode" = 4 ]; then
        ooo_kind=mutex
        ooo_symbol=nested_mutex
        ooo_records=1
    fi
    if [ "$dependency" != 0 ]; then
        ooo_records=1
    fi
    ooo_outer=$(awk -v name="${ooo_symbol}_a" '$3 == name && $4 == "[klock_module]" {print $1}' /proc/kallsyms)
    ooo_inner=$(awk -v name="${ooo_symbol}_b" '$3 == name && $4 == "[klock_module]" {print $1}' /proc/kallsyms)
    test -n "$ooo_outer"
    test -n "$ooo_inner"
    if [ "$ooo" = 3 ]; then
        ooo_symbol=_raw_spin_lock
        if [ "$mode" = 4 ]; then
            ooo_symbol=mutex_lock
        fi
        probe_ip=$(awk -v name="$ooo_symbol" '$3 == name {print $1}' /proc/kallsyms)
        test -n "$probe_ip"
    fi
fi
{
    date --iso-8601=seconds
    uname -a
    printf 'mode=%s stage=%s mutex_jit=1 pinned=%s rename=%s mixed=%s pending_contended=%s shadow_capacity=%s ooo=%s dependency=%s\n' \
        "$mode" "$stage" "$pinned" "$renamed" "$mixed" "$pending_contended" "$shadow_capacity" "$ooo" "$dependency"
    printf 'registers=%s probe_ip=%s\n' "$registers" "$probe_ip"
    printf 'native_control=%s target_process=%s\n' "$native_control" "$module_target"
    printf 'source_module=%s\n' "$source_module"
    printf 'stack_change=%s\n' "$stack_change"
    printf 'spin_acquired=%s\n' "$spin_acquired"
    printf 'shared_cpu=%s\n' "$shared_cpu"
    printf 'virtual_resource=%s\n' "$virtual_resource"
    printf 'waiter_signal=%s waiter_api=%s\n' "$waiter_signal" "$waiter_api"
    printf 'waiter_race=%s offset_us=%s expect=%s\n' "$waiter_race" "$waiter_race_us" "$waiter_expect"
} > "$out/environment.log"
if [ "$native_control" = 1 ]; then
    # No daemon, promotion or translation here. The loaded provider must never
    # admit these non-target callers; compare the same actual assembly probe.
    test "$(cat /sys/module/kdlock_km/parameters/target_process)" = kd_unused
    printf '1\n' > /sys/module/klock_module/parameters/native_regs_armed
    run_with_timeout 30 "$BENCH_BIN" 8 1 10 1 "$mode" > "$out/workload.log"
    PYTHONPATH="$KDLOCK_DIR/tests:$KDLOCK_DIR/disassem" python3 - "$out/native-state.json" <<'PY'
import json, os, sys
from pathlib import Path
import device_session
from native_only_protocol import entries
# A readonly observer cannot create a writer lease or pin source text.
fd = os.open(device_session.DEVICE, os.O_RDONLY | os.O_CLOEXEC)
try:
    state = device_session.info(fd)
finally:
    os.close(fd)
count = len(entries())
Path(sys.argv[1]).write_text(json.dumps({"source": state, "entries": count}) + "\n")
assert state == {"state": 0, "modules": 0, "frames": 0, "writers": 0}
assert count == 0, "native control registered a JIT entry"
PY
    unload_modules
    check_dmesg_ok
    check_complex_cs_integrity 8 1
    check_dmesg_has 'kd_resume records: requests=8 failures=0'
    check_mutex_origin_accounting
    dmesg > "$out/registers.log"
    python3 "$KDLOCK_DIR/tests/native_register_protocol.py" "$out/registers.log" \
        "$probe_ip" 8 --native-only > "$out/registers.json"
    pass "$TEST_NAME native-only mode=$mode; no JIT execution"
    exit 0
fi
start_daemon 2

promotion_mode="$mode"
artifacts=1
artifact_timeout=30
threads=8
states=1
operations=12009
requests=12009
case "$mode" in
    1) artifacts=2 ;;
    # Six guarded translations are serial; keep the native/JIT execution
    # timeout and all register/ownership checks unchanged.
    8) promotion_mode=1; artifacts=6; artifact_timeout=90 ;;
esac
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 "$promotion_mode" > "$out/warmup.log"
sleep 1
run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 "$promotion_mode" > "$out/promotion.log"
if [ "$mode" = 8 ]; then
    for role in 0 2 4; do
        run_with_timeout 10 "$BENCH_BIN" 1 1 10 1 8 "$role" >> "$out/registration.log"
    done
fi
if [ "$gate_pressure" = 1 ]; then
    # Publish a separate root before the old native interval. Its warm branch
    # skips C, so C still has no gate when the real table is later saturated.
    python3 "$KDLOCK_DIR/tests/spin_gate_protocol.py" promote-root "$out"
    run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 8 1073741833 > "$out/gate-warmup.log"
    artifacts=$((artifacts + 1))
fi
artifact_started=$SECONDS
artifact_output="$(wait_for_jit_artifact_count "$artifacts" "$artifact_timeout")"
mapfile -t asm_dirs <<< "$artifact_output"
info "JIT artifacts ready after $((SECONDS - artifact_started))s (limit ${artifact_timeout}s)"
for asm_dir in "${asm_dirs[@]}"; do
    check_jit_artifacts "$asm_dir"
done
sleep 1
check_daemon_read_kernel_text "$DAEMON_LOG"
check_dmesg_has "$JIT_INSTALL_PATTERN"
if [ "$policy_completion" = 1 ] || [ "$stage" = 5 ]; then
    kill -STOP -- "-$DAEMON_PID"
else
    stop_daemon
fi
if [ "$virtual_resource" = 3 ]; then
    # Only promotion is controlled. Each lock will occupy its ticket through
    # the real hook/acquisition; never write ticket counts or physical words.
    dmesg > "$out/ticket-promotion.log"
    python3 - "$out/ticket-promotion.log" <<'PY'
import re, sys
from pathlib import Path
rows = re.findall(r"kd_ticket lock: cpu=(\d+) index=(\d+) lock=([0-9a-f]+)",
                  Path(sys.argv[1]).read_text())
assert len(rows) == 62 and len({addr for _, _, addr in rows}) == 62
assert {(int(cpu), int(i)) for cpu, i, _ in rows} == {
    (cpu, i) for cpu in (4, 6) for i in range(31)}
for _, _, addr in rows:
    Path("/sys/module/kdlock_km/parameters/spin_selftest_promote").write_text("0x" + addr)
PY
fi
if [ "$gate_pressure" = 1 ]; then
    python3 "$KDLOCK_DIR/tests/spin_gate_protocol.py" prepare "$out"
    # The controller cannot compete with the pinned original roles while it
    # samples the map and releases B. This does not move any existing worker.
    taskset -pc 12 "$$" > "$out/gate-controller.log"
fi
if [ "$registers" = 1 ]; then
    printf '1\n' > /sys/module/klock_module/parameters/native_regs_armed
fi
if [ "$spin_acquired" != 0 ]; then
    test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    printf '1\n' > /sys/module/kdlock_km/parameters/spin_jit_fail_after_nested_lock
fi
if [ "$stack_change" = 1 ]; then
    python3 "$KDLOCK_DIR/tests/mutex_stack_protocol.py" prepare "$out" "${asm_dirs[0]}"
    printf '1\n' > /sys/module/klock_module/parameters/native_stack_armed
fi
if [ "$renamed" = 1 ]; then
    printf '1\n' > /sys/module/klock_module/parameters/native_resume_rename
fi
if [ "$ooo" != 0 ]; then
    printf '%s\n' "$ooo" > /sys/module/klock_module/parameters/native_resume_ooo
fi
if [ "$dependency" != 0 ]; then
    printf '%s\n' "$dependency" > "/sys/module/klock_module/parameters/${ooo_kind}_ooo_dependency"
fi
if [ "$stage" = 4 ]; then
    kind=1
    symbol=_raw_spin_lock
    if [ "$mode" = 4 ]; then
        kind=2
        symbol=mutex_lock
        case "$waiter_api" in
            1) symbol=mutex_lock_interruptible ;;
            2) symbol=mutex_lock_killable ;;
        esac
    fi
    probe_ip="$(awk -v name="$symbol" '$3 == name { print $1 }' /proc/kallsyms)"
    test -n "$probe_ip"
    if [ "$stack_change" = 1 ]; then
        # The runtime must detect an actual write after B's acquisition. Do
        # not turn this into an unstarted acquisition through fault injection.
        test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    elif [ "$waiter_api" != 0 ]; then
        # The actual native API must be the ordinary CALL-miss target. Do not
        # substitute a synthetic PENDING resource failure for cancellation.
        test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    elif [ "$shadow_capacity" = 1 ]; then
        test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_fill_shadow)" = 1
        test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    elif [ "$virtual_resource" != 0 ]; then
        test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_virtual_refusal)" = "$virtual_resource"
        test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    else
        printf '%s\n' "$kind" > /sys/module/kdlock_km/parameters/jit_fail_pending_lock
    fi
fi

if [ "$stage" = 5 ]; then
    # Learn the ordinary helper CALL from an actual miss. Recompile only after
    # every first-wave caller exits; no executor sees an in-place replacement.
    test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    probe_ip="$(awk '$3 == "mutex_lock" { print $1 }' /proc/kallsyms)"
    test -n "$probe_ip"
    asm_dir="${asm_dirs[0]}"
    entry="$(basename "$(dirname "$(dirname "$asm_dir")")")"
    cp "$asm_dir/jit.bin" "$out/entry-only.bin"
    helpers=(kd_resume_depth_mutex)
    if [ "$source_module" = 1 ]; then
        helpers+=(kd_depth_source_enter)
        python3 "$KDLOCK_DIR/tests/source_depth_protocol.py" root "$out" "$entry"
    fi
    printf '1\n' > /sys/module/klock_module/parameters/native_depth_armed
    previous_image="$out/entry-only.bin"
    # Learn one real CALL level per joined wave. Pause the existing writer
    # between waves; neither source addresses nor callee tables are preseeded.
    for helper in "${helpers[@]}"; do
        helper_ip="$(awk -v name="$helper" '$3 == name { print $1 }' /proc/kallsyms)"
        test -n "$helper_ip"
        dmesg > "$out/before-learning-$helper.log"
        run_with_timeout 60 "$BENCH_BIN" "$threads" 1 1000000 1 4 > "$out/learning-$helper.log"
        dmesg > "$out/after-learning-$helper.log"
        check_dmesg_has "kd_native begin:.* ip=$helper_ip .*held=1 mutex=1"
        PYTHONPATH="$KDLOCK_DIR/tests" python3 -c '
import sys
from native_only_protocol import entries
entry = next(e for e in entries() if e.rip == int(sys.argv[1], 16))
assert entry.status == 1 and entry.target == int(sys.argv[2], 16)
' "$entry" "$helper_ip"
        if [ "$source_module" = 1 ]; then
            phase=foreign-miss
            if [ "$helper" = kd_resume_depth_mutex ]; then
                phase=local-miss
            fi
            python3 "$KDLOCK_DIR/tests/source_depth_protocol.py" "$phase" "$out" "$entry"
        fi
        kill -CONT -- "-$DAEMON_PID"
        PYTHONPATH="$KDLOCK_DIR/tests" python3 -c '
import sys, time
from native_only_protocol import entries
deadline = time.monotonic() + 30
while True:
    entry = next(e for e in entries() if e.rip == int(sys.argv[1], 16))
    assert entry.status != -3, "deep callee was refused"
    if entry.status == 0:
        break
    assert time.monotonic() < deadline, "callee completion timed out"
    time.sleep(0.1)
' "$entry"
        if [ "$source_module:$helper" = 1:kd_resume_depth_mutex ]; then
            kill -STOP -- "-$DAEMON_PID"
            python3 "$KDLOCK_DIR/tests/source_depth_protocol.py" local-ready "$out" "$entry"
        else
            stop_daemon
        fi
        grep -q "^loc_${helper_ip}:" "$asm_dir/jit.S"
        grep -qi "$helper_ip" "$asm_dir/callee_table.txt"
        check_jit_artifacts "$asm_dir"
        if cmp -s "$previous_image" "$asm_dir/jit.bin"; then
            fail "$TEST_NAME" "callee completion did not change the JIT image"
            exit 1
        fi
        cp "$asm_dir/jit.bin" "$out/learned-$helper.bin"
        cp "$asm_dir/jit.S" "$out/learned-$helper.S"
        cp "$asm_dir/callee_table.txt" "$out/learned-$helper.table"
        previous_image="$out/learned-$helper.bin"
    done
    if [ "$source_module" = 1 ]; then
        python3 "$KDLOCK_DIR/tests/source_depth_protocol.py" ready "$out" "$entry"
    fi
    dmesg > "$out/before-capacity.log"
    run_with_timeout 60 "$BENCH_BIN" "$threads" 1 1000000 1 4 > "$out/workload.log"
    test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    depth_runs=$((threads * (${#helpers[@]} + 1)))
    operations=$((12001 + depth_runs))
    requests=$operations
elif [ "$pinned" = 1 ]; then
    timeout --kill-after=5s 90s taskset -c 0 "$BENCH_BIN" \
        1 1 200000000 1 3 > "$out/holder.log" 2>&1 &
    holder=$!
    sleep 0.1
    run_with_timeout 90 taskset -c 1 "$BENCH_BIN" \
        4 1 1000000 1 3 > "$out/workload.log"
    wait "$holder"
    operations=12006
    requests=12006
elif [ "$spin_acquired" = 2 ]; then
    # Real virtual B head plus native follower; no synthetic private queue.
    pids=()
    roles=(1 3 4 6 0 2 8)
    for role in "${roles[@]}"; do
        timeout --kill-after=5s 30s taskset -c "$role" "$BENCH_BIN" \
            1 1 50000 1 1 "$((2147483648 + role))" > "$out/role-$role.log" 2>&1 &
        pids+=("$!")
    done
    failed=0
    for index in "${!pids[@]}"; do
        status=0
        wait "${pids[$index]}" || status=$?
        printf '%s\t%s\n' "${roles[$index]}" "$status" >> "$out/role-status.tsv"
        test "$status" = 0 || failed=1
    done
    test "$failed" = 0
    operations=12008
    requests=12002
    states=2
elif [ "$mode" = 4 ] && { [ "$stage" != 4 ] || [ "$pending_contended" = 1 ]; }; then
    # A's delegation queue contends on native B. The opt-in placement needs
    # actual cooperative mutex waits so all three A roles can share CPU 4.
    pids=()
    roles=(1 3 2 4 0 5 6)
    if [ "$dependency" = 2 ]; then
        roles+=(7)
    fi
    for role in "${roles[@]}"; do
        role_cpu=$role
        if [ "$shared_cpu" = 1 ]; then
            case "$role" in 0|4|6) role_cpu=4 ;; esac
        fi
        printf '%s\t%s\n' "$role" "$role_cpu" >> "$out/role-cpus.tsv"
        role_comm="$TARGET_PROCESS"
        if [ "$role" = 7 ]; then
            role_comm=kd_native
        fi
        if [ "$pending_contended" = 1 ]; then
            case "$role" in 1|2|5) role_comm=kd_native ;; esac
        fi
        if [ "$role" = 0 ] && [ "$waiter_signal" != 0 ]; then
            signal_option=pending
            if [ "$waiter_race" = 1 ]; then
                signal_option=pending-race
            fi
            if [ "$waiter_signal" = 9 ]; then
                signal_option+=-kill
            else
                signal_option+=-int
            fi
            timeout --kill-after=5s 60s taskset -c "$role_cpu" "$out/signal-client" \
                0 "$TARGET_PROCESS" "$signal_option" > "$out/role-$role.log" 2>&1 &
        else
            timeout --kill-after=5s 60s env KD_TEST_COMM="$role_comm" \
                taskset -c "$role_cpu" "$BENCH_BIN" \
                1 1 50000 1 4 "$((2147483648 + role))" \
                > "$out/role-$role.log" 2>&1 &
        fi
        pids+=("$!")
    done
    failed=0
    if [ "$waiter_race" = 1 ]; then
        # Publish/trigger from userspace while all seven real ioctl tasks live.
        # Still join every role on controller failure before considering unload.
        run_with_timeout 20 python3 "$KDLOCK_DIR/tests/native_waiter_signal_race.py" \
            --client "$out/role-0.log" --signal "$waiter_signal" \
            --offset-us "$waiter_race_us" --output "$out/race-trigger.json" \
            > "$out/race-trigger.log" 2>&1 || failed=1
    fi
    for index in "${!pids[@]}"; do
        status=0
        wait "${pids[$index]}" || status=$?
        expected=0
        if [ "${roles[$index]}" = 0 ] && [ "$waiter_signal" = 9 ]; then
            expected=137
        fi
        printf '%s\t%s\n' "${roles[$index]}" "$status" >> "$out/role-status.tsv"
        if [ "$status" != "$expected" ]; then
            failed=1
        fi
    done
    test "$failed" = 0
    operations=12008
    waiter_acquired=1
    if [ "$waiter_api" != 0 ]; then
        # The cancelled acquisition never enters B's protected transition.
        waiter_acquired=0
        if [ "$waiter_race" = 1 ]; then
            waiter_acquired="$(cat /sys/module/klock_module/parameters/native_waiter_acquired)"
            case "$waiter_acquired" in 0|1) ;; *) exit 1 ;; esac
        fi
        operations=$((12007 + waiter_acquired))
    fi
    if [ "$dependency" = 2 ]; then
        operations=$((operations + 1))
    fi
    requests=12002
    states=2
elif [ "$mode" = 1 ] && [ "$dependency" != 0 ]; then
    # Holder, pending, combiner, nested waiter, trailing. C is held by the
    # trailing target or by a sixth participant using only native Linux locks.
    pids=()
    roles=(1 2 3 0 4)
    if [ "$dependency" = 2 ]; then
        roles+=(5)
    fi
    for role in "${roles[@]}"; do
        role_comm="$TARGET_PROCESS"
        if [ "$role" = 5 ]; then
            role_comm=kd_native
        fi
        timeout --kill-after=5s 60s env KD_TEST_COMM="$role_comm" \
            taskset -c "$role" "$BENCH_BIN" \
            1 1 50000 1 1 "$((2147483648 + role))" \
            > "$out/role-$role.log" 2>&1 &
        pids+=("$!")
    done
    failed=0
    for pid in "${pids[@]}"; do
        wait "$pid" || failed=1
    done
    test "$failed" = 0
    operations=12006
    if [ "$dependency" = 2 ]; then
        operations=$((operations + 1))
    fi
    requests=12002
    states=2
elif [ "$mode:$stage" = 8:4 ]; then
    # B has one pending-bit contender and one queued original waiter. A keeps
    # its ordinary holder/pending/head/waiter/trailing delegation topology.
    pids=()
    for role in 1 2 3 4 6 0 8; do
        timeout --kill-after=5s 60s taskset -c "$role" "$BENCH_BIN" \
            1 1 50000 1 8 "$((2147483648 + role))" \
            > "$out/role-$role.log" 2>&1 &
        pids+=("$!")
    done
    failed=0
    if [ "$gate_pressure" = 1 ]; then
        python3 "$KDLOCK_DIR/tests/spin_gate_protocol.py" held "$out" || failed=1
        if [ "$failed" = 0 ]; then
            status=0
            run_with_timeout 10 taskset -c 9 "$BENCH_BIN" \
                1 1 1 1 8 1073741824 > "$out/gate-role-0.log" 2>&1 || status=$?
            printf '0\t%s\n' "$status" > "$out/gate-role-status.tsv"
            test "$status" = 0 || failed=1
        fi
        if [ "$failed" = 0 ]; then
            python3 "$KDLOCK_DIR/tests/spin_gate_protocol.py" filled "$out" || failed=1
        fi
        if [ "$failed" = 0 ]; then
            gate_pids=()
            for role in 1 2; do
                comm="$TARGET_PROCESS"
                test "$role" != 1 || comm=kd_native
                timeout --kill-after=5s 10s env KD_TEST_COMM="$comm" \
                    taskset -c "$((9 + role))" "$BENCH_BIN" \
                    1 1 1 1 8 "$((1073741824 + role))" \
                    > "$out/gate-role-$role.log" 2>&1 &
                gate_pids+=("$!")
            done
            for index in "${!gate_pids[@]}"; do
                status=0
                wait "${gate_pids[$index]}" || status=$?
                printf '%s\t%s\n' "$((index + 1))" "$status" >> "$out/gate-role-status.tsv"
                test "$status" = 0 || failed=1
            done
        fi
        if [ "$failed" = 0 ]; then
            gate_pids=()
            # Six new CPUs keep the old pinned A/B protocol undisturbed.
            # C's non-target holder waits for Linux queue publication; A's
            # second candidate delegates the already-published root to JIT.
            for role in 3 4 5 6 7 8; do
                comm="$TARGET_PROCESS"
                test "$role" != 8 || comm=kd_native
                timeout --kill-after=5s 20s env KD_TEST_COMM="$comm" \
                    taskset -c "$((10 + role))" "$BENCH_BIN" \
                    1 1 1 1 8 "$((1073741824 + role))" \
                    > "$out/gate-role-$role.log" 2>&1 &
                gate_pids+=("$!")
            done
            python3 "$KDLOCK_DIR/tests/spin_gate_protocol.py" progress "$out" || failed=1
            # Release only the test holder, including on a failed observation;
            # never repair queue/frame storage to manufacture a passing drain.
            printf '1\n' > /sys/module/klock_module/parameters/native_gate_progress_release
            for index in "${!gate_pids[@]}"; do
                status=0
                wait "${gate_pids[$index]}" || status=$?
                printf '%s\t%s\n' "$((index + 3))" "$status" >> "$out/gate-role-status.tsv"
                test "$status" = 0 || failed=1
            done
            python3 "$KDLOCK_DIR/tests/spin_gate_protocol.py" drained "$out" || failed=1
        fi
        # Even a failed pressure oracle must let the original bounded case
        # drain; it remains failed and never gains an acceptance marker.
        printf '1\n' > /sys/module/klock_module/parameters/native_gate_release
    fi
    for pid in "${pids[@]}"; do
        wait "$pid" || failed=1
    done
    test "$failed" = 0
    operations=12011
    requests=12003
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

if [ "$ooo" != 0 ]; then
    operations=$((operations + ooo_records))
    dmesg > "$out/ooo-before-unload.log"
fi

if [ "$spin_acquired" != 0 ]; then
    test "$(cat /sys/module/kdlock_km/parameters/spin_jit_fail_after_nested_lock)" = 0
    check_dmesg_not_has 'reason=PENDING_LOCK_NATIVE'
fi

if [ "$stage" = 4 ]; then
    test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
fi
if [ "$stack_change" = 1 ]; then
    check_dmesg_not_has 'reason=PENDING_LOCK_NATIVE'
    python3 "$KDLOCK_DIR/tests/mutex_stack_protocol.py" snapshot "$out"
elif [ "$waiter_api" != 0 ]; then
    check_dmesg_not_has 'reason=PENDING_LOCK_NATIVE'
    # Read the ordinary miss's real device state while the module still lives.
    # The oracle later matches this entry/target to the returned JIT witness.
    PYTHONPATH="$KDLOCK_DIR/tests" python3 -c '
import json
from native_only_protocol import entries
print(json.dumps([dict(entry=hex(e.rip), target=hex(e.target), code=hex(e.code),
                      pid=e.pid, tgid=e.tgid, kind=e.lock_kind, status=e.status)
                  for e in entries()]))
' > "$out/cancel-publication.json"
elif [ "$stage" = 4 ]; then
    dmesg | grep 'reason=PENDING_LOCK_NATIVE' > "$out/pending-lock.log"
    python3 -c '
import errno, re, sys
lines = open(sys.argv[1]).read().splitlines()
assert len(lines) == 1 + int(sys.argv[5])
# Keep the original ticket packet check separate. The progressed ENOMEM root
# has its own ELF/identity/body/frame/owner oracle in spin_gate_protocol.py.
if sys.argv[5] == "1":
    lines = [line for line in lines if " error=-7 " in line]
assert len(lines) == 1
line = lines[0]
fields = dict(re.findall(r"(\w+)=(0x[0-9a-f]+|[0-9-]+)", line))
values = {k: int(v, 0) for k, v in fields.items()}
assert values["target"] == int(sys.argv[2], 16)
assert values["error"] == (-errno.ENOMEM if sys.argv[4] == "1" else -errno.E2BIG)
pre_stage = values["mutex"] or sys.argv[3] == "1"
assert values["staged_ip"] == (values["target"] if pre_stage else values["return"])
assert values["staged_sp"] == values["sp"] + (0 if pre_stage else 8)
' "$out/pending-lock.log" "$probe_ip" "$shadow_capacity" "$virtual_resource" "$gate_pressure"
fi
if [ "$virtual_resource" != 0 ]; then
    test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_virtual_refusal)" = 0
    dmesg > "$out/virtual-resource.log"
    python3 -c '
import errno, re, sys
text = open(sys.argv[1]).read()
lines = re.findall(r"kd_spin virtual refusal: ([^\n]+)", text)
assert len(lines) == 1, lines
fields = dict(re.findall(r"(\w+)=([-\w]+)", lines[0]))
kind = int(sys.argv[2])
expected = {"kind": kind, "ret": -errno.ENOMEM if kind == 1 else -errno.E2BIG,
            "phase": 1, "retired": 1, "pin": 1, "nodes": 1, "contexts": 1,
            "packet": 1, "frame": 1, "owner": 1, "executed": 1,
            "allocated": int(kind != 3), "injected": int(kind != 3)}
for key, value in expected.items():
    assert int(fields[key]) == value, (key, fields)
assert fields["cpu"] in {"4", "6"}
assert int(fields["target"], 16) == int(sys.argv[3], 16)
pid = fields["task"]
begins = re.findall(r"kd_native begin: task=" + pid + r" ([^\n]+)", text)
assert len(begins) == 1
begin = dict(re.findall(r"(\w+)=(\w+)", begins[0]))
assert begin["held"] == "1" and begin["mutex"] == "0"
assert all(begin[k] == fields[k] for k in ("outer", "entry", "cpu"))
assert int(begin["ip"], 16) == int(fields["target"], 16)
blocked = re.findall(r"kd_pending spin blocked: task=" + pid + r" ([^\n]+)", text)
assert len(blocked) == 1
blocked = dict(re.findall(r"(\w+)=(\w+)", blocked[0]))
assert all(blocked[k] == fields[k] for k in ("outer", "lock"))
events = [text.index(event) for event in ("kd_spin virtual refusal:",
          "reason=PENDING_LOCK_NATIVE", "kd_native begin: task=" + pid + " ",
          "kd_pending spin blocked:", "kd_pending spin acquired:",
          "kd_native complete: task=" + pid + " ")]
assert events == sorted(events)
assert "kd_spin virtual refusal error:" not in text
if kind == 3:
    # Both potential A combiners actually hold/release 31 distinct locks. The
    # observed combiner must keep them across this native frame and final ACK.
    held = re.findall(r"kd_ticket held: task=(\d+) cpu=(\d+) acquire=(\d+) "
                      r"owned=31 pins=31 valid=1", text)
    released = re.findall(r"kd_ticket released: task=(\d+) cpu=(\d+) "
                          r"locks=31 pins=0 valid=1", text)
    assert len(held) == 4 and len(released) == 2
    assert {(cpu, phase) for _, cpu, phase in held} == {
        (cpu, phase) for cpu in ("4", "6") for phase in ("0", "1")}
    assert len({task for task, _ in released}) == 2
    for task, cpu in released:
        assert [(task, cpu, phase) in held for phase in ("0", "1")] == [True, True]
        order = [text.index(event) for event in (
            f"kd_ticket held: task={task} cpu={cpu} acquire=1 ",
            f"kd_ticket held: task={task} cpu={cpu} acquire=0 ",
            f"kd_ticket released: task={task} cpu={cpu} ")]
        assert order == sorted(order)
        if cpu == fields["cpu"]:
            assert order[0] < events[0] < events[-1] < order[1]
    assert "valid=0" not in text
' "$out/virtual-resource.log" "$virtual_resource" "$probe_ip"
fi
if [ "$shadow_capacity" = 1 ]; then
    test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_fill_shadow)" = 0
    dmesg > "$out/shadow-capacity.log"
    python3 -c '
import errno, re, sys
text = open(sys.argv[1]).read()
lines = re.findall(r"kd_spin shadow pressure: ([^\n]+)", text)
assert len(lines) == 1
fields = dict(re.findall(r"(\w+)=([-\w]+)", lines[0]))
for key, expected in {"logical": 1, "local": 8, "held": 7, "physical": 1,
                      "ret": -errno.E2BIG, "phase": 1, "regs": 1,
                      "restored": 1, "executed": 1, "failures": 0}.items():
    assert int(fields[key]) == expected, (key, fields)
assert int(fields["target"], 16) == int(sys.argv[2], 16)
assert int(fields["outer"], 16) == int(sys.argv[3], 16)
assert int(fields["lock"], 16) == int(sys.argv[4], 16)
pid = fields["task"]
begins = re.findall(r"kd_native begin: task=" + pid + r" ([^\n]+)", text)
assert len(begins) == 1
begin = dict(re.findall(r"(\w+)=(\w+)", begins[0]))
assert begin["held"] == "1" and begin["mutex"] == "0"
for key in ("entry", "outer"):
    assert int(begin[key], 16) == int(fields[key], 16)
assert int(begin["ip"], 16) == int(fields["target"], 16)
assert len(re.findall(r"kd_native complete: task=" + pid + r" ", text)) == 1
events = [text.index(event) for event in ("kd_spin shadow pressure:",
          "reason=PENDING_LOCK_NATIVE", "kd_native begin: task=" + pid + " ",
          "kd_native complete: task=" + pid + " ")]
assert events == sorted(events)
assert "kd_spin selftest error:" not in text
' "$out/shadow-capacity.log" "$probe_ip" "$shadow_outer" "$shadow_inner"
fi

if [ "$policy_completion" = 1 ]; then
    # Preserve the executed generation before rejection removes its artifacts.
    (cd "$KDLOCK_DIR"
     tar -czf "$out/pre-completion-artifacts.tar.gz" daemon/0x*)
    before="$(dmesg | grep -c 'kd_native begin:' || true)"
    test "$before" -gt 0
    kill -CONT -- "-$DAEMON_PID"
    python3 "$KDLOCK_DIR/tests/native_only_protocol.py" --all --protocol > "$out/rejection.json"
    grep 'reason=CONTEXT_NATIVE_ONLY' "$DAEMON_LOG" > "$out/policy.log"
    run_with_timeout 60 "$BENCH_BIN" "$threads" 1 1000000 1 "$mode" > "$out/native-after-rejection.log"
    after="$(dmesg | grep -c 'kd_native begin:' || true)"
    test "$before" = "$after"
    operations=$((operations + threads))
    requests=$((requests + threads))
    stop_daemon
fi

if [ "$source_module" = 1 ]; then
    # The final capacity wave has joined and the compiler is gone. Observe
    # pin release before normal source unload, leaving the provider for cleanup.
    python3 "$KDLOCK_DIR/tests/source_depth_protocol.py" retire "$out" "$entry"
fi
unload_modules
check_dmesg_ok
if [ "$gate_pressure" = 1 ]; then
    dmesg > "$out/gate-protocol.log"
    python3 "$KDLOCK_DIR/tests/spin_gate_protocol.py" validate "$out" > "$out/gate-result.json"
fi
check_any_jit_entry_executed "${asm_dirs[@]}"
if [ "$shadow_capacity" = 1 ]; then
    check_any_jit_entry_executed_for_lock "$shadow_outer" "${asm_dirs[@]}"
fi
check_complex_cs_integrity "$operations" "$states"
check_dmesg_has "kd_resume records: requests=$requests failures=0"
if [ "$virtual_resource" = 3 ]; then
    check_dmesg_has 'kd_ticket stats: completed=1,1 locks=31'
fi
check_dmesg_has 'kd_native stats: started=[1-9][0-9]* completed=[1-9][0-9]*'
if [ "$spin_acquired" != 0 ]; then
    dmesg > "$out/spin-acquired.log"
    acquired_options=()
    if [ "$spin_acquired" = 2 ]; then
        acquired_options+=(--queued --statuses "$out/role-status.tsv")
    fi
    python3 "$KDLOCK_DIR/tests/spin_acquired_protocol.py" "$out/spin-acquired.log" \
        "$acquired_outer" "$acquired_inner" "$acquired_target" "${acquired_options[@]}" > "$out/spin-acquired.json"
    info "Checked post-acquisition continuation: $(cat "$out/spin-acquired.json")"
elif [ "$stack_change" = 1 ]; then
    dmesg > "$out/stack-change.log"
    python3 "$KDLOCK_DIR/tests/mutex_stack_protocol.py" check "$out" "${asm_dirs[0]}" \
        > "$out/stack-change.json"
    info "Real shared-stack continuation verified: $(cat "$out/stack-change.json")"
else
    check_dmesg_has "kd_native begin:.* ip=$probe_ip "
fi
if [ "$registers" = 1 ]; then
    dmesg > "$out/registers.log"
    python3 "$KDLOCK_DIR/tests/native_register_protocol.py" "$out/registers.log" \
        "$probe_ip" "$requests" > "$out/registers.json"
    info "CALL-miss register/stack witnesses verified: $(cat "$out/registers.json")"
fi
if [ "$stage" = 5 ]; then
    dmesg > "$out/depth-capacity.log"
    python3 -c '
import errno, re, sys
text = open(sys.argv[1]).read()
pending = re.findall(r"reason=PENDING_LOCK_NATIVE ([^\n]+)", text)
assert pending, "no real capacity failure"
for line in pending:
    values = {k: int(v, 0) for k, v in re.findall(r"(\w+)=(0x[0-9a-f]+|[0-9-]+)", line)}
    assert values["error"] == -errno.E2BIG and values["mutex"] == 1
    assert values["target"] == int(sys.argv[2], 16)
    assert values["staged_ip"] == values["target"] and values["staged_sp"] == values["sp"]
capacity, callee, native = map(int, re.search(
    r"kd_depth mutex stats: capacity=(\d+) callee=(\d+) native=(\d+)", text).groups())
assert capacity == len(pending) and callee > 0
assert capacity + callee + native == int(sys.argv[3])
assert len(re.findall(r"kd_native begin:.*held=8 mutex=1", text)) == capacity
assert len(re.findall(r"kd_depth mutex:.*retained=7 children=8 valid=1", text)) == capacity
assert len(re.findall(r"kd_depth mutex:.*retained=0 children=8 valid=1", text)) == callee
started, completed, unlocks = map(int, re.search(
    r"kd_native stats: started=(\d+) completed=(\d+) unlocks=(\d+)", text).groups())
assert started == completed == capacity + callee
assert unlocks == capacity * 8 + callee
assert "valid=0" not in text
' "$out/depth-capacity.log" "$probe_ip" "$depth_runs"
fi
if [ "$pending_contended" = 1 ] && [ "$mode" = 8 ]; then
    check_dmesg_has 'kd_pending spin: observed=1 acquired=1'
    dmesg > "$out/pending-contended.log"
    python3 -c '
import re, sys
text = open(sys.argv[1]).read()
def fields(kind):
    lines = re.findall(r"kd_pending spin " + kind + r": ([^\n]+)", text)
    assert len(lines) == 1, (kind, lines)
    return dict(re.findall(r"(\w+)=(\w+)", lines[0]))
blocked, acquired = fields("blocked"), fields("acquired")
assert blocked["queued"] == "0", "native waiter must not join the private queue"
assert blocked["valid"] == acquired["valid"] == "1"
for observation in (blocked, acquired):
    assert int(observation["a_val"], 16) & 0xff in (1, 3)
    assert int(observation["a_private"], 16) & 0xff == 3
assert int(blocked["b_val"], 16) & 0xff in (1, 3)
assert blocked["holder_comm"] == "klock_test"
assert blocked["cpu"] == acquired["cpu"] == "0"
assert blocked["holder_cpu"] == "1"
assert all(blocked[k] == acquired[k] for k in ("task", "outer", "lock"))
assert int(blocked["b_val"], 16) != int(acquired["b_val"], 16)
assert int(acquired["b_val"], 16) == 1
pid = blocked["task"]
begins = re.findall(r"kd_native begin: task=" + pid + r" ([^\n]+)", text)
assert len(begins) == 1
begin = dict(re.findall(r"(\w+)=(\w+)", begins[0]))
assert begin["outer"] == blocked["outer"]
assert begin["held"] == "1" and begin["mutex"] == "0"
assert begin["cpu"] in {"4", "6"}
assert int(begin["ip"], 16) == int(sys.argv[2], 16)
events = [text.index(event) for event in (
    "reason=PENDING_LOCK_NATIVE", "kd_native begin: task=" + pid + " ",
    "kd_pending spin blocked:", "kd_pending spin acquired:",
    "kd_native complete: task=" + pid + " ")]
assert events == sorted(events)
expected = 1 + int(sys.argv[3])
assert f"kd_native stats: started={expected} completed={expected} unlocks={expected}" in text
' "$out/pending-contended.log" "$probe_ip" "$gate_pressure"
elif [ "$pending_contended" = 1 ] && [ "$waiter_api" = 0 ] && [ "$stack_change" = 0 ]; then
    check_dmesg_has 'kd_pending mutex: observed=1 acquired=1'
    dmesg > "$out/pending-contended.log"
    PYTHONPATH="$KDLOCK_DIR/tests" python3 - "$out" "$shared_cpu" > "$out/pending-contended.json" <<'PY'
import json, sys
from pathlib import Path
from native_waiter_signal_protocol import validate_pending_mutex
out = Path(sys.argv[1])
print(json.dumps(validate_pending_mutex(
    (out / 'pending-contended.log').read_text(), bool(int(sys.argv[2])),
    (out / 'role-cpus.tsv').read_text(), (out / 'role-status.tsv').read_text()), sort_keys=True))
PY
elif [ "$pending_contended" = 1 ] && [ "$stack_change" = 0 ]; then
    check_dmesg_has "kd_pending mutex: observed=1 acquired=$waiter_acquired"
fi
if [ "$pinned" = 1 ]; then
    check_dmesg_has 'kd_native begin:.*mutex=1 cpu=1'
fi
if [ "$waiter_signal" != 0 ]; then
    dmesg > "$out/waiter-signal.log"
    signal_options=(--api "$waiter_api" --target "$probe_ip")
    if [ "$waiter_api" != 0 ]; then
        signal_options+=(--publication "$out/cancel-publication.json")
    fi
    if [ "$waiter_race" = 1 ]; then
        signal_options+=(--race-trigger "$out/race-trigger.json" --expect "$waiter_expect")
    fi
    python3 "$KDLOCK_DIR/tests/native_waiter_signal_protocol.py" \
        --dmesg "$out/waiter-signal.log" --client "$out/role-0.log" \
        --statuses "$out/role-status.tsv" --signal "$waiter_signal" \
        "${signal_options[@]}" > "$out/waiter-signal.json"
    info "Original waiter signal/continuation verified: $(cat "$out/waiter-signal.json")"
fi
started="$(dmesg | sed -n 's/.*kd_native stats: started=\([0-9]*\).*/\1/p' | tail -1)"
completed="$(dmesg | sed -n 's/.*kd_native stats:.*completed=\([0-9]*\).*/\1/p' | tail -1)"
test "$started" = "$completed"
if [ "$ooo" != 0 ]; then
    dmesg > "$out/ooo-final.log"
    ooo_options=()
    if [ "$ooo" = 2 ]; then
        ooo_options+=(--after-outer)
    elif [ "$ooo" = 3 ]; then
        ooo_options+=(--pending-after-outer)
    fi
    if [ "$dependency" != 0 ]; then
        ooo_options+=(--dependency "$dependency")
    fi
    python3 "$KDLOCK_DIR/tests/native_ooo_protocol.py" "$out/ooo-final.log" \
        "$ooo_kind" "$ooo_records" "$ooo_outer" "$ooo_inner" "$probe_ip" \
        "${ooo_options[@]}"
fi
if [ "$renamed" = 1 ]; then
    dmesg > "$out/rename.log"
    python3 -c '
import re, sys
text = open(sys.argv[1]).read()
spin = sys.argv[2] not in {"3", "4"}
renames = list(re.finditer(r"kd_resume rename: ([^\n]+)", text))
assert renames, "no observed rename"
for event in renames:
    fields = dict(re.findall(r"(\w+)=(\w+)", event[1]))
    assert fields["valid"] == "1"
    assert fields["preempt_before"] == fields["preempt_after"]
    assert fields["irq_before"] == fields["irq_after"] == "0"
    if fields["new"] == "klock_test":
        assert fields["old"] == "kd_renamed"
        assert fields["preempt_after"] == "0", "post-unlock pin leak"
    else:
        assert fields["old"] == "klock_test" and fields["new"] == "kd_renamed"
        if spin:
            assert int(fields["preempt_after"]) > 0, "spin suffix lost its pin"
begins = list(re.finditer(r"kd_native begin: task=(\d+) ", text))
assert begins, "rename without an actual JIT-to-native continuation"
unlocks = int(re.search(r"kd_native stats:.*unlocks=(\d+)", text)[1])
assert len(re.findall(r"kd_native ack: task=", text)) == unlocks > 0
for pid in {event[1] for event in begins}:
    first = next(event.start() for event in begins if event[1] == pid)
    completes = list(re.finditer(r"kd_native complete: task=" + pid + r" ", text))
    assert completes, pid
    changed = list(re.finditer(r"kd_resume rename: task=" + pid +
        r" old=klock_test new=kd_renamed ", text))
    restored = list(re.finditer(r"kd_resume rename: task=" + pid +
        r" old=kd_renamed new=klock_test ", text))
    assert len(changed) == len(restored) == 1, pid
    acks = list(re.finditer(r"kd_native ack: task=" + pid + r" ([^\n]+)", text))
    assert acks, "no waiter-side acknowledgment: " + pid
    assert first < changed[0].start() < acks[-1].start() < restored[0].start(), pid
    if spin:
        last = [event for event in acks if "last_spin=1" in event[1]]
        assert len(last) == 1 and last[0] is acks[-1], pid
print("JIT native rename verified: tasks=%d; final unlock precedes restored name/pin" %
      len({event[1] for event in begins}))
' "$out/rename.log" "$mode"
fi
if [ "$shadow_capacity" = 1 ]; then
    dmesg > "$out/shadow-final.log"
    python3 -c '
import re, sys
text = open(sys.argv[1]).read()
held = [int(n) for n in re.findall(r"kd_native begin:.*held=(\d+) mutex=0", text)]
started, completed, unlocks = map(int, re.search(
    r"kd_native stats: started=(\d+) completed=(\d+) unlocks=(\d+)", text).groups())
assert started == completed == len(held)
assert unlocks == sum(held)
' "$out/shadow-final.log"
fi
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
