#!/bin/bash
B=/root/lkpbench/stress-ng/stress-ng
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
for i in $(seq 12); do a=$(dmesg | grep -c "fatal signal 31"); (cd /root/lkpsng && timeout 66 $B --seccomp 64 --timeout 6 --verify --metrics --no-rand-seed --temp-path /root/lkpsng > /dev/null 2>&1); b=$(dmesg | grep -c "fatal signal 31"); echo "off run $i SIGSYS logged: $((b - a)) delegated $(awk '$1=="delegated" {print $2}' /sys/kernel/debug/kdlock_stats)"; done > /root/lkpres/secc-off.txt 2>&1
cd /; umount /root/lkpsng
echo SECC_OFF_DONE >> /root/lkpres/secc-off.txt
