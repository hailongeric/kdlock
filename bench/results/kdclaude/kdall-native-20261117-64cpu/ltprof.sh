#!/bin/bash
# locktorture mutex_lock, 64 writers: flat profile (no call graphs) and
# kd counters. Output /root/ltw/TAG-prof.txt
TAG=${1:?tag}; O=/root/ltw; mkdir -p $O; exec > $O/$TAG-prof.txt 2>&1
uname -rv
st() { [ -r /sys/kernel/debug/kdlock_stats ] && grep -vE "^#" /sys/kernel/debug/kdlock_stats; }
st > /tmp/p0
modprobe locktorture torture_type=mutex_lock nwriters_stress=64 stat_interval=0
sleep 5
perf record -a -F 999 -o /tmp/lt.data -- sleep 5 > /dev/null 2>&1
sleep 3
rmmod locktorture
st > /tmp/p1
dmesg | grep "Writes:" | tail -1 | sed 's/.*Writes:/Writes:/; s/acq_writer.*//'
perf report -i /tmp/lt.data --sort sym --stdio 2>/dev/null | grep -v "^#" | grep . | head -25
echo "-- annotate of the top kd symbol, hottest instructions"
top=$(perf report -i /tmp/lt.data --sort sym --stdio 2>/dev/null | grep -v "^#" | grep -oE "kd_[a-z_]+" | head -1)
[ -n "$top" ] && perf annotate -i /tmp/lt.data --stdio -s $top 2>/dev/null | grep -E "^\s+[0-9]+\.[0-9]+ +:" | sort -rn | head -12
[ -s /tmp/p0 ] && { echo "-- kd counters"; join <(sort /tmp/p0) <(sort /tmp/p1) | awk '$3 != $2 {printf "  %-16s %d\n", $1, $3 - $2}'; }
echo PROF_DONE
