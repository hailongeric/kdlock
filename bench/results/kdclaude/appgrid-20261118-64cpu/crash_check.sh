#!/bin/bash
# crash_check.sh MODE TAG: are the two process crashes seen in g1 on (an
# httpd worker in a core dump at an `apachectl -k stop`, a page_fault2
# threads process segfaulting in libc) tied to the kernel's locks or to
# delegation? MODE as in app_grid.sh (native, off, on). Fatal signals are
# logged (kernel.print-fatal-signals) and no core files are written.
#   apache: 22 cycles of the single-process configuration (1-64 threads)
#           and 5 of the default one; start, wrk 3 s, stop, then count the
#           httpd processes still there after 30 s
#   wis:    page_fault2_threads and page_fault1_threads at 16, 32 and 64
#           threads, 10 runs of 2 s each
# Output: /root/appgrid/TAG-MODE-crash.txt
MODE=${1:?mode}; TAG=${2:?tag}
O=/root/appgrid; mkdir -p $O; exec > $O/$TAG-$MODE-crash.txt 2>&1
A=/root/appbench; H=/usr/local/apache2; I=$A/ivm/apache
AL=/root/host_fs/kdlock/bench/allow
ulimit -c 0; ulimit -n 65536
sysctl -q kernel.print-fatal-signals=1
fatal() { dmesg | grep -cE "potentially unexpected fatal signal|segfault at|trap invalid opcode"; }
uname -rv
if [ $MODE = on ]; then
	cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/allow_cmp.txt
	(cd /root/host_fs/kdlock/jit || exit 1
	 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_cmp.json \
		--allow /root/allow_cmp.txt -v > $O/$TAG-crash.kdd 2>&1 < /dev/null &
	 echo $! > /root/kdd_crash.pid)
	sleep 10
fi
st() { [ -r /sys/kernel/debug/kdlock_stats ] && awk '$1 == "delegated" || $1 == "handback" {printf "%s %s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
cycle() {	# cycle CONF [THREADS]
	local f0=$(fatal) left i r
	cp $I/index_64KB.html $H/htdocs/index.html; cp $I/httpd.conf $H/conf/httpd.conf
	cp $I/$1 $H/conf/extra/httpd-mpm.conf
	[ -n "$2" ] && python3 $I/edit_mpm.py $2 64 > /dev/null
	$H/bin/apachectl -k start 2> /dev/null; sleep 2
	r=$($A/wrk/wrk -t64 -c100 -d3s http://localhost/ 2>&1 | sed -n 's/^Requests\/sec: *//p')
	$H/bin/apachectl -k stop 2> /dev/null
	for i in $(seq 30); do pgrep -x httpd > /dev/null || break; sleep 1; done
	left=$(pgrep -x httpd | wc -l)
	echo "apache $1 ${2:-default} req/s ${r:-0} left $left fatal $(( $(fatal) - f0 )) | $(st)"
	[ $left -gt 0 ] && { pkill -9 -x httpd; sleep 1; }
}
for n in 1 2 3 4 5 6 7 8 $(seq 12 4 64); do cycle httpd-mpm-single-process.conf $n; done
for i in 1 2 3 4 5; do cycle httpd-mpm-default.conf; done
mountpoint -q /tmp || mount -t tmpfs -o size=10G tmpfs /tmp
cd $A/tclocks/will-it-scale
for t in page_fault2 page_fault1; do for n in 16 32 64; do
	f0=$(fatal); bad=0
	for i in $(seq 10); do
		./build/${t}_threads -t $n -s 2 -n 32 2>&1 | grep -q "^average:" || bad=$((bad + 1))
	done
	echo "wis $t $n runs 10 without_result $bad fatal $(( $(fatal) - f0 )) | $(st)"
done; done
if [ $MODE = on ]; then
	P=$(cat /root/kdd_crash.pid); kill -INT $P
	for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
fi
echo "-- fatal signal lines"
dmesg | grep -E "potentially unexpected fatal signal|segfault at" | tail -20
echo CRASH_DONE
