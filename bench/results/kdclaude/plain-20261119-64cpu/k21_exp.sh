#!/bin/bash
# kdall21: correctness, then a reduced grid off / learn / on, LevelDB (IntervalVM configuration, saved database).
D=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
V=/root/host_fs/kdlock/bench/results/kdclaude/plain-20261119-64cpu
O=/root/plainprof
ulimit -c 0
rm -rf /root/kdb && mkdir /root/kdb
rsync -a --exclude="*.o" --exclude=".*" /root/host_fs/kdlock/bench /root/host_fs/kdlock/include /root/kdb/
make -C /lib/modules/$(uname -r)/build M=/root/kdb/bench modules > /root/kdb/make.log 2>&1 || echo "bench build failed" >> $O/progress.txt
sync; insmod /root/kdb/bench/kd_bench.ko
ERA=0 bash /root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu/kdall_check.sh k21
rmmod kd_bench
echo "K21_CHECK_DONE $(date +%T)" >> $O/progress.txt
export LDB_VARIANTS=ivm
rm -f /root/kds_cmp.json
WORKERS="4 16 32 48 60" bash $D/app_grid.sh off k21 wis apache > /root/appgrid/k21-off.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh off k21 leveldb > $O/k21-off.out 2>&1
echo "K21_OFF_DONE $(date +%T)" >> $O/progress.txt
for p in 1 2; do
	WORKERS="8 32 60" bash $D/app_grid.sh on k21-learn$p wis apache > /root/appgrid/k21-learn$p.out 2>&1
	WORKERS="8 32" bash $V/ivm_apps.sh on k21-learn$p leveldb > $O/k21-learn.out 2>&1
done
WORKERS="4 16 32 48 60" bash $D/app_grid.sh on k21 wis apache > /root/appgrid/k21-on.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh on k21 leveldb > $O/k21-on.out 2>&1
# The munmap site right after a workload that switches it off.
WORKERS="16 60" bash $D/app_grid.sh on k21-after wis > /root/appgrid/k21-after.out 2>&1
cat /sys/kernel/debug/kdlock_stats > $O/k21-on-stats.txt
python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock > $O/k21-pcpu.txt
echo "K21_EXP_DONE $(date +%T)" >> $O/progress.txt
