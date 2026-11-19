#!/bin/bash
# pcpu_check.sh TAG: on a fresh kdall boot, kd on (daemon, the comparison's
# allow lists: api, torture, mm), read the memcg per-CPU local trylock bytes
# (/root/pcpu.py, from lkp-macro-20261118-64cpu) before anything and after
# each delegated workload: will-it-scale mmap1, mmap2, brk1, page_fault1
# (64 threads, 10 s) and Apache single process (64 threads, wrk 10 s).
# Output: /root/appgrid/TAG-pcpu.txt
TAG=${1:?tag}
O=/root/appgrid; exec > $O/$TAG-pcpu.txt 2>&1
AL=/root/host_fs/kdlock/bench/allow; A=/root/appbench; H=/usr/local/apache2; I=$A/ivm/apache
ulimit -c 0; ulimit -n 65536
pc() { echo "-- $1: $(python3 /root/pcpu.py obj_stock memcg_stock | tr '\n' ' ')"; }
st() { awk '$1 ~ /^(delegated|handback|hb_miss|hb_frontier|vdown_hb)$/ {printf "%s %s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
uname -rv; uptime
pc "fresh boot"
cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/allow_cmp.txt
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_cmp.json \
	--allow /root/allow_cmp.txt -v > $O/$TAG-pcpu.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_pcpu.pid)
sleep 10
pc "daemon started"
cd $A/tclocks/will-it-scale
for t in mmap1 mmap2 brk1 page_fault1; do
	./build/${t}_threads -t 64 -s 10 -n 32 2>&1 | grep "^average:"
	pc "after $t | $(st)"
done
cp $I/index_64KB.html $H/htdocs/index.html; cp $I/httpd.conf $H/conf/httpd.conf
cp $I/httpd-mpm-single-process.conf $H/conf/extra/httpd-mpm.conf; python3 $I/edit_mpm.py 64 64 > /dev/null
$H/bin/apachectl -k start 2> /dev/null; sleep 2
$A/wrk/wrk -t64 -c100 -d10s http://localhost/ 2>&1 | grep "Requests/sec"
$H/bin/apachectl -k stop 2> /dev/null; sleep 5
pc "after apache single | $(st)"
kill -INT $(cat /root/kdd_pcpu.pid)
echo PCPU_DONE
