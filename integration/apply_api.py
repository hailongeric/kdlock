#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Switchable lock objects for selected syscall paths (CONFIG_KDLOCK_API).

    apply_api.py <kernel-source-dir>

Three generic headers get the dispatch layer at their end (linux/spinlock.h,
linux/mutex.h, linux/rwsem.h; include/kdlock/kd_sw_*.h). Then exactly these
lock fields change type, nothing else in their subsystems:

  files_struct.file_lock      spinlock_t        fcntl(F_SETFD), open, close, dup
  file_lock_context.flc_lock  spinlock_t        fcntl(F_OFD_GETLK/SETLK), flock
  pipe_inode_info.mutex       struct mutex      pipe read/write/ioctl/fcntl
  file.f_pos_lock             struct mutex      lseek/read/write on shared files
  simple_xattrs.lock          rwlock_t          tmpfs/kernfs xattrs
  uts_sem                     rw_semaphore      uname, sethostname, ...

Two static initialisers follow the new types (init_files, uts_sem), and the
two files that define the native mutex and rwsem functions opt out of the
dispatch. Each edit is wrapped in #ifdef CONFIG_KDLOCK_API with the native
line kept in the #else branch. Safe to run again.
"""
import sys

tree = sys.argv[1]
GUARD = "CONFIG_KDLOCK_API"


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


def switch(old, new):
    """Replace a line by an #ifdef CONFIG_KDLOCK_API choice of two lines."""
    return (new, old, "#ifdef %s\n%s\n#else\n%s\n#endif\n" % (GUARD, new.rstrip("\n"), old.rstrip("\n")))


def tail_include(rel, endif, header):
    marker = "<kdlock/%s>" % header
    edit(rel, [(marker, endif, "#ifdef %s\n#include %s\n#endif\n%s" % (GUARD, marker, endif))])


tail_include("include/linux/spinlock.h", "#undef __LINUX_INSIDE_SPINLOCK_H\n#endif /* __LINUX_SPINLOCK_H */\n",
             "kd_sw_spin.h")
tail_include("include/linux/mutex.h", "#endif /* __LINUX_MUTEX_H */\n", "kd_sw_mutex.h")
tail_include("include/linux/rwsem.h", "#endif /* _LINUX_RWSEM_H */\n", "kd_sw_rwsem.h")

for rel in ("kernel/locking/mutex.c", "kernel/locking/rwsem.c"):
    path = "%s/%s" % (tree, rel)
    s = open(path).read()
    if "KD_SW_NO_DISPATCH" not in s:
        i = s.index("#include")
        s = (s[:i] + "/* Defines the native functions that the kdlock dispatch selects. */\n"
             "#define KD_SW_NO_DISPATCH\n" + s[i:])
        open(path, "w").write(s)

edit("include/linux/fdtable.h", [switch(
    "\tspinlock_t file_lock ____cacheline_aligned_in_smp;\n",
    "\tstruct kd_sw_spinlock file_lock ____cacheline_aligned_in_smp;\n")])
edit("fs/file.c", [switch(
    "\t.file_lock\t= __SPIN_LOCK_UNLOCKED(init_files.file_lock),\n",
    "\t.file_lock\t= __KD_SW_SPIN_UNLOCKED(init_files.file_lock),\n")])
edit("include/linux/filelock.h", [switch(
    "\tspinlock_t\t\tflc_lock;\n",
    "\tstruct kd_sw_spinlock\tflc_lock;\n")])
edit("include/linux/pipe_fs_i.h", [switch(
    "\tstruct mutex mutex;\n",
    "\tstruct kd_sw_mutex mutex;\n")])
edit("include/linux/fs.h", [switch(
    "\t\tstruct mutex\t\tf_pos_lock;\n",
    "\t\tstruct kd_sw_mutex\tf_pos_lock;\n")])
edit("include/linux/xattr.h", [switch(
    "\trwlock_t lock;\n",
    "\tstruct kd_sw_rwlock lock;\n")])
edit("include/linux/utsname.h", [switch(
    "extern struct rw_semaphore uts_sem;\n",
    "extern struct kd_sw_rwsem uts_sem;\n")])
edit("kernel/sys.c", [switch(
    "DECLARE_RWSEM(uts_sem);\n",
    "DECLARE_KD_SW_RWSEM(uts_sem);\n")])
print("switchable lock objects (CONFIG_KDLOCK_API) placed in", tree)
