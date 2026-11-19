#!/bin/bash
# kd_boot.sh TAG: the kdall boot of the campaign, on a fresh boot: a short
# check pass (QUICK=1, kd off, tag quick-TAG, not counted), then the
# application grid with kd off and then with kd on (app_grid.sh of
# appgrid-20261118-64cpu; off runs first so that nothing has been delegated
# in the boot before it). WORKERS (exported by the caller) selects the worker
# counts of both passes. Output in /root/appgrid.
TAG=${1:?tag}
D=$(cd "$(dirname "$0")" && pwd)/../appgrid-20261118-64cpu
O=/root/appgrid; mkdir -p $O
QUICK=1 bash $D/app_grid.sh off quick-$TAG > $O/quick-$TAG-off.out 2>&1
bash $D/app_grid.sh off $TAG > $O/$TAG-off.out 2>&1
bash $D/app_grid.sh on $TAG > $O/$TAG-on.out 2>&1
echo "KD_BOOT_DONE $(date +%T)" >> $O/progress.txt
