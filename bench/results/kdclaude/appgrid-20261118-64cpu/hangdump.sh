#!/bin/bash
# Evidence for the httpd exit hang: every task whose kernel stack shows kd
# code or mm work, every httpd/wrk task's state and stack, kd counters.
O=/root/appgrid/hang-$(date +%H%M%S); mkdir -p $O
for d in /proc/[0-9]*; do
	p=${d#/proc/}; c=$(cut -d' ' -f2 $d/stat 2>/dev/null)
	for t in $d/task/*; do
		st=$(timeout 2 cat $t/stack 2>/dev/null)
		s=$(cut -d' ' -f3 $t/stat 2>/dev/null)
		if echo "$st" | grep -qE "kd_|mmap|munmap|brk|vm_|exit_mm|coredump" || echo "$c" | grep -qE "httpd|wrk"; then
			echo "== pid $p tid ${t##*/} $c state $s wchan $(cat $t/wchan 2>/dev/null)"
			echo "$st" | head -20
		fi
	done
done > $O/stacks.txt 2>&1
grep -vE "^#" /sys/kernel/debug/kdlock_stats > $O/kdstats.txt
dmesg > $O/dmesg.txt
cp /proc/meminfo $O/
ps -eo pid,stat,wchan:30,comm --no-headers 2>/dev/null | grep -vE " S .* (kworker|ksoftirq|migration|rcu|cpuhp|idle_inject)" > $O/ps.txt
echo $O
