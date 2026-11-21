#!/bin/bash
# kdall22: correctness; without the daemon: fio profile, a reduced application grid, LevelDB (IntervalVM configuration),
# a part of the lkp macro set; then with the daemon: how fast the mmap sites are learned from nothing, the application
# grid, and the macro part (allow lists of the lkp round).
D=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
V=/root/host_fs/kdlock/bench/results/kdclaude/plain-20261119-64cpu
L=/root/host_fs/kdlock/bench/results/kdclaude/lkp-macro-20261119-64cpu
O=/root/plainprof; AL=/root/host_fs/kdlock/bench/allow
ulimit -c 0
rm -rf /root/kdb && mkdir /root/kdb
rsync -a --exclude="*.o" --exclude=".*" /root/host_fs/kdlock/bench /root/host_fs/kdlock/include /root/kdb/
make -C /lib/modules/$(uname -r)/build M=/root/kdb/bench modules > /root/kdb/make.log 2>&1 || echo "bench build failed" >> $O/progress.txt
sync; insmod /root/kdb/bench/kd_bench.ko
ERA=0 bash /root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu/kdall_check.sh k22
rmmod kd_bench
echo "K22_CHECK_DONE $(date +%T)" >> $O/progress.txt
# without the daemon
bash /root/fio_prof.sh k22off
export LDB_VARIANTS=ivm
WORKERS="4 16 32 48 60" bash $D/app_grid.sh off k22 wis apache > /root/appgrid/k22-off.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh off k22 leveldb > $O/k22-off.out 2>&1
M='^(pbe-ctl|fio-randwrite-shared|wis-mmap1|wis-brk1|sng-shm|vms-small-allocs|ub-execl|wis-fallocate1|wis-open2|sysbench-threads|filebench-webserver|dbench-ext4)$'
MG="perfb sysbench filebench fio fsx wis sng vms unixbench wis2"
ONLY="$M" NS="4 16 32 48 64" DUR=6 bash $L/screen.sh off m2 $MG > /root/lkpres/m2-off.out 2>&1
echo "K22_OFF_DONE $(date +%T)" >> $O/progress.txt
# learning from nothing: mmap1 at 16 threads, 6 s runs, counters per run
cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/lkpres/tmp/mm3.allow
bash /root/mm_check3.sh /root/lkpres/tmp/mm3.allow > /root/lkpres/mm-check-k22.txt 2>&1
# application grid with the daemon (its state from nothing as well)
rm -f /root/kds_cmp.json
for p in 1 2; do
	WORKERS="8 32 60" bash $D/app_grid.sh on k22-learn$p wis apache > /root/appgrid/k22-learn$p.out 2>&1
	WORKERS="8 32" bash $V/ivm_apps.sh on k22-learn$p leveldb > $O/k22-learn.out 2>&1
done
WORKERS="4 16 32 48 60" bash $D/app_grid.sh on k22 wis apache > /root/appgrid/k22-on.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh on k22 leveldb > $O/k22-on.out 2>&1
cat /sys/kernel/debug/kdlock_stats > $O/k22-on-stats.txt
python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock > $O/k22-pcpu.txt
echo "K22_GRID_DONE $(date +%T)" >> $O/progress.txt
# the macro part with the lkp allow lists
rm -f /root/kds_lkp.json
for p in 1 2; do ONLY="$M" NS=32 DUR=30 bash $L/screen.sh on learn-m2-$p $MG > /root/lkpres/m2-learn.out 2>&1; done
ONLY="$M" NS="4 16 32 48 64" DUR=6 bash $L/screen.sh on m2 $MG > /root/lkpres/m2-on.out 2>&1
cat /sys/kernel/debug/kdlock_stats > /root/lkpres/m2-on-stats.txt
python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock > /root/lkpres/m2-pcpu.txt
echo "K22_EXP_DONE $(date +%T)" >> $O/progress.txt
