#!/bin/bash
# era_ab.sh TAG [ROUNDS]: what the era logic (kd_era.c) costs or gains on the
# path without delegation. On a kdall kernel with no daemon, in one boot:
# will-it-scale mmap1, mmap2, brk1 and page_fault1 (threads, 10 s) with eras
# on (kd_rw_era_ns at its default) and off (kd_rw_era_ns=0: no era in either
# family and the queue heads measure nothing), alternating, ROUNDS times
# (default 2). The reader phase of the rwsem (kd_rwsem_rphase_ns) is a
# third setting, off with eras on, because it is the other piece of
# plain-path logic a queue head runs before it closes the read side.
# WORKERS overrides the worker counts.
# Output: /root/plainprof/TAG-era.txt, one line per point:
#   TAG ROUND SETTING TEST N RATE | counters added
TAG=${1:?tag}; R=${2:-2}
O=/root/plainprof; mkdir -p $O; exec > $O/$TAG-era.txt 2>&1
W=/root/appbench/tclocks/will-it-scale
P=/sys/module/kernel/parameters
WORKERS=${WORKERS:-"1 2 4 8 16 32 40 48 60"}
ulimit -c 0
uname -rv
[ -r $P/kd_rw_era_ns ] || { echo "no kd_rw_era_ns: not a kdall kernel"; exit 1; }
ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
ERA0=$(cat $P/kd_rw_era_ns); RPH0=$(cat $P/kd_rwsem_rphase_ns)
echo "defaults: kd_rw_era_ns=$ERA0 kd_rwsem_era_ns=$(cat $P/kd_rwsem_era_ns) kd_rwsem_rphase_ns=$RPH0"
K="delegated plain era_gate era_claim era_start parked head_sleep no_spin abandon rd_behind rd_queue numa_local"
snap() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
dsnap() { python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split())
b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b if int(b[k]) != int(a.get(k, 0))))' "$1" "$2"; }
set_mode() {
	case $1 in
	era)	echo $ERA0 > $P/kd_rw_era_ns; echo $RPH0 > $P/kd_rwsem_rphase_ns ;;
	noera)	echo 0 > $P/kd_rw_era_ns; echo $RPH0 > $P/kd_rwsem_rphase_ns ;;
	norph)	echo $ERA0 > $P/kd_rw_era_ns; echo 0 > $P/kd_rwsem_rphase_ns ;;
	esac
}
mountpoint -q /tmp || mount -t tmpfs -o size=10G tmpfs /tmp
cd $W
for r in $(seq $R); do
	for t in mmap1 mmap2 brk1 page_fault1; do for n in $WORKERS; do
		# The order of the settings rotates per point so drift hits them alike.
		case $(( (r + n) % 3 )) in 0) order="era noera norph" ;; 1) order="noera norph era" ;; *) order="norph era noera" ;; esac
		for m in $order; do
			set_mode $m
			s0=$(snap)
			v=$(timeout 120 setarch linux64 -R ./build/${t}_threads -t $n -s 10 -n 32 2>&1 | grep "^average:" | cut -d: -f2)
			echo "$TAG $r $m $t $n ${v:-0} | $(dsnap "$s0" "$(snap)")"
		done
	done; done
done
set_mode era
echo "restored: kd_rw_era_ns=$(cat $P/kd_rw_era_ns) kd_rwsem_rphase_ns=$(cat $P/kd_rwsem_rphase_ns)"
echo ERA_AB_DONE
