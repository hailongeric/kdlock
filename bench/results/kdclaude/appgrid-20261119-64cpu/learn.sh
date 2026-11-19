#!/bin/bash
# learn.sh TAG [PASSES]: learning passes for the daemon state of this build
# (/root/kds_cmp.json), not counted: the application grid in mode "on" at 8,
# 32 and 64 workers, PASSES times (default 2). The state persists across
# boots of the same build (nokaslr), so the measured "on" pass of a later
# fresh boot starts with these images. Each pass prints the counters it
# added; a pass that adds few hb_miss shows the state has converged.
# Output: /root/appgrid/TAG-learn.txt (and the usual lines under the tags
# TAG-learn1, TAG-learn2, ...).
TAG=${1:?tag}; N=${2:-2}
D=$(cd "$(dirname "$0")" && pwd)/../appgrid-20261118-64cpu
O=/root/appgrid; mkdir -p $O; exec > $O/$TAG-learn.txt 2>&1
K="delegated handback hb_miss hb_frontier hb_region done_in_region"
snap() { awk -v k=" $K " 'index(k, " " $1 " ") {printf "%s=%s ", $1, $2}' /sys/kernel/debug/kdlock_stats; }
uname -rv
ls -l /root/kds_cmp.json
for p in $(seq $N); do
	s0=$(snap)
	WORKERS="8 32 64" bash $D/app_grid.sh on $TAG-learn$p > $O/$TAG-learn$p.out 2>&1
	s1=$(snap)
	echo "-- pass $p $(date +%T): $(python3 -c 'import sys
a = dict(x.split("=") for x in sys.argv[1].split())
b = dict(x.split("=") for x in sys.argv[2].split())
print(" ".join("%s+%d" % (k, int(b[k]) - int(a.get(k, 0))) for k in b))' "$s0" "$s1")"
	python3 -c 'import json; d = json.load(open("/root/kds_cmp.json")); print("   state: %d sites, %d functions" % (len(d["sites"]), sum(len(s["code"]) for s in d["sites"].values())))'
done
python3 /root/host_fs/kdlock/bench/vm/pcpu.py obj_stock memcg_stock
echo LEARN_DONE
