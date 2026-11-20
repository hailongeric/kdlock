#!/bin/bash
# stress-ng seccomp with the daemon, 24 runs each: (A) the lkp allow lists without the sighand->siglock users,
# (B) only the sighand->siglock users. SIGSYS kills logged per variant.
B=/root/lkpbench/stress-ng/stress-ng; O=/root/lkpres; AL=/root/host_fs/kdlock/bench/allow
SIG="do_send_sig_info set_current_blocked get_signal signal_setup_done"
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
cat $AL/api.txt $AL/torture.txt $AL/mm.txt $AL/lkp.txt | grep -vxE "$(echo $SIG | tr ' ' '|')" > $O/tmp/secc-A.allow
echo $SIG | tr ' ' '\n' > $O/tmp/secc-B.allow
for v in A B; do
	rm -f /root/kds_secc.json
	(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_secc.json --allow $O/tmp/secc-$v.allow -v > $O/kdd-secc-$v.log 2>&1 < /dev/null &)
	sleep 10
	s0=$(dmesg | grep -c "fatal signal 31"); d0=$(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats)
	for i in $(seq 24); do (cd /root/lkpsng && timeout 66 $B --seccomp 64 --timeout 6 --verify --metrics --no-rand-seed --temp-path /root/lkpsng > /dev/null 2>&1); done
	echo "variant $v: 24 runs, SIGSYS logged $(( $(dmesg | grep -c "fatal signal 31") - s0 )), delegated $(( $(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats) - d0 ))"
	P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for i in $(seq 120); do kill -0 $P 2>/dev/null || break; sleep 1; done
done > $O/secc-bisect.txt 2>&1
cd /; umount /root/lkpsng; echo SECC_BISECT_DONE >> $O/secc-bisect.txt
