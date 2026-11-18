#!/bin/bash
# suite.sh MODE TAG: one pass over every workload of the native comparison.
#   MODE native  kdnat1 (CONFIG_KDLOCK_ALL off), native locks
#   MODE off     kdall1, every lock a kdlock, no daemon (no delegation)
#   MODE on      kdall1, daemon with the api, torture and mm allow lists
# One line per run is appended to /root/cmp/runs.txt:
#   TAG MODE KIND NAME THREADS VALUE [extra] | kd counters before | after
# The counters (kdall1 only) are: delegated handback hb_frontier hb_miss
# offered plain sessions.
MODE=${1:?mode}; TAG=${2:?tag}
O=/root/cmp; mkdir -p $O
OUT=$O/runs.txt
B=/root/host_fs/kdlock/bench
A=$B/allow
ST=/root/kds_cmp.json
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
	# cd first: "cd && cmd &" would background a subshell, and $! would be
	# that shell, not the daemon.
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $ST \
		--allow /root/allow_cmp.txt -v >> $O/kdd-$TAG.log 2>&1 < /dev/null &
	 echo $! > /root/kdd_cmp.pid)
	sleep 10	# republish the stored sites
}
d_off() {
	P=$(cat /root/kdd_cmp.pid); kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
	kill -0 $P 2>/dev/null && { echo "daemon $P did not stop"; exit 1; }
}

[ $MODE = on ] && d_on
c0=$(complaints)

# 1. Page faults on a 10 GB mapping in pseudo-random order (bench/pf_random.c).
for mode in read write; do for n in 16 32 64; do
	w=""; [ $mode = write ] && w=-w
	s0=$(st); r=$(cd /tmp && timeout 120 /root/pf_random $n 15 -g 10 $w 2>&1 | tail -1)
	v=$(echo "$r" | awk '{for (i = 1; i < NF; i++) if ($i == "fault_rate") print $(i + 1)}')
	line "pf $mode $n ${v:-0} $(echo "$r" | sed 's/.*rounds/rounds/') | $s0| $(st)"
done; done

# 2. will-it-scale, threads model.
for t in mmap1 mmap2 brk1 page_fault1 page_fault_shared1 page_fault_shared3; do for n in 16 32 64; do
	s0=$(st); r=$(cd /tmp && timeout 60 /root/wis/build/${t}_threads -t $n -s 5 -n 1 2>&1 | grep -E "^average:" | sed 's/average://; s/:.*//')
	line "wis $t $n ${r:-0} | $s0| $(st)"
done; done

# 3. api_stress: the syscalls of the CONFIG_KDLOCK_API locks, data-checked.
for x in setfd ofd pipe seek uts xattr; do for n in 16 64; do
	s0=$(st); r=$(/root/api_stress $x $n 5 | tail -1)
	line "api $x $n $(echo $r | awk '{print $10, $11}') | $s0| $(st)"
done; done

# 4. locktorture, 30 s, default writers and readers.
for t in spin_lock rw_lock mutex_lock rwsem_lock ww_mutex_lock; do
	s0=$(st); echo "cmp: $TAG $MODE $t" > /dev/kmsg
	modprobe locktorture torture_type=$t stat_interval=0; sleep 30; rmmod locktorture
	r=$(dmesg | awk -v m="cmp: $TAG $MODE $t" 'index($0,m){f=1} f' | grep -E "Writes:" | tail -1 | sed 's/.*Total: *//; s/ .*//')
	line "torture $t 128 ${r:-0} | $s0| $(st)"
done

# 5. Added for the c series (section 8): the mmap lock tests at 48 and 60
# threads as well, after everything else so that sections 1-4 keep their
# order. 64 threads leave no CPU for anything else, which 60 does.
for t in mmap1 mmap2 brk1; do for n in 48 60; do
	s0=$(st); r=$(cd /tmp && timeout 60 /root/wis/build/${t}_threads -t $n -s 5 -n 1 2>&1 | grep -E "^average:" | sed 's/average://; s/:.*//')
	line "wis $t $n ${r:-0} | $s0| $(st)"
done; done

[ $MODE = on ] && d_off
echo "$TAG $MODE complaints $(( $(complaints) - c0 ))" >> $O/complaints.txt
echo SUITE_DONE
