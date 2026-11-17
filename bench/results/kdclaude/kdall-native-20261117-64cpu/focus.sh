#!/bin/bash
# focus.sh MODE TAG: the bad cases of the native comparison only, two runs
# each, in the format of suite.sh (same MODEs, same output file).
MODE=${1:?mode}; TAG=${2:?tag}
O=/root/cmp; mkdir -p $O
OUT=$O/focus.txt
A=/root/host_fs/kdlock/bench/allow
# Knowledge is per kernel build: one state file per release.
ST=/root/kds_cmp-$(uname -r).json
ulimit -n 65536
C="delegated handback hb_frontier hb_miss offered plain sessions"
st() {
	[ -r /sys/kernel/debug/kdlock_stats ] || { echo -n "- "; return; }
	local k
	for k in $C; do awk -v k=$k '$1 == k {printf "%s ", $2}' /sys/kernel/debug/kdlock_stats; done
}
complaints() { dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall"; }
line() { echo "$TAG $MODE $*" >> $OUT; }

d_on() {
	ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
	cat $A/api.txt $A/torture.txt $A/mm.txt > /root/allow_cmp.txt
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $ST \
		--allow /root/allow_cmp.txt -v >> $O/kdd-focus-$TAG.log 2>&1 < /dev/null &
	 echo $! > /root/kdd_cmp.pid)
	sleep 10
}
d_off() {
	P=$(cat /root/kdd_cmp.pid); kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
	kill -0 $P 2>/dev/null && { echo "daemon $P did not stop"; exit 1; }
}

[ $MODE = on ] && d_on
c0=$(complaints)
cd /tmp
for rep in 1 2; do
	for t in ww_mutex_lock mutex_lock rwsem_lock; do
		s0=$(st); echo "focus: $TAG $MODE $t $rep" > /dev/kmsg
		modprobe locktorture torture_type=$t stat_interval=0; sleep 30; rmmod locktorture
		r=$(dmesg | awk -v m="focus: $TAG $MODE $t $rep" 'index($0,m){f=1} f' | grep -E "Writes:" | tail -1 | sed 's/.*Total: *//; s/ .*//')
		line "torture $t 128 ${r:-0} | $s0| $(st)"
	done
	for x in seek pipe xattr; do for n in 16 64; do
		s0=$(st); r=$(/root/api_stress $x $n 5 | tail -1)
		line "api $x $n $(echo $r | awk '{print $10, $11}') | $s0| $(st)"
	done; done
	for t in page_fault1 page_fault_shared3; do for n in 16 32; do
		s0=$(st); r=$(timeout 60 /root/wis/build/${t}_threads -t $n -s 5 -n 1 2>&1 | grep -E "^average:" | sed 's/average://; s/:.*//')
		line "wis $t $n ${r:-0} | $s0| $(st)"
	done; done
done
[ $MODE = on ] && d_off
echo "$TAG $MODE complaints $(( $(complaints) - c0 ))" >> $O/complaints.txt
echo SUITE_DONE
