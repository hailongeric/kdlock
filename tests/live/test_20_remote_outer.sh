#!/bin/bash
# Recovery-only remote ancestor unlock with an independent owner dependency.
TEST_NAME="test_20_remote_outer"
source "$(dirname "$0")/../common.sh"

run_multi_roots() {
    local out pid role artifacts failed=0 quota=${1:-0}
    local -a pids=() roles=() asm_dirs=()
    local -a quota_options=() module_args=()

    test "${KDLOCK_RECOVERY_CONFIRMED:-0}" = 1
    grep -Eq '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt
    test -z "$(lsmod | grep -E '^(kdlock_km|klock_module) ')"
    if pgrep -x 'klock_test|daemon|kd_native|kd_renamed'; then return 1; fi
    out=$(mktemp -d /tmp/kdlock-remote-multi.XXXXXX)
    info "Evidence: $out"
    DAEMON_LOG="$out/daemon.log"
    # The public runner captures this directory after drain, also on failure.
    # All waits are bounded; the EXIT trap must not unload beneath a live ioctl.
    MULTI_OUT=$out
    MULTI_SELFTEST=$quota
    trap finish_multi_roots EXIT
    PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$out/placement.json" <<'PY'
import json, sys
from pathlib import Path
from cpu_placement import capture_topology
Path(sys.argv[1]).write_text(json.dumps(capture_topology(list(range(14))), indent=2) + "\n")
PY
    build_all
    if test "$quota" = 1; then
        make -C "$KM_DIR" KDLOCK_SELFTEST=1 KDLOCK_NUMA=0 W=1 -j8 > "$out/build-selftest.log" 2>&1
        cp "$KM_DIR/.kd_exec.o.cmd" "$out/exec-build.cmd"
        cp "$KM_DIR/kdlock_km.ko" "$out/kdlock-selftest.ko"
        module_args=(spin_selftest_exit_after_ack=1)
    fi
    clear_dmesg
    load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1 "${module_args[@]}"
    insmod "$KLOCK_DIR/klock_module.ko" spin_multi_roots=1 spin_multi_quota="$quota"
    test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
    test "$(cat /sys/module/klock_module/parameters/spin_multi_roots)" = Y
    start_daemon 2
    run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 8 2 > "$out/warmup.log"
    run_with_timeout 30 "$BENCH_BIN" 1 12000 1 1 8 2 > "$out/promotion.log"
    for role in 7 11; do
        run_with_timeout 30 "$BENCH_BIN" 1 12001 1 1 8 "$role" >> "$out/promotion.log"
    done
    for role in 0 5; do
        run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 8 "$role" >> "$out/registration.log"
    done
    artifacts=$(wait_for_jit_artifact_count 3 90)
    mapfile -t asm_dirs <<< "$artifacts"
    for artifacts in "${asm_dirs[@]}"; do
        check_jit_artifacts "$artifacts"
        check_complex_cs_artifact "$artifacts"
        PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$artifacts" <<'PY' >> "$out/published.jsonl"
import json, sys
from mutex_signal_protocol import wait_ready
print(json.dumps(wait_ready(sys.argv[1], lock_kind=1)))
PY
    done
    check_daemon_read_kernel_text "$DAEMON_LOG"
    # Freeze code before the two roots share an entry. This tests packet/scope
    # separation, not the explicitly deferred concurrent-code-version problem.
    stop_daemon
    if test "$quota" = 1; then
        # Bind the observer only after preparation. Derive B from the loaded
        # array and actual ELF size; do not guess spinlock_t's build layout.
        python3 - "$KLOCK_DIR/klock_module.ko" > "$out/exit-gate.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
from elftools.elf.elffile import ELFFile

module = Path(sys.argv[1])
with module.open('rb') as stream:
    table = ELFFile(stream).get_section_by_name('.symtab')
    (array,) = table.get_symbol_by_name('multi_locks')
    size = array['st_size']
assert size > 0 and size % 3 == 0
(base,) = [int(row[0], 16) for line in Path('/proc/kallsyms').read_text().splitlines()
           if len(row := line.split()) == 4 and row[2:] == ['multi_locks', '[klock_module]']]
assert base
lock = base + 2 * (size // 3)
params = Path('/sys/module/kdlock_km/parameters')
assert (params / 'spin_selftest_exit_after_ack').read_text().strip() == 'Y'
(params / 'spin_selftest_exit_lock').write_text(hex(lock) + '\n')
assert int((params / 'spin_selftest_exit_lock').read_text()) == lock
print(json.dumps({'shared_lock': hex(lock), 'base': hex(base), 'stride': size // 3,
                  'after_ack': True, 'module_sha256': hashlib.sha256(module.read_bytes()).hexdigest()}))
PY
    fi
    for role in 10 1 6 11 12 2 3 7 8 0 5 4 9 13; do
        timeout --kill-after=5s 45s taskset -c "$role" "$BENCH_BIN" \
            1 1 1 1 8 "$((2147483648 + role))" > "$out/role-$role.log" 2>&1 &
        pids+=("$!")
        roles+=("$role")
    done
    for role in "${!pids[@]}"; do
        pid=0
        wait "${pids[$role]}" || pid=$?
        printf '%s\t%s\n' "${roles[$role]}" "$pid" >> "$out/statuses.tsv"
        if test "$pid" != 0; then failed=1; fi
    done
    test "$failed" = 0
    if test "$quota" = 1; then
        for artifacts in "${asm_dirs[@]}"; do
            PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$artifacts" <<'PY' >> "$out/published-after.jsonl"
import json, sys
from mutex_signal_protocol import wait_ready
print(json.dumps(wait_ready(sys.argv[1], lock_kind=1)))
PY
        done
        quota_options=(--quota --published-after "$out/published-after.jsonl"
                       --artifacts "${asm_dirs[@]}")
    fi
    check_any_jit_entry_executed "${asm_dirs[@]}"
    unload_modules
    check_dmesg_ok
    check_dmesg_has 'kd_exec invariant_failures=0'
    check_dmesg_has 'kd_spin diag invariant_failures=0'
    check_dmesg_not_has 'JIT retry\|abort release\|non-continuable exit\|jit_disabled=1'
    check_complex_cs_integrity 36023 3
    dmesg > "$out/protocol.log"
    python3 "$KDLOCK_DIR/tests/protocols/remote_outer_protocol.py" "$out/protocol.log" 1 \
        --multi --placement "$out/placement.json" --publications "$out/published.jsonl" \
        --statuses "$out/statuses.tsv" --result "$out/protocol.json" "${quota_options[@]}"
    pass "$TEST_NAME: two independent roots share B's JIT combiner"
}

finish_multi_roots() {
    local status=$?
    trap - EXIT
    stop_daemon
    if pgrep -x 'klock_test|kd_native|kd_renamed' >/dev/null; then
        fail "$TEST_NAME" "callers remain; retain modules for recovery"
        status=1
    else
        unload_modules || status=1
        # A following module session clears daemon workspaces. Retain this
        # phase's images before the joined mode-8 driver starts that session.
        (cd "$KDLOCK_DIR"
         find daemon -path 'daemon/0x*' -type f -print0 |
             tar --null -T - -czf "$MULTI_OUT/artifacts.tar.gz") || status=1
        if test "$MULTI_SELFTEST" = 1; then
            make -C "$KM_DIR" KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8 > "$MULTI_OUT/build-default.log" 2>&1 || status=1
        fi
    fi
    dmesg > "$MULTI_OUT/dmesg.log"
    printf '%s\n' "$status" > "$MULTI_OUT/exit-status"
    exit "$status"
}

if [[ ${1:-} == multi ]]; then
    [[ $# == 1 || ( $# == 2 && $2 == quota ) ]]
    if [[ ${2:-} == quota ]]; then
        run_multi_roots 1
    else
        run_multi_roots 0
    fi
    exit 0
fi

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
placement_output=$(PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - \
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
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1
insmod "$KLOCK_DIR/klock_module.ko" native_resume_stage="$resume_stage"
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
start_daemon 2
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 1 > "$out/warmup.log"
run_with_timeout 30 "$BENCH_BIN" 1 12000 10 1 1 > "$out/promotion.log"
if test "$depth" = 3; then
    # Keep C's samples consecutive within its own fixed observation window.
    run_with_timeout 30 "$BENCH_BIN" 1 12001 10 1 8 11 > "$out/c-promotion.log"
fi
for role in 0 2 4; do
    run_with_timeout 10 "$BENCH_BIN" 1 1 10 1 8 "$role" >> "$out/registration.log"
done
artifact_output=$(wait_for_jit_artifact_count "$((depth + 4))" 30)
mapfile -t asm_dirs <<< "$artifact_output"
for asm_dir in "${asm_dirs[@]}"; do
    check_jit_artifacts "$asm_dir"
    PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 -c '
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
python3 "$KDLOCK_DIR/tests/protocols/remote_outer_protocol.py" "$out/protocol.log" "$stage" "${options[@]}"
pass "$TEST_NAME stage=$stage depth=$depth reverse=$reverse native_owner=$native_owner rename=$renamed cross_numa=$cross_numa"
