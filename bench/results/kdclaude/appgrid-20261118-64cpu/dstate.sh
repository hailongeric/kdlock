#!/bin/bash
# Tasks in D state and their kernel stacks, without reading cmdline.
for d in /proc/[0-9]*; do
	s=$(cut -d' ' -f3 $d/stat 2>/dev/null)
	[ "$s" = D ] || continue
	p=${d#/proc/}
	echo "== $p $(cut -d' ' -f2 $d/stat) ppid $(cut -d' ' -f4 $d/stat) threads $(ls $d/task | wc -l)"
	for t in $d/task/*; do
		ts=$(cut -d' ' -f3 $t/stat 2>/dev/null)
		[ "$ts" = D ] && { echo "  task ${t##*/} D"; timeout 2 cat $t/stack 2>/dev/null | head -12 | sed 's/^/    /'; }
	done
done | head -120
echo "-- dmesg"
dmesg | grep -E "blocked for more|hung_task|BUG:|lockup|segfault|fatal signal|Call Trace" | tail -10
