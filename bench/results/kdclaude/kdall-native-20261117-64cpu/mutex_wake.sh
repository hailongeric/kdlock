#!/bin/bash
# mutex_wake.sh TAG [KNOB=VALUE ...]: locktorture mutex_lock for 20 s
# (W writers from the environment, default 128: 2 per CPU) on the running
# kernel, no daemon, with the
# ftrace function profiler counting wake_up_q, try_to_wake_up and schedule
# calls (kd's own files are built without ftrace, so their callers are
# counted). Also the writes, context switches and kd counters. KNOB=VALUE
# pairs set kernel parameters for the run. Output: /root/mwake/TAG.txt
TAG=${1:?tag}; shift
O=/root/mwake; mkdir -p $O; exec > $O/$TAG.txt 2>&1
P=/sys/module/kernel/parameters
T=/sys/kernel/debug/tracing
uname -rv
echo "writers ${W:-128}"
declare -A old
for kv in "$@"; do
	k=${kv%%=*}; v=${kv#*=}
	old[$k]=$(cat $P/$k) || exit 1
	echo $v > $P/$k || exit 1
	echo "set $k=$v (was ${old[$k]})"
done
st() { [ -r /sys/kernel/debug/kdlock_stats ] && grep -vE "^#" /sys/kernel/debug/kdlock_stats; }
ctxt() { awk '$1 == "ctxt" {print $2}' /proc/stat; }
echo 0 > $T/function_profile_enabled
echo "wake_up_q try_to_wake_up schedule" > $T/set_ftrace_filter || exit 1
echo "mwake: $TAG" > /dev/kmsg
st > /tmp/w0; c0=$(ctxt)
modprobe locktorture torture_type=mutex_lock nwriters_stress=${W:-128} stat_interval=0
sleep 2
echo 1 > $T/function_profile_enabled
sleep 16
echo 0 > $T/function_profile_enabled
sleep 2
rmmod locktorture
c1=$(ctxt); st > /tmp/w1
dmesg | awk -v m="mwake: $TAG" 'index($0,m){f=1} f' | grep -E "Writes:" | tail -1 | sed 's/.*Writes:/Writes:/; s/acq_writer.*//'
echo "context switches $((c1 - c0)) in 20 s"
echo "-- calls per second while profiling (16 s), all CPUs"
cat $T/trace_stat/function* | awk '$1 ~ /^(wake_up_q|try_to_wake_up|schedule)$/ {n[$1] += $2} END {for (f in n) printf "  %-16s %10.0f /s\n", f, n[f] / 16}'
echo > $T/set_ftrace_filter
[ -s /tmp/w0 ] && { echo "-- kd counters over the run"; join <(sort /tmp/w0) <(sort /tmp/w1) | awk '$3 != $2 {printf "  %-16s %d\n", $1, $3 - $2}'; }
for k in "${!old[@]}"; do echo ${old[$k]} > $P/$k; done
echo MWAKE_DONE
