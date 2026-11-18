#!/bin/bash
# locktorture mutex_lock and ww_mutex_lock with 64 writers (one per CPU)
# and with the default 128, 30 s, 2 runs each; no daemon. Output /root/ltw/TAG.txt
TAG=${1:?tag}; O=/root/ltw; mkdir -p $O; exec > $O/$TAG.txt 2>&1
uname -rv
for rep in 1 2; do for t in mutex_lock ww_mutex_lock; do for w in 64 128; do
	echo "ltw: $TAG $t $w $rep" > /dev/kmsg
	c0=$(awk '$1 == "ctxt" {print $2}' /proc/stat)
	modprobe locktorture torture_type=$t nwriters_stress=$w stat_interval=0; sleep 30; rmmod locktorture
	c1=$(awk '$1 == "ctxt" {print $2}' /proc/stat)
	echo "$t $w $rep ctxt $((c1 - c0)) $(dmesg | awk -v m="ltw: $TAG $t $w $rep" 'index($0,m){f=1} f' | grep -E "Writes:|End of test" | sed 's/.*Writes:/Writes:/; s/acq_writer.*//; s/.*End of test/End of test/' | tr '\n' ' ')"
done; done; done
dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall" | sed 's/^/complaints /'
echo LTW_DONE
