#!/bin/bash
set -euo pipefail
R=/mnt/kdlock-builds/main-spin-handoff-1d29a9a1-20261117
V=7.0.0-38-kdmainspin2
exec > "$R/install.log" 2>&1
test -f "$R/kernel-sha256.txt"
test ! -e "/boot/vmlinuz-$V"
test ! -e "/lib/modules/$V"
sha256sum /etc/default/grub /etc/default/grub.d/* > "$R/grub-default-before.sha256"
make -C "$R/src" O="$R/out" KERNELRELEASE="$V" INSTALL_MOD_STRIP=1 modules_install
make -C "$R/src" O="$R/out" KERNELRELEASE="$V" install
sha256sum -c "$R/grub-default-before.sha256"
sha256sum /boot/vmlinuz-$V /boot/initrd.img-$V > "$R/installed-sha256.txt"
sync
printf 'INSTALL_COMPLETE\n'
