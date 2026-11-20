#!/bin/bash
# When in a run does the SIGSYS kill happen? Uptime at the start and end of each run next to the kernel log's time stamps.
B=/root/lkpbench/stress-ng/stress-ng; O=/root/lkpres; AL=/root/host_fs/kdlock/bench/allow; N=${1:-60}
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
for a in api torture mm lkp; do cat $AL/$a.txt; done > $O/tmp/on.allow
(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_secc.json --allow $O/tmp/on.allow -v > $O/kdd-secc-time.log 2>&1 < /dev/null &)
sleep 25
for i in $(seq $N); do
	t0=$(cut -d" " -f1 /proc/uptime)
	(cd /root/lkpsng && timeout 66 $B --seccomp 64 --timeout 6 --verify --metrics --no-rand-seed --temp-path /root/lkpsng > /dev/null 2>&1)
	echo "run $i $t0 $(cut -d" " -f1 /proc/uptime)"
done
dmesg | grep "fatal signal 31" | sed 's/^\[ *\([0-9.]*\)\].*/sigsys \1/'
P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for j in $(seq 120); do kill -0 $P 2>/dev/null || break; sleep 1; done
cd /; umount /root/lkpsng; echo SECC_TIME_DONE
