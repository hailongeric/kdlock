#!/bin/bash
cd /root/host_fs/kdlock/bench
D=/sys/module/kernel/parameters
for cfg in "200000 5000" "200000 0" "0 5000" "200000 5000"; do
	set -- $cfg
	echo $1 > $D/kd_rw_era_ns || exit 1
	echo $2 > $D/kd_rw_era_drain_ns || exit 1
	echo "era_ns $(cat $D/kd_rw_era_ns) drain_ns $(cat $D/kd_rw_era_drain_ns)"
	rm -f /root/split.jsonl
	python3 run_grid.py --out /root/split.jsonl --profiles rwsem_c01_w100 --workers 32 --rounds 2 --ms 2000 --commit split > /dev/null 2>&1
	python3 -c '
import json
for l in open("/root/split.jsonl"):
    r = json.loads(l)
    d = r.get("kd_delta") or {}
    print("   ", r["backend"], "%.2f" % r["mops"], {k: v for k, v in d.items() if k.startswith("era") and v})
'
done
