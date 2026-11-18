#!/bin/bash
# ltkp.sh TAG [W]: locktorture mutex_lock with W writers (default 64), no
# daemon; kprobe hit counts from /root/kdkp/kd_kpcount.ko over a 5 s window
# (PROBES from the environment: "name:symbol+offset ..."), plus the writes.
# Output: /root/ltw/TAG-kp.txt
TAG=${1:?tag}; W=${2:-64}; O=/root/ltw; mkdir -p $O; exec > $O/$TAG-kp.txt 2>&1
uname -rv
echo "writers $W probes: $PROBES"
modprobe locktorture torture_type=mutex_lock nwriters_stress=$W stat_interval=0
sleep 4
echo "ltkp: $TAG" > /dev/kmsg
insmod /root/kdkp/kd_kpcount.ko probes=$(echo $PROBES | tr ' ' ',') || { rmmod locktorture; exit 1; }
s0=$(date +%s.%N); sleep 5; rmmod kd_kpcount; s1=$(date +%s.%N)
rmmod locktorture
dmesg | grep "Writes:" | tail -1 | sed 's/.*Writes:/Writes:/; s/acq_writer.*//'
echo "-- hits per second"
dmesg | awk -v m="ltkp: $TAG" 'index($0,m){f=1} f' | grep "kd_kpcount: hits" | \
	awk -v t=$(echo "$s1 - $s0" | bc) '{printf "  %-12s %10.0f /s  missed %s\n", $4, $5 / t, $7}'
echo KP_DONE
