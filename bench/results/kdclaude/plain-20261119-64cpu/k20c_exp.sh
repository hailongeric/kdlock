#!/bin/bash
# kdall20: lock1 again (two more sets of three rounds), then the correctness checks.
O=/root/plainprof
bash /root/lock1_boot.sh k20-b
bash /root/lock1_boot.sh k20-c
rm -rf /root/kdb && mkdir /root/kdb
rsync -a --exclude="*.o" --exclude=".*" /root/host_fs/kdlock/bench /root/host_fs/kdlock/include /root/kdb/
make -C /lib/modules/$(uname -r)/build M=/root/kdb/bench modules > /root/kdb/make.log 2>&1 || echo "bench build failed" >> $O/progress.txt
sync; insmod /root/kdb/bench/kd_bench.ko
ERA=0 bash /root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu/kdall_check.sh k20
rmmod kd_bench
echo "K20C_DONE $(date +%T)" >> $O/progress.txt
