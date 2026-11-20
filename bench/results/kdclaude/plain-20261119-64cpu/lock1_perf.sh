#!/bin/bash
# lock1_perf.sh TAG SYM: lock1 at 16 threads: counters per operation and the annotated slow path.
TAG=$1; SYM=$2; O=/root/plainprof; f=$O/$TAG-lock1-annot.txt
cd /root/appbench/tclocks/will-it-scale || exit 1
{
echo "## $TAG $(uname -r)"
for n in 16 32; do
	( timeout 60 setarch linux64 -R ./build/lock1_threads -t $n -s 12 -n 32 > $O/tmp/l1.out 2>&1 ) &
	sleep 3
	perf stat -a -e cycles,instructions,cache-misses,cache-references,L1-dcache-load-misses,branch-misses -o $O/tmp/st.out -- sleep 4 > /dev/null 2>&1
	if [ $n = 16 ]; then perf record -a -F 1999 -o $O/tmp/l1.data -- sleep 4 > /dev/null 2>&1; fi
	wait
	echo "## $n threads: $(grep '^average:' $O/tmp/l1.out)"
	grep -E "cycles|instructions|cache|branch" $O/tmp/st.out
done
echo "## flat"; perf report -i $O/tmp/l1.data --no-children --sort sym --stdio 2>/dev/null | grep -E "^ +[0-9]" | head -8
echo "## annotate $SYM"
perf annotate -i $O/tmp/l1.data --stdio -s $SYM 2>/dev/null | grep -vE "^\s*$" | awk '$1+0 >= 0.3 || /cmpxchg|xchg|pause|lock / ' | head -120
} > $f 2>&1
echo "LOCK1_PERF_DONE $TAG" >> $O/progress.txt
