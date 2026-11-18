#!/bin/bash
# woken_ab.sh TAG: in one boot of a kdall kernel that has KD_QF_WOKEN, no
# daemon. locktorture mutex_lock and ww_mutex_lock with 64 and 128 writers
# and rwsem_lock with its defaults, 30 s each, under kd_mutex_woken=1 and
# kd_mutex_woken=0, 3 rounds with the order of the two settings
# alternating. Then the wakeup counts (mutex_wake.sh) with 64 and 128
# writers under both settings, and a flat profile with 64 writers
# (ltprof.sh) under the default.
# Output: /root/woken/TAG.txt
TAG=${1:?tag}
O=/root/woken; mkdir -p $O; exec > $O/$TAG.txt 2>&1
D=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
P=/sys/module/kernel/parameters
uname -rv
[ -w $P/kd_mutex_woken ] || { echo "no kd_mutex_woken"; exit 1; }
st() { grep -vE "^#" /sys/kernel/debug/kdlock_stats; }
complaints() { dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall"; }
c0=$(complaints)

# run SETTING TYPE WRITERS ROUND (WRITERS "def": the module's default)
run() {
	local m="woken: $TAG $*" w e
	echo $1 > $P/kd_mutex_woken
	echo "$m" > /dev/kmsg
	st > /tmp/wk0
	if [ $3 = def ]; then
		modprobe locktorture torture_type=$2 stat_interval=0
	else
		modprobe locktorture torture_type=$2 nwriters_stress=$3 stat_interval=0
	fi
	sleep 30
	rmmod locktorture
	st > /tmp/wk1
	w=$(dmesg | awk -v m="$m" 'index($0,m){f=1} f' | grep -E "Writes:" | tail -1 | sed 's/.*Total: *//; s/ .*//')
	e=$(dmesg | awk -v m="$m" 'index($0,m){f=1} f' | grep -cE "End of test: SUCCESS")
	echo "woken=$1 $2 $3 round $4 writes ${w:-0} success $e |" \
		$(join <(sort /tmp/wk0) <(sort /tmp/wk1) | \
		  awk '$3 != $2 && $1 ~ /^(abandon|handoff|head_sleep|no_spin|parked)$/ {printf "%s %d ", $1, $3 - $2}')
}

for r in 1 2 3; do
	if [ $((r % 2)) = 1 ]; then order="1 0"; else order="0 1"; fi
	for s in $order; do
		for t in "mutex_lock 64" "mutex_lock 128" "ww_mutex_lock 64" \
			 "ww_mutex_lock 128" "rwsem_lock def"; do
			run $s $t $r
		done
	done
done
echo 1 > $P/kd_mutex_woken
for w in 64 128; do
	for s in 1 0; do
		W=$w bash $D/mutex_wake.sh $TAG-w$w-woken$s kd_mutex_woken=$s
		cat /root/mwake/$TAG-w$w-woken$s.txt
	done
done
bash $D/ltprof.sh $TAG-woken1 && cat /root/ltw/$TAG-woken1-prof.txt
echo "complaints $(( $(complaints) - c0 ))"
echo WOKEN_DONE
