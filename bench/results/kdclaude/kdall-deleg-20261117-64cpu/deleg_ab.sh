#!/bin/bash
# deleg_ab.sh: kdall1, delegation off (no daemon) against on (daemon with the
# three allow lists), alternated in one boot. Output: /root/dab/ab.txt
O=/root/dab; mkdir -p $O; exec > $O/ab.txt 2> $O/ab.err
A=/root/host_fs/kdlock/bench/allow
cat $A/api.txt $A/torture.txt > /root/allow_all.txt
S=/root/kds_ab.json
ulimit -n 65536
st() { grep -E "^(delegated|handback) " /sys/kernel/debug/kdlock_stats | awk '{printf "%s ", $2}'; }
d_on() {
	pgrep -f kd_daemon.py > /dev/null && { echo "a daemon is running"; exit 1; }
	# cd first: "cd && cmd &" would background a subshell, and $! would be
	# that shell, not the daemon.
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $S \
		--allow /root/allow_all.txt -v >> $O/kdd.log 2>&1 < /dev/null &
	 echo $! > /root/kdd.pid)
	sleep 8	# republish the stored sites
}
d_off() {
	P=$(cat /root/kdd.pid); kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
	kill -0 $P 2>/dev/null && { echo "daemon $P did not stop"; exit 1; }
}
run() {	# run TAG: one pass over every workload, one line each
	local tag=$1 s0 r
	for x in setfd ofd pipe seek uts xattr; do for n in 16 64; do
		s0=$(st); r=$(/root/api_stress $x $n 5 | tail -1)
		echo "$tag api $x $n $(echo $r | awk '{print $10, $11}') | $s0| $(st)"
	done; done
	for t in mmap1 mmap2 brk1; do for n in 16 64; do
		s0=$(st); r=$(cd /tmp && timeout 60 /root/wis/build/${t}_threads -t $n -s 5 -n 1 2>&1 | grep -E "^average:|abort" | tr '\n' ' ')
		echo "$tag wis $t $n $r | $s0| $(st)"
	done; done
	for t in rwsem_lock mutex_lock; do
		s0=$(st); echo "dab: $tag $t" > /dev/kmsg
		modprobe locktorture torture_type=$t stat_interval=0; sleep 20; rmmod locktorture
		r=$(dmesg | awk -v m="dab: $tag $t" 'index($0,m){f=1} f' | grep -E "Writes:|End of test" | sed 's/^\[[^]]*\] //;s/acq_writer.*//' | tr '\n' ' ')
		echo "$tag torture $t 128 $r | $s0| $(st)"
	done
}
uname -rv
d_on; run learn1; run learn2; d_off
for r in 1 2 3; do
	if [ $((r % 2)) = 1 ]; then run r$r-off; d_on; run r$r-on; d_off
	else d_on; run r$r-on; d_off; run r$r-off; fi
done
echo "complaints:"; dmesg | grep -iE "BUG:|WARNING:|lockup|hung_task|blocked for more|rcu.*stall" | head -20
echo AB_DONE
