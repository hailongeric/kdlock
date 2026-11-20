#!/bin/bash
# The SIGSYS kill happens at the instant a run ends. Count it over many short runs (1 s each), without and with the daemon.
B=/root/lkpbench/stress-ng/stress-ng; O=/root/lkpres; AL=/root/host_fs/kdlock/bench/allow; N=${1:-150}
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
run() {
	local s0=$(dmesg | grep -c "fatal signal 31") d0=$(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats) i
	for i in $(seq $N); do (cd /root/lkpsng && timeout 30 $B --seccomp 64 --timeout 1 --verify --no-rand-seed --temp-path /root/lkpsng > /dev/null 2>&1); done
	echo "$1: $N runs of 1 s, SIGSYS logged $(( $(dmesg | grep -c "fatal signal 31") - s0 )), delegated $(( $(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats) - d0 ))"
}
run "$(uname -r) no daemon"
if [ -r /dev/kdlock ] && uname -r | grep -q kdall; then
	for a in api torture mm lkp; do cat $AL/$a.txt; done > $O/tmp/on.allow
	(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_secc.json --allow $O/tmp/on.allow -v > $O/kdd-secc-ends.log 2>&1 < /dev/null &)
	sleep 25
	run "$(uname -r) daemon"
	P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for j in $(seq 120); do kill -0 $P 2>/dev/null || break; sleep 1; done
	run "$(uname -r) no daemon again"
fi
cd /; umount /root/lkpsng; echo SECC_ENDS_DONE
