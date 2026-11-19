#!/bin/bash
# nano_grid.sh TAG: on a kdnat kernel (native locks, kdlock built in), the
# nano grid with cachelines 1 and 8 of every family (run_grid.py
# --profiles appgrid, 12 profiles), workers 1-8 then every fourth to 64:
#   1. kd without the daemon (plain mode), 2 rounds;
#   2. with the daemon for the bench module only (bench/allow/kd_bench.txt),
#      after a warm-up pass: native, kd and TCLock, 2 rounds, as round 12.
# Builds the four TCLock modules (TCLOCK_NUMA=1) and the bench module with
# KDB_TCLOCK=1 against this kernel first. TCLock runs one worker per CPU
# at most, which the grid never exceeds.
# WORKERS and ROUNDS override the worker counts and the rounds (g2 of
# appgrid-20261119-64cpu ran 14 worker counts, 1 round).
# Output: /root/appgrid/TAG-nano-plain.jsonl, TAG-nano.jsonl, TAG-nano.log
TAG=${1:?tag}
WORKERS=${WORKERS:-"1 2 3 4 5 6 7 8 $(seq -s ' ' 12 4 64)"}
ROUNDS=${ROUNDS:-2}
O=/root/appgrid; mkdir -p $O; exec > $O/$TAG-nano.log 2>&1
K=/lib/modules/$(uname -r)/build
S=/root/host_fs/kdlock
uname -rv
echo "workers: $WORKERS; rounds: $ROUNDS"
set -e
for f in spin mutex rwlock rwsem; do
	rm -rf /root/tc/$f; mkdir -p /root/tc/$f
	rsync -a --exclude="*.o" --exclude=".*" $S/tclock_backend/ /root/tc/$f/
	case $f in spin) o="";; mutex) o="TCLOCK_MUTEX=1";; rwlock) o="TCLOCK_RWLOCK=1";; rwsem) o="TCLOCK_RWSEM=1";; esac
	make -C $K M=/root/tc/$f $o TCLOCK_NUMA=1 modules > /root/tc/$f.log 2>&1 || { echo "tclock $f build failed"; exit 1; }
done
rm -rf /root/kdbt && mkdir /root/kdbt && rsync -a --exclude="*.o" --exclude=".*" $S/bench $S/include /root/kdbt/
make -C $K M=/root/kdbt/bench KDB_TCLOCK=1 TCLOCK_DIR=$S/tclock_backend \
	KBUILD_EXTRA_SYMBOLS="/root/tc/spin/Module.symvers /root/tc/mutex/Module.symvers /root/tc/rwlock/Module.symvers /root/tc/rwsem/Module.symvers" \
	modules > /root/kdbt/make.log 2>&1 || { echo "bench build failed"; exit 1; }
set +e
sync
lsmod | grep -q "^kd_bench" && rmmod kd_bench
for f in spin/tclock_backend_km mutex/tclock_mutex_backend_km \
	 rwlock/tclock_rwlock_backend_km rwsem/tclock_rwsem_backend_km; do
	insmod /root/tc/$f.ko || { echo "insmod $f failed"; exit 1; }
done
insmod /root/kdbt/bench/kd_bench.ko || { echo "insmod kd_bench failed"; exit 1; }
c0=$(dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall")
cd $S/bench
echo "== plain $(date +%T)"
python3 run_grid.py --out $O/$TAG-nano-plain.jsonl --profiles appgrid --backends kd \
	--workers $WORKERS --rounds $ROUNDS --ms 1000 --commit "$(uname -r)-plain" > $O/$TAG-nano-plain.out 2>&1; echo "plain exit $?"
(cd $S/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state "" \
	--allow $S/bench/allow/kd_bench.txt -v > $O/$TAG-nano.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_nano.pid)
sleep 5
echo "== warm-up $(date +%T)"
python3 run_grid.py --out $O/$TAG-nano-warm.jsonl --profiles appgrid --backends kd \
	--workers 8 32 64 --rounds 1 --ms 500 --commit warm > /dev/null 2>&1
echo "== delegated, native kd tclock $(date +%T)"
python3 run_grid.py --out $O/$TAG-nano.jsonl --profiles appgrid --backends native kd tclock \
	--workers $WORKERS --rounds $ROUNDS --ms 1000 --commit "$(uname -r)" > $O/$TAG-nano.out 2>&1; echo "grid exit $?"
P=$(cat /root/kdd_nano.pid); kill -INT $P
for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
echo "complaints $(( $(dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall") - c0 ))"
echo "NANO_DONE $(date +%T)"
