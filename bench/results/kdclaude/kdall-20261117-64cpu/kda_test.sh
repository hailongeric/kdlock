#!/bin/bash
# kda_test.sh TAG: checks on the running kernel, written to /root/kda/TAG.log.
# On kdall1 (every lock kdlock, no daemon) and, for the cross-boot reference,
# on kdclaude1 with kd_mm=0 and kd_api=0 (native locks).
TAG=${1:?tag}
O=/root/kda; mkdir -p $O
exec > $O/$TAG.log 2>&1
mark() { echo "kda: $*" > /dev/kmsg; echo "== $* $(date +%T)"; }
since() { dmesg | awk -v m="kda: $1" 'index($0, m) {f=1} f'; }

mark kernel
uname -a; cat /proc/cmdline; nproc
echo "boot complaints:"; dmesg | grep -iE "BUG:|WARNING:|lockup|hung_task|blocked for more|Call Trace|rcu.*stall" | head -30
grep -E "^(delegation|sessions|delegated|handback)\b" /sys/kernel/debug/kdlock_stats 2>/dev/null | head
pgrep -af kd_daemon || echo "no daemon"
systemctl is-system-running; systemctl --failed --no-legend | head

# ---- locktorture: every lock type it has, 60 s each -----------------------------
for t in lock_busted spin_lock spin_lock_irq raw_spin_lock raw_spin_lock_irq rw_lock rw_lock_irq \
	 mutex_lock ww_mutex_lock rwsem_lock rtmutex_lock percpu_rwsem_lock; do
	mark "torture $t"
	modprobe locktorture torture_type=$t stat_interval=0 || { echo "modprobe failed"; continue; }
	sleep 60
	rmmod locktorture
	since "torture $t" | grep -E "End of test|Writes:|Reads:" | sed 's/^\[[^]]*\] //' | tail -3
done

# ---- ww_mutex self test (runs at load) ----------------------------------------------
mark "test-ww_mutex"
timeout 900 modprobe test-ww_mutex; echo "modprobe rc=$?"
since "test-ww_mutex" | sed 's/^\[[^]]*\] //' | tail -8
rmmod test_ww_mutex 2>/dev/null

# ---- data-checked syscall stress (bench/api_stress.c) -------------------------------
mark "api_stress"
ulimit -n 65536
for m in setfd ofd pipe seek uts xattr; do
	for n in 16 64; do
		/root/api_stress $m $n 20 > /tmp/kda_o 2> /tmp/kda_e; rc=$?
		echo "$m n$n rc=$rc $(tail -1 /tmp/kda_o) $(head -c 200 /tmp/kda_e)"
	done
done

# ---- will-it-scale with page checks, 64 workers ------------------------------------
mark "wis"
for t in page_fault_shared1 page_fault_shared2 page_fault_shared3 page_fault1 mmap1 mmap2 brk1; do
	for m in threads processes; do
		r=$(cd /tmp && timeout 120 /root/wis/build/${t}_$m -t 64 -s 5 -n 1 2>&1 | grep -E "^average:|abort|page_fault_shared:" | tr '\n' ' ')
		echo "$t $m rc=${PIPESTATUS[0]} $r"
	done
done

# ---- a kernel build (defconfig) as a general load -------------------------------------
mark "kbuild"
S=/mnt/kdlock-builds/kda/src; B=/mnt/kdlock-builds/stress-$TAG
rm -rf $B; mkdir -p $B
make -C $S O=$B defconfig > /dev/null 2>&1
t0=$(date +%s.%N); make -C $S O=$B -j64 bzImage > $B.log 2>&1; rc=$?
echo "kbuild rc=$rc elapsed $(echo "$(date +%s.%N) - $t0" | bc) s"
tail -1 $B.log; ls -la $B/arch/x86/boot/bzImage
rm -rf $B

# ---- the bench module's correctness pass (kdall only; no daemon) --------------------
if [ -f /root/kdb_all/bench/kd_bench.ko ] && uname -r | grep -q kdall; then
	mark "run_corr"
	insmod /root/kdb_all/bench/kd_bench.ko && \
	python3 /root/host_fs/kdlock/bench/run_corr.py --out $O/corr-$TAG.jsonl --backends native kd > $O/corr-$TAG.out 2>&1
	echo "run_corr rc=$?"; tail -5 $O/corr-$TAG.out
	rmmod kd_bench
fi

mark done
echo "complaints since start:"; since kernel | grep -iE "BUG:|WARNING:|lockup|hung_task|blocked for more|Call Trace|rcu.*stall|torture.*FAIL" | head -30
grep -E "^(delegation|sessions|delegated|handback)\b" /sys/kernel/debug/kdlock_stats 2>/dev/null | head
echo KDA_TEST_DONE
