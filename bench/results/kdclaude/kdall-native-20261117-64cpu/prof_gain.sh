#!/bin/bash
# prof_gain.sh TAG: profiles of the workloads where kd without delegation
# is far ahead of native at 64 threads (section 8), on the running kernel
# (a kdnat kernel, or a kdall kernel without the daemon). For each: context
# switches and migrations over 5 s (perf stat -a), a 5 s flat profile
# (perf record -a, no call graphs), the rate, and the kd counters (kdall
# only). Output: /root/prof/TAG.log
TAG=${1:?tag}
O=/root/prof; mkdir -p $O; exec > $O/$TAG.log 2>&1
ulimit -n 65536
cd /tmp
uname -rv
st() { [ -r /sys/kernel/debug/kdlock_stats ] && grep -vE "^#" /sys/kernel/debug/kdlock_stats; }
measure() {	# measure: profile the running workload
	sleep 3
	perf stat -a -e context-switches,cpu-migrations -- sleep 5 2>&1 | grep -E "context|migr"
	perf record -a -F 499 -o /tmp/p.data -- sleep 5 > /dev/null 2>&1
	perf report -i /tmp/p.data --sort sym --stdio 2>/dev/null | grep -v "^#" | grep . | head -16
}
run() {		# run NAME CMD...: run the workload, profile it, report counters
	local name=$1; shift
	echo "== $name"
	st > /tmp/s0
	"$@" > /tmp/w.out 2>&1 &
	local p=$!
	measure
	wait $p
	tail -1 /tmp/w.out
	st > /tmp/s1
	[ -s /tmp/s0 ] && join <(sort /tmp/s0) <(sort /tmp/s1) | awk '$3 != $2 {printf "  %-16s %d\n", $1, $3 - $2}'
}
run "api setfd 64" /root/api_stress setfd 64 15
run "api ofd 64" /root/api_stress ofd 64 15
run "api uts 64" /root/api_stress uts 64 15
run "wis brk1 64" /root/wis/build/brk1_threads -t 64 -s 15 -n 1
run "wis mmap1 64" /root/wis/build/mmap1_threads -t 64 -s 15 -n 1
echo PROF_DONE
