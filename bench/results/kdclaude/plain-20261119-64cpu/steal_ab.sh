#!/bin/bash
# steal_ab.sh TAG [ROUNDS]: rwsem write stealing (kd_rwsem.c, kd_rwsem_steal)
# off and on in one boot of a kdall kernel with no daemon: will-it-scale
# page_fault1-3, mmap1 and brk1 (threads, 10 s), the two settings
# alternating per point. TESTS and WORKERS override the lists.
# Output: /root/plainprof/TAG-steal.txt, one line per point:
#   TAG ROUND steal0|steal1 TEST N RATE | counters added
TAG=${1:?tag}; R=${2:-1}
O=/root/plainprof; mkdir -p $O; exec > $O/$TAG-steal.txt 2>&1
W=/root/appbench/tclocks/will-it-scale
P=/sys/module/kernel/parameters
WORKERS=${WORKERS:-"4 8 16 32 60"}
TESTS=${TESTS:-"page_fault1 page_fault2 page_fault3 mmap1 brk1"}
ulimit -c 0
uname -rv
[ -r $P/kd_rwsem_steal ] || { echo "no kd_rwsem_steal on this kernel"; exit 1; }
ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
K="plain parked head_sleep no_spin abandon rd_behind rd_queue wr_steal wr_handoff era_gate numa_local"
snap() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
dsnap() { python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split())
b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b if int(b[k]) != int(a.get(k, 0))))' "$1" "$2"; }
c0=$(dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall|WARNING")
mountpoint -q /tmp || mount -t tmpfs -o size=10G tmpfs /tmp
cd $W
for r in $(seq $R); do
	for t in $TESTS; do for n in $WORKERS; do
		[ $(( (r + n / 4) % 2 )) = 0 ] && order="1 0" || order="0 1"
		for m in $order; do
			echo $m > $P/kd_rwsem_steal
			s0=$(snap)
			v=$(timeout 120 setarch linux64 -R ./build/${t}_threads -t $n -s 10 -n 32 2>&1 | grep "^average:" | cut -d: -f2)
			echo "$TAG $r steal$m $t $n ${v:-0} | $(dsnap "$s0" "$(snap)")"
		done
	done; done
done
echo 1 > $P/kd_rwsem_steal
echo "kernel complaints added: $(( $(dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall|WARNING") - c0 ))"
echo STEAL_AB_DONE
