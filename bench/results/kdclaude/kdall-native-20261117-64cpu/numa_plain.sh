#!/bin/bash
# numa_plain.sh OUT: in one boot of kdnat2 (native locks, kdlock built in,
# no daemon, so kd is in plain mode), the bench module's mutex and rwsem
# writer bodies, native against kd with kd_numa_plain at 0, 16 and 64.
# The settings alternate within each of 2 rounds.
OUT=${1:?out.jsonl}
P=/sys/module/kernel/parameters/kd_numa_plain
cd /root/host_fs/kdlock/bench
for r in 1 2; do
	for v in 0 16 64; do
		echo $v > $P
		python3 run_grid.py --out $OUT.$v --profiles mutex_c01 mutex_c16 rwsem_c01_w100 rwsem_c16_w20 \
			--workers 32 48 64 --rounds 1 --ms 2000 --commit numa-plain-kdnat2 > /dev/null 2>&1
	done
done
echo 16 > $P
echo NUMA_DONE
