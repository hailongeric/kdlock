#!/bin/bash
# nano_era.sh: in one boot of a kdall kernel with the bench module loaded,
# the rwsem and rwlock nano bodies (kd backend) at 32, 48 and 64 workers
# with kd_rw_era_ns 200000 (default), 1000000 and 2000000, 2 rounds with
# the order rotated; first without the daemon (plain mode), then with the
# daemon delegating the bench module only (bench/allow/kd_bench.txt).
# Output: /root/mdiag/nera-<mode>.jsonl.<era_ns>
O=/root/mdiag; mkdir -p $O; exec > $O/nera.out 2>&1
P=/sys/module/kernel/parameters/kd_rw_era_ns
orig=$(cat $P)
PROFILES="rwsem_c01_w20 rwsem_c16_w20 rwsem_c16_w1 rwsem_c01_w100 rwlock_c01_w20 rwlock_c16_w20 rwlock_c01_w100"
eras=(200000 1000000 2000000)
cd /root/host_fs/kdlock/bench
sweep() {	# sweep MODE
	for r in 1 2; do
		for i in 0 1 2; do
			e=${eras[$(( (i + r - 1) % 3 ))]}
			echo $e > $P || exit 1
			python3 run_grid.py --out $O/nera-$1.jsonl.$e --profiles $PROFILES --backends kd \
				--workers 32 48 64 --rounds 1 --ms 2000 --commit "$(uname -r)-era$e" > /dev/null 2>&1
		done
	done
}
rm -f $O/nera-*.jsonl.*
sweep plain
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state "" \
	--allow /root/host_fs/kdlock/bench/allow/kd_bench.txt -v > $O/nera.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_nera.pid)
sleep 5
echo $orig > $P
python3 run_grid.py --out $O/nera-warm.jsonl --profiles $PROFILES --backends kd \
	--workers 32 48 64 --rounds 1 --ms 1000 --commit warm > /dev/null 2>&1
sweep deleg
D=$(cat /root/kdd_nera.pid); kill -INT $D
for i in $(seq 60); do kill -0 $D 2>/dev/null || break; sleep 1; done
echo $orig > $P
dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall" | sed 's/^/complaints /'
echo NERA_DONE
