#!/bin/bash
# lock1_boot.sh TAG: will-it-scale lock1 (threads) at a few thread counts, 3 rounds, in this boot.
TAG=$1; O=/root/plainprof/lock1-boots.txt
cd /root/appbench/tclocks/will-it-scale || exit 1
b=$(cut -c1-8 /proc/sys/kernel/random/boot_id)
for r in 1 2 3; do for n in 8 16 32 48 60; do
	v=$(timeout 60 setarch linux64 -R ./build/lock1_threads -t $n -s 5 -n 32 2>&1 | grep "^average:" | cut -d: -f2)
	echo "$TAG $(uname -r) $b $r $n $v" >> $O
done; done
echo "LOCK1_BOOT_DONE $TAG" >> /root/plainprof/progress.txt
