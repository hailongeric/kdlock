#!/bin/bash
set -euo pipefail
R=/mnt/kdlock-builds/main-spin-20e9db0c-20261117
mkdir "$R"
mkdir "$R/repo"
tar -xf /tmp/main-spin-20e9db0c-source.tar -C "$R/repo"
cp -a --reflink=auto /mnt/kdlock-builds/kdc/src "$R/src"
cp -a --reflink=auto /mnt/kdlock-builds/kdc/out "$R/out"
# Only the copied output's source link is replaced.
ln -sfn "$R/src" "$R/out/source"
bash "$R/repo/integration/apply_to_tree.sh" "$R/src"
cd "$R/src"
make O="$R/out" KERNELRELEASE=7.0.0-38-kdmainspin1 olddefconfig
make O="$R/out" KERNELRELEASE=7.0.0-38-kdmainspin1 -j32
make -C "$R/out" KERNELRELEASE=7.0.0-38-kdmainspin1 M="$R/repo/bench" -j8 modules
sha256sum "$R/out/.config" "$R/out/vmlinux" "$R/out/arch/x86/boot/bzImage" "$R/repo/bench/kd_bench.ko" > "$R/build-sha256.txt"
printf 'BUILD_COMPLETE\n'
