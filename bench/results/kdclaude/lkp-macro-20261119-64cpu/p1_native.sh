#!/bin/bash
# p1_native.sh TAG: phase 1 (README 4.2) on a kdnat kernel, three passes of
# screen.sh in mode native:
#   1. the application groups of this round at 16 and 64 workers, 10 s;
#   2. the first round's groups again on this kernel (its native values were
#      from kdnat9);
#   3. the rest of will-it-scale and stress-ng at 64 workers only, 5 s, with
#      the profile (tag TAG-w64): the candidates that pass are run at 16
#      workers later.
# Output in /root/lkpres.
TAG=${1:?tag}
S=$(cd "$(dirname "$0")" && pwd)/screen.sh
O=/root/lkpres
bash $S native $TAG perfb pft schbench net redis memcached sysbench blogbench filebench fio \
	pgbench vms2 kbuild fsx > $O/$TAG-native-apps.out 2>&1
bash $S native $TAG wis wisp sng vms hackbench futex ebizzy tlbflush aim7 fsmark dbench \
	unixbench > $O/$TAG-native-first.out 2>&1
NS=64 DUR=5 bash $S native $TAG-w64 wis2 wisp2 sng2 > $O/$TAG-native-w64.out 2>&1
echo "P1_NATIVE_DONE $(date +%T)" >> $O/progress.txt
