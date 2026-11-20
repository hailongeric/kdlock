#!/bin/bash
# Does a child of the seccomp stressor start life with a filter already installed? A probe at wake_up_new_task()
# records every new task whose seccomp mode is not 0 (task_struct.seccomp.mode at 0xd28 in kdall21, from
# prctl_get_seccomp()); the forking parents of the stressor have none. $1: on (with the daemon) or off.
B=/root/lkpbench/stress-ng/stress-ng; O=/root/lkpres; AL=/root/host_fs/kdlock/bench/allow; M=$1; N=${2:-40}
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
perf probe -d "probe:wake_up_new_task*" > /dev/null 2>&1
perf probe -a 'wake_up_new_task mode=+0xd28(%di):s32 filter=+0xd30(%di):x64' > /dev/null 2>&1 || { echo "no probe"; exit 1; }
if [ $M = on ]; then
	for a in api torture mm lkp; do cat $AL/$a.txt; done > $O/tmp/on.allow
	(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_secc.json --allow $O/tmp/on.allow -v > $O/kdd-secc-probe.log 2>&1 < /dev/null &)
	sleep 25
fi
s0=$(dmesg | grep -c "fatal signal 31"); d0=$(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats)
rm -f $O/tmp/secc-probe.data
perf record -a -q -e probe:wake_up_new_task --filter 'mode != 0' -o $O/tmp/secc-probe.data -- \
	sh -c "for i in \$(seq $N); do (cd /root/lkpsng && timeout 66 $B --seccomp 64 --timeout 6 --verify --metrics --no-rand-seed --temp-path /root/lkpsng > /dev/null 2>&1); done" > /dev/null 2>&1
echo "$M: $N runs, SIGSYS logged $(( $(dmesg | grep -c "fatal signal 31") - s0 )), delegated $(( $(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats) - d0 ))"
echo "new tasks with a seccomp mode set at their first wakeup, by the forking task's name:"
perf script -i $O/tmp/secc-probe.data 2>/dev/null | awk '{print $1}' | sort | uniq -c | sort -rn | head -8
perf script -i $O/tmp/secc-probe.data 2>/dev/null | grep "stress-ng" | head -6 | cut -c1-200
dmesg | grep -A1 "fatal signal 31" | grep -o "PID: [0-9]*" | tail -4 | tr '\n' ' '; echo
if [ $M = on ]; then P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for j in $(seq 120); do kill -0 $P 2>/dev/null || break; sleep 1; done; fi
perf probe -d "probe:wake_up_new_task*" > /dev/null 2>&1
cd /; umount /root/lkpsng; echo SECC_PROBE_DONE
