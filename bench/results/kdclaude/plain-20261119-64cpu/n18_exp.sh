#!/bin/bash
# kdnat18, the native twin of kdall21: the same reduced grid.
D=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
V=/root/host_fs/kdlock/bench/results/kdclaude/plain-20261119-64cpu
O=/root/plainprof
ulimit -c 0
python3 /root/skey.py virt_spin_lock_key > $O/n18-key.txt
export LDB_VARIANTS=ivm
WORKERS="4 16 32 48 60" bash $D/app_grid.sh native n18 wis apache > /root/appgrid/n18.out 2>&1
WORKERS="4 8 16 32 60" bash $V/ivm_apps.sh native n18 leveldb > $O/n18.out 2>&1
echo "N18_EXP_DONE $(date +%T)" >> $O/progress.txt
