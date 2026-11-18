#!/bin/bash
# kdall10 boot (after the c series): bench module, then the correctness
# checks (kdall_check.sh without the era step).
exec > /root/kd10.out 2>&1
D=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
uname -rv
rm -rf /root/kdb10 && mkdir -p /root/kdb10 && cp -r /root/host_fs/kdlock/bench /root/host_fs/kdlock/include /root/kdb10/ || exit 1
(cd /root/kdb10/bench && make -C /mnt/kdlock-builds/kda/out3 M=$PWD modules > /root/kdb10/make.log 2>&1) || { echo "bench module build failed"; exit 1; }
sync
lsmod | grep -q "^kd_bench" && rmmod kd_bench
insmod /root/kdb10/bench/kd_bench.ko || { echo "insmod failed"; exit 1; }
ls /dev/kdbench || exit 1
echo "== kdall_check $(date +%T)"
ERA=0 bash $D/kdall_check.sh kdall10; tail -12 /root/kdc6/kdall10.out
echo "== cldemote $(date +%T)"
bash $D/cldemote_ab.sh kdall10; cat /root/prof/kdall10-cldemote.txt
echo "KD10_DONE $(date +%T)"
