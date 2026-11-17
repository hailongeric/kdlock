#!/bin/bash
# prof.sh TAG [on]: profiles of the workloads that lose against native, on
# the running kernel (kdnat1, or kdall1 without the daemon, or with it when
# "on" is given: api, torture and mm allow lists, knowledge of suite.sh).
# For each workload: context switches and migrations over 5 s (perf stat
# -a), a 5 s flat profile (perf record -a, no call graphs), and the kd
# counters over the run (kdall1 only). Output: /root/prof/TAG.log
TAG=${1:?tag}; MODE=${2:-plain}
O=/root/prof; mkdir -p $O; exec > $O/$TAG.log 2>&1
A=/root/host_fs/kdlock/bench/allow
ulimit -n 65536
cd /tmp
uname -rv
if [ $MODE = on ]; then
	cat $A/api.txt $A/torture.txt $A/mm.txt > /root/allow_cmp.txt
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_cmp.json \
		--allow /root/allow_cmp.txt -v >> $O/$TAG.kdd 2>&1 < /dev/null &
	 echo $! > /root/kdd_prof.pid)
	sleep 10
fi
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
torture() {	# torture TYPE: locktorture for 15 s
	modprobe locktorture torture_type=$1 stat_interval=0; sleep 15; rmmod locktorture
	dmesg | grep "Writes:" | tail -1 | sed 's/.*Writes:/Writes:/; s/acq_writer.*//'
}
run "torture mutex_lock" torture mutex_lock
run "torture rwsem_lock" torture rwsem_lock
run "api seek 64" /root/api_stress seek 64 15
run "api xattr 64" /root/api_stress xattr 64 15
run "api pipe 16" /root/api_stress pipe 16 15
run "api pipe 64" /root/api_stress pipe 64 15
run "wis page_fault1 16" /root/wis/build/page_fault1_threads -t 16 -s 15 -n 1
run "wis page_fault_shared1 32" /root/wis/build/page_fault_shared1_threads -t 32 -s 15 -n 1
run "wis page_fault_shared3 32" /root/wis/build/page_fault_shared3_threads -t 32 -s 15 -n 1
if [ $MODE = on ]; then
	P=$(cat /root/kdd_prof.pid); kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
fi
echo PROF_DONE
