#!/bin/bash
# SPDX-License-Identifier: GPL-2.0
# Place kdlock into a Linux 7 source tree: the minimum that lets
# kernel/locking/kdlock/ build in. It does NOT switch the kernel's lock API
# over; that is the macro layer in kd_linux_map.h.
#
#   apply_to_tree.sh <kernel-source-dir>
#
# Safe to run again: copies overwrite, hooks are added once.
set -euo pipefail

here=$(cd "$(dirname "$0")/.." && pwd)
tree=${1:?usage: $0 <kernel-source-dir>}
[ -f "$tree/kernel/locking/Makefile" ] || { echo "$tree is not a kernel tree" >&2; exit 1; }

mkdir -p "$tree/include/kdlock" "$tree/kernel/locking/kdlock"
cp "$here"/include/kdlock/*.h "$tree/include/kdlock/"
# Source only; the standalone Makefile/Kconfig are the ones the tree uses.
cp "$here"/kernel/*.[chS] "$here"/kernel/Makefile "$here"/kernel/Kconfig "$tree/kernel/locking/kdlock/"

add_once() {	# file, line
	grep -qxF "$2" "$1" || printf '%s\n' "$2" >> "$1"
}
add_once "$tree/kernel/Kconfig.locks" 'source "kernel/locking/kdlock/Kconfig"'
add_once "$tree/kernel/locking/Makefile" 'obj-$(CONFIG_KDLOCK) += kdlock/'
# Symbols exported from assembly need C prototypes (MODVERSIONS/gendwarfksyms).
add_once "$tree/arch/x86/include/asm/asm-prototypes.h" '#include <kdlock/kd_api.h>'
# mm->mmap_lock routing (CONFIG_KDLOCK_MM); needs the __mmap_sem_* layer.
if grep -q "__mmap_sem_down_write" "$tree/include/linux/mmap_lock.h"; then
	python3 "$here/integration/apply_mm.py" "$tree"
fi
echo "kdlock placed in $tree"
