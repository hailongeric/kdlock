#!/bin/bash
# repro_variant.sh NAME VDOWN XCHG FUNC...: kd on with the daemon allowed
# only FUNC... (functions of bench/allow/mm.txt), kd_vdown=VDOWN,
# kd_xchg=XCHG; Apache's default configuration, up to CYCLES (default 8) cycles of start /
# wrk 3 s / stop. Prints CLEAN, or HUNG with the mmap lock states of the
# httpd processes that cannot exit (section 6). httpd processes are found
# through /proc/*/comm, which does not need their mm (pgrep can block on a
# stuck mmap lock). Output: /root/appgrid/repro-NAME.txt
NAME=${1:?name}; V=${2:?vdown}; X=${3:?xchg}; shift 3
O=/root/appgrid; exec > $O/repro-$NAME.txt 2>&1
A=/root/appbench; H=/usr/local/apache2; I=$A/ivm/apache; P=/sys/module/kernel/parameters
ulimit -c 0; ulimit -n 65536
sysctl -q kernel.print-fatal-signals=1
nhttpd() { cat /proc/[0-9]*/comm 2>/dev/null | grep -cx httpd; }
uname -rv; echo "kd_vdown=$V kd_xchg=$X allow: $*"
# The lock state dump module, for this kernel build.
(cd /root/mmdump && make -C /lib/modules/$(uname -r)/build M=/root/mmdump modules > /dev/null 2>&1)
dmesg -n 8 2>/dev/null
printf '%s\n' "$@" > /root/allow_repro.txt
echo $V > $P/kd_vdown; echo $X > $P/kd_xchg
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_cmp.json \
	--allow /root/allow_repro.txt -v > $O/repro-$NAME.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_repro.pid)
sleep 10
st() { awk '$1 ~ /^(delegated|handback|vdown|vdown_hb|xchg_taken|nested_delegated)$/ {printf "%s %s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
cp $I/index_64KB.html $H/htdocs/index.html; cp $I/httpd.conf $H/conf/httpd.conf
cp $I/httpd-mpm-default.conf $H/conf/extra/httpd-mpm.conf
for c in $(seq ${CYCLES:-8}); do
	$H/bin/apachectl -k start 2> /dev/null; sleep 2
	r=$($A/wrk/wrk -t64 -c100 -d3s http://localhost/ 2>&1 | sed -n 's/^Requests\/sec: *//p')
	$H/bin/apachectl -k stop 2> /dev/null
	for i in $(seq 30); do [ "$(nhttpd)" = 0 ] && break; sleep 1; done
	left=$(nhttpd)
	echo "cycle $c req/s ${r:-0} left $left | $(st)"
	if [ $left -gt 0 ]; then
		echo "kdmm: repro $NAME" > /dev/kmsg
		insmod /root/mmdump/kd_mmdump.ko 2> /dev/null
		dmesg | awk "/kdmm: repro $NAME/{f=1} f" | grep "kd_mmdump: pid"
		echo HUNG
		exit 0
	fi
done
kill -INT $(cat /root/kdd_repro.pid)
echo CLEAN
