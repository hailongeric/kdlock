#!/bin/bash
# stress-ng seccomp, 64 instances, 6 s, 12 times with the daemon (the lkp allow lists) and 12 times without: SIGSYS kills logged.
B=/root/lkpbench/stress-ng/stress-ng; O=/root/lkpres; AL=/root/host_fs/kdlock/bench/allow
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
run() { local i a b; for i in $(seq 12); do a=$(dmesg | grep -c "fatal signal 31"); (cd /root/lkpsng && timeout 66 $B --seccomp 64 --timeout 6 --verify --metrics --no-rand-seed --temp-path /root/lkpsng 2>&1 | grep -E "seccomp +[0-9]|failed:|untrustworthy" | tr -s ' ' | cut -c1-110 | tr '\n' ' '); b=$(dmesg | grep -c "fatal signal 31"); echo "| $1 run $i SIGSYS logged: $((b - a)) | delegated $(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats)"; done; }
for a in api torture mm lkp; do cat $AL/$a.txt; done > $O/tmp/on.allow
(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_lkp.json --allow $O/tmp/on.allow -v > $O/kdd-secc.log 2>&1 < /dev/null & echo $! > /root/kdd_secc.pid)
sleep 15
run on
kill -INT $(cat /root/kdd_secc.pid); for i in $(seq 120); do kill -0 $(cat /root/kdd_secc.pid) 2>/dev/null || break; sleep 1; done
echo "daemon stopped after $i s"
run off
cd /; umount /root/lkpsng
