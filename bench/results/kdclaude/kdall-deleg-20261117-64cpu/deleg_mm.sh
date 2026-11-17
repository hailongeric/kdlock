#!/bin/bash
# deleg_mm.sh: kdall1, delegation of the mmap_lock writers of brk(), mmap()
# and munmap() (bench/allow/mm.txt) off against on, alternated in one boot.
# Two learning passes, then 3 rounds. Output: /root/dmm/ab.txt
O=/root/dmm; mkdir -p $O; exec > $O/ab.txt 2> $O/ab.err
A=/root/host_fs/kdlock/bench/allow
S=/root/kds_mm.json
# Images stay loaded after their daemon exits, and the kernel requests a
# build only for a site without one: drop the previous run's images so that
# the first pass does not run code from an earlier translator.
[ -f $S ] && /root/kdvenv/bin/python - $S <<'EOF'
import json, sys
sys.path.insert(0, "/root/host_fs/kdlock/jit")
from kdjit.kernel import Device
dev = Device()
for site in json.load(open(sys.argv[1]))["sites"]:
    try:
        dev.site_drop(int(site))
        print("dropped image of site %#x" % int(site))
    except OSError as err:
        print("site %#x: %s" % (int(site), err))
EOF
rm -f $S
# Counters per run: delegated, handback, and the handback causes.
C="delegated handback hb_frontier hb_miss hb_acquire hb_downgrade hb_other offered"
st() {
	local k
	for k in $C; do awk -v k=$k '$1 == k {printf "%s ", $2}' /sys/kernel/debug/kdlock_stats; done
}
d_on() {
	ps -e -o cmd | grep -q "^/root/kdvenv/bin/python -u kd_daemon.py" && { echo "a daemon is running"; exit 1; }
	# cd first: "cd && cmd &" would background a subshell, and $! would be
	# that shell, not the daemon.
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state $S \
		--allow $A/mm.txt -v >> $O/kdd.log 2>&1 < /dev/null &
	 echo $! > /root/kdd_mm.pid)
	sleep 8	# republish the stored sites
}
d_off() {
	P=$(cat /root/kdd_mm.pid); kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
	kill -0 $P 2>/dev/null && { echo "daemon $P did not stop"; exit 1; }
}
run() {	# run TAG: one pass over every workload, one line each
	local tag=$1 s0 r
	for t in mmap1 mmap2 brk1; do for n in 16 32 64; do
		s0=$(st); r=$(cd /tmp && timeout 60 /root/wis/build/${t}_threads -t $n -s 5 -n 1 2>&1 | grep -E "^average:|abort" | tr '\n' ' ')
		echo "$tag wis $t $n $r | $s0| $(st)"
	done; done
}
echo "counters: $C"
uname -rv
d_on; run learn1; run learn2; d_off
for r in 1 2 3; do
	if [ $((r % 2)) = 1 ]; then run r$r-off; d_on; run r$r-on; d_off
	else d_on; run r$r-on; d_off; run r$r-off; fi
done
echo "complaints:"; dmesg | grep -iE "BUG:|WARNING:|lockup|hung_task|blocked for more|rcu.*stall" | head -20
echo AB_DONE
