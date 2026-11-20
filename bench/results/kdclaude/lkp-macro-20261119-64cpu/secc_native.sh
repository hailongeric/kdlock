#!/bin/bash
B=/root/lkpbench/stress-ng/stress-ng
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
for t in 6 6 6 12 12 12 20 20 20; do a=$(dmesg | grep -c "fatal signal 31"); o=$(cd /root/lkpsng && timeout 90 $B --seccomp 64 --timeout $t --verify --metrics --no-rand-seed --temp-path /root/lkpsng 2>&1 | awk '/seccomp +[0-9]/ {print $5}' | head -1); b=$(dmesg | grep -c "fatal signal 31"); echo "$(uname -r) ${t}s bogo ops $o SIGSYS logged: $((b - a))"; done > /root/lkpres/secc-native.txt 2>&1
cd /; umount /root/lkpsng; echo SECC_NATIVE_DONE >> /root/lkpres/secc-native.txt
