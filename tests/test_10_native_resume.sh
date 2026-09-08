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
ooo="${KD_NATIVE_OOO:-0}"
dependency="${KD_NATIVE_OOO_DEPENDENCY:-0}"
registers="${KD_NATIVE_REGISTERS:-0}"
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
        if [ "$shadow_capacity" = 1 ]; then
            make -C "$KM_DIR" KDLOCK_SELFTEST=0 W=1 -j8 > "$out/build-default.log" 2>&1 || status=1
        fi
    elif [ "$shadow_capacity" = 1 ]; then
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

build_all
unload_modules
clear_dmesg
module_args=()
if [ "$shadow_capacity" = 1 ]; then
    make -C "$KM_DIR" KDLOCK_SELFTEST=1 W=1 -j8 > "$out/build-selftest.log" 2>&1
    cp "$KM_DIR/kdlock_km.ko" "$out/kdlock-selftest.ko"
    module_args+=(spin_selftest_fill_shadow=1)
fi
insmod "$KM_DIR/kdlock_km.ko" target_process="$TARGET_PROCESS" mutex_jit=1 "${module_args[@]}"
insmod "$KLOCK_DIR/klock_module.ko" native_resume_stage="$stage" \
    native_pending_contended="$pending_contended" native_resume_registers="$registers"
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
if [ "$policy_completion" = 1 ] || [ "$stage" = 5 ]; then
    kill -STOP -- "-$DAEMON_PID"
else
    stop_daemon
fi
if [ "$registers" = 1 ]; then
    printf '1\n' > /sys/module/klock_module/parameters/native_regs_armed
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
    fi
    probe_ip="$(awk -v name="$symbol" '$3 == name { print $1 }' /proc/kallsyms)"
    test -n "$probe_ip"
    if [ "$shadow_capacity" = 1 ]; then
        test "$(cat /sys/module/kdlock_km/parameters/spin_selftest_fill_shadow)" = 1
        test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    else
        printf '%s\n' "$kind" > /sys/module/kdlock_km/parameters/jit_fail_pending_lock
    fi
fi

if [ "$stage" = 5 ]; then
    # Learn the ordinary helper CALL from an actual miss. Recompile only after
    # every first-wave caller exits; no executor sees an in-place replacement.
    test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    helper_ip="$(awk '$3 == "kd_resume_depth_mutex" { print $1 }' /proc/kallsyms)"
    probe_ip="$(awk '$3 == "mutex_lock" { print $1 }' /proc/kallsyms)"
    test -n "$helper_ip"
    test -n "$probe_ip"
    asm_dir="${asm_dirs[0]}"
    entry="$(basename "$(dirname "$(dirname "$asm_dir")")")"
    cp "$asm_dir/jit.bin" "$out/entry-only.bin"
    printf '1\n' > /sys/module/klock_module/parameters/native_depth_armed
    run_with_timeout 60 "$BENCH_BIN" "$threads" 1 1000000 1 4 > "$out/learning.log"
    check_dmesg_has "kd_native begin:.* ip=$helper_ip .*held=1 mutex=1"
    PYTHONPATH="$KDLOCK_DIR/tests" python3 -c '
import sys
from native_only_protocol import entries
entry = next(e for e in entries() if e.rip == int(sys.argv[1], 16))
assert entry.status == 1 and entry.target == int(sys.argv[2], 16)
' "$entry" "$helper_ip"
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
    stop_daemon
    grep -q "^loc_${helper_ip}:" "$asm_dir/jit.S"
    grep -qi "$helper_ip" "$asm_dir/callee_table.txt"
    check_jit_artifacts "$asm_dir"
    if cmp -s "$out/entry-only.bin" "$asm_dir/jit.bin"; then
        fail "$TEST_NAME" "callee completion did not change the JIT image"
        exit 1
    fi
    dmesg > "$out/before-capacity.log"
    run_with_timeout 60 "$BENCH_BIN" "$threads" 1 1000000 1 4 > "$out/workload.log"
    test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    operations=12017
    requests=12017
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
elif [ "$mode" = 4 ] && { [ "$stage" != 4 ] || [ "$pending_contended" = 1 ]; }; then
    # A's delegation queue contends on native B, pinned to separate CPUs.
    pids=()
    roles=(1 3 2 4 0 5 6)
    if [ "$dependency" = 2 ]; then
        roles+=(7)
    fi
    for role in "${roles[@]}"; do
        role_comm="$TARGET_PROCESS"
        if [ "$role" = 7 ]; then
            role_comm=kd_native
        fi
        if [ "$pending_contended" = 1 ]; then
            case "$role" in 1|2|5) role_comm=kd_native ;; esac
        fi
        timeout --kill-after=5s 60s env KD_TEST_COMM="$role_comm" \
            taskset -c "$role" "$BENCH_BIN" \
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

if [ "$stage" = 4 ]; then
    test "$(cat /sys/module/kdlock_km/parameters/jit_fail_pending_lock)" = 0
    dmesg | grep 'reason=PENDING_LOCK_NATIVE' > "$out/pending-lock.log"
    test "$(wc -l < "$out/pending-lock.log")" = 1
    python3 -c '
import errno, re, sys
line = open(sys.argv[1]).read()
fields = dict(re.findall(r"(\w+)=(0x[0-9a-f]+|[0-9-]+)", line))
values = {k: int(v, 0) for k, v in fields.items()}
assert values["target"] == int(sys.argv[2], 16)
assert values["error"] == -errno.E2BIG
pre_stage = values["mutex"] or sys.argv[3] == "1"
assert values["staged_ip"] == (values["target"] if pre_stage else values["return"])
assert values["staged_sp"] == values["sp"] + (0 if pre_stage else 8)
' "$out/pending-lock.log" "$probe_ip" "$shadow_capacity"
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

unload_modules
check_dmesg_ok
check_any_jit_entry_executed "${asm_dirs[@]}"
if [ "$shadow_capacity" = 1 ]; then
    check_any_jit_entry_executed_for_lock "$shadow_outer" "${asm_dirs[@]}"
fi
check_complex_cs_integrity "$operations" "$states"
check_dmesg_has "kd_resume records: requests=$requests failures=0"
check_dmesg_has 'kd_native stats: started=[1-9][0-9]* completed=[1-9][0-9]*'
check_dmesg_has "kd_native begin:.* ip=$probe_ip "
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
assert capacity + callee + native == 16
assert len(re.findall(r"kd_native begin:.*held=8 mutex=1", text)) == capacity
assert len(re.findall(r"kd_depth mutex:.*retained=7 children=8 valid=1", text)) == capacity
assert len(re.findall(r"kd_depth mutex:.*retained=0 children=8 valid=1", text)) == callee
started, completed, unlocks = map(int, re.search(
    r"kd_native stats: started=(\d+) completed=(\d+) unlocks=(\d+)", text).groups())
assert started == completed == capacity + callee
assert unlocks == capacity * 8 + callee
assert "valid=0" not in text
' "$out/depth-capacity.log" "$probe_ip"
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
assert "kd_native stats: started=1 completed=1 unlocks=1" in text
' "$out/pending-contended.log" "$probe_ip"
elif [ "$pending_contended" = 1 ]; then
    check_dmesg_has 'kd_pending mutex: observed=1 acquired=1'
    dmesg > "$out/pending-contended.log"
    python3 -c '
import re, sys
text = open(sys.argv[1]).read()
def fields(kind):
    lines = re.findall(r"kd_pending mutex " + kind + r": ([^\n]+)", text)
    assert len(lines) == 1, (kind, lines)
    return dict(re.findall(r"(\w+)=(\w+)", lines[0]))
blocked, acquired = fields("blocked"), fields("acquired")
assert blocked["queued"] == blocked["valid"] == acquired["preserved"] == "1"
assert blocked["holder_comm"] == "kd_native"
assert blocked["task"] == acquired["task"]
assert blocked["waiter"] == acquired["waiter"] == acquired["b_owner"]
assert blocked["a_owner"] == acquired["a_owner"]
assert len({blocked[k] for k in ("waiter", "a_owner", "b_owner")}) == 3
assert int(blocked["a_owner"], 16) != 0
pid = blocked["task"]
assert re.search(r"kd_native begin: task=" + pid + r" .*held=1 mutex=1", text)
assert re.search(r"kd_native complete: task=" + pid + r" .*mutex=1", text)
events = [text.index(event) for event in (
    "reason=PENDING_LOCK_NATIVE", "kd_native begin: task=" + pid,
    "kd_pending mutex blocked:", "kd_pending mutex acquired:",
    "kd_native complete: task=" + pid)]
assert events == sorted(events)
assert "kd_native stats: started=1 completed=1 unlocks=1" in text
' "$out/pending-contended.log"
fi
if [ "$pinned" = 1 ]; then
    check_dmesg_has 'kd_native begin:.*mutex=1 cpu=1'
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
