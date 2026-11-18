#!/bin/bash
# cldemote_ab.sh TAG: on a kdall kernel without the daemon, api setfd and
# ofd at 64 threads (spinlocks in plain mode) with kd_cldemote at its
# default and at 0, 3 rounds alternating. Is CLDEMOTE of the queued
# waiter's lines what makes kd's contended spinlock hand over faster than
# native's (section 8.2)? Output: /root/prof/TAG-cldemote.txt
TAG=${1:?tag}
O=/root/prof; mkdir -p $O; exec > $O/$TAG-cldemote.txt 2>&1
P=/sys/module/kernel/parameters/kd_cldemote
d0=$(cat $P)
uname -rv; echo "default kd_cldemote $d0"
ulimit -n 65536
for r in 1 2 3; do
	if [ $((r % 2)) = 1 ]; then order="$d0 0"; else order="0 $d0"; fi
	for c in $order; do
		echo $c > $P
		for x in setfd ofd; do
			echo "cldemote=$c $x 64 round $r $(/root/api_stress $x 64 5 | tail -1)"
		done
	done
done
echo $d0 > $P
echo CLDEMOTE_DONE
