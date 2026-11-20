#!/bin/bash
# kdall18 without the daemon: lock1 profile; writer parking: never / always above the drain threshold / with a queue of 4 / of 8.
D=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
V=/root/host_fs/kdlock/bench/results/kdclaude/plain-20261119-64cpu
P=/sys/module/kernel/parameters; O=/root/plainprof; W=/root/appbench/tclocks/will-it-scale
K="parked head_sleep no_spin wr_steal wr_handoff"
snap() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
dsnap() { python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split())
b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b if int(b[k]) != int(a.get(k, 0))))' "$1" "$2"; }
ulimit -c 0
bash /root/lock1_perf.sh k18 kd_q_lock_slow
export LDB_VARIANTS=ivm
for r in 1 2; do for v in off q0 q4 q8; do
	case $v in off) echo 0 > $P/kd_rwsem_park_drain_ns;; *) echo 5000 > $P/kd_rwsem_park_drain_ns; echo ${v#q} > $P/kd_rwsem_park_queue;; esac
	WORKERS="16 32 60" bash $D/app_grid.sh off k18-$v-$r apache > /root/appgrid/k18-park.out 2>&1
	WORKERS="4 8 16 32" bash $V/ivm_apps.sh off k18-$v-$r leveldb > $O/k18-ldb.out 2>&1
	for t in mmap1 brk1; do for n in 8 16 32; do
		s0=$(snap)
		x=$(cd $W && timeout 120 setarch linux64 -R ./build/${t}_threads -t $n -s 10 -n 32 2>&1 | grep "^average:" | cut -d: -f2)
		echo "k18 $r $v $t $n ${x:-0} | $(dsnap "$s0" "$(snap)")" >> $O/k18-park.txt
	done; done
done; done
echo 5000 > $P/kd_rwsem_park_drain_ns; echo 4 > $P/kd_rwsem_park_queue
echo "K18_EXP_DONE $(date +%T)" >> $O/progress.txt
