#!/bin/bash
# fio_prof.sh TAG: fio, random 4 KiB writes of N jobs to one tmpfs file (the inode rwsem, writers only):
# rate, CPUs used, sleeps, and the profile, at 16 and 64 jobs.
TAG=$1; O=/root/plainprof; B=/root/lkpbench; d=/root/lkpfs
mkdir -p $O/tmp
for n in 4 16 64; do
	mkdir -p $d; mountpoint -q $d && umount $d; mount -t tmpfs -o size=8G tmpfs $d
	f=$O/$TAG-fio-$n.txt
	( timeout 120 $B/fio/fio --name=j --directory=$d --filename=$d/shared --rw=randwrite --bs=4k --size=64M --numjobs=$n \
		--time_based --runtime=14 --group_reporting --ioengine=psync --output-format=terse 2>/dev/null | awk -F';' '{print $8 + $49}' | tail -1 > $O/tmp/fio.out ) &
	sleep 4
	{
	echo "## $TAG fio randwrite shared $n $(uname -r)"
	perf stat -a -e context-switches,cpu-migrations,cycles,instructions -- sleep 3 2>&1 | grep -E "context|migr|cycles|instr"
	echo "## run queue: $(awk '/^procs_running/ {print $2}' /proc/stat) running"
	perf record -a -g -F 499 -o $O/tmp/fio.data -- sleep 4 > /dev/null 2>&1
	echo "## by comm"; perf report -i $O/tmp/fio.data --no-children --sort comm --stdio -g none 2>/dev/null | grep -E "^ +[0-9]" | head -4
	echo "## flat by symbol"; perf report -i $O/tmp/fio.data --no-children --sort sym --stdio -g none 2>/dev/null | grep -E "^ +[0-9]" | head -22
	echo "## callers of the top lock symbols"
	perf report -i $O/tmp/fio.data --no-children --sort sym --stdio -g caller,0.5,callee,function,percent --max-stack 6 2>/dev/null | grep -v "^$" | grep -vE "^#" | head -45
	} > $f 2>&1
	wait
	echo "## result: $(cat $O/tmp/fio.out) iops" >> $f
	cd /; umount $d
done
echo "FIO_PROF_DONE $TAG" >> $O/progress.txt
