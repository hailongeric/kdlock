#!/bin/bash
# fix_ab.sh TAG: one fresh kdall boot, three modes in this order:
#   off   no daemon (every lock a kdlock, plain mode)
#   new   kd_daemon.py with the translator of this tree (per-CPU regions)
#   old   kd_daemon.py with the translator of commit OLD (default b6041b6f,
#         before the per-CPU regions), from /root/jit_old
# "old" runs last: it can leave per-CPU lock bytes set (README section 6),
# which would slow the modes after it. A daemon that exits leaves its
# images loaded, so each daemon mode starts by dropping every site the
# previous one built (drop_sites.py). Each mode: the comparison's allow
# lists (api, torture, mm), warm-up passes (mmap1, mmap2, brk1 at 8, 32 and
# 64 threads, 5 s each) until a pass adds fewer than 1000 translation misses
# (at most 10), then will-it-scale mmap1, mmap2, brk1 and page_fault1 at 1,
# 8, 32 and 64 threads, 10 s, two rounds. Each point is printed with the kd counters it
# added and the memcg per-CPU lock bytes (/root/pcpu.py) after it.
# Output: /root/appgrid/TAG-fixab.txt
TAG=${1:?tag}; OLD=${OLD:-b6041b6f}
O=/root/appgrid; exec > $O/$TAG-fixab.txt 2>&1
AL=/root/host_fs/kdlock/bench/allow; W=/root/appbench/tclocks/will-it-scale
ulimit -c 0
uname -rv; echo "old translator: $OLD ($(cat /root/jit_old/COMMIT 2>/dev/null))"
cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/allow_cmp.txt
K="delegated handback hb_miss hb_frontier hb_region done_in_region vdown_hb"
snap() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
diff_snap() {	# before after -> added
	python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split())
b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b))' "$1" "$2"
}
pc() { python3 /root/pcpu.py obj_stock memcg_stock | sed 's/acquired set on //; s/ CPUs.*//' | tr '\n' ' '; }
run() {	# mode
	local m=$1 t b r v s0 s1 p miss
	for p in 1 2 3 4 5 6 7 8 9 10; do
		s0=$(snap)
		for b in mmap1 mmap2 brk1; do for t in 8 32 64; do
			$W/build/${b}_threads -t $t -s 5 -n 32 > /dev/null 2>&1
		done; done
		s1=$(snap)
		echo "-- $m warm $p: $(diff_snap "$s0" "$s1")"
		miss=$(diff_snap "$s0" "$s1" | sed -n 's/.*hb_miss+\([0-9]*\).*/\1/p')
		[ "$m" = off ] || [ "${miss:-0}" -lt 1000 ] && break
	done
	echo "-- $m warm done: $(pc)"
	for r in 1 2; do for b in mmap1 mmap2 brk1 page_fault1; do for t in 1 8 32 64; do
		s0=$(snap)
		v=$($W/build/${b}_threads -t $t -s 10 -n 32 2>&1 | sed -n 's/^average://p' | cut -d: -f1)
		s1=$(snap)
		echo "$TAG $m $r $b $t ${v:-0} | $(diff_snap "$s0" "$s1") | $(pc)"
	done; done; done
}
daemon() {	# jit dir, state file
	(cd $1 || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $2 \
		--allow /root/allow_cmp.txt -v > $O/$TAG-fixab-$(basename $1).kdd 2>&1 < /dev/null &
	 echo $! > /root/kdd_fixab.pid)
	sleep 10
}
stop() {
	local p=$(cat /root/kdd_fixab.pid); kill -INT $p
	for i in $(seq 60); do kill -0 $p 2>/dev/null || break; sleep 1; done
}
echo "-- fresh: $(pc)"
run off
rm -f /root/kds_fixab_new.json /root/kds_fixab_old.json
daemon /root/host_fs/kdlock/jit /root/kds_fixab_new.json; run new; stop
python3 $(dirname $0)/drop_sites.py /root/kds_fixab_new.json
daemon /root/jit_old/jit /root/kds_fixab_old.json; run old; stop
python3 $(dirname $0)/drop_sites.py /root/kds_fixab_old.json
echo FIXAB_DONE
