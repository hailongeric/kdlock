#!/bin/bash
# disc.sh: daemon with an empty allow list; which sites does each workload contend?
L=/root/kdd_disc.log
: > /root/allow_none.txt
cd /root/host_fs/kdlock/jit
setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state '' --allow /root/allow_none.txt -v \
    > $L 2>&1 < /dev/null & echo $! > /root/kdd.pid
sleep 3
m() { echo "#### $*" >> $L; }
for t in rwsem_lock mutex_lock spin_lock rw_lock; do
	m "torture $t"; modprobe locktorture torture_type=$t stat_interval=0; sleep 15; rmmod locktorture; sleep 1
done
ulimit -n 65536
for x in setfd ofd pipe seek uts xattr; do m "api $x"; /root/api_stress $x 32 5 > /dev/null; sleep 1; done
for t in mmap1 mmap2 brk1 page_fault_shared1 page_fault_shared2 page_fault1; do
	m "wis $t"; (cd /tmp && timeout 60 /root/wis/build/${t}_threads -t 64 -s 3 -n 1 > /dev/null 2>&1); sleep 1
done
kill -INT $(cat /root/kdd.pid); sleep 3
grep "^delegation\|^delegated\|^offered\|^plain" /sys/kernel/debug/kdlock_stats
echo DISC_DONE >> $L
