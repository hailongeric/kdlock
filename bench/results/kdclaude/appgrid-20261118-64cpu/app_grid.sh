#!/bin/bash
# app_grid.sh MODE TAG [BENCH...]: the application benchmarks over the
# worker grid on the running kernel, in the guest.
#   MODE native  a kdnat kernel (CONFIG_KDLOCK_ALL off): native locks
#   MODE off     a kdall kernel, no daemon: every lock a kdlock, plain mode
#   MODE on      a kdall kernel with jit/kd_daemon.py and the allow lists of
#                the native comparison (bench/allow/api.txt, torture.txt,
#                mm.txt), state /root/kds_cmp.json (learned for this build)
# BENCH: wis fxmark leveldb metis psearchy apache (default: all, in this
# order). WORKERS overrides the grid (default 1-8, then every fourth to
# 64); QUICK=1 runs 1 and 64 workers with short durations, as a check.
#
# Methods (README.md of this directory):
#   wis       TCLock's will-it-scale copy, threads, -n 32 (cores per
#             socket), 10 s per point; lock1 mmap1 (TCLock's set), mmap2
#             brk1 page_fault1 page_fault2 page_fault3; /tmp on tmpfs
#   fxmark    MWRM and MRDM on tmpfs, 30 s (TCLock's run-fxmark.py set)
#   leveldb   TCLock's leveldb-1.20: fillseq with 1 thread into a tmpfs
#             database, then readrandom with N pinned threads for 30 s
#   metis     wrmem -p N, default input, under taskset 0..N-1 (TCLock's
#             vbench model "default"); wall time
#   psearchy  pedsort -t /tmp/db/db -c N -m 128 -l 200000 over the files of
#             a kernel source tree in the page cache, index on tmpfs
#             (TCLock's vbench psearchy, mode thread)
#   apache    httpd 2.4.62 mpm_event, 64 KiB static page, wrk -t64 -c100
#             -d10s (IntervalVM, SOSP'25): one server process with N
#             threads, and the default configuration once per pass
# One line per point is appended to /root/appgrid/runs.txt:
#   TAG MODE BENCH VARIANT N VALUE UNIT [extra] | kd counters before | after
MODE=${1:?mode}; TAG=${2:?tag}; shift 2
BENCHES=${*:-wis fxmark leveldb metis psearchy apache}
O=/root/appgrid; mkdir -p $O
OUT=$O/runs.txt
A=/root/appbench
AL=/root/host_fs/kdlock/bench/allow
ST=/root/kds_cmp.json
WORKERS=${WORKERS:-"1 2 3 4 5 6 7 8 $(seq -s ' ' 12 4 64)"}
WIS_S=10; FX_S=30; LDB_MS=30000; WRK_D=10s
if [ "${QUICK:-0}" = 1 ]; then
	WORKERS="1 64"; WIS_S=2; FX_S=3; LDB_MS=3000; WRK_D=3s
fi
ulimit -n 65536
# Added after g1 off/on (README): no core files, so a crashing benchmark
# process cannot block on a core dump pipe (an httpd worker did so at the
# shutdown after g1 on), and every fatal signal is logged and counted.
ulimit -c 0
sysctl -q kernel.print-fatal-signals=1
fatal() { dmesg | grep -cE "potentially unexpected fatal signal|segfault at|trap invalid opcode"; }
C="delegated handback hb_frontier hb_miss offered plain sessions"
st() {
	[ -r /sys/kernel/debug/kdlock_stats ] || { echo -n "- "; return; }
	local k
	for k in $C; do awk -v k=$k '$1 == k {printf "%s ", $2}' /sys/kernel/debug/kdlock_stats; done
}
complaints() { dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall"; }
line() { echo "$TAG $MODE $*" >> $OUT; }

d_on() {
	ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
	cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/allow_cmp.txt
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $ST \
		--allow /root/allow_cmp.txt -v >> $O/kdd-$TAG.log 2>&1 < /dev/null &
	 echo $! > /root/kdd_app.pid)
	sleep 10
}
d_off() {
	local P=$(cat /root/kdd_app.pid) i
	kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
	kill -0 $P 2>/dev/null && { echo "daemon $P did not stop"; exit 1; }
}

b_wis() {
	local t n s0 r m=0
	# TCLock runs it with /tmp on tmpfs; unmount only what was mounted here.
	mountpoint -q /tmp || { mount -t tmpfs -o size=10G tmpfs /tmp && m=1; }
	cd $A/tclocks/will-it-scale
	for t in lock1 mmap1 mmap2 brk1 page_fault1 page_fault2 page_fault3; do
		for n in $WORKERS; do
			s0=$(st)
			r=$(timeout 120 setarch linux64 -R ./build/${t}_threads -t $n -s $WIS_S -n 32 2>&1 | grep "^average:" | cut -d: -f2)
			line "wis $t $n ${r:-0} ops/s | $s0| $(st)"
		done
	done
	cd /; [ $m = 1 ] && umount /tmp
}

b_fxmark() {
	local t n s0 r M=/root/fxm
	mkdir -p $M
	for t in MWRM MRDM; do
		for n in $WORKERS; do
			mount -t tmpfs -o mode=0777,size=16G tmpfs $M
			s0=$(st)
			r=$(cd $A/tclocks/fxmark && timeout 300 ./bin/fxmark --type $t --ncore $n --nbg 0 \
				--duration $FX_S --directio 0 --root $M 2>&1 | awk 'NF == 4 && $1 ~ /^[0-9]+$/ {print $4}' | tail -1)
			line "fxmark $t $n ${r:-0} works/s | $s0| $(st)"
			umount $M
		done
	done
}

b_leveldb() {
	local n s0 r d D=/root/ldb B=$A/tclocks/leveldb-1.20/out-static/db_bench
	mkdir -p $D
	for n in $WORKERS; do
		mount -t tmpfs -o size=10G tmpfs $D
		$B --db=$D --benchmarks=fillseq --threads=1 > /dev/null 2>&1
		s0=$(st)
		r=$(taskset -c 0-$((n - 1)) $B --pin_threads=1 --benchmarks=readrandom --use_existing_db=1 \
			--db=$D --threads=$n --time_ms=$LDB_MS 2>&1 | grep "^readrandom")
		# "readrandom : X micros/op; (DONE) ...": DONE operations in LDB_MS
		d=$(echo "$r" | sed -n 's/.*micros\/op; (\([0-9]*\)).*/\1/p')
		line "leveldb readrandom $n $(( ${d:-0} * 1000 / LDB_MS )) ops/s $(echo "$r" | awk '{print $3}')us/op | $s0| $(st)"
		umount $D
	done
}

b_metis() {
	local n s0 t0 t1 ok
	cd $A/ivm/metis
	for n in $WORKERS; do
		s0=$(st); t0=$(date +%s.%N)
		timeout 1200 taskset -c 0-$((n - 1)) ./obj/app/wrmem -p $n > /tmp/metis.out 2>&1; ok=$?
		t1=$(date +%s.%N)
		line "metis wrmem $n $(echo "$t1 - $t0" | bc) s exit=$ok | $s0| $(st)"
	done
	cd /
}

b_psearchy() {
	local n i s0 r P=$A/ivm/psearchy
	[ -s $A/text-files.txt ] || { echo "no psearchy input"; return 1; }
	$P/prefetch -r $A/text > /dev/null 2>&1
	for n in $WORKERS; do
		mkdir -p /tmp/db && mount -t tmpfs none /tmp/db
		for i in $(seq 0 $n); do mkdir /tmp/db/db$i; done
		s0=$(st)
		r=$(timeout 1200 taskset -c 0-$((n - 1)) $P/mkdb/pedsort -t /tmp/db/db -c $n -m 128 -l 200000 \
			< $A/text-files.txt 2>&1 | sed -n 's/.*throughput: *\([0-9.]*\).*/\1/p' | tail -1)
		# pedsort reports jobs/hour per core
		line "psearchy pedsort $n $(echo "${r:-0} * $n" | bc) jobs/hour ${r:-0}/core | $s0| $(st)"
		umount /tmp/db; rmdir /tmp/db
	done
}

ap_run() {	# ap_run MPMCONF [THREADS]: start httpd, wrk, stop; prints req/s
	local H=/usr/local/apache2 I=$A/ivm/apache
	cp $I/index_64KB.html $H/htdocs/index.html
	cp $I/httpd.conf $H/conf/httpd.conf
	cp $I/$1 $H/conf/extra/httpd-mpm.conf
	[ -n "$2" ] && python3 $I/edit_mpm.py $2 64 > /dev/null
	$H/bin/apachectl -k stop > /dev/null 2>&1; sleep 1
	$H/bin/apachectl -k start || return 1
	sleep 2
	$A/wrk/wrk -t64 -c100 -d$WRK_D http://localhost/ 2>&1 | sed -n 's/^Requests\/sec: *//p' | tail -1
	$H/bin/apachectl -k stop > /dev/null 2>&1
	# Wait until every httpd has left; record it when one had to be killed.
	local i
	for i in $(seq 30); do pgrep -x httpd > /dev/null || break; sleep 1; done
	if pgrep -x httpd > /dev/null; then
		echo "$TAG $MODE apache: httpd left after stop, killed: $(pgrep -x httpd | tr '\n' ' ')" >> $O/complaints.txt
		pkill -9 -x httpd; sleep 1
	fi
}
b_apache() {
	local n s0 r
	for n in $WORKERS; do
		s0=$(st); r=$(ap_run httpd-mpm-single-process.conf $n)
		line "apache single $n ${r:-0} req/s | $s0| $(st)"
	done
	s0=$(st); r=$(ap_run httpd-mpm-default.conf)
	line "apache default 0 ${r:-0} req/s | $s0| $(st)"
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
echo APPGRID_DONE
