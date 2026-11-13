#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Route mm->mmap_lock through kdlock under CONFIG_KDLOCK_MM.

    apply_mm.py <kernel-source-dir>

Edits two headers of a Linux 7.0 tree that already carries the
__mmap_sem_* indirection of the earlier mmap adapter
(kernel_integration/linux70/mmap-lock.patch): include/linux/mm_types.h
gets the struct kd_mm_lock member, include/linux/mmap_lock.h maps
__mmap_sem_* onto include/kdlock/kd_mm.h. Each edit adds an #elif branch
next to the existing CONFIG_KDLOCK_MMAP one; the native and earlier
branches stay byte-identical. Safe to run again.
"""
import sys

tree = sys.argv[1]


def edit(rel, pairs):
    path = "%s/%s" % (tree, rel)
    s = open(path).read()
    for marker, old, new in pairs:
        if marker in s:
            continue
        if s.count(old) != 1:
            sys.exit("%s: anchor not found once: %r" % (rel, old[:60]))
        s = s.replace(old, new)
    open(path, "w").write(s)


edit("include/linux/mm_types.h", [
    ("kdlock/kd_mm_types.h",
     "#ifdef CONFIG_KDLOCK_MMAP\n#include <linux/kd_mmap_lock_types.h>\n#endif\n",
     "#ifdef CONFIG_KDLOCK_MMAP\n#include <linux/kd_mmap_lock_types.h>\n"
     "#elif defined(CONFIG_KDLOCK_MM)\n#include <kdlock/kd_mm_types.h>\n#endif\n"),
    ("struct kd_mm_lock mmap_lock",
     "\t\tstruct kd_mmap_lock mmap_lock;\n#else\n",
     "\t\tstruct kd_mmap_lock mmap_lock;\n#elif defined(CONFIG_KDLOCK_MM)\n"
     "\t\tstruct kd_mm_lock mmap_lock;\n#else\n"),
])

MAP = """#elif defined(CONFIG_KDLOCK_MM)
#include <kdlock/kd_mm.h>
#define MMAP_LOCK_INITIALIZER(name) \\
	.mmap_lock = KD_MM_LOCK_INITIALIZER((name).mmap_lock),
#define __mmap_sem_init_rwsem kd_mm_init
#define __mmap_sem_down_write kd_mm_down_write
#define __mmap_sem_down_write_nested kd_mm_down_write_nested
#define __mmap_sem_down_write_killable kd_mm_down_write_killable
#define __mmap_sem_up_write kd_mm_up_write
#define __mmap_sem_downgrade_write kd_mm_downgrade_write
#define __mmap_sem_down_read kd_mm_down_read
#define __mmap_sem_down_read_killable kd_mm_down_read_killable
#define __mmap_sem_down_read_trylock kd_mm_down_read_trylock
#define __mmap_sem_up_read kd_mm_up_read
#define __mmap_sem_up_read_non_owner kd_mm_up_read_non_owner
#define __mmap_sem_rwsem_is_locked kd_mm_is_locked
#define __mmap_sem_rwsem_is_contended kd_mm_is_contended
#define __mmap_sem_rwsem_assert_held kd_mm_assert_held
#define __mmap_sem_rwsem_assert_held_write kd_mm_assert_held_write
#else
#define MMAP_LOCK_INITIALIZER(name) \\
	.mmap_lock = __RWSEM_INITIALIZER((name).mmap_lock),
"""
edit("include/linux/mmap_lock.h", [
    ("kdlock/kd_mm.h",
     "#else\n#define MMAP_LOCK_INITIALIZER(name) \\\n\t.mmap_lock = __RWSEM_INITIALIZER((name).mmap_lock),\n",
     MAP),
    ("kd_mm_destroy(&mm->mmap_lock)",
     "#ifdef CONFIG_KDLOCK_MMAP\n\tkd_mmap_destroy(&mm->mmap_lock);\n#endif\n",
     "#ifdef CONFIG_KDLOCK_MMAP\n\tkd_mmap_destroy(&mm->mmap_lock);\n"
     "#elif defined(CONFIG_KDLOCK_MM)\n\tkd_mm_destroy(&mm->mmap_lock);\n#endif\n"),
])
print("mmap lock routed through kdlock (CONFIG_KDLOCK_MM) in", tree)
