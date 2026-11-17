#!/bin/bash
# mm_check.sh: data-checked mm_stress (bench/mm_stress.c) with the mmap_lock
# writers of brk(), mmap() and munmap() delegated (bench/allow/mm.txt).
# 16, 32 and 64 threads, 30 s each; kd counters per run. Output: /root/dmm/check.txt
O=/root/dmm; mkdir -p $O; exec > $O/check.txt 2>&1
A=/root/host_fs/kdlock/bench/allow
S=/root/kds_mm.json
C="delegated handback hb_frontier hb_miss hb_acquire hb_downgrade hb_other offered"
st() {
	local k
	for k in $C; do awk -v k=$k '$1 == k {printf "%s ", $2}' /sys/kernel/debug/kdlock_stats; done
}
ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
gcc -O2 -pthread -o /root/mm_stress /root/host_fs/kdlock/bench/mm_stress.c || exit 1
uname -rv
echo "counters: $C"
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $S \
	--allow $A/mm.txt -v >> $O/check.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_mm.pid)
sleep 8
for n in 16 32 64; do
	s0=$(st)
	r=$(cd /tmp && timeout 120 /root/mm_stress $n 30 2>&1 | tail -3 | tr '\n' ' '); rc=$?
	echo "mm_stress $n: $r| $s0| $(st)"
done
P=$(cat /root/kdd_mm.pid); kill -INT $P
for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
kill -0 $P 2>/dev/null && echo "daemon $P did not stop"
echo "complaints:"; dmesg | grep -iE "BUG:|WARNING:|lockup|hung_task|blocked for more|rcu.*stall" | head -20
echo CHECK_DONE
