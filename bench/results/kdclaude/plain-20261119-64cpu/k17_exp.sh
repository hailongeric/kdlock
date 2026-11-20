#!/bin/bash
# kdall17: correctness, then a reduced grid off / learn / on, LevelDB (IntervalVM configuration, saved database),
# and the mm allow list without munmap.
D=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
V=/root/host_fs/kdlock/bench/results/kdclaude/plain-20261119-64cpu
O=/root/plainprof; AL=/root/host_fs/kdlock/bench/allow
rm -rf /root/kdb && mkdir /root/kdb
rsync -a --exclude="*.o" --exclude=".*" /root/host_fs/kdlock/bench /root/host_fs/kdlock/include /root/kdb/
make -C /lib/modules/$(uname -r)/build M=/root/kdb/bench modules > /root/kdb/make.log 2>&1 || echo "bench build failed" >> $O/progress.txt
sync; insmod /root/kdb/bench/kd_bench.ko
ERA=0 bash /root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu/kdall_check.sh k17
rmmod kd_bench
echo "K17_CHECK_DONE $(date +%T)" >> $O/progress.txt
export LDB_VARIANTS=ivm
WORKERS="4 16 32 48 60" bash $D/app_grid.sh off k17 wis apache > /root/appgrid/k17-off.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh off i5 leveldb > $O/i5-off.out 2>&1
echo "K17_OFF_DONE $(date +%T)" >> $O/progress.txt
for p in 1 2; do WORKERS="8 32 60" bash $D/app_grid.sh on k17-learn$p wis apache > /root/appgrid/k17-learn$p.out 2>&1; done
WORKERS="8 32" bash $V/ivm_apps.sh on i5-learn leveldb > $O/i5-learn.out 2>&1
WORKERS="4 16 32 48 60" bash $D/app_grid.sh on k17 wis apache > /root/appgrid/k17-on.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh on i5 leveldb > $O/i5-on.out 2>&1
cat /sys/kernel/debug/kdlock_stats > $O/k17-on-stats.txt
echo "K17_ON_DONE $(date +%T)" >> $O/progress.txt
# The mm allow list without munmap: brk and mmap delegated, munmap plain.
python3 $D/drop_sites.py /root/kds_cmp.json > $O/k17-drop.txt 2>&1
{ cat $AL/api.txt $AL/torture.txt; grep -v "__vm_munmap" $AL/mm.txt; } > /root/allow_nomunmap.txt
rm -f /root/kds_nomunmap.json
export KD_ALLOW=/root/allow_nomunmap.txt KD_STATE=/root/kds_nomunmap.json
WORKERS="8 32" bash $V/ivm_apps.sh on i5nm-learn leveldb > $O/i5nm-learn.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh on i5nm leveldb > $O/i5nm-on.out 2>&1
(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $KD_STATE --allow $KD_ALLOW -v > $O/kdd-k17nm.log 2>&1 < /dev/null & echo $! > /root/kdd_nm.pid)
sleep 10
WORKERS="8 32 60" bash $D/app_grid.sh off k17nm-learn wis apache > /root/appgrid/k17nm-learn.out 2>&1
WORKERS="4 16 32 48 60" bash $D/app_grid.sh off k17nm wis apache > /root/appgrid/k17nm.out 2>&1
kill -INT $(cat /root/kdd_nm.pid); sleep 5
python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock > $O/k17-pcpu.txt
echo "K17_EXP_DONE $(date +%T)" >> $O/progress.txt
