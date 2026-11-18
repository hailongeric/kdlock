#!/bin/bash
# mmap1 threads, 32 workers, delegation on: the hottest sample addresses in
# module space (generated images), and the images the daemon loaded.
O=/root/mdiag; exec > $O/mip.txt 2>&1
A=/root/host_fs/kdlock/bench/allow
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_mm.json --allow $A/mm.txt -v \
	> $O/mip.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_mip.pid)
sleep 10
cd /tmp
for n in 32 64; do
	echo "== mmap1 $n"
	/root/wis/build/mmap1_threads -t $n -s 12 -n 1 > /tmp/mp.out 2>&1 &
	sleep 4
	perf record -a -F 999 -o /tmp/mi.data -- sleep 4 > /dev/null 2>&1
	wait
	grep average /tmp/mp.out
	echo "-- total samples: $(perf script -i /tmp/mi.data -F ip 2>/dev/null | wc -l)"
	echo "-- module-space ips (top 15)"
	perf script -i /tmp/mi.data -F ip 2>/dev/null | awk '{print $1}' | grep -E "^ffffffffc" | sort | uniq -c | sort -rn | head -15
	echo "-- kernel symbols outside the waits (top 25)"
	perf script -i /tmp/mi.data -F ip,sym 2>/dev/null | awk '{ $1=""; print }' | grep -vE "kd_wait_sleepable|kd_rw_era_wait|kd_mutex_can_spin|pvclock|^ *\[unknown\]" | sort | uniq -c | sort -rn | head -25
done
P=$(cat /root/kdd_mip.pid); kill -INT $P
for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
grep -E "instructions, .* bytes at" $O/mip.kdd | tail -10
echo MIP_DONE
