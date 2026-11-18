#!/bin/bash
# kdnat9 boot: bench module, then nat_check.sh (native wakeups, mutex nano,
# oversubscription, ww nano), locktorture mutex/ww at 64 and 128 writers
# (ltw.sh), the native wakeup counts with 64 writers, the gain profiles,
# the reader spin nano (rspin_nano.sh) and the page_fault1 lock words.
exec > /root/nat9.out 2>&1
D=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
uname -rv
rm -rf /root/kdbn9 && mkdir -p /root/kdbn9 && cp -r /root/host_fs/kdlock/bench /root/host_fs/kdlock/include /root/kdbn9/ || exit 1
(cd /root/kdbn9/bench && make -C /mnt/kdlock-builds/kda/outnat2 M=$PWD modules > /root/kdbn9/make.log 2>&1) || { echo "bench module build failed"; exit 1; }
sync
insmod /root/kdbn9/bench/kd_bench.ko || { echo "insmod failed"; exit 1; }
ls /dev/kdbench || exit 1
echo "== nat_check $(date +%T)"
bash $D/nat_check.sh kdnat9; tail -2 /root/natc/kdnat9.out
echo "== ltw $(date +%T)"
bash $D/ltw.sh kdnat9; tail -2 /root/ltw/kdnat9.txt
echo "== native wakeups, 64 writers $(date +%T)"
W=64 bash $D/mutex_wake.sh kdnat9-w64-native; cat /root/mwake/kdnat9-w64-native.txt
echo "== gain profiles $(date +%T)"
bash $D/prof_gain.sh kdnat9-gain; tail -1 /root/prof/kdnat9-gain.log
echo "== reader spin nano $(date +%T)"
bash $D/rspin_nano.sh kdnat9
echo "== page_fault1 lock words $(date +%T)"
bash $D/pf1_regs.sh kdnat9 16; tail -22 /root/prof/kdnat9-pf1regs.txt
echo "NAT9_DONE $(date +%T)"
