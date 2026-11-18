#!/bin/bash
# Fairness and rate at asymmetric placements, era bound 200 us / 1 ms / 2 ms,
# kd backend: plain (no daemon), then delegated (bench module only).
O=/root/mdiag; exec > $O/place_era.out 2>&1
cd /root/host_fs/kdlock/bench
CFG="kd_rw_era_ns=200000 kd_rw_era_ns=1000000 kd_rw_era_ns=2000000"
rm -f $O/place-plain.jsonl $O/place-deleg.jsonl
python3 run_place.py --out $O/place-plain.jsonl --profiles rwsem:1:20 rwsem:16:20 rwlock:1:20 \
	--workers 32 --firsts 16 8 4 1 --backends kd --configs $CFG --rounds 2 || echo "plain failed"
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state "" \
	--allow /root/host_fs/kdlock/bench/allow/kd_bench.txt -v > $O/place.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_place.pid)
sleep 5
python3 run_place.py --out $O/place-warm.jsonl --profiles rwsem:1:20 rwsem:16:20 rwlock:1:20 \
	--workers 32 --firsts 16 --backends kd --rounds 1 > /dev/null 2>&1
python3 run_place.py --out $O/place-deleg.jsonl --profiles rwsem:1:20 rwsem:16:20 rwlock:1:20 \
	--workers 32 --firsts 16 8 4 1 --backends kd --configs $CFG --rounds 2 || echo "deleg failed"
D=$(cat /root/kdd_place.pid); kill -INT $D
for i in $(seq 60); do kill -0 $D 2>/dev/null || break; sleep 1; done
cat /sys/module/kernel/parameters/kd_rw_era_ns
dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall" | sed 's/^/complaints /'
echo PLACE_DONE
