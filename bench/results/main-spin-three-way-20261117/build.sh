#!/bin/bash
set -euo pipefail
R=/mnt/kdlock-builds/main-spin-handoff-1d29a9a1-20261117
OLD=/mnt/kdlock-builds/main-spin-20e9db0c-20261117
mkdir "$R"
exec > "$R/build.log" 2>&1
mkdir "$R/repo"
tar -xf /tmp/main-spin-handoff-source.tar -C "$R/repo"
cp -a --reflink=auto "$OLD/src" "$R/src"
cp -a --reflink=auto "$OLD/out" "$R/out"
ln -sfn "$R/src" "$R/out/source"
bash "$R/repo/integration/apply_to_tree.sh" "$R/src"
make -C "$R/src" O="$R/out" KERNELRELEASE=7.0.0-38-kdmainspin2 olddefconfig
make -C "$R/src" O="$R/out" KERNELRELEASE=7.0.0-38-kdmainspin2 -j32
for variant in baseline candidate; do
 if [ "$variant" = baseline ]; then K="$OLD/out"; else K="$R/out"; fi
 B="$R/$variant"
 mkdir -p "$B/tc"
 cp -a "$R/repo/bench" "$R/repo/include" "$B/"
 symvers=""
 for family in spin mutex rwlock rwsem; do
  cp -a "$R/repo/tclock_backend" "$B/tc/$family"
  opts=()
  case "$family" in mutex) opts=(TCLOCK_MUTEX=1);; rwlock) opts=(TCLOCK_RWLOCK=1);; rwsem) opts=(TCLOCK_RWSEM=1);; esac
  make -C "$K" M="$B/tc/$family" "${opts[@]}" TCLOCK_NUMA=1 -j8 modules > "$B/tc/$family.log" 2>&1
  symvers="$symvers $B/tc/$family/Module.symvers"
 done
 make -C "$K" M="$B/bench" KDB_TCLOCK=1 TCLOCK_DIR="$B/tc/spin" KBUILD_EXTRA_SYMBOLS="$symvers" -j8 modules > "$B/bench-build.log" 2>&1
 sha256sum "$B/bench/kd_bench.ko" "$B"/tc/*/*.ko > "$B/module-sha256.txt"
done
sha256sum "$R/out/.config" "$R/out/vmlinux" "$R/out/arch/x86/boot/bzImage" > "$R/kernel-sha256.txt"
printf 'BUILD_COMPLETE\n'
