#!/bin/bash
# nat_check.sh TAG: on a kdnat kernel (native locks, kdlock built in, no
# daemon), in one boot:
#   1. locktorture mutex_lock with the wakeup counts (mutex_wake.sh) for
#      the native mutex;
#   2. the mutex nano bodies, native against kd (plain mode), 32/48/64
#      workers, 2 rounds;
#   3. more workers than CPUs: mutex and ww bodies on 32 CPUs, 1 and 2
#      workers per CPU, from CPU 0 (one node) and from CPU 16 (both);
#   4. the ww body at 32 and 64 workers, native against kd.
# The bench module must be built and loaded. Output: /root/natc/TAG-*
TAG=${1:?tag}
O=/root/natc; mkdir -p $O; exec > $O/$TAG.out 2>&1
D=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
uname -rv
bash $D/mutex_wake.sh $TAG-native && cat /root/mwake/$TAG-native.txt
cd /root/host_fs/kdlock/bench
python3 run_grid.py --out $O/$TAG-grid.jsonl --profiles mutex_c01 mutex_c16 \
	--workers 32 48 64 --rounds 2 --ms 2000 --commit "$(uname -r)" > /dev/null 2>&1
for first in 0 16; do
	python3 run_oversub.py --out $O/$TAG-oversub.jsonl --profiles mutex:1:100 mutex:16:100 ww:2:100 \
		--cpus 32 --factors 1 2 --first-cpu $first --rounds 2 --tag first$first > /dev/null 2>&1
done
for w in 32 64; do for b in native kd; do
	python3 run_nano.py --family ww --lines 2 --backend $b --workers $w --ms 2000 --repeat 2 \
		> $O/$TAG-ww-$b-$w.json 2>/dev/null
done; done
dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall" | sed 's/^/complaints /'
echo NATC_DONE
