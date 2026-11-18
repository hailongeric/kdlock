#!/bin/bash
# rstall_ab.sh TAG: in one boot of a kdall kernel that has the reader stall
# rule (kd_rwsem_rstall_ns), no daemon.
#   1. will-it-scale (threads) page_fault1 at 8, 16 and 32 threads,
#      page_fault_shared3 at 16 and 32, mmap1 at 16 and 64, mmap2 and brk1
#      at 64, 5 s each, under three settings, 3 rounds with the order
#      rotated, with the reader counters of each run:
#        stall    the defaults
#        nostall  kd_rwsem_rstall_ns=0 (every reader spins its full time)
#        rspin0   kd_rwsem_rspin_ns=0 (readers never spin; MMAP_LOCKS 5)
#   2. the rwsem nano bodies with readers (kd backend) at 32 and 64 workers
#      under stall and nostall, 2 rounds alternating. The bench module must
#      be loaded.
# Output: /root/rstall/TAG.txt, /root/rstall/TAG-nano.jsonl.<setting>
TAG=${1:?tag}
O=/root/rstall; mkdir -p $O; exec > $O/$TAG.txt 2>&1
P=/sys/module/kernel/parameters
uname -rv
[ -w $P/kd_rwsem_rstall_ns ] || { echo "no kd_rwsem_rstall_ns"; exit 1; }
st0=$(cat $P/kd_rwsem_rstall_ns); sp0=$(cat $P/kd_rwsem_rspin_ns)
echo "defaults: kd_rwsem_rstall_ns $st0 kd_rwsem_rspin_ns $sp0"
st() { grep -vE "^#" /sys/kernel/debug/kdlock_stats; }
complaints() { dmesg | grep -ciE "BUG:|lockup|hung_task|blocked for more|rcu.*stall"; }
c0=$(complaints)
setcfg() {
	case $1 in
	stall)   echo $st0 > $P/kd_rwsem_rstall_ns; echo $sp0 > $P/kd_rwsem_rspin_ns ;;
	nostall) echo 0 > $P/kd_rwsem_rstall_ns;    echo $sp0 > $P/kd_rwsem_rspin_ns ;;
	rspin0)  echo $st0 > $P/kd_rwsem_rstall_ns; echo 0 > $P/kd_rwsem_rspin_ns ;;
	esac
}
ulimit -n 65536
cfgs=(stall nostall rspin0)
cd /tmp
for r in 1 2 3; do
	for i in 0 1 2; do
		c=${cfgs[$(( (i + r - 1) % 3 ))]}
		setcfg $c
		for tn in "page_fault1 8" "page_fault1 16" "page_fault1 32" \
			  "page_fault_shared3 16" "page_fault_shared3 32" \
			  "mmap1 16" "mmap1 64" "mmap2 64" "brk1 64"; do
			set -- $tn
			st > /tmp/rs0
			v=$(timeout 60 /root/wis/build/$1_threads -t $2 -s 5 -n 1 2>&1 | grep -E "^average:" | sed 's/average://; s/:.*//')
			st > /tmp/rs1
			echo "$c $1 $2 round $r rate ${v:-0} |" \
				$(join <(sort /tmp/rs0) <(sort /tmp/rs1) | \
				  awk '$3 != $2 && $1 ~ /^(rd_behind|rd_queue|rd_stall|parked)$/ {printf "%s %d ", $1, $3 - $2}')
		done
	done
done
cd /root/host_fs/kdlock/bench
rm -f $O/$TAG-nano.jsonl.*
for r in 1 2; do
	if [ $r = 1 ]; then order="stall nostall"; else order="nostall stall"; fi
	for c in $order; do
		setcfg $c
		python3 run_grid.py --out $O/$TAG-nano.jsonl.$c \
			--profiles rwsem_c01_w20 rwsem_c16_w20 rwsem_c01_w1 rwsem_c16_w1 \
			--backends kd --workers 32 64 --rounds 1 --ms 2000 \
			--commit "$(uname -r)-$c" > /dev/null 2>&1 || echo "grid failed: $c round $r"
	done
done
setcfg stall
echo "complaints $(( $(complaints) - c0 ))"
echo RSTALL_DONE
