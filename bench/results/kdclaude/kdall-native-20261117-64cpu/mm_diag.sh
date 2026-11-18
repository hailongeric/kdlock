#!/bin/bash
# mm_diag.sh TAG [KNOB=VALUE ...]: will-it-scale mmap1 (threads) with the
# mmap lock writers delegated (bench/allow/mm.txt), at 32, 48, 60 and 64
# workers, 5 s each; every kd counter that changed, and the context
# switches (/proc/stat ctxt), per run. KNOB=VALUE pairs set kernel
# parameters (/sys/module/kernel/parameters/KNOB) for the run and restore
# them afterwards. Output: /root/mdiag/TAG.txt
TAG=${1:?tag}; shift
O=/root/mdiag; mkdir -p $O; exec > $O/$TAG.txt 2>&1
A=/root/host_fs/kdlock/bench/allow
P=/sys/module/kernel/parameters
ST=/root/kds_mm.json
WORKERS=${WORKERS:-32 48 60 64}
TESTS=${TESTS:-mmap1}
uname -rv
ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
declare -A old
for kv in "$@"; do
	k=${kv%%=*}; v=${kv#*=}
	old[$k]=$(cat $P/$k) || exit 1
	echo $v > $P/$k || exit 1
	echo "set $k=$v (was ${old[$k]})"
done
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $ST --allow $A/mm.txt -v \
	>> $O/$TAG.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_diag.pid)
sleep 10
st() { grep -vE "^#" /sys/kernel/debug/kdlock_stats; }
ctxt() { awk '$1 == "ctxt" {print $2}' /proc/stat; }
cd /tmp
for t in $TESTS; do for n in $WORKERS; do
	st > /tmp/d0; c0=$(ctxt)
	r=$(timeout 60 /root/wis/build/${t}_threads -t $n -s 5 -n 1 2>&1 | grep -E "^average:" | sed 's/average://; s/:.*//')
	c1=$(ctxt); st > /tmp/d1
	echo "== $t $n rate ${r:-0} ctxt $((c1 - c0))"
	join <(sort /tmp/d0) <(sort /tmp/d1) | awk '$3 != $2 {printf "  %-16s %d\n", $1, $3 - $2}'
done; done
P2=$(cat /root/kdd_diag.pid); kill -INT $P2
for i in $(seq 60); do kill -0 $P2 2>/dev/null || break; sleep 1; done
for k in "${!old[@]}"; do echo ${old[$k]} > $P/$k; done
dmesg | grep -ciE "BUG:|lockup|hung_task|rcu.*stall" | sed 's/^/complaints /'
echo DIAG_DONE
