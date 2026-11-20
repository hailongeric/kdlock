#!/bin/bash
# stress-ng seccomp with the daemon (only the sighand->siglock users allowed) until a child is killed by SIGSYS;
# every failed system call of the stressor is recorded (the expected failures of seccomp() and prctl() left out).
B=/root/lkpbench/stress-ng/stress-ng; O=/root/lkpres
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
rm -f /root/kds_secc.json
(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_secc.json --allow $O/tmp/secc-B.allow -v > $O/kdd-secc-T.log 2>&1 < /dev/null &)
sleep 10
s0=$(dmesg | grep -c "fatal signal 31")
for i in $(seq 40); do
	rm -f $O/tmp/secc.data
	perf record -a -q -e raw_syscalls:sys_exit --filter 'ret < 0 && id != 317 && id != 157' -o $O/tmp/secc.data -- \
		sh -c "cd /root/lkpsng && timeout 66 $B --seccomp 64 --timeout 6 --verify --metrics --no-rand-seed --temp-path /root/lkpsng > $O/tmp/secc-run.out 2>&1" > /dev/null 2>&1
	if [ $(dmesg | grep -c "fatal signal 31") -gt $s0 ]; then
		echo "SIGSYS in run $i"
		dmesg | grep -A9 "fatal signal 31" | tail -10 | cut -c1-150
		pid=$(dmesg | grep -A1 "fatal signal 31" | tail -1 | sed -n 's/.*PID: \([0-9]*\) .*/\1/p')
		echo "killed pid $pid; its failed system calls:"
		perf script -i $O/tmp/secc.data 2>/dev/null | awk -v p=$pid '$2 == p' | tail -12 | cut -c1-170
		echo "failed system calls of all stressor tasks in this run, by number and return value:"
		perf script -i $O/tmp/secc.data 2>/dev/null | grep "stress-ng" | sed -n 's/.*NR \([0-9]*\) = \(-[0-9]*\).*/\1 \2/p' | sort | uniq -c | sort -rn | head -12
		grep -E "fail|unexpected|error" $O/tmp/secc-run.out | head -5 | cut -c1-200
		break
	fi
done
echo "runs: $i"
P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for j in $(seq 120); do kill -0 $P 2>/dev/null || break; sleep 1; done
cd /; umount /root/lkpsng; echo SECC_TRACE_DONE
