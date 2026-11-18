#!/bin/bash
# wis_exit_check.sh TAG: kd on (daemon, the comparison's allow lists,
# defaults), will-it-scale page_fault2/page_fault1/mmap1 threads at 16, 32
# and 64 threads, 10 runs of 2 s each: runs without a result and fatal
# signals (the page_fault2 exit segfault of g1 on, section 6).
# Output: /root/appgrid/TAG-wisexit.txt
TAG=${1:?tag}
O=/root/appgrid; exec > $O/$TAG-wisexit.txt 2>&1
AL=/root/host_fs/kdlock/bench/allow
ulimit -c 0; sysctl -q kernel.print-fatal-signals=1
fatal() { dmesg | grep -cE "potentially unexpected fatal signal|segfault at"; }
uname -rv
cat $AL/api.txt $AL/torture.txt $AL/mm.txt > /root/allow_cmp.txt
(cd /root/host_fs/kdlock/jit || exit 1
 setsid nohup /root/kdvenv/bin/python -u kd_daemon.py --state /root/kds_cmp.json \
	--allow /root/allow_cmp.txt -v > $O/$TAG-wisexit.kdd 2>&1 < /dev/null &
 echo $! > /root/kdd_wisexit.pid)
sleep 10
cd /root/appbench/tclocks/will-it-scale
for t in page_fault2 page_fault1 mmap1; do for n in 16 32 64; do
	f0=$(fatal); bad=0
	for i in $(seq 10); do
		timeout 60 ./build/${t}_threads -t $n -s 2 -n 32 2>&1 | grep -q "^average:" || bad=$((bad + 1))
	done
	echo "wis $t $n runs 10 without_result $bad fatal $(( $(fatal) - f0 ))"
done; done
kill -INT $(cat /root/kdd_wisexit.pid)
dmesg | grep -E "potentially unexpected fatal signal|segfault at" | tail -5
echo WISEXIT_DONE
