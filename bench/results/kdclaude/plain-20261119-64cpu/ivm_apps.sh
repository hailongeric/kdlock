#!/bin/bash
# ivm_apps.sh MODE TAG [BENCH...]: Psearchy and LevelDB in the configurations
# of the IntervalVM artifact (kaist-cp/interval-vm, SOSP '25), where stock
# Linux stops scaling at about 36 threads (Psearchy) and 4 threads (LevelDB),
# next to the TCLocks configurations of ../appgrid-20261118-64cpu/app_grid.sh,
# where it does not (README section 5).
#   MODE native | off | on   as in app_grid.sh ("on": daemon with the allow
#                            lists api, torture, mm and /root/kds_cmp.json)
#   BENCH psearchy leveldb   (default: both)
# psearchy  pedsort -t /tmp/db/db -c N -m M over the kernel source tree, no
#           -l; the artifact uses -m 2048 (four 512 MB arrays per thread),
#           which needs about 1.5 GB per thread: here -m PS_M (default 256)
#           at every worker count and -m 1024 up to 16 workers. Variant
#           "m128l" is the TCLocks line (-m 128 -l 200000) for comparison.
# leveldb   the artifact's database: fillrandom --num=2000000
#           --value_size=4096 (8 GB, several thousand 2 MB tables), here on
#           tmpfs, then readrandom with N threads for 20 s (LevelDB 1.20 of
#           the TCLocks copy; the artifact has 1.23 and "readrandomsmall").
#           Variant "open50k" adds --open_files=50000: every table stays
#           open and mapped, so no mmap/munmap per lookup.
# Threads are pinned as in the grid (taskset 0..N-1); the artifact does not
# pin. PS_VARIANTS (big m1024 m512 m128l) and LDB_VARIANTS (ivm open50k) select
# the variants. One line per point in /root/plainprof/ivm-runs.txt, app_grid.sh's
# format: TAG MODE BENCH VARIANT N VALUE UNIT [extra] | counters | counters
MODE=${1:?mode}; TAG=${2:?tag}; shift 2
BENCHES=${*:-psearchy leveldb}
O=/root/plainprof; mkdir -p $O; OUT=$O/ivm-runs.txt
A=/root/appbench; AL=/root/host_fs/kdlock/bench/allow
WORKERS=${WORKERS:-"1 2 4 8 16 24 32 40 48 60"}
PS_M=${PS_M:-256}
ulimit -n 65536; ulimit -c 0
sysctl -q kernel.print-fatal-signals=1
C="delegated handback hb_frontier hb_miss offered plain sessions hb_region done_in_region"
st() {
	[ -r /sys/kernel/debug/kdlock_stats ] || { echo -n "- "; return; }
	local k
	for k in $C; do awk -v k=$k '$1 == k {printf "%s ", $2}' /sys/kernel/debug/kdlock_stats; done
}
complaints() { dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall"; }
fatal() { dmesg | grep -cE "potentially unexpected fatal signal|segfault at|trap invalid opcode"; }
line() { echo "$TAG $MODE $*" >> $OUT; }
d_on() {
	ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
	cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/allow_cmp.txt
	# KD_ALLOW and KD_STATE replace the allow list and the state file (a
	# comparison of allow lists in one boot needs a state of its own).
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state ${KD_STATE:-/root/kds_cmp.json} \
		--allow ${KD_ALLOW:-/root/allow_cmp.txt} -v >> $O/kdd-$TAG.log 2>&1 < /dev/null &
	 echo $! > /root/kdd_ivm.pid)
	sleep 10
}
d_off() {
	local P=$(cat /root/kdd_ivm.pid) i
	kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
}

ps1() {	# ps1 VARIANT N OPTS...
	local v=$1 n=$2 i s0 r t0 t1 P=$A/ivm/psearchy; shift 2
	mkdir -p /tmp/db && mount -t tmpfs none /tmp/db
	for i in $(seq 0 $n); do mkdir /tmp/db/db$i; done
	s0=$(st); t0=$(date +%s.%N)
	r=$(timeout 1800 taskset -c 0-$((n - 1)) $P/mkdb/pedsort -t /tmp/db/db -c $n "$@" \
		< $A/text-files.txt 2>&1 | sed -n 's/.*throughput: *\([0-9.]*\).*/\1/p' | tail -1)
	t1=$(date +%s.%N)
	line "psearchy $v $n $(echo "${r:-0} * $n" | bc) jobs/hour ${r:-0}/core $(echo "$t1 - $t0" | bc | cut -c1-6)s | $s0| $(st)"
	umount /tmp/db; rmdir /tmp/db
}
b_psearchy() {
	local n
	[ -s $A/text-files.txt ] || { echo "no psearchy input"; return 1; }
	$A/ivm/psearchy/prefetch -r $A/text > /dev/null 2>&1
	local v
	for v in ${PS_VARIANTS:-big m1024 m128l}; do
		case $v in
		big)   for n in $WORKERS; do ps1 m$PS_M $n -m $PS_M; done ;;
		m1024) for n in $WORKERS; do [ $n -le 16 ] && ps1 m1024 $n -m 1024; done ;;
		m512)  for n in $WORKERS; do [ $n -le 32 ] && ps1 m512 $n -m 512; done ;;
		m128l) for n in $WORKERS; do ps1 m128l $n -m 128 -l 200000; done ;;
		esac
	done
}

b_leveldb() {
	local n v o s0 r d D=/root/ldb_ivm B=$A/tclocks/leveldb-1.20/out-static/db_bench
	mkdir -p $D; mountpoint -q $D && umount $D
	mount -t tmpfs -o size=14G tmpfs $D || return 1
	# The same database for every pass and kernel: how fillrandom and its
	# compactions leave the tables differs from fill to fill, and with it
	# how many tables a lookup opens. The first fill is kept on disk
	# (LDB_PRISTINE) and copied to tmpfs from then on.
	local PR=${LDB_PRISTINE:-/root/ldb_ivm_pristine}
	if [ -d $PR/db ]; then
		echo "$TAG $MODE leveldb copy of $PR $(date +%T)" >> $O/progress.txt
		cp -a $PR/db $D/db
	else
		echo "$TAG $MODE leveldb fill $(date +%T)" >> $O/progress.txt
		$B --db=$D/db --benchmarks=fillrandom --num=2000000 --value_size=4096 > $O/tmp-ldbfill.out 2>&1
		mkdir -p $PR && cp -a $D/db $PR/db && sync
	fi
	echo "$TAG $MODE leveldb db: $(ls $D/db | grep -cE '\.(ldb|sst)$') tables, $(du -sh $D/db | cut -f1) $(date +%T)" >> $O/progress.txt
	for v in ${LDB_VARIANTS:-ivm open50k}; do
		o=""; [ $v = open50k ] && o="--open_files=50000"
		for n in $WORKERS; do
			s0=$(st)
			r=$(taskset -c 0-$((n - 1)) $B --pin_threads=1 --benchmarks=readrandom --use_existing_db=1 \
				--db=$D/db --num=2000000 --value_size=4096 --threads=$n --time_ms=20000 $o 2>&1 | grep "^readrandom")
			d=$(echo "$r" | sed -n 's/.*micros\/op; (\([0-9]*\)[ )].*/\1/p')
			line "leveldb $v $n $(( ${d:-0} / 20 )) ops/s $(echo "$r" | awk '{print $3}')us/op | $s0| $(st)"
		done
	done
	umount $D
}

[ $MODE = on ] && d_on
c0=$(complaints); f0=$(fatal)
echo "$TAG $MODE start $(date +%T) $(uname -r) workers: $WORKERS" >> $O/progress.txt
for b in $BENCHES; do
	echo "$TAG $MODE $b $(date +%T)" >> $O/progress.txt
	b_$b
done
[ $MODE = on ] && d_off
echo "$TAG $MODE complaints $(( $(complaints) - c0 )) fatal signals $(( $(fatal) - f0 ))" >> $O/complaints.txt
echo "$TAG $MODE done $(date +%T)" >> $O/progress.txt
echo IVM_DONE
