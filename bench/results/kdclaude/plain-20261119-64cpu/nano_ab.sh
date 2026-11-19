#!/bin/bash
# nano_ab.sh TAG PARAM "VALUES" DAEMON "PROFILES" "WORKERS" [ROUNDS]: the nano
# bench (bench/run_grid.py, native and kd side by side, 1 s per point) with
# the kd core parameter PARAM at each of VALUES, alternating, in one boot of
# a kdnat kernel. DAEMON 0: no daemon (kd waits in plain mode); 1: the
# daemon runs for the bench module's sites (bench/allow/kd_bench.txt) after
# a warm-up pass. The setting is in each result line's "commit" field
# (PARAM=VALUE). Builds and loads the bench module if /dev/kdbench is absent.
# Output: /root/plainprof/TAG-nano.jsonl; nano_ab_summary.py prints it.
TAG=${1:?tag}; PARAM=${2:?param}; VALUES=${3:?values}; DAEMON=${4:?0|1}
PROFILES=${5:?profiles}; WORKERS=${6:?workers}; R=${7:-2}
O=/root/plainprof; mkdir -p $O
S=/root/host_fs/kdlock; P=/sys/module/kernel/parameters
exec > $O/$TAG-nano.log 2>&1
uname -rv
[ -w $P/$PARAM ] || { echo "no parameter $PARAM"; exit 1; }
if [ ! -c /dev/kdbench ]; then
	rm -rf /root/kdb && mkdir /root/kdb
	rsync -a --exclude="*.o" --exclude=".*" $S/bench $S/include /root/kdb/
	make -C /lib/modules/$(uname -r)/build M=/root/kdb/bench modules > /root/kdb/make.log 2>&1 || { echo "bench build failed"; exit 1; }
	sync; insmod /root/kdb/bench/kd_bench.ko || { echo "insmod failed"; exit 1; }
fi
V0=$(cat $P/$PARAM)
cd $S/bench
if [ $DAEMON = 1 ]; then
	(cd $S/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state "" \
		--allow $S/bench/allow/kd_bench.txt -v > $O/$TAG-nano.kdd 2>&1 < /dev/null &
	 echo $! > /root/kdd_nanoab.pid)
	sleep 5
	python3 run_grid.py --out $O/$TAG-nano-warm.jsonl --profiles $PROFILES --backends kd \
		--workers 8 32 60 --rounds 1 --ms 500 --commit warm > /dev/null 2>&1
fi
for r in $(seq $R); do
	for v in $VALUES; do
		echo $v > $P/$PARAM
		python3 run_grid.py --out $O/$TAG-nano.jsonl --profiles $PROFILES --backends native kd \
			--workers $WORKERS --rounds 1 --ms 1000 --commit "$PARAM=$v" > /dev/null 2>&1
		echo "round $r $PARAM=$v exit $? $(date +%T)"
	done
done
echo $V0 > $P/$PARAM
if [ $DAEMON = 1 ]; then
	p=$(cat /root/kdd_nanoab.pid); kill -INT $p
	for i in $(seq 60); do kill -0 $p 2>/dev/null || break; sleep 1; done
fi
echo "complaints $(dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall")"
echo NANO_AB_DONE
