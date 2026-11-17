# The one inherited kernel patch

`mmap-lock.patch` is **not** part of this implementation. It comes from the
earlier kdlock tree (`kernel_integration/linux70/mmap-lock.patch`, reachable
through the tag `full-tree-before-cleanup-20261115`) and is kept here because
this tree's mmap integration builds on it:

* It introduces the `__mmap_sem_*` indirection in `include/linux/mmap_lock.h`
  (plus the `CONFIG_KDLOCK_MMAP` branch it was written for) and the members and
  hooks that go with it in `include/linux/mm_types.h`, `include/linux/sched/mm.h`,
  `kernel/fork.c`, `mm/mmap_lock.c`, `mm/Kconfig`, `kernel/locking/Makefile` and
  three BPF files.
* `../apply_mm.py` adds an `#elif CONFIG_KDLOCK_MM` branch next to that
  `CONFIG_KDLOCK_MMAP` one, and `../apply_to_tree.sh` runs it only when
  `__mmap_sem_down_write` is already present in the tree. So without this patch
  `CONFIG_KDLOCK_MM` (KERNEL_INTEGRATION 4a, the mmap1 measurements) cannot be
  built; everything else in this tree can.
* `mmap-base-sha256.json` is that patch's record of the base file hashes it
  applies to.

The development VM's kernel source already carries it: the tree is copied from
`/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source`, which was prepared with it,
and the build then disables `CONFIG_KDLOCK_MMAP` and enables `CONFIG_KDLOCK`,
`CONFIG_KDLOCK_MM` and `CONFIG_KDLOCK_API` (docs/BUILD_AND_TEST.md). The patch
is kept so that base tree can be reproduced from a plain Linux 7.0.0-38 source.

Replacing it with a patch of this tree's own, so that the mmap integration does
not depend on the earlier layer, is open work.
