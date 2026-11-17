#!/bin/bash
# nano_check.sh OUT: in one boot of a kdnat kernel (native locks, kdlock
# built in, no daemon, so kd runs in plain mode for mutex and delegation is
# off), the bench module's mutex, rwsem and rwlock bodies, native against
# kd, 2 rounds. Then the writer-only bodies once more with kd_rw_era_ns=0,
# the reference for the measurement moved off the handover path.
OUT=${1:?out.jsonl}
D=/sys/module/kernel/parameters
cd /root/host_fs/kdlock/bench
python3 run_grid.py --out $OUT --profiles mutex_c01 mutex_c16 rwsem_c01_w100 rwsem_c01_w20 \
	rwsem_c16_w20 rwsem_c16_w1 rwlock_c01_w100 rwlock_c01_w20 rwlock_c16_w20 \
	--workers 32 48 64 --rounds 2 --ms 2000 --commit "$(uname -r)" > /dev/null 2>&1
era=$(cat $D/kd_rw_era_ns)
echo 0 > $D/kd_rw_era_ns
python3 run_grid.py --out $OUT.era0 --profiles rwsem_c01_w100 rwlock_c01_w100 \
	--workers 32 48 64 --rounds 2 --ms 2000 --commit "$(uname -r)-era0" > /dev/null 2>&1
echo $era > $D/kd_rw_era_ns
echo NANO_DONE
