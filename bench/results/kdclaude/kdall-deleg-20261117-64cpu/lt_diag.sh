#!/bin/bash
# lt_diag.sh TAG native|kd: rwsem_lock and ww_mutex_lock under locktorture,
# 40 s each, with kd stats, context switches and a flat profile.
TAG=${1:?tag}; MODE=${2:?mode}
O=/root/ltd; mkdir -p $O
exec > $O/$TAG.log 2>&1
D=/root/kdc_torture
mark() { echo "ltd: $*" > /dev/kmsg; echo "== $* $(date +%T)"; }
since() { dmesg | awk -v m="ltd: $1" 'index($0, m) {f=1} f'; }
stats() { cat /sys/kernel/debug/kdlock_stats 2>/dev/null; }
uname -rv; pgrep -af kd_daemon || echo "no daemon"
[ $MODE = native ] && insmod $D/torture.ko
for t in rwsem_lock ww_mutex_lock mutex_lock; do
	mark "torture $t"
	stats > /tmp/s0
	if [ $MODE = native ]; then
		insmod $D/locktorture_ext.ko torture_type=$t stat_interval=0 || continue
	else
		modprobe locktorture torture_type=$t stat_interval=0 || continue
	fi
	sleep 10
	perf stat -a -e context-switches,cpu-migrations -- sleep 10 2>&1 | grep -E "context|migr"
	perf record -a -F 499 -o /tmp/p.data -- sleep 5 > /dev/null 2>&1
	perf report -i /tmp/p.data --sort sym --stdio 2>/dev/null | grep -v "^#" | grep . | head -14
	sleep 15
	if [ $MODE = native ]; then rmmod locktorture_ext; else rmmod locktorture; fi
	stats > /tmp/s1
	since "torture $t" | grep -E "End of test|Writes:|Reads:" | sed 's/^\[[^]]*\] //' | sed 's/acq_writer_lim.*//' | tail -3
	echo "-- kd stat changes"
	join <(sort /tmp/s0) <(sort /tmp/s1) | awk '$3 != $2 {printf "%-22s %d\n", $1, $3 - $2}'
done
echo "complaints:"; dmesg | grep -iE "BUG:|WARNING:|lockup|hung_task|rcu.*stall" | head
echo LTD_DONE
