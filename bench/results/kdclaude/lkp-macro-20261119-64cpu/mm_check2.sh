#!/bin/bash
O=/root/lkpres; W=/root/lkpbench/wis-upstream; T=/root/appbench/tclocks/will-it-scale
K="delegated handback hb_frontier hb_miss hb_acquire hb_downgrade hb_other hb_region vdown vdown_hb offered site_retry"
c() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
d() { python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split()); b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b if int(b[k]) != int(a.get(k, 0))))' "$1" "$2"; }
(cd /root/host_fs/kdlock/jit && setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_lkp.json --allow ${ALLOWF:-$O/tmp/on.allow} -v > $O/kdd-mmcheck2.log 2>&1 < /dev/null &)
sleep 20
a=$(c); v=$(cd $O/tmp && timeout 60 $W/mmap1_threads -t 64 -s 6 | grep "^average:" | cut -d: -f2); echo "upstream mmap1 64: $v | $(d "$a" "$(c)")"
a=$(c); v=$(cd $T && timeout 60 setarch linux64 -R ./build/mmap1_threads -t 60 -s 6 -n 32 | grep "^average:" | cut -d: -f2); echo "tclocks mmap1 60: $v | $(d "$a" "$(c)")"
a=$(c); v=$(cd $T && timeout 60 setarch linux64 -R ./build/mmap1_threads -t 16 -s 6 -n 32 | grep "^average:" | cut -d: -f2); echo "tclocks mmap1 16: $v | $(d "$a" "$(c)")"
a=$(c); v=$(cd $O/tmp && timeout 60 $W/mmap1_threads -t 16 -s 6 | grep "^average:" | cut -d: -f2); echo "upstream mmap1 16: $v | $(d "$a" "$(c)")"
P=$(ps -e -o pid,cmd | awk '/[k]d_daemon.py/ {print $1}' | head -1); kill -INT $P; for i in $(seq 90); do kill -0 $P 2>/dev/null || break; sleep 1; done
grep -E "handback at|miss" $O/kdd-mmcheck2.log | sed "s/site 0x[0-9a-f]*: //; s/, exit.*//; s/ -> .*//" | sort | uniq -c | sort -rn | head -6
echo MM_CHECK2_DONE
