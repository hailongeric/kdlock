#!/bin/bash
# Real frame overlap with code-pool refusal, or combined context/node/task refusal.
TEST_NAME=test_23_mutex_parallel_native
source "$(dirname "$0")/../common.sh"

first=${KD_MUTEX_PARALLEL_FIRST:-0}
shared_cpu=${KD_MUTEX_PARALLEL_SHARED_CPU:-0}
pressure=${KD_MUTEX_PARALLEL_PRESSURE:-0}
if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 || ! $first =~ ^[01]$ ||
      ! $shared_cpu =~ ^[01]$ || ! $pressure =~ ^[01]$ ||
      ( $shared_cpu == 1 && $first != 1 ) ||
      ( $pressure == 1 && $shared_cpu != 1 ) ]]; then
    fail "$TEST_NAME" "confirm recovery; FIRST/SHARED_CPU/PRESSURE must be 0/1; pressure requires shared CPU and FIRST=1"
    exit 1
fi
callers='klock_test|kd_native|kd_renamed'
workers="$callers|daemon"
if pgrep -x "$workers" >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no kdlock modules or workers"
    exit 1
fi
python3 -c 'import os; assert set(range(8)) <= os.sched_getaffinity(0)'
if [[ $shared_cpu == 0 ]]; then
    python3 -c 'import os; assert set(range(8, 14)) <= os.sched_getaffinity(0)'
fi
out=$(mktemp -d /tmp/kdlock-mutex-parallel.XXXXXX)
info "Evidence: $out"
DAEMON_LOG="$out/daemon.log"
waiter_controller=

cleanup() {
    local status=$?
    trap - EXIT
    # Only fixture gates are released here. A retained physical owner still
    # performs every unlock/ACK; never terminate its delegated kernel request.
    for gate in mutex_parallel_source_hold mutex_parallel_exit_hold; do
        if [[ -e /sys/module/klock_module/parameters/$gate ]]; then
            printf '0\n' > "/sys/module/klock_module/parameters/$gate" || status=1
        fi
    done
    if [[ -n $waiter_controller ]]; then
        wait "$waiter_controller" || status=1
        waiter_controller=
    fi
    python3 "$KDLOCK_DIR/tests/protocols/source_retirement.py" release "$out" || status=1
    # A timed-out ioctl can still own a frame. Never force unload or remove
    # its evidence; retain the module for the documented VM recovery path.
    if pgrep -x "$callers" >/dev/null; then
        fail "$TEST_NAME" "callers remain; retain module for VM recovery"
        status=1
    else
        stop_daemon
        unload_modules || status=1
        # Restore the default module only after callers and the observed
        # SELFTEST session have drained; never replace a still-loaded image.
        if [[ $shared_cpu == 0 ]] && ! lsmod | grep -q '^kdlock_km '; then
            make -C "$KM_DIR" KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8 \
                > "$out/build-default.log" 2>&1 || status=1
        fi
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
if [[ $shared_cpu == 0 ]]; then
    make -C "$KM_DIR" KDLOCK_SELFTEST=1 KDLOCK_NUMA=0 W=1 -j8 \
        > "$out/build-selftest.log" 2>&1
    cp "$KM_DIR/kdlock_km.ko" "$out/kdlock-selftest.ko"
    cc -O2 -Wall -Wextra -Werror -I"$KDLOCK_DIR/include" \
        "$KDLOCK_DIR/tests/clients/source_session_driver.c" -o "$out/source-session-driver"
    cc -O2 -Wall -Wextra -Werror "$KDLOCK_DIR/tests/clients/mutex_signal_client.c" \
        -o "$out/mutex-signal-client"
fi
clear_dmesg
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=1
insmod "$KLOCK_DIR/klock_module.ko" mutex_parallel=1 mutex_parallel_first="$first" \
    mutex_parallel_shared_cpu="$shared_cpu" mutex_parallel_pressure="$pressure" \
    mutex_parallel_peers="$((1-shared_cpu))" mutex_parallel_shadow="$((1-shared_cpu))" \
    native_resume_rename="$((1-shared_cpu))"
test "$(cat /sys/module/kdlock_km/parameters/mutex_jit)" = 1
if [[ $shared_cpu == 0 ]]; then
    test "$(cat /sys/module/klock_module/parameters/native_resume_rename)" = Y
fi
probe=$(awk '$3 == "kd_parallel_native" && $4 == "[klock_module]" {print $1}' /proc/kallsyms)
test -n "$probe"
printf 'first=%s shared_cpu=%s pressure=%s mutex_jit=1 probe=%s renamed=%s\n' \
    "$first" "$shared_cpu" "$pressure" "$probe" "$((1-shared_cpu))" > "$out/environment.log"
start_daemon 2
for lane in 0 1; do
    role=$((lane * 8 + 4))
    run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 3 "$role" > "$out/warm-$lane.log"
done
# Prime both lanes before the module-wide warmup. Sleeping during either
# lane's later sample would consume its own fixed window and may select IGNORE.
sleep 1
for lane in 0 1; do
    role=$((lane * 8 + 4))
    run_with_timeout 30 "$BENCH_BIN" 1 12000 1 1 3 "$role" > "$out/promote-$lane.log"
done
if ! artifact_output=$(wait_for_jit_artifact_count 2 60); then
    printf '%s\n' "$artifact_output"
    exit 1
fi
mapfile -t artifacts <<< "$artifact_output"
for artifact in "${artifacts[@]}"; do
    check_jit_artifacts "$artifact"
done
# An artifact is not publication. Require the exact two device entries NORMAL
# before stopping the daemon and arming any contention on either physical lock.
PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$out/published.json" "${artifacts[@]}" <<'PY'
import json, sys
from pathlib import Path
from mutex_signal_protocol import wait_ready
# Reuse the production-layout observer: pid=0 is the registry key, whereas
# TGID is the actual registering process and is encoded in the artifact path.
selected = [wait_ready(Path(p), lock_kind=2) for p in sys.argv[2:]]
assert len({p["entry"] for p in selected}) == 2
for item in selected:
    item.update(entry=int(item["entry"], 16), code=int(item["code"], 16), kind=2)
Path(sys.argv[1]).write_text(json.dumps(selected))
PY
stop_daemon
find "$DAEMON_DIR" -name jit.bin -print0 | sort -z | xargs -0 sha256sum > "$out/images-before.sha256"
if [[ $shared_cpu == 0 ]]; then
    # Promotion prepares a different real mutex, not another JIT smoke. Keep
    # the daemon stopped so all capacity filler entries stay uncompiled.
    run_with_timeout 30 "$BENCH_BIN" 1 12000 1 1 3 16 > "$out/code-pool-warm.log"
    python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" code-pool prepare "$out"
    python3 "$KDLOCK_DIR/tests/protocols/mutex_shadow_protocol.py" prepare "$out"
fi
printf '1\n' > /sys/module/klock_module/parameters/mutex_parallel_armed
if [[ $shared_cpu == 0 ]]; then
    printf '1\n' > /sys/module/klock_module/parameters/mutex_parallel_source_hold
    printf '1\n' > /sys/module/klock_module/parameters/mutex_parallel_exit_hold
fi
launch_wave() {
    local wave_out=$1 role lane cpu
    local -a command
    pids=()
    for role in 0 1 2 3; do
        for lane in 0 1; do
            cpu=$((lane * 4 + role))
            # Shared mode moves only the second combiner. Pressure also places
            # its two queued followers on CPU 1, filling all four real nodes
            # together with lane 0's paused combiner before the extra request.
            if [[ $shared_cpu == 1 && $lane == 1 && $role != 0 &&
                  ( $role == 1 || $pressure == 1 ) ]]; then cpu=1; fi
            printf '%s\t%s\t%s\n' "$lane" "$role" "$cpu" >> "$wave_out/role-cpus.tsv"
            command=("$BENCH_BIN" 1 1 1 1 3 "$((lane * 8 + role))")
            if [[ $shared_cpu == 0 && $wave_out == "$out" && $role == 2 ]]; then
                # A single ioctl process gives pidfd an exact waiter identity,
                # without signalling the benchmark's supervisor/pthread group.
                command=("$out/mutex-signal-client" "$lane" klock_test parallel-waiter)
            fi
            timeout --kill-after=5s 45s taskset -c "$cpu" "${command[@]}" \
                > "$wave_out/role-$lane-$role.log" 2>&1 &
            pids+=("$!")
        done
    done
}

join_wave() {
    local wave_out=$1 index status expected
    failed=0
    for index in "${!pids[@]}"; do
        status=0
        wait "${pids[$index]}" || status=$?
        printf '%s\t%s\n' "$index" "$status" >> "$wave_out/role-status.tsv"
        expected=0
        if [[ $shared_cpu == 0 && $wave_out == "$out" && $index == $((4 + first)) ]]; then
            expected=137
        fi
        # SIGKILL status alone is not acceptance. The controller retains the
        # original pidfd and the final oracle checks its suffix/ACK and exit.
        if [[ $status != "$expected" ]]; then failed=1; fi
    done
    test "$failed" = 0
}

peer_pids=()
launch_wave "$out"
failed=0
if [[ $shared_cpu == 0 ]]; then
    code_pool_wave() {
        # Dynamic locals keep the original eight supervisors available for
        # join_wave after this independent queue drains, including on failure.
        local pids=() failed=0 role status=0
        python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" code-pool held "$out" || return 1
        run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 3 17 > "$out/code-pool-fill.log" || return 1
        python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" code-pool filled "$out" || return 1
        mkdir "$out/code-pool-queue" || return 1
        for role in 0 1 2 3; do
            timeout --kill-after=5s 30s taskset -c "$((8 + role))" "$BENCH_BIN" \
                1 1 1 1 3 "$((18 + role))" > "$out/code-pool-queue/role-$role.log" 2>&1 &
            pids+=("$!")
        done
        join_wave "$out/code-pool-queue" || status=1
        if [[ $status != 0 ]]; then return "$status"; fi
        python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" code-pool drained "$out"
    }
    if ! code_pool_wave; then
        fail "$TEST_NAME" "code pool/independent queue gate failed"
        failed=1
    fi
    shadow_pool_wave() {
        local pids=() failed=0 role comm
        python3 "$KDLOCK_DIR/tests/protocols/mutex_shadow_protocol.py" held "$out" || return 1
        run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 3 25 > "$out/shadow-pool-fill.log" || return 1
        python3 "$KDLOCK_DIR/tests/protocols/mutex_shadow_protocol.py" filled "$out" || return 1
        mkdir "$out/shadow-pool-queue" || return 1
        for role in 0 1 2; do
            # Only the holder is non-target. Both real Linux waiters must
            # reach the exhausted-shadow hook and use the same native lock.
            comm="$TARGET_PROCESS"
            [[ $role != 0 ]] || comm=kd_native
            timeout --kill-after=5s 15s env KD_TEST_COMM="$comm" \
                taskset -c "$((8 + role))" "$BENCH_BIN" 1 1 1 1 3 "$((26 + role))" \
                > "$out/shadow-pool-queue/role-$role.log" 2>&1 &
            pids+=("$!")
        done
        join_wave "$out/shadow-pool-queue" || return 1
        python3 "$KDLOCK_DIR/tests/protocols/mutex_shadow_protocol.py" drained "$out"
    }
    if [[ $failed == 0 ]] && ! shadow_pool_wave; then
        fail "$TEST_NAME" "shadow map/native queue gate failed"
        failed=1
    fi
    if [[ $failed == 0 ]]; then
        # Native peers must really queue on each retained B before either old
        # frame resumes. They use separate supervisors from the eight A roles.
        mkdir "$out/native-peers"
        for lane in 0 1; do
            timeout --kill-after=5s 45s taskset -c "$((12 + lane))" \
                "$out/mutex-signal-client" "$lane" kd_native parallel-peer \
                > "$out/native-peers/role-$lane.log" 2>&1 &
            peer_pids+=("$!")
        done
        if ! run_with_timeout 15 env KD_TEST_COMM=kd_native "$BENCH_BIN" \
                1 1 1 1 3 24 > "$out/native-peers/queued.log"; then
            fail "$TEST_NAME" "native B peers did not reach both Linux wait lists"
            failed=1
        fi
        # Only the verified single-process peers receive SIGUSR1. Their first
        # ioctl must return EINTR before an explicit retry reaches wait_list;
        # neither retained frame may resume while this cancellation is checked.
        if [[ $failed == 0 ]]; then
            if ! python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" native-peers signal "$out/native-peers" ||
               ! run_with_timeout 15 env KD_TEST_COMM=kd_native "$BENCH_BIN" \
                    1 2 1 1 3 24 > "$out/native-peers/requeued.log" ||
               ! python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" native-peers requeued "$out/native-peers"; then
                fail "$TEST_NAME" "native B peers did not cancel and requeue before frame release"
                failed=1
            fi
        fi
    fi
    if [[ $failed == 0 ]]; then
        timeout --kill-after=2s 20s python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" \
            waiter-signals "$out" "$first" > "$out/waiter-controller.log" 2>&1 &
        waiter_controller=$!
        deadline=$((SECONDS + 5))
        # The controller retains both pidfds while this shell performs busy
        # retirement. A ready file is published only after both verified sends.
        while [[ ! -e $out/waiter-signals.ready ]]; do
            if ! kill -0 "$waiter_controller" 2>/dev/null || ((SECONDS >= deadline)); then
                fail "$TEST_NAME" "original waiter signal controller did not become ready"
                failed=1
                break
            fi
            sleep 0.02
        done
    fi
    # Upgrade this existing complex case instead of adding a second baseline.
    # Always release the bounded fixture gate, even after a failed observation.
    if ! python3 "$KDLOCK_DIR/tests/protocols/source_retirement.py" busy "$out/source-busy.json"; then
        failed=1
    fi
    printf '0\n' > /sys/module/klock_module/parameters/mutex_parallel_source_hold
    if [[ -n $waiter_controller ]]; then
        wait "$waiter_controller" || failed=1
        waiter_controller=
    fi
fi
if [[ $pressure == 1 ]]; then
    printf '1\t5\t1\n' >> "$out/role-cpus.tsv"
    timeout --kill-after=5s 45s taskset -c 1 "$BENCH_BIN" \
        1 1 1 1 3 13 > "$out/role-1-5.log" 2>&1 &
    pids+=("$!")
    # All existing requests have reached their queue/native wait before the
    # one-shot task fault is armed. This isolates it to the new caller, not
    # the retained waiter or the earlier no-node caller's routing reference.
    observe_refusal() {
        local pattern=$1 label=$2 attempt
        for ((attempt=0; attempt<120; attempt++)); do
            dmesg > "$out/$label-observation.log"
            if grep -Eq "$pattern" "$out/$label-observation.log"; then return 0; fi
            sleep 0.05
        done
        return 1
    }
    if observe_refusal 'mutex node fallback: .* cpu=1 slots=f$' pressure; then
        printf '1\n' > /sys/module/kdlock_km/parameters/mutex_task_fail_once
        printf '1\t6\t1\n' >> "$out/role-cpus.tsv"
        timeout --kill-after=5s 45s taskset -c 1 "$BENCH_BIN" \
            1 1 1 1 3 14 > "$out/role-1-6.log" 2>&1 &
        pids+=("$!")
        if ! observe_refusal 'mutex task fallback: .* cpu=1$' task; then
            fail "$TEST_NAME" "no task allocation refusal observed"
            failed=1
        fi
    else
        fail "$TEST_NAME" "no full real node reservation observed"
        failed=1
    fi
    # Always release the fixture holder and join callers on failed observation.
    # A log alone is not acceptance: the final oracle checks both exact records
    # and the older frame's ACKs after these own-native suffixes have completed.
    printf '1\n' > /sys/module/klock_module/parameters/mutex_parallel_pressure_release
fi
# Join every supervisor, including after an earlier failure, before cleanup.
# Preserve control failures as well as worker exit codes across the shared join.
control_failed=$failed
join_wave "$out" || control_failed=1
if [[ ${#peer_pids[@]} != 0 ]]; then
    pids=("${peer_pids[@]}")
    join_wave "$out/native-peers" || control_failed=1
fi
test "$control_failed" = 0
test "$(cat /sys/module/kdlock_km/parameters/mutex_task_fail_once)" = 0
sha256sum -c "$out/images-before.sha256" > "$out/images-after.log"
# The observed callee RIP must also be the ordinary device CALL_MISS target.
# Other cold holder entries are irrelevant; do not rewrite their status.
PYTHONPATH="$KDLOCK_DIR/tests/protocols" python3 - "$out/published.json" "$probe" \
    "$out/after.json" "$shared_cpu" <<'PY'
import json, sys
from pathlib import Path
from native_only_protocol import entries
before = {p["entry"]: p for p in json.loads(Path(sys.argv[1]).read_text())}
after = [e for e in entries() if e.rip in before and e.tgid == before[e.rip]["tgid"]]
assert len(after) == 2
shared = int(sys.argv[4])
# Refusal must leave one already published image untouched, not mark it
# unavailable and pass a no-translation fallback as a CPU-context refusal.
assert sum(e.status == 1 for e in after) == 2 - shared
assert sum(e.status == 0 for e in after) == shared
assert all((e.status == 0 or e.target == int(sys.argv[2], 16)) and e.code == before[e.rip]["code"] for e in after)
Path(sys.argv[3]).write_text(json.dumps([{"entry": e.rip, "code": e.code, "status": e.status, "target": e.target} for e in after]))
PY
if [[ $shared_cpu == 0 ]]; then
    python3 "$KDLOCK_DIR/tests/protocols/source_retirement.py" finish "$out/source-retired.json"
    # A fresh source incarnation reuses the same lexical entries and mutexes.
    # Run the identical eight roles under native contention, without warmup,
    # daemon restart, a new kdlock provider or any registry status rewrite.
    python3 "$KDLOCK_DIR/tests/protocols/source_retirement.py" reload "$out/source-reload.json"
    mkdir "$out/reloaded"
    printf '1\n' > /sys/module/klock_module/parameters/mutex_parallel_armed
    launch_wave "$out/reloaded"
    join_wave "$out/reloaded"
    python3 "$KDLOCK_DIR/tests/protocols/source_retirement.py" reloaded "$out/source-reload.json"
fi
unload_modules
dmesg > "$out/final.log"
reload_args=()
if [[ $shared_cpu == 0 ]]; then
    reload_args=(--reload-metadata "$out/source-reload.json" --code-pool-metadata "$out/code-pool.json" --native-peers "$out/native-peers" --shadow-pool-metadata "$out/shadow-pool.json")
fi
python3 "$KDLOCK_DIR/tests/protocols/mutex_parallel_protocol.py" "$out/final.log" \
    "$out/published.json" "$probe" "$first" --shared-cpu "$shared_cpu" \
    --pressure "$pressure" --after "$out/after.json" "${reload_args[@]}" > "$out/protocol.json"
check_dmesg_ok
check_dmesg_not_has 'kd_parallel error:\|WARNING:\|scheduling while atomic'
check_dmesg_stat_equals active_waiters 0
check_dmesg_stat_equals reserved_nodes 0
check_dmesg_stat_equals frame_failure 0
check_mutex_origin_accounting "$pressure"
pass "$TEST_NAME first=$first shared-cpu=$shared_cpu node-fallbacks=$pressure task-fallbacks=$pressure JIT-bodies=$((2-shared_cpu)) native-frames=$((2-shared_cpu)) owner-ACKs=$((4-2*shared_cpu))"
