#!/bin/bash
# Deterministic real hook routing; deliberately no translator or JIT image.
TEST_NAME=test_18_spin_routing
source "$(dirname "$0")/../common.sh"
scenario=${1:-1}
cpus=${KD_ROUTE_CPUS:-0,1,2,3}
if [[ ${KDLOCK_RECOVERY_CONFIRMED:-0} != 1 || ! $scenario =~ ^[1-4]$ ]]; then
    fail "$TEST_NAME" "require recovery confirmation and scenario 1 through 4"
    exit 1
fi
grep -Eq '\((none|voluntary)\)' /sys/kernel/debug/sched/preempt
python3 -c 'import os, sys; cpus=list(map(int,sys.argv[1].split(","))); assert len(cpus)==len(set(cpus))==4 and set(cpus)<=os.sched_getaffinity(0)' "$cpus"
IFS=, read -r -a cpu <<< "$cpus"
if pgrep -x 'daemon|klock_test|kd_native|kd_renamed' >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "guest must have no active workers or modules"
    exit 1
fi
out=$(mktemp -d /tmp/kdlock-spin-routing-case.XXXXXX)
info "Evidence: $out"
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -e /sys/module/klock_module/parameters/spin_route_abort ]]; then
        printf '1\n' > /sys/module/klock_module/parameters/spin_route_abort
    fi
    if pgrep -x 'klock_test|kd_native|kd_renamed' >/dev/null; then
        fail "$TEST_NAME" "workers remain; retain code for VM recovery"
        status=1
    else
        unload_modules
        make -C "$KM_DIR" KDLOCK_SELFTEST=0 W=1 -j8 > "$out/build-default.log" 2>&1 || status=1
    fi
    dmesg > "$out/dmesg.log"
    printf '%s\n' "$status" > "$out/exit-status"
    exit "$status"
}
trap cleanup EXIT
build_all
make -C "$KM_DIR" KDLOCK_SELFTEST=1 W=1 -j8 > "$out/build-selftest.log" 2>&1
cp "$KM_DIR/kdlock_km.ko" "$out/kdlock-selftest.ko"
clear_dmesg
load_kdlock target_process="$TARGET_PROCESS" mutex_jit=0
insmod "$KLOCK_DIR/klock_module.ko" spin_route_probe="$scenario" spin_route_cpus="$cpus"
lock=$(awk '$3 == "global_lock" && $4 == "[klock_module]" { print $1 }' /proc/kallsyms)
test -n "$lock"
printf 'scenario=%s cpus=%s lock=%s JIT=0\n' "$scenario" "$cpus" "$lock" > "$out/environment.log"
promote() {
    printf '0x%s\n' "$lock" > /sys/module/kdlock_km/parameters/spin_selftest_promote
}
[[ $scenario == 1 ]] || promote
pids=()
start() {
    local role=$1 comm=$TARGET_PROCESS
    if [[ $role == 2 || $scenario:$role == 3:0 ]]; then comm=kd_native; fi
    timeout --kill-after=5s 30s env KD_TEST_COMM="$comm" taskset -c "${cpu[$role]}" \
        "$BENCH_BIN" 1 1 1 1 0 "$role" > "$out/role-$role.log" 2>&1 &
    pids+=("$!")
}
start 0
python3 -c '
import time
from pathlib import Path
p=Path("/sys/module/klock_module/parameters/spin_route_ready")
end=time.monotonic()+3
while p.read_text().strip() != "1":
    assert time.monotonic() < end, "owner did not acquire L"
    time.sleep(.005)
'
[[ $scenario != 1 ]] || promote
start 1
start 2
start 3
failed=0
for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
test "$failed" = 0
unload_modules
check_dmesg_ok
check_dmesg_not_has 'WARNING:\|\[KD_JIT\]\[ERROR\]\|kd_route timeout:'
check_complex_cs_integrity 4 1
check_dmesg_has "kd_route summary: scenario=$scenario roles=15 finished=15 entries=1,1,1,1 failures=0 original=0 private=0 waiters=0"
check_dmesg_has 'kd_spin oracle: inside=0 overlaps=0 origin_missing=0 context_failures=0'
check_dmesg_not_has 'install JIT chunk:\|JIT delegation ok\|kd_native begin:'
dmesg > "$out/routing.log"
python3 -c '
import re, sys
text=open(sys.argv[1]).read(); scenario=int(sys.argv[2]); cpus=list(map(int,sys.argv[3].split(",")))
def events(prefix):
    return [(m.start(), dict(re.findall(r"(\w+)=([\w,]+)", m[1])))
            for m in re.finditer(prefix + r": ([^\n]+)", text)]
owned=events("kd_route owned"); departed=events("kd_route departed")
assert len(owned)==len(departed)==4
by_role={int(f["role"]):(pos,f) for pos,f in owned}
assert set(by_role)=={0,1,2,3}
for _, f in owned:
    assert int(f["preempt"])==1 and int(f["cpu"])==cpus[int(f["role"])]
    assert int(f["original"],16)&0xff in (1,3)
for _, f in departed:
    assert f["preempt"]==f["irq"]=="0" and int(f["cpu"])==cpus[int(f["role"])]
queued=events("kd_route queued"); assert len(queued)==1
qpos,q=queued[0]; spos,s=by_role[0]
promotion=text.index("kd_hotlock selftest promote: lock=" + sys.argv[4])
assert (spos < promotion < qpos) if scenario==1 else (promotion < spos < qpos)
assert all(pos > qpos for role,(pos,_) in by_role.items() if role)
assert q["owner"]==s["task"]
private=int(q["private"],16); original=int(q["original"],16)
assert private&0xff==1 and q["private_pending"]=="1"
if scenario in (1,3):
    assert int(s["private"],16)==0 and q["private_waiters"]=="0"
    assert int(q["original_tail_cpu"])==cpus[2]+1
else:
    assert int(s["private"],16)&0xff==1 and q["private_waiters"]=="1"
    assert int(q["private_tail_cpu"])==cpus[3]+1
    assert q["original_pending"]=="1" or int(q["original_tail_cpu"])==cpus[2]+1
if scenario in (2,3):
    old,new=("klock_test","kd_renamed") if scenario==2 else ("kd_native","klock_test")
    change=text.index("kd_resume rename: task="+s["task"]+" old="+old+" new="+new)
    leave=next(pos for pos,f in departed if f["role"]=="0")
    assert qpos < change < leave
elif scenario==4:
    changes=events("kd_route queued rename"); assert len(changes)==1
    pos,f=changes[0]; target_pos,target=by_role[3]
    assert qpos < pos < target_pos and f["task"]==target["task"]
    assert int(f["cpu"])==cpus[3] and target["comm"]=="kd_renamed"
print("real L/S routing verified: scenario=%d, four callers, JIT=0" % scenario)
' "$out/routing.log" "$scenario" "$cpus" "$lock"
pass "$TEST_NAME scenario=$scenario cpus=$cpus JIT=0"
