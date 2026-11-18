#!/bin/bash
# kdall_check.sh TAG: on a kdall kernel, in one boot:
#   1. locktorture mutex_lock with the wakeup counts (mutex_wake.sh), no daemon;
#   2. locktorture ww_mutex_lock, mutex_lock and rwsem_lock, no daemon, 30 s,
#      2 runs each;
#   3. the rwsem era bound: kd_rwsem_era_ns at its default against 200 us,
#      mmap1/mmap2/brk1 with the mmap lock writers delegated (era_ab.sh);
#      ERA=0 in the environment skips this step;
#   4. correctness: run_corr.py plain and delegated (bench module only),
#      test-ww_mutex, and mm_stress with brk/mmap/munmap delegated.
# The bench module must be built and loaded. Output: /root/kdc6/TAG.out
TAG=${1:?tag}
O=/root/kdc6; mkdir -p $O; exec > $O/$TAG.out 2>&1
D=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
uname -rv
echo "== 1. wakeups"
bash $D/mutex_wake.sh $TAG-kd && cat /root/mwake/$TAG-kd.txt
echo "== 2. locktorture, no daemon"
for rep in 1 2; do for t in ww_mutex_lock mutex_lock rwsem_lock; do
	echo "kdc6: $TAG $t $rep" > /dev/kmsg
	modprobe locktorture torture_type=$t stat_interval=0; sleep 30; rmmod locktorture
	echo "$t $rep $(dmesg | awk -v m="kdc6: $TAG $t $rep" 'index($0,m){f=1} f' | grep -E "Writes:|End of test" | sed 's/.*Writes:/Writes:/; s/acq_writer.*//; s/.*End of test/End of test/' | tr '\n' ' ')"
done; done
echo "== 3. rwsem era bound"
if [ "${ERA:-1}" = 0 ]; then
	echo "skipped (ERA=0)"
else
	# Learn the mmap sites of this build first (the state file is per build).
	bash $D/mm_diag.sh $TAG-warm
	CFGS="base r200" PREFIX=$TAG-era bash $D/era_ab.sh
fi
echo "== 4. correctness"
cd /root/host_fs/kdlock/bench
python3 run_corr.py --out $O/$TAG-corr-plain.jsonl --tag $TAG-plain > $O/$TAG-corr-plain.out 2>&1; echo "corr plain exit $?"; tail -2 $O/$TAG-corr-plain.out
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state "" \
	--allow /root/host_fs/kdlock/bench/allow/kd_bench.txt -v > $O/$TAG-corr.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_kdc6.pid)
sleep 5
python3 run_corr.py --out $O/$TAG-corr-warm.jsonl --tag warm > /dev/null 2>&1
python3 run_corr.py --out $O/$TAG-corr-deleg.jsonl --tag $TAG-deleg > $O/$TAG-corr-deleg.out 2>&1; echo "corr deleg exit $?"; tail -2 $O/$TAG-corr-deleg.out
P=$(cat /root/kdd_kdc6.pid); kill -INT $P
for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
echo "kdc6: $TAG wwself" > /dev/kmsg
timeout 240 modprobe test-ww_mutex; echo "test-ww_mutex modprobe $?"
dmesg | awk -v m="kdc6: $TAG wwself" 'index($0,m){f=1} f' | grep -vE "kdc6:" | sed 's/^\[[^]]*\] //' | sort | uniq -c
rmmod test_ww_mutex 2>/dev/null
[ -d /root/dmm ] && mv /root/dmm /root/dmm-before-$TAG
bash /root/host_fs/kdlock/bench/results/kdclaude/kdall-deleg-20261117-64cpu/mm_check.sh
cat /root/dmm/check.txt
dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall" | sed 's/^/complaints /'
echo KDC_DONE
