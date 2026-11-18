#!/bin/bash
# nat_boot.sh TAG: the kdnat boot of the campaign: the nano grid
# (nano_grid.sh), then the application grid with native locks
# (app_grid.sh native). Output in /root/appgrid.
TAG=${1:?tag}
D=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
bash $D/nano_grid.sh $TAG
rmmod kd_bench 2>/dev/null
for m in tclock_rwsem_backend_km tclock_rwlock_backend_km tclock_mutex_backend_km tclock_backend_km; do
	rmmod $m 2>/dev/null
done
bash $D/app_grid.sh native $TAG > /root/appgrid/$TAG-native.out 2>&1
echo "NAT_BOOT_DONE $(date +%T)" >> /root/appgrid/progress.txt
