#!/bin/bash
# kdall20 with the daemon: the kept downgrade on (kd_vdown=1, default) and off (0: hand back at the downgrade), in one boot.
D=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
V=/root/host_fs/kdlock/bench/results/kdclaude/plain-20261119-64cpu
P=/sys/module/kernel/parameters; O=/root/plainprof
ulimit -c 0
export LDB_VARIANTS=ivm
rm -f /root/kds_cmp.json
for p in 1 2; do
	WORKERS="8 32 60" bash $D/app_grid.sh on k20-learn$p wis apache > /root/appgrid/k20-learn.out 2>&1
	WORKERS="8 32" bash $V/ivm_apps.sh on k20-learn$p leveldb > $O/k20-learn.out 2>&1
done
echo "K20B_LEARN_DONE $(date +%T)" >> $O/progress.txt
for r in 1 2; do for v in 1 0; do
	echo $v > $P/kd_vdown
	WORKERS="16 32 60" bash $D/app_grid.sh on k20-vd$v-$r apache > /root/appgrid/k20-vd.out 2>&1
	WORKERS="4 8 16 32" bash $V/ivm_apps.sh on k20-vd$v-$r leveldb > $O/k20-vd.out 2>&1
done; done
for v in 1 0; do
	echo $v > $P/kd_vdown
	WORKERS="16 60" bash $D/app_grid.sh on k20-vd$v-w wis > /root/appgrid/k20-vd.out 2>&1
done
echo 1 > $P/kd_vdown
cat /sys/kernel/debug/kdlock_stats > $O/k20b-stats.txt
python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock > $O/k20b-pcpu.txt
echo "K20B_EXP_DONE $(date +%T)" >> $O/progress.txt
