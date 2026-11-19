#!/bin/bash
# prof.sh MODE TAG [POINT...]: profile single points of the application grid
# while they run, to see where kd without delegation ("off", a kdall kernel
# with no daemon) spends its time against native (a kdnat kernel with real
# queued spinlocks, README section 1). MODE names the kernel's role only:
# native | off | on (with "on" start the daemon yourself first).
#
# POINT is BENCH:VARIANT:WORKERS, as in app_grid.sh of
# ../appgrid-20261118-64cpu: wis:<test>:N, leveldb:readrandom:N,
# psearchy:pedsort:N, metis:wrmem:N, apache:single:N, fxmark:<type>:N.
# Default: the points of README section 2.
#
# Per point, in /root/plainprof/TAG-MODE-BENCH-VARIANT-N.txt:
#   the benchmark's own result, context switches and migrations over 2 s,
#   system calls by number over 3 s (bpftrace, the benchmark's processes),
#   a 5 s profile of all CPUs with call chains (perf record -a -g -F 499):
#   by object, flat by symbol, and the call chains of every symbol above 1.5%.
# One summary line per point is appended to /root/plainprof/points.txt.
MODE=${1:?mode}; TAG=${2:?tag}; shift 2
POINTS=${*:-"wis:page_fault1:8 wis:page_fault1:16 wis:page_fault2:16 wis:page_fault3:16 wis:lock1:8 wis:lock1:32 wis:brk1:2 wis:brk1:8 wis:mmap1:16 wis:mmap1:60 leveldb:readrandom:1 leveldb:readrandom:4 leveldb:readrandom:8 leveldb:readrandom:32 leveldb:readrandom:60 psearchy:pedsort:32 psearchy:pedsort:60 apache:single:60 fxmark:MRDM:56"}
O=/root/plainprof; mkdir -p $O
A=/root/appbench
ulimit -n 65536; ulimit -c 0
st() { [ -r /sys/kernel/debug/kdlock_stats ] && awk '$1 ~ /^(delegated|handback|plain|sessions|era_gate|parked|no_spin|abandon|head_sleep|rd_behind|rd_queue|numa_local)$/ {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }

# start BENCH VARIANT N: run the workload in the background for about 25 s;
# its output goes to $O/tmp/out. Sets COMM (process name) and UNIT.
start() {
	local b=$1 v=$2 n=$3 H=/usr/local/apache2 I=$A/ivm/apache
	case $b in
	wis)	COMM=${v}_threads; UNIT=ops/s
		( cd $A/tclocks/will-it-scale && setarch linux64 -R ./build/${v}_threads -t $n -s 25 -n 32 ) > $O/tmp/out 2>&1 & ;;
	leveldb) COMM=db_bench; UNIT=ops/s
		mkdir -p /root/ldb; mountpoint -q /root/ldb || mount -t tmpfs -o size=10G tmpfs /root/ldb
		$A/tclocks/leveldb-1.20/out-static/db_bench --db=/root/ldb --benchmarks=fillseq --threads=1 > /dev/null 2>&1
		( taskset -c 0-$((n - 1)) $A/tclocks/leveldb-1.20/out-static/db_bench --pin_threads=1 --benchmarks=readrandom \
			--use_existing_db=1 --db=/root/ldb --threads=$n --time_ms=25000 ) > $O/tmp/out 2>&1 & ;;
	psearchy) COMM=pedsort; UNIT=jobs/hour/core
		$A/ivm/psearchy/prefetch -r $A/text > /dev/null 2>&1
		mkdir -p /tmp/db; mountpoint -q /tmp/db || mount -t tmpfs none /tmp/db
		local i; for i in $(seq 0 $n); do mkdir -p /tmp/db/db$i; done
		( taskset -c 0-$((n - 1)) $A/ivm/psearchy/mkdb/pedsort -t /tmp/db/db -c $n -m 128 -l 200000 < $A/text-files.txt ) > $O/tmp/out 2>&1 & ;;
	metis)	COMM=wrmem; UNIT=s
		( cd $A/ivm/metis && taskset -c 0-$((n - 1)) ./obj/app/wrmem -p $n ) > $O/tmp/out 2>&1 & ;;
	apache)	COMM=httpd; UNIT=req/s
		cp $I/index_64KB.html $H/htdocs/index.html; cp $I/httpd.conf $H/conf/httpd.conf
		cp $I/httpd-mpm-single-process.conf $H/conf/extra/httpd-mpm.conf
		python3 $I/edit_mpm.py $n 64 > /dev/null
		$H/bin/apachectl -k stop > /dev/null 2>&1; sleep 1
		$H/bin/apachectl -k start; sleep 2
		( $A/wrk/wrk -t64 -c100 -d25s http://localhost/ ) > $O/tmp/out 2>&1 & ;;
	fxmark)	COMM=fxmark; UNIT=works/s
		mkdir -p /root/fxm; mountpoint -q /root/fxm || mount -t tmpfs -o mode=0777,size=16G tmpfs /root/fxm
		( cd $A/tclocks/fxmark && ./bin/fxmark --type $v --ncore $n --nbg 0 --duration 25 --directio 0 --root /root/fxm ) > $O/tmp/out 2>&1 & ;;
	esac
	WPID=$!
}
finish() {	# finish BENCH: the benchmark's value from its output; clean up
	case $1 in
	wis)	grep "^average:" $O/tmp/out | cut -d: -f2 ;;
	leveldb) grep "^readrandom" $O/tmp/out | sed -n 's/.*micros\/op; (\([0-9]*\)).*/\1/p' | awk '{print $1 / 25}'; umount /root/ldb ;;
	psearchy) sed -n 's/.*throughput: *\([0-9.]*\).*/\1/p' $O/tmp/out | tail -1; umount /tmp/db ;;
	metis)	echo - ;;
	apache)	sed -n 's/^Requests\/sec: *//p' $O/tmp/out | tail -1
		/usr/local/apache2/bin/apachectl -k stop > /dev/null 2>&1; sleep 3; pkill -9 -x httpd 2>/dev/null ;;
	fxmark)	awk 'NF == 4 && $1 ~ /^[0-9]+$/ {print $4}' $O/tmp/out | tail -1; umount /root/fxm ;;
	esac
}

mkdir -p $O/tmp
for p in $POINTS; do
	b=${p%%:*}; r=${p#*:}; v=${r%%:*}; n=${r##*:}
	f=$O/$TAG-$MODE-$b-$v-$n.txt
	s0=$(st)
	start $b $v $n
	# psearchy spends its first seconds reading the file list; fxmark and
	# leveldb populate first.
	case $b in psearchy) sleep 10 ;; fxmark|leveldb) sleep 6 ;; *) sleep 4 ;; esac
	{
	echo "## $TAG $MODE $p $(uname -r) $(date +%T)"
	echo "## context switches, migrations (2 s)"
	perf stat -a -e context-switches,cpu-migrations -- sleep 2 2>&1 | grep -E "context|migr"
	echo "## system calls by number (3 s, comm $COMM)"
	timeout 20 bpftrace -e "tracepoint:raw_syscalls:sys_enter /comm == \"${COMM:0:15}\"/ { @[args->id] = count(); } interval:s:3 { exit(); }" 2>/dev/null | grep "^@" | sort -t: -k2 -n -r | head -12
	perf record -a -g -F 499 -o $O/tmp/p.data -- sleep 5 > /dev/null 2>&1
	echo "## by object"
	perf report -i $O/tmp/p.data --no-children --sort dso --stdio -g none 2>/dev/null | grep -E "^# Samples|^ +[0-9]" | head -8
	echo "## flat by symbol"
	perf report -i $O/tmp/p.data --no-children --sort sym --stdio -g none 2>/dev/null | grep -E "^ +[0-9]" | head -45
	echo "## call chains of symbols above 1.5%"
	perf report -i $O/tmp/p.data --no-children --sort sym --stdio -g caller,0.5,callee,function,percent --max-stack 7 --percent-limit 1.5 2>/dev/null | grep -v "^$" | grep -v "^#" | head -260
	} > $f 2>&1
	wait $WPID
	val=$(finish $b)
	echo "## result: ${val:-0} $UNIT | $s0| $(st)" >> $f
	echo "$TAG $MODE $b $v $n ${val:-0} $UNIT | $s0| $(st)" >> $O/points.txt
done
echo PROF_DONE >> $O/points.txt
echo PROF_DONE
