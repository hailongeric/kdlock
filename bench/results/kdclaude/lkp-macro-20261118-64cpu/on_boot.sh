#!/bin/bash
# on_boot.sh TAG: a kdall boot of the lkp screening with delegation
# (README 4.4): kd_vdown=0 (an mmap-lock leak with delegated munmap and
# kd_vdown=1 is open, found in the appgrid round), then a learning pass at
# 64 workers (5 s per point, tag learn-TAG, not counted) and the screening
# pass with delegation at 16 and 64 workers. Daemon state /root/kds_lkp.json.
TAG=${1:?tag}
S=/root/host_fs/kdlock-lkp/bench/results/kdclaude/lkp-macro-20261118-64cpu/screen.sh
echo 0 > /sys/module/kernel/parameters/kd_vdown || exit 1
echo "kd_vdown $(cat /sys/module/kernel/parameters/kd_vdown)" > /root/lkpres/$TAG-on.knobs
NS=64 DUR=5 bash $S on learn-$TAG > /root/lkpres/learn-$TAG.out 2>&1
bash $S on $TAG > /root/lkpres/$TAG-on.out 2>&1
echo "ON_BOOT_DONE $(date +%T)" >> /root/lkpres/progress.txt
