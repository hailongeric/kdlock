#!/bin/bash
# p4_macro.sh kd|native: phase 4 of the reduced round, the macro set at 4,
# 16, 32, 48 and 64 workers, 6 s per point, tag m1.
#   kd      on a kdall kernel, fresh boot: kd off; two learning passes at 32
#           workers with 30 s per point and a new daemon state (the mmap lock
#           sites need about a minute of contended load to be learned); kd on
#   native  on the native twin, fresh boot
# The set: what kd on was ahead with in the screening, the applications at
# parity, and three cases where delegation loses (sysbench threads, epoll
# ctl, pread2 in processes).
S=$(cd "$(dirname "$0")" && pwd)/screen.sh
O=/root/lkpres
G="perfb sysbench filebench fio vms2 fsx wis wisp2 sng vms unixbench wis2 sng2"
export ONLY='^(pbe-ctl|sysbench-threads|filebench-webserver|filebench-varmail|fio-randwrite-shared|vms-lru-file-mmap-read|dbench-ext4|wis-mmap1|wis-brk1|wisp-pread2|sng-shm|vms-small-allocs|ub-execl|wis-open2|wis-fallocate1|sng-fd-abuse)$'
export NS="4 16 32 48 64" DUR=6
if [ "$1" = native ]; then
	bash $S native m1 $G > $O/m1-native.out 2>&1
	echo "P4_NATIVE_DONE $(date +%T)" >> $O/progress.txt
	exit
fi
bash $S off m1 $G > $O/m1-off.out 2>&1
echo "P4_OFF_DONE $(date +%T)" >> $O/progress.txt
rm -f /root/kds_lkp.json
for p in 1 2; do NS=32 DUR=30 bash $S on learn-m1-$p $G > $O/m1-learn$p.out 2>&1; done
echo "P4_LEARN_DONE $(date +%T)" >> $O/progress.txt
bash $S on m1 $G > $O/m1-on.out 2>&1
cat /sys/kernel/debug/kdlock_stats > $O/m1-on-stats.txt
python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock > $O/m1-pcpu.txt
echo "P4_KD_DONE $(date +%T)" >> $O/progress.txt
