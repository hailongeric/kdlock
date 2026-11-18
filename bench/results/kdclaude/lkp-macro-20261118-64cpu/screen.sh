#!/bin/bash
# screen.sh MODE TAG [GROUP...]: phase 1-2 screening (README 4.2, 4.3).
# Every candidate at 16 workers (one node) and 64 (both nodes), one run of
# DUR seconds (default 10). At 64 workers also the context switches over 5
# s and a 5 s flat profile (perf record -a, no call graphs), whose top
# symbols are kept for the lock share (screen_summary.py).
#   MODE native (kdnat kernel) or off (kdall kernel without the daemon)
#   GROUP wis wisp sng vms hackbench futex ebizzy tlbflush aim7 fsmark
#         dbench unixbench (default: all)
# Output: /root/lkpres/screen.txt, one line per point:
#   TAG MODE ID N VALUE UNIT | kd counters before | after
# and /root/lkpres/prof/TAG-MODE-ID.txt per profiled point.
MODE=${1:?mode}; TAG=${2:?tag}; shift 2
GROUPS_=${*:-wis wisp sng vms hackbench futex ebizzy tlbflush aim7 fsmark dbench unixbench}
B=/root/lkpbench; O=/root/lkpres; mkdir -p $O/prof $O/tmp
OUT=$O/screen.txt
DUR=${DUR:-10}
NS=${NS:-"16 64"}
ulimit -n 65536
C="delegated handback offered plain sessions"
st() {
	[ -r /sys/kernel/debug/kdlock_stats ] || { echo -n "- "; return; }
	local k
	for k in $C; do awk -v k=$k '$1 == k {printf "%s ", $2}' /sys/kernel/debug/kdlock_stats; done
}
complaints() { dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall"; }

# point ID N UNIT CMD...: run CMD (it prints the value on its last line); at
# 64 workers profile it while it runs.
point() {
	local id=$1 n=$2 unit=$3 s0 v pf; shift 3
	s0=$(st)
	if [ $n = 64 ]; then
		pf=$O/prof/$TAG-$MODE-$id.txt
		( "$@" > $O/tmp/out 2>&1 ) &
		local p=$!
		sleep $((DUR / 3 + 1))
		{ perf stat -a -e context-switches,cpu-migrations -- sleep 2 2>&1 | grep -E "context|migr"
		  perf record -a -F 499 -o $O/tmp/p.data -- sleep 3 > /dev/null 2>&1
		  perf report -i $O/tmp/p.data --sort sym --stdio 2>/dev/null | grep -E "^# Samples|^[^#]" | grep . | head -41
		} > $pf
		wait $p
	else
		"$@" > $O/tmp/out 2>&1
	fi
	v=$(tail -1 $O/tmp/out)
	echo "$TAG $MODE $id $n ${v:-0} $unit | $s0| $(st)" >> $OUT
}

# will-it-scale: thread (wis) and process (wisp) models.
W=$B/wis-upstream/build
wis1() { cd $O/tmp && timeout $((DUR + 30)) $W/$1 -t $2 -s $DUR | grep "^average:" | cut -d: -f2; }
g_wis() {
	local t n
	for t in brk1 brk2 malloc1 mmap1 mmap2 page_fault1 page_fault2 page_fault3 \
		 tlb_flush1 tlb_flush2 tlb_flush3 signal1 dup1 lock2 open1 open3 unlink1 \
		 pwrite2 pwrite3 writeseek3 readseek2 lseek2 read2 pread2 futex1 futex2 \
		 pthread_mutex1 pthread_mutex3 pthread_mutex4 posix_semaphore1 \
		 context_switch1 sched_yield getppid1 read1; do
		for n in $NS; do point wis-$t $n ops/s wis1 ${t}_threads $n; done
	done
}
g_wisp() {
	local t n
	for t in lock2 open1 open3 unlink1 pwrite2 pwrite3 futex1 posix_semaphore1; do
		for n in $NS; do point wisp-$t $n ops/s wis1 ${t}_processes $n; done
	done
}

# stress-ng, lkp's options (--times --verify --metrics), one stressor at a time.
sng1() {
	cd $O/tmp && timeout $((DUR + 60)) $B/stress-ng/stress-ng --$1 $2 --timeout $DUR \
		--verify --metrics --no-rand-seed --yaml $O/tmp/sng.yaml > /dev/null 2>&1
	awk '/bogo-ops-per-second-real-time/ {print $2}' $O/tmp/sng.yaml | head -1
}
g_sng() {
	local s n
	for s in dentry dir link rename unlink getdent filerace open dup close inotify \
		 fork vfork clone exit zombie wait kill signal sigq \
		 sem semsysv msg mq shm shmsysv futex pipe pipeherd sock sockpair udp \
		 epoll eventfd switch vm mmap mmapfork mremap mprotect madvise brk vma \
		 flock fcntl lockf lockofd tmpfs; do
		for n in $NS; do point sng-$s $n bogo/s sng1 $s $n; done
	done
}

# vm-scalability, cases with usemem only; throughput is the sum over tasks.
vms1() {
	cd $B/vm-scalability && nr_task=$2 runtime=$DUR size=$((8 << 30)) unit_size=$((8 << 30)) \
		USEMEM="./usemem --runtime $DUR" timeout $((DUR + 120)) sh ./case-$1 2>&1 | \
		awk '/KB\/s/ {for (i = 1; i < NF; i++) if ($(i+1) == "KB/s") s += $i} END {print s + 0}'
}
g_vms() {
	local c n
	for c in anon-w-rand-mt anon-r-rand-mt anon-cow-rand-mt anon-wx-rand-mt small-allocs-mt \
		 anon-w-rand small-allocs; do
		for n in $NS; do point vms-$c $n KB/s vms1 $c $n; done
	done
}

# hackbench (rt-tests), lkp's modes; rate = 1 / time.
hb1() {
	local o=""
	[ $2 = threads ] && o=-T; [ $2 = process ] && o=-P
	[ $1 = pipe ] && o="$o -p"
	timeout 300 $B/rt-tests/hackbench $o -g $3 -l 2000 | awk '/^Time:/ {printf "%.4f\n", 1 / $2}'
}
g_hackbench() {
	local ipc m n
	for ipc in pipe socket; do for m in process threads; do
		for n in $NS; do point hb-$ipc-$m $n 1/s hb1 $ipc $m $((n / 2)); done
	done; done
}

# perf bench futex (lkp's tests), ops/s.
pbf1() { timeout $((DUR + 60)) perf bench futex $1 -t $2 -r $DUR 2>&1 | awk '/Averaged/ {print $2}' | tail -1; }
pbf_wake() { timeout 120 perf bench futex wake-parallel -t $1 2>&1 | awk '/Averaged/ {for (i = 1; i <= NF; i++) if ($i ~ /ms/) print 1000 / $(i-1)}' | tail -1; }
g_futex() {
	local t n
	for t in hash lock-pi; do for n in $NS; do point pbf-$t $n ops/s pbf1 $t $n; done; done
	for n in $NS; do point pbf-hash-shared $n ops/s pbf1 "hash -S" $n; done
	for n in $NS; do point pbf-wakepar $n 1/ms pbf_wake $n; done
	for n in $NS; do point pbms-thread $n 1/s sh -c "perf bench sched messaging -t -g $((n / 4)) -l 1000 2>&1 | awk '/Total time/ {printf \"%.4f\\n\", 1 / \$3}'"; done
}

ebz1() { timeout $((DUR + 30)) $B/ebizzy-0.3/ebizzy -t $1 -S $DUR 2>&1 | awk '/records\/s/ {print $1}' | tail -1; }
g_ebizzy() { local n; for n in $NS; do point ebizzy $n records/s ebz1 $n; done; }

tlb1() { cd $B/tlbflush && timeout 300 ./tlbflush -t $1 -n 512 2>&1 | awk -F'times/thread/ms' '/times\/thread\/ms/ {split($1, a, " "); print a[length(a)]}' | tail -1; }
g_tlbflush() { local n; for n in $NS; do point tlbflush $n per-thread/ms tlb1 $n; done; }

# AIM7 on tmpfs (lkp's setup when no disk is given), jobs per minute.
aim1() {
	local d=$B/aim7/run; rm -rf $d; mkdir -p $d /fs/shm
	mountpoint -q /fs/shm || mount -t tmpfs /dev/shm /fs/shm
	cp -r $B/aim7/s7110/* $d/ 2>/dev/null || cp -r $B/aim7/*/* $d/
	cd $d && printf 'FILESIZE: 1M\nPOOLSIZE: 10M\n10 %s\n' $1 > workfile && echo /fs/shm > config
	echo "500 32000 128 512" > /proc/sys/kernel/sem
	printf 'lkp\n%s\n1\n%s\n2\n%s\n1\n' $1 $2 $2 | timeout 600 ./multitask -t 2>&1 | \
		awk '/^ *[0-9]+ +[0-9.]+/ {v = $2} END {print v + 0}'
	umount /fs/shm
}
g_aim7() {
	local t n
	for t in creat-clo disk_rr disk_rw disk_cp disk_src; do
		for n in $NS; do point aim7-$t $n jobs/min aim1 $t $((n * 50)); done
	done
}

fsm1() {
	local M=/root/lkpfs; mkdir -p $M; mount -t tmpfs -o size=8G tmpfs $M
	local d="" i; for i in $(seq 1 $1); do mkdir -p $M/d$i; d="$d -d $M/d$i"; done
	cd /root && timeout 300 $B/fs_mark/fs_mark $d -n 2000 -s 4096 -L 3 -k 2>&1 | \
		awk '$1 ~ /^[0-9]+$/ && NF >= 4 {v = $4} END {print v + 0}'
	umount $M
}
g_fsmark() { local n; for n in $NS; do point fsmark $n files/s fsm1 $n; done; }

dbn1() {
	local M=/root/lkpfs; mkdir -p $M; mount -t tmpfs -o size=8G tmpfs $M
	timeout $((DUR + 60)) $B/dbench/dbench -c $B/dbench/loadfiles/client.txt -D $M -t $DUR $1 2>&1 | \
		awk '/^Throughput/ {print $2}'
	umount $M
}
g_dbench() { local n; for n in $NS; do point dbench $n MB/s dbn1 $n; done; }

ub1() {
	cd $B/byte-unixbench/UnixBench && timeout 600 ./Run -q -c $2 -i 1 $1 2>&1 | \
		awk '/^[A-Za-z].*[0-9.]+ +(lps|lpm|KBps)/ {v = $(NF - 1)} END {print v + 0}'
}
g_unixbench() {
	local t n
	for t in execl spawn shell8 pipe context1 syscall fstime; do
		for n in $NS; do point ub-$t $n lps ub1 $t $n; done
	done
}

c0=$(complaints)
echo "$TAG $MODE start $(date +%T) $(uname -r)" >> $O/progress.txt
for g in $GROUPS_; do
	echo "$TAG $MODE $g $(date +%T)" >> $O/progress.txt
	g_$g
done
echo "$TAG $MODE complaints $(( $(complaints) - c0 ))" >> $O/complaints.txt
echo "$TAG $MODE done $(date +%T)" >> $O/progress.txt
echo SCREEN_DONE
