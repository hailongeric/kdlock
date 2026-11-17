#!/bin/bash
# trial.sh: first delegation on kdall1, the three allow lists together, short runs.
A=/root/host_fs/kdlock/bench/allow
cat $A/mm.txt $A/api.txt $A/torture.txt > /root/allow_all.txt
L=/root/kdd_trial.log
st() { grep -E "^(delegated|handback|sessions|offered) " /sys/kernel/debug/kdlock_stats | tr '\n' ' '; }
pgrep -f kd_daemon.py > /dev/null && { echo "a daemon is running"; exit 1; }
cd /root/host_fs/kdlock/jit
setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_trial.json --allow /root/allow_all.txt -v \
    > $L 2>&1 < /dev/null & echo $! > /root/kdd.pid
sleep 3
ulimit -n 65536
for x in setfd ofd pipe seek uts xattr; do
	echo "api $x: $(/root/api_stress $x 32 5 | tail -1) | $(st)"
done
for t in mmap1 mmap2 brk1; do
	r=$(cd /tmp && timeout 60 /root/wis/build/${t}_threads -t 64 -s 3 -n 1 2>&1 | grep -E "^average:|abort" | tr '\n' ' ')
	echo "wis $t: $r | $(st)"
done
for t in rwsem_lock mutex_lock spin_lock; do
	modprobe locktorture torture_type=$t stat_interval=0; sleep 15; rmmod locktorture
	echo "torture $t: $(dmesg | grep -E "Writes:" | tail -1 | sed 's/^\[[^]]*\] //') $(dmesg | grep "End of test" | tail -1 | grep -o "SUCCESS\|FAILURE") | $(st)"
done
P=$(cat /root/kdd.pid); kill -INT $P; for i in $(seq 30); do kill -0 $P 2>/dev/null || break; sleep 1; done
kill -0 $P 2>/dev/null && echo "daemon $P did not stop"
echo "complaints:"; dmesg | grep -iE "BUG:|WARNING:|lockup|hung_task|blocked for more|rcu.*stall|preempt" | head -20
echo TRIAL_DONE
