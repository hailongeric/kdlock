#!/bin/bash
# stress-ng seccomp with the daemon (lkp allow lists), 36 runs: per run the SIGSYS kills logged and the deltas of the
# handback and region counters; the daemon writes the per-CPU data of every image (--gs-report).
B=/root/lkpbench/stress-ng/stress-ng; O=/root/lkpres; AL=/root/host_fs/kdlock/bench/allow
K="delegated handback hb_frontier hb_miss hb_acquire hb_other hb_region done_in_region handback_pinned vdown_hb"
c() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
d() { python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split()); b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b if int(b[k]) != int(a.get(k, 0))))' "$1" "$2"; }
sysctl -q kernel.print-fatal-signals=1; ulimit -c 0
mkdir -p /root/lkpsng; mountpoint -q /root/lkpsng || mount -t tmpfs -o size=8G tmpfs /root/lkpsng
for a in api torture mm lkp; do cat $AL/$a.txt; done > $O/tmp/on.allow
rm -f /root/kds_secc.json $O/gs-secc.jsonl
(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_secc.json --allow $O/tmp/on.allow -v --gs-report $O/gs-secc.jsonl > $O/kdd-secc-gs.log 2>&1 < /dev/null &)
sleep 10
for i in $(seq ${RUNS:-36}); do
	s0=$(dmesg | grep -c "fatal signal 31"); a=$(c)
	(cd /root/lkpsng && timeout 66 $B --seccomp 64 --timeout 6 --verify --metrics --no-rand-seed --temp-path /root/lkpsng > /dev/null 2>&1)
	echo "run $i SIGSYS $(( $(dmesg | grep -c "fatal signal 31") - s0 )) | $(d "$a" "$(c)")"
done
P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for j in $(seq 120); do kill -0 $P 2>/dev/null || break; sleep 1; done
grep -c . $O/gs-secc.jsonl; tail -3 $O/kdd-secc-gs.log | cut -c1-200
cd /; umount /root/lkpsng; echo SECC_GS_DONE
