#!/bin/bash
# Era pressure threshold with sampled measurements: mmap1, brk1 and fio on one file, without the daemon.
P=/sys/module/kernel/parameters; W=/root/appbench/tclocks/will-it-scale; B=/root/lkpbench; d=/root/lkpfs
g() { awk -v k=" era_gate era_start parked " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
fio1() { mkdir -p $d; mountpoint -q $d && umount $d; mount -t tmpfs -o size=8G tmpfs $d
	timeout 60 $B/fio/fio --name=j --directory=$d --filename=$d/shared --rw=randwrite --bs=4k --size=64M --numjobs=$1 --time_based --runtime=6 --group_reporting --ioengine=psync --output-format=terse 2>/dev/null | awk -F';' '{print $8 + $49}' | tail -1
	cd /; umount $d; }
for r in 1 2; do for v in "16 225" "16 190" "1 225"; do
	set -- $v; echo $1 > $P/kd_rw_era_sample; echo $2 > $P/kd_rw_era_press
	for t in mmap1 brk1; do for n in 16 32 48 60; do
		a=$(g); x=$(cd $W && timeout 60 setarch linux64 -R ./build/${t}_threads -t $n -s 6 -n 32 2>&1 | grep "^average:" | cut -d: -f2)
		echo "r$r sample $1 press $2 $t $n ${x:-0} | $a| $(g)"
	done; done
	for n in 16 64; do echo "r$r sample $1 press $2 fio $n $(fio1 $n)"; done
done; done
echo 16 > $P/kd_rw_era_sample; echo 225 > $P/kd_rw_era_press
echo ERA_PRESS_DONE
