#!/bin/bash
# mmap1 threads at 32 and 64 workers, mmap lock writers delegated: flat
# profile (no call graphs) over 5 s in the middle of a 15 s run.
O=/root/mdiag; exec > $O/mprof.txt 2>&1
A=/root/host_fs/kdlock/bench/allow
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_mm.json --allow $A/mm.txt -v \
	>> $O/mprof.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_mprof.pid)
sleep 10
cd /tmp
for n in 32 64; do
	echo "== mmap1 $n"
	/root/wis/build/mmap1_threads -t $n -s 15 -n 1 > /tmp/mp.out 2>&1 &
	sleep 5
	perf record -a -F 999 -o /tmp/mp.data -- sleep 5 > /dev/null 2>&1
	wait
	grep average /tmp/mp.out
	perf report -i /tmp/mp.data --sort sym --stdio 2>/dev/null | grep -v "^#" | grep . | head -40
done
P=$(cat /root/kdd_mprof.pid); kill -INT $P
for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
echo MPROF_DONE
