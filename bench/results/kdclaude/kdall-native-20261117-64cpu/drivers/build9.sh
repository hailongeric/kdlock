#!/bin/bash
# Wait for the kdnat7 build, then build kdall9 (out3) and kdnat8 (outnat2)
# from the synced kd sources, and install both.
cd /mnt/kdlock-builds/kda
until grep -q "^EXIT" build-kdnat7.log; do sleep 10; done
grep -q "^EXIT 0" build-kdnat7.log || { echo "kdnat7 failed"; exit 1; }
for f in /root/host_fs/kdlock/kernel/*.c /root/host_fs/kdlock/kernel/*.h; do
	cmp -s $f src/kernel/locking/kdlock/$(basename $f) || { cp $f src/kernel/locking/kdlock/; echo "copied $(basename $f)"; }
done
for f in /root/host_fs/kdlock/include/kdlock/*.h; do
	cmp -s $f src/include/kdlock/$(basename $f) || { cp $f src/include/kdlock/; echo "copied inc $(basename $f)"; }
done
cd src
make O=../out3 -j64 KERNELRELEASE=7.0.0-38-kdall9 > ../build-kdall9.log 2>&1; echo "EXIT $?" >> ../build-kdall9.log
make O=../outnat2 -j64 KERNELRELEASE=7.0.0-38-kdnat8 > ../build-kdnat8.log 2>&1; echo "EXIT $?" >> ../build-kdnat8.log
tail -1 ../build-kdall9.log; tail -1 ../build-kdnat8.log
grep -E "kdlock/kd_.*(warning|error)|include/kdlock.*(warning|error)" ../build-kdall9.log ../build-kdnat8.log | head -5
for k in all9:out3 nat8:outnat2; do
	r=7.0.0-38-kd${k%%:*}; o=../${k##*:}
	make O=$o KERNELRELEASE=$r INSTALL_MOD_STRIP=1 modules_install > ../modinst-${k%%:*}.log 2>&1; echo "$r modinst $?"
	make O=$o KERNELRELEASE=$r install > ../install-${k%%:*}.log 2>&1; echo "$r install $?"
done
ls /boot | grep -E "vmlinuz-.*kd(nat8|all9)"
sync
echo BUILD9_DONE
