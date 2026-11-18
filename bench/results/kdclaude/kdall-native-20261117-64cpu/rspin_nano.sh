#!/bin/bash
# rspin_nano.sh TAG: on a kdnat kernel (native locks, kdlock built in, the
# bench module loaded), the rwsem nano bodies with readers at 32 and 64
# workers: native, and kd with kd_rwsem_rspin_ns 50000 (default), 5000 and
# 0, 2 rounds with the order of the kd settings rotated. What the reader
# spin time is worth to reader-heavy bodies (section 8.5).
# Output: /root/natc/TAG-rspin.jsonl.<setting>
TAG=${1:?tag}
O=/root/natc; mkdir -p $O
P=/sys/module/kernel/parameters/kd_rwsem_rspin_ns
orig=$(cat $P)
PROFILES="rwsem_c01_w20 rwsem_c16_w20 rwsem_c01_w1 rwsem_c16_w1"
cd /root/host_fs/kdlock/bench
rm -f $O/$TAG-rspin.jsonl.*
cfgs=(50000 5000 0)
for r in 1 2; do
	python3 run_grid.py --out $O/$TAG-rspin.jsonl.native --profiles $PROFILES --backends native \
		--workers 32 64 --rounds 1 --ms 2000 --commit "$(uname -r)" > /dev/null 2>&1 || echo "native grid failed"
	for i in 0 1 2; do
		c=${cfgs[$(( (i + r - 1) % 3 ))]}
		echo $c > $P || exit 1
		python3 run_grid.py --out $O/$TAG-rspin.jsonl.$c --profiles $PROFILES --backends kd \
			--workers 32 64 --rounds 1 --ms 2000 --commit "$(uname -r)-rspin$c" > /dev/null 2>&1 || echo "grid failed: $c"
	done
done
echo $orig > $P
echo RSPIN_DONE
