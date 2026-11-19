#!/bin/bash
# Fresh kdall10 boot: kd off check, a delegated pass over the will-it-scale
# and stress-ng groups (as the learning pass), kd off check again.
S=/root/host_fs/kdlock-lkp/bench/results/kdclaude/lkp-macro-20261118-64cpu/screen.sh
exec > /root/lkpres/degrade.out 2>&1
CHK="^(sng-(epoll|msg|dup|eventfd))$"
uname -rv
NS=64 DUR=10 ONLY=$CHK bash $S off dg-before sng
echo 0 > /sys/module/kernel/parameters/kd_vdown
NS=64 DUR=5 bash $S on dg-deleg wis sng
NS=64 DUR=10 ONLY=$CHK bash $S off dg-after sng
grep -E "^dg-(before|after)" /root/lkpres/screen.txt | cut -d"|" -f1
cat /sys/fs/cgroup/cgroup.stat | grep dying
echo DEGRADE_DONE
