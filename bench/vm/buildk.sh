#!/bin/bash
# buildk.sh NAME OUTDIR: guest helper (kdclaude VM). Copy the kdlock sources
# (C, headers, the entry assembly, Kconfig and Makefile of kernel/, and
# include/kdlock) from /root/host_fs/kdlock into the kernel tree
# /mnt/kdlock-builds/kda/src,
# build 7.0.0-38-NAME into ../OUTDIR, then modules_install and install.
# Prints BUILDK_DONE at the end. Boot the result with grub-reboot
# (docs/HANDOFF.md section 2).
k=${1:?name}; o=${2:?outdir}; r=7.0.0-38-$k
cd /mnt/kdlock-builds/kda || exit 1
for f in /root/host_fs/kdlock/kernel/*.c /root/host_fs/kdlock/kernel/*.h /root/host_fs/kdlock/kernel/*.S \
	 /root/host_fs/kdlock/kernel/Kconfig /root/host_fs/kdlock/kernel/Makefile; do
	cmp -s $f src/kernel/locking/kdlock/$(basename $f) || { cp $f src/kernel/locking/kdlock/; echo "copied $(basename $f)"; }
done
for f in /root/host_fs/kdlock/include/kdlock/*.h; do
	cmp -s $f src/include/kdlock/$(basename $f) || { cp $f src/include/kdlock/; echo "copied inc $(basename $f)"; }
done
cd src
make O=../$o -j64 KERNELRELEASE=$r > ../build-$k.log 2>&1; e=$?; echo "build $e"
grep -E "kdlock/.*(warning|error)" ../build-$k.log | head -5
[ $e = 0 ] || { echo BUILDK_DONE; exit 1; }
make O=../$o KERNELRELEASE=$r INSTALL_MOD_STRIP=1 modules_install > ../modinst-$k.log 2>&1; echo "modinst $?"
make O=../$o KERNELRELEASE=$r install > ../install-$k.log 2>&1; echo "install $?"
ls /boot | grep -c "vmlinuz-$r"
sync
echo BUILDK_DONE
