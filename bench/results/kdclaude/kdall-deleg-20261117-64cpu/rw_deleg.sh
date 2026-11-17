#!/bin/bash
# rw_deleg.sh TYPE [SECONDS] [on|off]: locktorture TYPE with the daemon on
# (torture allow list only) or off; every kd counter is sampled every 5 s,
# and the changes per interval are printed, as are locktorture's own
# statistics every 5 s. Output: /root/rwd/TYPE-MODE.log
T=${1:?torture type}; N=${2:-40}; M=${3:-on}
O=/root/rwd; mkdir -p $O; exec > $O/$T-$M.log 2>&1
A=/root/host_fs/kdlock/bench/allow
ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
uname -rv
[ $M = on ] && (cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state "" --allow $A/torture.txt -v \
	> $O/$T-$M.kdd 2>&1 < /dev/null &
 echo $! > /root/rwd.pid)
sleep 5
st() { grep -vE "^#" /sys/kernel/debug/kdlock_stats; }
echo "rwd: $T" > /dev/kmsg
modprobe locktorture torture_type=$T stat_interval=5
st > /tmp/rwd0
for i in $(seq 5 5 $N); do
	sleep 5; st > /tmp/rwd1
	echo "== $((i - 5))-$i s"
	join <(sort /tmp/rwd0) <(sort /tmp/rwd1) | awk '$3 != $2 {printf "  %-16s %d\n", $1, $3 - $2}'
	mv /tmp/rwd1 /tmp/rwd0
done
rmmod locktorture
dmesg | awk -v m="rwd: $T" 'index($0,m){f=1} f' | grep -E "Writes:|Reads:|End of test" | sed 's/^\[[^]]*\] //;s/acq_writer.*//'
if [ $M = on ]; then
	P=$(cat /root/rwd.pid); kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
	kill -0 $P 2>/dev/null && echo "daemon $P did not stop"
fi
echo RWD_DONE
