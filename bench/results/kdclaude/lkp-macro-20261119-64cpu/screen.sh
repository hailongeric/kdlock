#!/bin/bash
# screen.sh MODE TAG [GROUP...]: screening and delegation runs of the
# second lkp round (README sections 4-5), on kdnat10 and kdall13. It is the
# first round's script (../lkp-macro-20261118-64cpu/screen.sh, kept as that
# round ran it) with the source at /root/host_fs/kdlock, the region counters
# and the per-CPU lock bytes recorded, and the groups of section 3 added.
# Every candidate at the worker counts NS (default 16 and 64), one run of
# DUR seconds (default 10). At PN workers (default 64) also the context
# switches over 2 s and a 3 s flat profile (perf record -a, no call
# graphs), whose top symbols are kept for the lock share
# (screen_summary.py).
#   MODE native    a kdnat kernel
#        off       a kdall kernel without the daemon (plain mode)
#        discover  a kdall kernel; per candidate, PN workers only, a daemon
#                  with an empty allow list: the sites it refuses are the
#                  contended lock users (/root/lkpres/discover/TAG-ID.txt)
#        on        a kdall kernel, one daemon for the whole run with the
#                  allow lists in ALLOW (default api torture mm lkp of
#                  bench/allow), state /root/kds_lkp.json; run a pass with
#                  another TAG first so the images are learned
#   GROUP first round: wis wisp sng vms hackbench futex ebizzy tlbflush
#               aim7 fsmark dbench unixbench (the default)
#         added:       wis2 wisp2 sng2 vms2 perfb pft schbench fsx net
#               redis memcached sysbench kbuild blogbench filebench fio
#               pgbench (build_lkp2.sh; a component that is not built
#               reports 0)
#   ONLY  an extended regex: run only the candidates whose ID matches
# Output: /root/lkpres/screen.txt, one line per point:
#   TAG MODE ID N VALUE UNIT | kd counters before | after
# (counters: delegated handback hb_frontier hb_miss offered plain sessions
# hb_region done_in_region), /root/lkpres/prof/TAG-MODE-ID.txt per profiled
# point, and after each group the memcg per-CPU lock bytes in
# /root/lkpres/pcpu.txt.
MODE=${1:?mode}; TAG=${2:?tag}; shift 2
GROUPS_=${*:-wis wisp sng vms hackbench futex ebizzy tlbflush aim7 fsmark dbench unixbench}
B=/root/lkpbench; O=/root/lkpres; mkdir -p $O/prof $O/tmp
OUT=$O/screen.txt
DUR=${DUR:-10}
NS=${NS:-"16 64"}
PN=${PN:-64}
ulimit -n 65536
# No core dumps: a dump into apport stuck during shutdown hung a reboot
# (appgrid round, 2026-11-18); report fatal signals in the kernel log.
ulimit -c 0
sysctl -q kernel.print-fatal-signals=1
C="delegated handback hb_frontier hb_miss offered plain sessions hb_region done_in_region"
J=/root/host_fs/kdlock/jit
AL=/root/host_fs/kdlock/bench/allow
[ $MODE = discover ] && NS=$PN
d_start() {	# d_start LOG STATE ALLOWFILE
	ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
	(cd $J || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state "$2" --allow "$3" -v \
		>> "$1" 2>&1 < /dev/null &
	 echo $! > /root/kdd_lkp.pid)
	sleep 8
}
d_stop() {
	local P=$(cat /root/kdd_lkp.pid) i
	kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
	kill -0 $P 2>/dev/null && { echo "daemon $P did not stop"; exit 1; }
}
st() {
	[ -r /sys/kernel/debug/kdlock_stats ] || { echo -n "- "; return; }
	local k
	for k in $C; do awk -v k=$k '$1 == k {printf "%s ", $2}' /sys/kernel/debug/kdlock_stats; done
}
complaints() { dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall"; }
fatal() { dmesg | grep -cE "potentially unexpected fatal signal|segfault at|trap invalid opcode"; }
pc() {	# pc WHEN: the memcg per-CPU lock bytes now
	echo "$TAG $MODE $1 $(date +%T): $(python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock 2>&1 |
		sed 's/: acquired set on / /; s/ of [0-9]* CPUs: /:/' | tr '\n' ' ')| $(st)" >> $O/pcpu.txt
}

# point ID N UNIT CMD...: run CMD (it prints the value on its last line); at
# PN workers profile it while it runs.
point() {
	local id=$1 n=$2 unit=$3 s0 v pf; shift 3
	[ -n "$ONLY" ] && ! [[ $id =~ $ONLY ]] && return
	if [ $MODE = discover ]; then
		mkdir -p $O/discover; : > $O/tmp/kdd.log
		d_start $O/tmp/kdd.log "" $O/tmp/empty.allow
	fi
	s0=$(st)
	if [ $n = $PN ]; then
		pf=$O/prof/$TAG-$MODE-$id.txt
		( "$@" > $O/tmp/out 2>&1 ) &
		local p=$!
		sleep $((DUR / 3 + 1))
		{ perf stat -a -e context-switches,cpu-migrations -- sleep 2 2>&1 | grep -E "context|migr"
		  perf record -a -F 499 -o $O/tmp/p.data -- sleep 3 > /dev/null 2>&1
		  perf report -i $O/tmp/p.data --sort sym --stdio 2>/dev/null | grep -E "^# Samples|^[^#]" | grep . | head -41
		} > $pf
		wait $p
		# Nothing of the point may outlive it (child processes included).
		pkill -9 -P $p 2>/dev/null
	else
		"$@" > $O/tmp/out 2>&1
	fi
	v=$(tail -1 $O/tmp/out)
	echo "$TAG $MODE $id $n ${v:-0} $unit | $s0| $(st)" >> $OUT
	if [ $MODE = discover ]; then
		d_stop
		sed -n '/^refused/,$p' $O/tmp/kdd.log > $O/discover/$TAG-$id.txt
	fi
}

# will-it-scale: thread (wis) and process (wisp) models.
W=$B/wis-upstream
wis1() { cd $O/tmp && timeout $((DUR + 30)) $W/$1 -t $2 -s $DUR | grep "^average:" | cut -d: -f2; }
g_wis() {
	local t n
	for t in brk1 brk2 mmap1 mmap2 page_fault1 page_fault2 page_fault3 \
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
# Work files on tmpfs (lkp gives the file stressors a mounted test
# directory); a fresh YAML file per run, so a stressor that fails reports 0.
SNGD=/root/lkpsng
sng1() {
	rm -f $O/tmp/sng.yaml
	cd $SNGD && timeout $((DUR + 60)) $B/stress-ng/stress-ng --$1 $2 --timeout $DUR \
		--verify --metrics --no-rand-seed --temp-path $SNGD --yaml $O/tmp/sng.yaml > /dev/null 2>&1
	[ -f $O/tmp/sng.yaml ] && awk '/bogo-ops-per-second-real-time/ {print $2}' $O/tmp/sng.yaml | head -1
}
g_sng() {
	local s n
	mkdir -p $SNGD; mountpoint -q $SNGD || mount -t tmpfs -o size=8G tmpfs $SNGD
	for s in dentry dir link rename unlink getdent filerace open dup close inotify \
		 fork vfork clone exit-group zombie wait kill signal sigq \
		 sem sem-sysv msg mq shm shm-sysv futex pipe pipeherd sock sockpair udp \
		 epoll eventfd switch vm mmap mmapfork mremap mprotect madvise brk vma \
		 flock fcntl lockf lockofd tmpfs; do
		for n in $NS; do point sng-$s $n bogo/s sng1 $s $n; done
	done
	cd /; umount $SNGD
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
# wake-parallel prints the average per-thread wake latency; the rate is its inverse.
pbf_wake() { timeout 120 perf bench futex wake-parallel -t $1 2>&1 | sed -n 's/^Avg per-thread latency.* in \([0-9.]*\) ms.*/\1/p' | tail -1 | awk '{print ($1 > 0) ? 1 / $1 : 0}'; }
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
	cp -r $B/aim7/aim7/* $d/
	cd $d && tar -xf fakeh.tar && printf 'FILESIZE: 1M\nPOOLSIZE: 10M\n10 %s\n' $1 > workfile && echo /fs/shm > config
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
		awk '/^Average Files\/sec:/ {print $3}'
	umount $M
}
g_fsmark() { local n; for n in $NS; do point fsmark $n files/s fsm1 $n; done; }

dbn1() {
	local M=/root/lkpfs; mkdir -p $M; mount -t tmpfs -o size=8G tmpfs $M
	timeout $((DUR + 60)) $B/dbench/dbench -B fileio -c $B/dbench/loadfiles/client.load -D $M -t $DUR $1 2>&1 | \
		awk '/^Throughput/ {print $2}'
	umount $M
}
g_dbench() { local n; for n in $NS; do point dbench $n MB/s dbn1 $n; done; }

ub1() {
	cd $B/byte-unixbench/UnixBench && timeout 600 ./Run -c $2 -i 1 $1 2>&1 | \
		awk '/ (lps|lpm|KBps) +\(/ {for (i = 1; i < NF; i++) if ($(i + 1) ~ /^(lps|lpm|KBps)$/) v = $i} END {print v + 0}'
}
g_unixbench() {
	local t n
	for t in execl spawn shell8 pipe context1 syscall fstime; do
		for n in $NS; do point ub-$t $n lps ub1 $t $n; done
	done
}

# ---------------------------------------------------------------------------
# Groups added in the second round (README section 3).

# The will-it-scale tests of lkp's jobs that the first round left out.
g_wis2() {
	local t n
	# malloc1 has a process mode only (lkp's job runs it so; its thread
	# binary reports 0).
	for t in eventfd1 fallocate1 fallocate2 futex3 futex4 lock1 lseek1 malloc2 \
		 open2 pipe1 poll1 poll2 pread1 pread3 pthread_mutex2 pthread_mutex5 pwrite1 \
		 read3 read4 readseek1 readseek3 unix1 unlink2 write1 writeseek1 writeseek2; do
		[ -x $W/${t}_threads ] || continue
		for n in $NS; do point wis-$t $n ops/s wis1 ${t}_threads $n; done
	done
}
g_wisp2() {
	local t n
	for t in brk1 brk2 context_switch1 dup1 eventfd1 fallocate1 fallocate2 futex2 futex3 \
		 futex4 getppid1 lock1 lseek1 lseek2 malloc1 malloc2 mmap1 mmap2 open2 \
		 page_fault1 page_fault2 page_fault3 pipe1 poll1 poll2 pread1 pread2 pread3 \
		 pthread_mutex1 pthread_mutex2 pthread_mutex3 pthread_mutex4 pthread_mutex5 \
		 pwrite1 read1 read2 read3 read4 readseek1 readseek2 readseek3 sched_yield \
		 signal1 tlb_flush1 tlb_flush2 tlb_flush3 unix1 unlink2 write1 writeseek1 \
		 writeseek2 writeseek3; do
		[ -x $W/${t}_processes ] || continue
		for n in $NS; do point wisp-$t $n ops/s wis1 ${t}_processes $n; done
	done
}

# The stress-ng stressors of lkp's jobs (386 of them exist in this stress-ng)
# that exercise the kernel and that the first round left out. Not run: the compute, sort, math and cache
# stressors (lkp's cpu-cache job and the like: no kernel lock on their
# path), and those that change the machine or need hardware or a device
# (cpu-online, memhotplug, module, swap, umount, loop, rawdev, watchdog,
# softlockup, smi, ioport, kvm, binderfs, efivar, led, apparmor, cgroup,
# bind-mount, dev, oom-pipe, resources, tun, netdev, dccp, sctp, verity,
# uprobe, hugepage, idle-page, klog, quota, rtc, pci, reboot, bad-ioctl,
# sysinval, spawn and exec as root).
SNG2="acct affinity aio alarm bad-altstack bigheap cap chroot clock context cpu-sched daemon \
dev-shm dynlib enosys env fault fd-abuse fd-fork fd-race fifo filehole full forkheavy \
get getrandom hrtimers io-uring itimer kcmp key landlock lockmix malloc mcontend membarrier \
memfd mincore min-nanosleep mlock mlockmany mmapaddr mmapfiles mmapfixed mmaprandom \
mmaptorture mseal msync msyncmany mtx munmap mutex loadavg mmapmany mmapcow \
nanosleep netlink-proc netlink-task nice pthread poll prio-inv race-sched \
schedmix schedpolicy seal seccomp secretmem seek sendfile session set sigabrt sigbus \
sigchld sigfd sigfpe sighup sigill sigio signest sigpending sigpipe sigrt sigsegv \
sigstop sigsuspend sigtrap sigurg sigvtalrm sigxcpu sigxfsz sleep sockabuse sockdiag \
sockfd sockmany splice stack stackmmap statmount syncload sysbadaddr syscall sysfs \
sysinfo tee timer timerfd timermix tlb-shootdown umask unshare urandom userfaultfd \
usersyscall vdso vforkmany vm-addr vm-rw vm-segv vm-splice waitcpu x86syscall zero \
access acl aiol chdir chmod chown copy-file dentrycache dirdeep dirmany dnotify fiemap \
file-ioctl filename fpunch fsize fstat handle inode-flags io iomix ioprio lease locka \
metamix mknod procfs sync-file utime xattr chattr fanotify touch hdd fallocate \
epollmany icmp-flood ping-sock rawpkt rawsock rawudp udp-flood \
pagemove physpage pidfd pkey prctl pseek ptrace pty ramfs readahead remap resched revio \
ring-pipe rlimit rmap rseq personality numa"
g_sng2() {
	local s n
	mkdir -p $SNGD; mountpoint -q $SNGD || mount -t tmpfs -o size=8G tmpfs $SNGD
	for s in ${SNG2_LIST:-$SNG2}; do
		for n in $NS; do point sng-$s $n bogo/s sng1 $s $n; done
	done
	cd /; umount $SNGD
}

# vm-scalability cases that need its sparse files and tmpfs (hw_vars), in a
# size that fits the guest; lkp's sizes (16-256 G) do not. Left out:
# lru-file-readonce and lru-file-readtwice (dd, no usemem rate) and truncate
# (it reads all of memory first and reports one time).
vms2() {
	cd $B/vm-scalability || return 1
	(
	echo 1 > /proc/sys/vm/overcommit_memory
	export nr_task=$2 runtime=$DUR size=$((4 << 30)) unit_size=$((4 << 30))
	export USEMEM="./usemem --runtime $DUR"
	. ./hw_vars > /dev/null 2>&1
	mount_tmpfs > /dev/null 2>&1; create_sparse_root > /dev/null 2>&1
	timeout $((DUR + 180)) sh ./case-$1 2>&1
	remove_sparse_root > /dev/null 2>&1; remove_tmpfs > /dev/null 2>&1
	) | awk '/KB\/s/ {for (i = 1; i < NF; i++) if ($(i+1) == "KB/s") s += $i} END {print s + 0}'
}
g_vms2() {
	local c n
	for c in lru-file-mmap-read lru-file-mmap-read-rand \
		 mmap-pread-rand-mt mmap-pread-seq-mt mmap-xread-rand-mt mmap-xread-seq-mt \
		 mremap-xread-rand-mt shm-pread-rand-mt shm-xread-rand-mt lru-shm-rand \
		 msync-mt anon-r-seq-mt anon-rx-rand-mt; do
		[ -f $B/vm-scalability/case-$c ] || continue
		for n in $NS; do point vms-$c $n KB/s vms2 $c $n; done
	done
}

# perf bench epoll (one epoll instance shared by the threads) and the futex
# tests the first round left out.
pbe1() { timeout $((DUR + 60)) perf bench epoll $1 -t $2 -r $DUR 2>&1 | awk '/Averaged/ {print $2; exit}'; }
g_perfb() {
	local t n
	for t in wait ctl; do for n in $NS; do point pbe-$t $n ops/s pbe1 $t $n; done; done
	for n in $NS; do point pbf-requeue $n 1/ms sh -c "timeout 120 perf bench futex requeue -t $n 2>&1 | sed -n 's/^Requeued.* in \([0-9.]*\) ms.*/\1/p' | tail -1 | awk '{print (\$1 > 0) ? 1 / \$1 : 0}'"; done
	for n in $NS; do point pbf-wake $n 1/ms sh -c "timeout 120 perf bench futex wake -t $n 2>&1 | sed -n 's/^Wokeup.* in \([0-9.]*\) ms.*/\1/p' | tail -1 | awk '{print (\$1 > 0) ? 1 / \$1 : 0}'"; done
}

# pft (page faults of one mapping, threads), faults per second.
pft1() { cd $B/pft && timeout $((DUR + 120)) ./pft -m 4G -t $1 2>&1 | awk 'NF >= 8 && $NF + 0 > 0 {v = $NF} END {print v + 0}'; }
g_pft() { local n; for n in $NS; do point pft $n faults/s pft1 $n; done; }

# schbench, lkp's second form: 2 message threads, N workers; requests/s.
sch1() { timeout $((DUR + 60)) $B/schbench/schbench -m 2 -t $(($1 / 2)) -r $DUR 2>&1 | awk '/average rps/ {v = $NF} END {print v + 0}'; }
g_schbench() { local n; for n in $NS; do point schbench $n rps sch1 $n; done; }

# File systems on a RAM block device (lkp's 1BRD disk, here 8 G): ext4, xfs
# and btrfs under AIM7, fs_mark, dbench and fio. FSX selects the file
# systems.
M=/root/lkpfs
fs_up() {	# fs_up FS
	mkdir -p $M; mountpoint -q $M && umount $M
	lsmod | grep -q "^brd" && rmmod brd
	modprobe brd rd_nr=1 rd_size=$((8 << 20)) || return 1
	case $1 in
	ext4) mkfs.ext4 -q -F /dev/ram0 ;;
	xfs) mkfs.xfs -q -f /dev/ram0 ;;
	btrfs) mkfs.btrfs -q -f /dev/ram0 ;;
	esac > /dev/null 2>&1 || return 1
	mount /dev/ram0 $M
}
fs_down() { cd /; umount $M 2>/dev/null; rmmod brd 2>/dev/null; }
aim_load() {	# aim_load FS TEST N: lkp's load for a 64-worker point (aim7-fs-1brd), scaled to N
	local l
	case $2 in
	disk_cp|disk_rr) [ $1 = btrfs ] && l=1500 || l=3000 ;;
	disk_rw|disk_src) [ $1 = btrfs ] && l=500 || l=3000 ;;
	sync_disk_rw) [ $1 = btrfs ] && l=10 || l=600 ;;
	creat-clo) case $1 in btrfs) l=4 ;; ext4) l=1000 ;; *) l=1500 ;; esac ;;
	*) l=9000 ;;
	esac
	l=$((l * $3 / 64)); [ $l -lt 2 ] && l=2
	echo $l
}
aimx() {	# aimx FS TEST LOAD
	local d=$B/aim7/run; rm -rf $d; mkdir -p $d
	fs_up $1 || { echo 0; return; }
	cp -r $B/aim7/aim7/* $d/
	cd $d && tar -xf fakeh.tar && printf 'FILESIZE: 1M\nPOOLSIZE: 10M\n10 %s\n' $2 > workfile && echo $M > config
	echo "500 32000 128 512" > /proc/sys/kernel/sem
	printf 'lkp\n%s\n1\n%s\n2\n%s\n1\n' $2 $3 $3 | timeout 900 ./multitask -t 2>&1 | \
		awk '/^ *[0-9]+ +[0-9.]+/ {v = $2} END {print v + 0}'
	fs_down
}
fsmx() {	# fsmx FS SYNC N: fs_mark, one directory per thread; SYNC 0 none, 1 fsync before close
	fs_up $1 || { echo 0; return; }
	local d="" i; for i in $(seq 1 $3); do mkdir -p $M/d$i; d="$d -d $M/d$i"; done
	cd /root && timeout 300 $B/fs_mark/fs_mark $d -n 2000 -s 4096 -L 3 -S $2 -k 2>&1 | \
		awk '/^Average Files\/sec:/ {print $3}'
	fs_down
}
dbnx() {	# dbnx FS N
	fs_up $1 || { echo 0; return; }
	timeout $((DUR + 60)) $B/dbench/dbench -B fileio -c $B/dbench/loadfiles/client.load -D $M -t $DUR $2 2>&1 | \
		awk '/^Throughput/ {print $2}'
	fs_down
}
g_fsx() {
	local f t n
	for f in ${FSX:-ext4 xfs btrfs}; do
		for t in disk_cp disk_rr disk_rw disk_src creat-clo sync_disk_rw disk_rd; do
			for n in $NS; do point aim7-$f-$t $n jobs/min aimx $f $t $(aim_load $f $t $n); done
		done
		for n in $NS; do point fsmark-$f-nosync $n files/s fsmx $f 0 $n; done
		for n in $NS; do point fsmark-$f-fsync $n files/s fsmx $f 1 $n; done
		for n in $NS; do point dbench-$f $n MB/s dbnx $f $n; done
	done
}

# netperf on loopback, lkp's tests: N instances, the sum of their rates
# (transactions/s; 10^6 bit/s for the stream test). tbench with N clients.
np1() {	# np1 TEST N
	local i
	{ for i in $(seq $2); do
		$B/netperf/src/netperf -4 -H 127.0.0.1 -p 12865 -t $1 -l $DUR -P 0 -- -o THROUGHPUT 2>/dev/null &
	  done; wait; } | awk '{s += $1} END {print s + 0}'
}
tb1() { timeout $((DUR + 60)) $B/dbench/tbench -c $B/dbench/loadfiles/client.txt -t $DUR $1 127.0.0.1 2>&1 | awk '/^Throughput/ {print $2}'; }
g_net() {
	local t n
	[ -x $B/netperf/src/netserver ] || { echo "netperf not built"; return; }
	pkill -x netserver 2>/dev/null; $B/netperf/src/netserver -4 -p 12865 > /dev/null 2>&1; sleep 1
	for t in TCP_RR TCP_CRR UDP_RR; do
		for n in $NS; do point netperf-$t $n trans/s np1 $t $n; done
	done
	for n in $NS; do point netperf-TCP_STREAM $n Mbit/s np1 TCP_STREAM $n; done
	pkill -x netserver
	if [ -x $B/dbench/tbench_srv ]; then
		( $B/dbench/tbench_srv > /dev/null 2>&1 & ); sleep 1
		for n in $NS; do point tbench $n MB/s tb1 $n; done
		pkill -x tbench_srv
	fi
}

# redis, as lkp's job but with N/2 servers: one redis-benchmark per server
# (set and get, 5 clients, pipeline 3, 1 KiB values); the sum of the rates.
rds1() {	# rds1 N
	local k=$(($1 / 2)) i R=$B/redis/src
	for i in $(seq $k); do $R/redis-server --port $((6400 + i)) --save "" --appendonly no --daemonize no > /dev/null 2>&1 & done
	sleep 2
	{ for i in $(seq $k); do
		timeout 300 $R/redis-benchmark -p $((6400 + i)) -t set,get -d 1024 -c 5 -P 3 -r 1000000 -n ${RDS_N:-1500000} --csv 2>/dev/null &
	  done; wait; } | awk -F, '{gsub(/"/, "", $2); if ($2 + 0 > 0) s += $2} END {print s + 0}'
	pkill -x redis-server; sleep 1
}
g_redis() { local n; [ -x $B/redis/src/redis-server ] || return; for n in $NS; do point redis $n req/s rds1 $n; done; }

# memcached with N/2 threads and memtier_benchmark with N/2 threads of 4
# connections (1:4 set:get, 1 KiB values); operations per second.
mc1() {	# mc1 N
	local k=$(($1 / 2))
	$B/memcached-1.6.39/memcached -u root -p 11311 -t $k -m 2048 -c 4096 > /dev/null 2>&1 &
	sleep 1
	timeout $((DUR + 60)) $B/memtier_benchmark/memtier_benchmark -s 127.0.0.1 -p 11311 -P memcache_text \
		--threads=$k -c 4 --ratio=1:4 -d 1024 --test-time=$DUR --hide-histogram 2>/dev/null | awk '/^Totals/ {print $2}'
	pkill -x memcached; sleep 1
}
g_memcached() {
	local n
	[ -x $B/memcached-1.6.39/memcached ] && [ -x $B/memtier_benchmark/memtier_benchmark ] || return
	for n in $NS; do point memcached $n ops/s mc1 $n; done
}

# sysbench mutex and threads, lkp's parameters, but 500 lock rounds per
# event instead of 50000 (an event then takes about 10 ms, not a second, so
# a 10 s point counts enough of them); events per second.
sb1() {	# sb1 N ARGS...
	local n=$1; shift
	timeout $((DUR + 120)) $B/sysbench/src/sysbench --threads=$n "$@" run 2>&1 | \
		awk '/events\/s \(eps\):/ {print $NF}' | tail -1
}
g_sysbench() {
	local n
	[ -x $B/sysbench/src/sysbench ] || return
	for n in $NS; do point sysbench-mutex $n events/s sb1 $n --time=$DUR mutex --mutex-num=4096 --mutex-locks=500 --mutex-loops=10000; done
	for n in $NS; do point sysbench-threads $n events/s sb1 $n --time=$DUR threads --thread-yields=1000 --thread-locks=8; done
}

# Kernel build (lkp's kbuild: defconfig, vmlinux), objects on tmpfs, from
# the clean copy of the kernel source that Psearchy indexes; builds/hour.
kb1() {	# kb1 N
	local src=/root/appbench/text/linux obj=/root/lkpkb t0 t1
	mkdir -p $obj; mountpoint -q $obj && umount $obj
	mount -t tmpfs -o size=12G tmpfs $obj || return 1
	make -C $src O=$obj defconfig > /dev/null 2>&1
	t0=$(date +%s.%N)
	timeout 3600 make -C $src O=$obj -j$1 vmlinux > $O/tmp/kbuild.log 2>&1; local e=$?
	t1=$(date +%s.%N)
	cd /; umount $obj
	[ $e = 0 ] && echo "3600 / ($t1 - $t0)" | bc -l | awk '{printf "%.2f\n", $1}' || echo 0
}
g_kbuild() { local n; [ -d /root/appbench/text/linux ] || return; for n in ${KB_NS:-$PN}; do point kbuild $n builds/h kb1 $n; done; }

# blogbench on tmpfs: N readers, N/8 writers, rewriters and commenters,
# 3 iterations of 10 s; its two scores are two candidates of one run each.
bb1() {	# bb1 writes|reads N
	local d=/root/lkpfs k=$(($2 / 8 + 1))
	mkdir -p $d; mountpoint -q $d && umount $d; mount -t tmpfs -o size=8G tmpfs $d
	timeout 300 $B/blogbench-1.2/src/blogbench -d $d -i 3 -r $2 -w $k -W $k -c $k 2>&1 | awk -v w=$1 '$0 ~ "Final score for " w {print $NF}'
	cd /; umount $d
}
g_blogbench() {
	local n
	[ -x $B/blogbench-1.2/src/blogbench ] || return
	for n in $NS; do point blogbench-w $n score bb1 writes $n; done
	for n in $NS; do point blogbench-r $n score bb1 reads $n; done
}

# filebench personalities of lkp's job, N threads, on tmpfs; operations/s.
fb1() {	# fb1 WORKLOAD N
	local d=/root/lkpfs F=$B/filebench/inst
	mkdir -p $d; mountpoint -q $d && umount $d; mount -t tmpfs -o size=8G tmpfs $d
	sed -e "s#^set \$dir=.*#set \$dir=$d#" -e "s#^set \$nthreads=.*#set \$nthreads=$2#" \
	    -e "s#^run .*#run $DUR#" $F/share/filebench/workloads/$1.f > $O/tmp/fb.f
	echo 0 > /proc/sys/kernel/randomize_va_space
	timeout $((DUR + 240)) $F/bin/filebench -f $O/tmp/fb.f 2>&1 | sed -n 's/.*IO Summary:.* \([0-9.]*\) ops\/s.*/\1/p' | tail -1
	echo 2 > /proc/sys/kernel/randomize_va_space
	cd /; umount $d
}
g_filebench() {
	local w n
	[ -x $B/filebench/inst/bin/filebench ] || return
	for w in fileserver varmail webserver webproxy; do
		for n in $NS; do point filebench-$w $n ops/s fb1 $w $n; done
	done
}

# fio, buffered 4 KiB I/O with the sync engine (lkp's fio-basic) on tmpfs:
# N jobs on one shared file and on a file each; IOPS.
fio1() {	# fio1 RW shared|own N
	local d=/root/lkpfs f=""
	mkdir -p $d; mountpoint -q $d && umount $d; mount -t tmpfs -o size=8G tmpfs $d
	[ $2 = shared ] && f="--filename=$d/shared"
	timeout $((DUR + 120)) $B/fio/fio --name=j --directory=$d $f --rw=$1 --bs=4k --size=64M --numjobs=$3 \
		--time_based --runtime=$DUR --group_reporting --ioengine=psync --output-format=terse 2>/dev/null | \
		awk -F';' '{print $8 + $49}' | tail -1
	cd /; umount $d
}
g_fio() {
	local r m n
	[ -x $B/fio/fio ] || return
	for r in randwrite randread; do for m in shared own; do
		for n in $NS; do point fio-$r-$m $n iops fio1 $r $m $n; done
	done; done
}

# pgbench: PostgreSQL 17 on tmpfs (user lkppg), scale 100, select-only and
# simple-update (-N) with N clients; transactions per second.
PG=/opt/lkp-pgsql/bin; PGD=/var/tmp/lkppg
pg_up() {
	[ -x $PG/postgres ] || return 1
	id lkppg > /dev/null 2>&1 || useradd -m lkppg || return 1
	mkdir -p $PGD; mountpoint -q $PGD || mount -t tmpfs -o size=8G tmpfs $PGD
	chown lkppg $PGD
	su lkppg -c "$PG/initdb -D $PGD/data" > $O/tmp/pg-init.log 2>&1 || return 1
	su lkppg -c "$PG/pg_ctl -D $PGD/data -l $PGD/log -w -o '-c shared_buffers=4GB -c max_connections=300 -c fsync=off -c synchronous_commit=off -c max_wal_size=8GB' start" >> $O/tmp/pg-init.log 2>&1 || return 1
	su lkppg -c "$PG/createdb bench && $PG/pgbench -q -i -s 100 bench" >> $O/tmp/pg-init.log 2>&1
}
pg_down() { su lkppg -c "$PG/pg_ctl -D $PGD/data -m fast -w stop" > /dev/null 2>&1; cd /; umount $PGD; }
pg1() {	# pg1 N OPTS
	local n=$1; shift
	su lkppg -c "$PG/pgbench $* -c $n -j $n -T $DUR bench" 2>&1 | sed -n 's/^tps = \([0-9.]*\) (without.*/\1/p'
}
g_pgbench() {
	local n
	pg_up || { echo "pgbench: no server"; pg_down 2>/dev/null; return; }
	for n in $NS; do point pgbench-select $n tps pg1 $n -S; done
	for n in $NS; do point pgbench-update $n tps pg1 $n -N; done
	pg_down
}

echo "# empty: refuse every site" > $O/tmp/empty.allow
if [ $MODE = on ]; then
	for a in ${ALLOW:-api torture mm lkp}; do cat $AL/$a.txt; done > $O/tmp/on.allow
	d_start $O/kdd-$TAG.log /root/kds_lkp.json $O/tmp/on.allow
fi
c0=$(complaints); f0=$(fatal)
echo "$TAG $MODE start $(date +%T) $(uname -r) ns: $NS dur: $DUR" >> $O/progress.txt
pc start
for g in $GROUPS_; do
	echo "$TAG $MODE $g $(date +%T)" >> $O/progress.txt
	g_$g
	pc "after-$g"
done
[ $MODE = on ] && d_stop
echo "$TAG $MODE complaints $(( $(complaints) - c0 )) fatal signals $(( $(fatal) - f0 ))" >> $O/complaints.txt
echo "$TAG $MODE done $(date +%T)" >> $O/progress.txt
echo SCREEN_DONE
