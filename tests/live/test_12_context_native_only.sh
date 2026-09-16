#!/bin/bash
# Context-incompatible requests must stay native, even with mutex_jit=1.
TEST_NAME="test_12_context_native_only"
source "$(dirname "$0")/../common.sh"

if [ "${KDLOCK_RECOVERY_CONFIRMED:-0}" != 1 ]; then
    fail "$TEST_NAME" "confirm a recoverable VM with KDLOCK_RECOVERY_CONFIRMED=1"
    exit 1
fi
mode="${1:-3}"
module_args=()
operations=12129
states=1
context_api=${KD_CONTEXT_LOCK_API:-none}
context_kind=0
context_symbol=
case "$mode" in
    3) kind=mutex; module_args=(mixed_lock_probe=1); operations=12257; states=2 ;;
    *) fail "$TEST_NAME" "use mode 3; GS modes 10/11 are JIT positives in test_24_gs_jit.sh"; exit 1 ;;
esac
case "$context_api" in
    none) ;;
    irqsave) context_kind=1; context_symbol=_raw_spin_lock_irqsave ;;
    bh) context_kind=2; context_symbol=_raw_spin_lock_bh ;;
    percpu) context_kind=3; context_symbol=__per_cpu_offset; operations=12129; states=1 ;;
    percpu-reg) context_kind=4; context_symbol=__per_cpu_offset; operations=12129; states=1 ;;
    percpu-flow) context_kind=5; context_symbol=__per_cpu_offset; operations=12129; states=1 ;;
    percpu-cmov) context_kind=6; context_symbol=__per_cpu_offset; operations=12129; states=1 ;;
    percpu-rotate) context_kind=7; context_symbol=__per_cpu_offset; operations=12129; states=1 ;;
    percpu-implicit) context_kind=8; context_symbol=__per_cpu_offset; operations=12129; states=1 ;;
    percpu-spill) context_kind=9; context_symbol=__per_cpu_offset; operations=12129; states=1 ;;
    *) fail "$TEST_NAME" "KD_CONTEXT_LOCK_API must be none, irqsave, bh, percpu, percpu-reg, percpu-flow, percpu-cmov, percpu-rotate, percpu-implicit or percpu-spill"; exit 1 ;;
esac
if [ "$context_kind" != 0 ]; then
    test "$mode" = 3 || { fail "$TEST_NAME" "context API probe requires mode 3"; exit 1; }
    module_args+=("context_lock_probe=$context_kind")
fi
out="$(mktemp -d "/tmp/kdlock-native-only-mode${mode}.XXXXXX")"
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"
cleanup() {
    local status=$?
    stop_daemon
    if ! pgrep -x klock_test >/dev/null; then
        unload_modules
    fi
    dmesg > "$out/dmesg.log"
    printf '%s\n' "$status" > "$out/exit-status"
}
trap cleanup EXIT

build_all
unload_modules
clear_dmesg
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1
insmod "$KLOCK_DIR/klock_module.ko" "${module_args[@]}"
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
start_daemon 2
# Keep each probe on its own CPU; its prepare/finish span both native locks.
run_with_timeout 10 taskset -c 0 "$BENCH_BIN" 1 1 1 1 "$mode" 0 > "$out/warmup.log"
sleep 1
run_with_timeout 30 taskset -c 0 "$BENCH_BIN" 1 12000 10 1 "$mode" 0 > "$out/promotion.log"
python3 "$KDLOCK_DIR/tests/protocols/native_only_protocol.py" --all --protocol --lock-kind "$kind" > "$out/rejection-before.json"
check_daemon_read_kernel_text "$DAEMON_LOG"
grep 'reason=CONTEXT_NATIVE_ONLY' "$DAEMON_LOG" > "$out/policy.log"
if [ "$mode" = 3 ]; then
    if [ "$context_kind" != 0 ]; then
        if [ "$context_kind" = 9 ]; then
            grep -E 'context-sensitive symbol requires native execution: __per_cpu_offset|bounded register-address alternatives require native execution' "$out/policy.log"
        else
            grep "context-sensitive symbol requires native execution: $context_symbol" "$out/policy.log"
        fi
        if [ "$context_kind" = 8 ] || [ "$context_kind" = 9 ]; then
            grep 'inst="LODSQ' "$out/policy.log"
        elif [ "$context_kind" -ge 4 ]; then
            grep 'inst="MOV.*\[RAX\]"' "$out/policy.log"
        fi
        if grep -q 'spin lock reference in mutex entry\|GS/current' "$out/policy.log"; then
            fail "$TEST_NAME" "another rejection must not mask the API policy check"
            exit 1
        fi
    else
        grep 'spin lock reference in mutex entry' "$out/policy.log"
    fi
fi
check_dmesg_not_has 'install JIT chunk:'
test -z "$(find "$DAEMON_DIR" -path '*/0x*' -name jit.bin -print -quit)"
if [ "$context_kind" = 6 ]; then
    objdump -dr --disassemble=kd_context_mutex_percpu_cmov \
        "$KLOCK_DIR/klock_module.o" > "$out/cmov-disassembly.log"
    grep -Eq 'cmovne[[:space:]]+%rcx,%rax' "$out/cmov-disassembly.log"
elif [ "$context_kind" = 7 ]; then
    objdump -dr --disassemble=kd_context_mutex_percpu_rotate \
        "$KLOCK_DIR/klock_module.o" > "$out/rotate-disassembly.log"
    grep -Eq 'rol[[:space:]]+%cl,%rax' "$out/rotate-disassembly.log"
    grep -Eq 'ror[[:space:]]+%cl,%rax' "$out/rotate-disassembly.log"
elif [ "$context_kind" = 8 ]; then
    objdump -dr --disassemble=kd_context_mutex_percpu_implicit \
        "$KLOCK_DIR/klock_module.o" > "$out/implicit-disassembly.log"
    mapfile -t lods_offsets < <(awk '/lods.*%rsi.*%rax/ {sub(/:$/, "", $1); print $1}' \
        "$out/implicit-disassembly.log")
    test "${#lods_offsets[@]}" = 2
    text_base=$(cat /sys/module/klock_module/sections/.text)
    printf '%s\n' "$text_base" > "$out/module-text-base"
    second_lods=$(printf '0x%x' "$((16#${text_base#0x} + 16#${lods_offsets[1]}))")
    grep "rip=\"$second_lods\"" "$out/policy.log"
elif [ "$context_kind" = 9 ]; then
    objdump -dr --disassemble=kd_context_mutex_percpu_spill \
        "$KLOCK_DIR/klock_module.o" > "$out/spill-disassembly.log"
    mapfile -t lods_offsets < <(awk '/lods.*%rsi.*%rax/ {sub(/:$/, "", $1); print $1}' \
        "$out/spill-disassembly.log")
    test "${#lods_offsets[@]}" = 1
    matched_slots=0
    while IFS= read -r store; do
        slot=${store#%rax,}
        if grep -Fq -- "$slot,%rsi" "$out/spill-disassembly.log"; then
            matched_slots=$((matched_slots + 1))
        fi
    done < <(awk '/mov.*%rax,.*\(%r(bp|sp)\)/ {print $NF}' "$out/spill-disassembly.log")
    test "$matched_slots" = 1
    text_base=$(cat /sys/module/klock_module/sections/.text)
    printf '%s\n' "$text_base" > "$out/module-text-base"
    spill_lods=$(printf '0x%x' "$((16#${text_base#0x} + 16#${lods_offsets[0]}))")
    grep "rip=\"$spill_lods\"" "$out/policy.log"
fi
if [ "$mode" = 3 ]; then
    # Do not execute the sensitive branch until its exact refusal is verified.
    printf '2\n' > /sys/module/klock_module/parameters/mixed_lock_probe
fi

pids=()
for cpu in 0 1 2 3; do
    work_load=100000
    if [ "$context_kind" = 6 ] || [ "$context_kind" = 7 ]; then
        work_load=$((work_load + cpu % 2))
    fi
    timeout --kill-after=5s 60s taskset -c "$cpu" "$BENCH_BIN" \
        1 32 "$work_load" 1 "$mode" 0 > "$out/cpu-$cpu.log" 2>&1 &
    pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
    wait "$pid" || failed=1
done
test "$failed" = 0
python3 "$KDLOCK_DIR/tests/protocols/native_only_protocol.py" --all --protocol --lock-kind "$kind" > "$out/rejection-after.json"
stop_daemon
unload_modules
check_dmesg_ok
check_dmesg_not_has 'install JIT chunk:'
check_dmesg_not_has 'JIT delegation ok\|kd_native begin:'
if [ "$mode" = 3 ]; then
    check_dmesg_has 'kd_mutex oracle: inside=0 overlaps=0'
    if [ "$context_kind" != 0 ]; then
        inner=128
        [ "$context_kind" -lt 3 ] || inner=0
        check_dmesg_has "kd_context native: api=$context_kind inside=128 checked=12129 failures=0 outer=12129 inner=$inner"
        if [ "$context_kind" = 6 ]; then
            check_dmesg_has 'kd_context cmov: false=64 true=64'
        elif [ "$context_kind" = 7 ]; then
            check_dmesg_has 'kd_context rotate: zero=64 one=64'
        fi
    fi
else
    check_dmesg_has "kd_gs $kind stats: attempts=12129 successes=12129 failures=0"
fi
check_complex_cs_integrity "$operations" "$states"
check_dmesg_has 'kd_exec invariant_failures=0'
if [ "$kind" = mutex ]; then
    check_mutex_origin_accounting
    check_dmesg_stat_equals jit_success 0
    check_dmesg_stat_equals jit_failure 0
    check_dmesg_stat_equals frame_failure 0
    check_dmesg_stat_equals active_waiters 0
    check_dmesg_stat_equals reserved_nodes 0
    check_dmesg_has 'jit_not_ready=[1-9][0-9]*'
else
    check_dmesg_has 'kd_spin diag invariant_failures=0'
    check_dmesg_has 'kd_spin diag overflow=0'
    check_dmesg_not_has 'kd_spin lock stats:.*waiters=[1-9]'
    check_dmesg_not_has 'kd_spin lock stats:.*jit_success=[1-9]'
    check_dmesg_has 'jit_not_ready=[1-9][0-9]*'
fi
pass "$TEST_NAME mode=$mode context_api=$context_api native-only requests=12129 JIT=0"
