#!/bin/bash
# rwsem_lock locktorture, 40 s, at two reader spin bounds, alternated.
exec > /root/ltd/rspin.log 2>&1
P=/sys/module/kernel/parameters/kd_rwsem_rspin_ns
stats() { cat /sys/kernel/debug/kdlock_stats; }
for r in 50000 1000000000 50000 1000000000; do
	echo $r > $P
	echo "== rspin $r"
	stats > /tmp/s0
	echo "ltd: rspin $r" > /dev/kmsg
	modprobe locktorture torture_type=rwsem_lock stat_interval=0; sleep 40; rmmod locktorture
	stats > /tmp/s1
	dmesg | awk -v m="ltd: rspin $r" 'index($0,m){f=1} f' | grep -E "Writes:|Reads:" | sed 's/^\[[^]]*\] //' | tail -2
	join <(sort /tmp/s0) <(sort /tmp/s1) | awk '$3 != $2 && $1 ~ /rd_|parked|head_sleep|handoff/ {printf "%s=%d ", $1, $3 - $2}'; echo
done
echo 50000 > $P
echo RS_DONE
