#!/bin/bash
# p1_native_reduced.sh TAG: what p1_native.sh had left when it was stopped
# (2026-11-20, at the user's request to shorten the round), at 64 workers
# only and 6 s per point (the 3 s profile window fits into no less), all
# under TAG-w64:
#   - btrfs: fs_mark and dbench (AIM7 on btrfs is left out: disk_rr with 64
#     tasks did not finish in 900 s on the native kernel);
#   - the first round's groups;
#   - the rest of will-it-scale and stress-ng (as before).
# A candidate that passes gets its 16-worker point later.
TAG=${1:?tag}
S=$(cd "$(dirname "$0")" && pwd)/screen.sh
O=/root/lkpres
export NS=64 DUR=6
FSX=btrfs FSX_AIM=- bash $S native $TAG-w64 fsx > $O/$TAG-native-w64.out 2>&1
bash $S native $TAG-w64 wis wisp sng vms hackbench futex ebizzy tlbflush aim7 fsmark dbench \
	unixbench >> $O/$TAG-native-w64.out 2>&1
bash $S native $TAG-w64 wis2 wisp2 sng2 >> $O/$TAG-native-w64.out 2>&1
echo "P1_NATIVE_REDUCED_DONE $(date +%T)" >> $O/progress.txt
