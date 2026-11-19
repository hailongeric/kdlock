#!/bin/bash
# bisect.sh TAG ALLOWFILES GROUPS: fresh kdall boot: kd off indicator
# (stress-ng dup, msg), a delegated pass with only the given allow lists
# (from bench/allow, or files under /root/lkpres/bisect/) over GROUPS, and
# the indicator again. Output /root/lkpres/bisect-TAG.out
TAG=$1; ALLOWS=$2; GRPS=$3
S=/root/host_fs/kdlock-lkp/bench/results/kdclaude/lkp-macro-20261118-64cpu/screen.sh
exec > /root/lkpres/bisect-$TAG.out 2>&1
CHK="^(sng-(dup|msg))$"
echo 0 > /sys/module/kernel/parameters/kd_vdown
NS=64 DUR=10 ONLY=$CHK bash $S off bs-$TAG-before sng
ALLOW="$ALLOWS" NS=64 DUR=5 bash $S on bs-$TAG-deleg $GRPS
NS=64 DUR=10 ONLY=$CHK bash $S off bs-$TAG-after sng
grep -E "^bs-$TAG-(before|after)" /root/lkpres/screen.txt | cut -d"|" -f1
echo BISECT_DONE
