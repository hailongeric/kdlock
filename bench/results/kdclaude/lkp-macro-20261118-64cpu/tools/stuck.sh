#!/bin/bash
# stuck.sh: fresh kdall boot; per-CPU obj_stock flags, then wis-unlink1 with
# only path_openat delegated, then the flags again.
S=/root/host_fs/kdlock-lkp/bench/results/kdclaude/lkp-macro-20261118-64cpu/screen.sh
exec > /root/lkpres/stuck.out 2>&1
echo "== before"; python3 /root/pcpu.py obj_stock memcg_stock
echo 0 > /sys/module/kernel/parameters/kd_vdown
ALLOW="lkpA2i" NS=64 DUR=10 ONLY="^wis-unlink1$" bash $S on stuck wis
grep "^stuck on" /root/lkpres/screen.txt
echo "== after"; python3 /root/pcpu.py obj_stock memcg_stock
grep -c "miss code" /root/lkpres/kdd-stuck.log
echo STUCK_DONE
