#!/bin/bash
# kdall9 boot: bench module, then woken_ab.sh, rstall_ab.sh and the
# correctness checks (kdall_check.sh without the era step), in sequence.
exec > /root/kd9.out 2>&1
D=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
uname -rv
rm -rf /root/kdb9 && mkdir -p /root/kdb9 && cp -r /root/host_fs/kdlock/bench /root/host_fs/kdlock/include /root/kdb9/ || exit 1
(cd /root/kdb9/bench && make -C /mnt/kdlock-builds/kda/out3 M=$PWD modules > /root/kdb9/make.log 2>&1) || { echo "bench module build failed"; exit 1; }
sync
insmod /root/kdb9/bench/kd_bench.ko || { echo "insmod failed"; exit 1; }
ls /dev/kdbench || exit 1
(cd /root/kdaddrs && make -C /lib/modules/$(uname -r)/build M=/root/kdaddrs modules > /dev/null 2>&1)
(cd /root/kdkp && make -C /lib/modules/$(uname -r)/build M=/root/kdkp modules > /dev/null 2>&1)
sync
echo "== woken_ab $(date +%T)"
bash $D/woken_ab.sh kdall9; tail -2 /root/woken/kdall9.txt
echo "== rstall_ab $(date +%T)"
bash $D/rstall_ab.sh kdall9; tail -2 /root/rstall/kdall9.txt
echo "== kdall_check $(date +%T)"
ERA=0 bash $D/kdall_check.sh kdall9; tail -3 /root/kdc6/kdall9.out
echo "KD9_DONE $(date +%T)"
