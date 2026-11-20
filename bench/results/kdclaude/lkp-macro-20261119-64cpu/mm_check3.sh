#!/bin/bash
# The same with a new state file: does learning converge within a few short runs?
O=/root/lkpres; T=/root/appbench/tclocks/will-it-scale
K="delegated handback hb_frontier hb_miss vdown vdown_hb offered site_retry"
c() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
d() { python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split()); b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b if int(b[k]) != int(a.get(k, 0))))' "$1" "$2"; }
rm -f /root/kds_test.json
(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_test.json --allow $1 -v > $O/kdd-mmcheck3.log 2>&1 < /dev/null &)
sleep 10
for r in 1 2 3 4 5 6; do
	a=$(c); v=$(cd $T && timeout 60 setarch linux64 -R ./build/mmap1_threads -t 16 -s 6 -n 32 | grep "^average:" | cut -d: -f2); echo "$(date +%T) run $r mmap1 16: $v | $(d "$a" "$(c)")"
done
P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for i in $(seq 90); do kill -0 $P 2>/dev/null || break; sleep 1; done
grep -E "handback at|miss" $O/kdd-mmcheck3.log | sed "s/site 0x[0-9a-f]*: //; s/, exit.*//; s/ -> .*//" | sort | uniq -c | sort -rn | head -5; grep -c "instructions" $O/kdd-mmcheck3.log
echo MM_CHECK3_DONE
