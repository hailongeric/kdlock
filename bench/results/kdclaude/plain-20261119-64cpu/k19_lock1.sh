#!/bin/bash
# kdall19: lock1 with the temporary switches (1 reload the lock word at slow-path entry, 2 prefetch the successor,
# 4 no second look at the lock word when a queue was seen at entry), interleaved, 4 rounds.
P=/sys/module/kernel/parameters; O=/root/plainprof; W=/root/appbench/tclocks/will-it-scale
for r in 1 2 3 4; do for v in 0 1 2 4 6; do
	echo $v > $P/kd_dbg
	for n in 8 16 32; do
		x=$(cd $W && timeout 60 setarch linux64 -R ./build/lock1_threads -t $n -s 5 -n 32 2>&1 | grep "^average:" | cut -d: -f2)
		echo "k19 $r dbg$v lock1 $n ${x:-0}" >> $O/k19-dbg.txt
	done
done; done
echo 0 > $P/kd_dbg
echo "K19_LOCK1_DONE $(date +%T)" >> $O/progress.txt
