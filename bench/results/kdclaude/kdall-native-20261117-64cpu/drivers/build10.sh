#!/bin/bash
# Build kdall10 (out3) and kdnat9 (outnat2) from the synced kd sources
# (kdall9 without the reader stall rule), and install both.
cd /mnt/kdlock-builds/kda
for f in /root/host_fs/kdlock/kernel/*.c /root/host_fs/kdlock/kernel/*.h; do
	cmp -s $f src/kernel/locking/kdlock/$(basename $f) || { cp $f src/kernel/locking/kdlock/; echo "copied $(basename $f)"; }
done
for f in /root/host_fs/kdlock/include/kdlock/*.h; do
	cmp -s $f src/include/kdlock/$(basename $f) || { cp $f src/include/kdlock/; echo "copied inc $(basename $f)"; }
done
cd src
make O=../out3 -j64 KERNELRELEASE=7.0.0-38-kdall10 > ../build-kdall10.log 2>&1; echo "EXIT $?" >> ../build-kdall10.log
make O=../outnat2 -j64 KERNELRELEASE=7.0.0-38-kdnat9 > ../build-kdnat9.log 2>&1; echo "EXIT $?" >> ../build-kdnat9.log
tail -1 ../build-kdall10.log; tail -1 ../build-kdnat9.log
grep -E "kdlock/kd_.*(warning|error)|include/kdlock.*(warning|error)" ../build-kdall10.log ../build-kdnat9.log | head -5
for k in all10:out3 nat9:outnat2; do
	r=7.0.0-38-kd${k%%:*}; o=../${k##*:}
	make O=$o KERNELRELEASE=$r INSTALL_MOD_STRIP=1 modules_install > ../modinst-${k%%:*}.log 2>&1; echo "$r modinst $?"
	make O=$o KERNELRELEASE=$r install > ../install-${k%%:*}.log 2>&1; echo "$r install $?"
done
ls /boot | grep -E "vmlinuz-.*kd(nat9|all10)"
sync
echo BUILD10_DONE
