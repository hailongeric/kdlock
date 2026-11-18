#!/bin/bash
# vdown_ab.sh TAG: kd on (daemon, the comparison's allow lists), Apache's
# default configuration, 8 cycles of start / wrk 3 s / stop, first with
# kd_vdown=0, then with kd_vdown=1. A cycle after which an httpd process is
# still there 30 s after the stop ends that setting; the mmap lock states
# of the processes left are then printed (/root/mmdump/kd_mmdump.ko) and
# the run stops, since their exit cannot finish (README section 6).
# Output: /root/appgrid/TAG-vdown.txt
TAG=${1:?tag}
O=/root/appgrid; exec > $O/$TAG-vdown.txt 2>&1
A=/root/appbench; H=/usr/local/apache2; I=$A/ivm/apache
AL=/root/host_fs/kdlock/bench/allow; P=/sys/module/kernel/parameters
ulimit -c 0; ulimit -n 65536
sysctl -q kernel.print-fatal-signals=1
uname -rv
cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/allow_cmp.txt
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_cmp.json \
	--allow /root/allow_cmp.txt -v > $O/$TAG-vdown.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_vdown.pid)
sleep 10
st() { awk '$1 ~ /^(delegated|handback|vdown|vdown_hb|xchg_taken|nested_delegated)$/ {printf "%s %s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
cp $I/index_64KB.html $H/htdocs/index.html; cp $I/httpd.conf $H/conf/httpd.conf
cp $I/httpd-mpm-default.conf $H/conf/extra/httpd-mpm.conf
for v in 0 1; do
	echo $v > $P/kd_vdown
	for c in 1 2 3 4 5 6 7 8; do
		$H/bin/apachectl -k start 2> /dev/null; sleep 2
		r=$($A/wrk/wrk -t64 -c100 -d3s http://localhost/ 2>&1 | sed -n 's/^Requests\/sec: *//p')
		$H/bin/apachectl -k stop 2> /dev/null
		for i in $(seq 30); do [ -z "$(pgrep -x httpd)" ] && break; sleep 1; done
		left=$(pgrep -x httpd | wc -l)
		echo "kd_vdown=$v cycle $c req/s ${r:-0} left $left | $(st)"
		if [ $left -gt 0 ]; then
			echo "kdmm: vdown $v cycle $c" > /dev/kmsg
			insmod /root/mmdump/kd_mmdump.ko 2> /dev/null
			dmesg | awk "/kdmm: vdown $v cycle $c/{f=1} f" | grep "kd_mmdump: pid"
			echo VDOWN_HUNG
			exit 0
		fi
	done
done
echo 1 > $P/kd_vdown
D=$(cat /root/kdd_vdown.pid); kill -INT $D
echo VDOWN_DONE
