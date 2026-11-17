#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Whole-kernel lock API switch (CONFIG_KDLOCK_ALL).

    apply_all.py <kernel-source-dir>

Every edit is wrapped in #ifdef CONFIG_KDLOCK_ALL with the native text kept
in the #else branch, so a tree with the option off builds as before. Safe
to run again (each edit is skipped once its marker is present).

  asm-generic/qspinlock.h  queued_spin_lock() is kd_arch_spin_lock(): every
                           raw_spinlock_t and arch_spin_lock() user takes the
                           kd queue algorithm (same word layout)
  asm-generic/qrwlock.h    arch_read_lock()/arch_write_lock() are the kd ones
  linux/spinlock.h         spinlock_t and rwlock_t operations are calls to the
                           kd entries (kdlock/kd_all_spin.h), before the guards
  linux/mutex_types.h      struct mutex is { struct kd_mutex kd; }
  linux/mutex.h            mutex operations (kdlock/kd_all_mutex.h)
  linux/rwsem.h            struct rw_semaphore is { struct kd_rwsem kd; } and
                           its operations (kdlock/kd_all_rwsem*.h)
  kernel/locking/Makefile  mutex.c and rwsem.c are not built; kernel/kd_all.c
                           defines their function names

See docs/KERNEL_INTEGRATION.md 4d.
"""
import re
import sys

tree = sys.argv[1]
GUARD = "CONFIG_KDLOCK_ALL"
MARK = "/* kdlock: whole-kernel switch */"


def load(rel):
    return open("%s/%s" % (tree, rel)).read()


def store(rel, s):
    open("%s/%s" % (tree, rel), "w").write(s)


def once(s, old, rel):
    if s.count(old) != 1:
        sys.exit("%s: anchor not found once: %r" % (rel, old[:70]))


def insert_before(rel, anchor, text):
    """Insert an #ifdef CONFIG_KDLOCK_ALL block before the anchor."""
    s = load(rel)
    if MARK in s:
        return
    once(s, anchor, rel)
    s = s.replace(anchor, "#ifdef %s %s\n%s#endif\n\n%s" % (GUARD, MARK, text, anchor))
    store(rel, s)


def wrap(rel, start, end, text, end_inclusive=True):
    """Replace s[start .. end] by #ifdef GUARD text #else old #endif."""
    s = load(rel)
    if MARK in s:
        return
    once(s, start, rel)
    i = s.index(start)
    j = s.index(end, i)
    if end_inclusive:
        j += len(end)
    old = s[i:j]
    if not old.endswith("\n"):
        sys.exit("%s: wrapped text must end a line" % rel)
    s = s[:i] + "#ifdef %s %s\n%s#else\n%s#endif\n" % (GUARD, MARK, text, old) + s[j:]
    store(rel, s)


# ---- arch level: raw spinlocks and the arch_*() users ------------------------
insert_before("include/asm-generic/qspinlock.h", "#ifndef queued_spin_lock\n",
              """/*
 * Every raw_spinlock_t and arch_spin_lock() user takes the kd queue
 * algorithm on the same word (kdlock/kd_types.h struct kd_qlock has the
 * qspinlock layout). Trylock and unlock are the same operations for both.
 */
struct kd_spinlock;
extern void kd_arch_spin_lock(struct kd_spinlock *l);
#define queued_spin_lock queued_spin_lock
static __always_inline void queued_spin_lock(struct qspinlock *lock)
{
	kd_arch_spin_lock((struct kd_spinlock *)lock);
}
""")

s = load("include/asm-generic/qrwlock.h")
if MARK not in s:
    m = re.search(r"#define arch_read_lock\(l\)\s+queued_read_lock\(l\)\n"
                  r"#define arch_write_lock\(l\)\s+queued_write_lock\(l\)\n", s)
    if not m:
        sys.exit("qrwlock.h: arch_read_lock/arch_write_lock anchor not found")
    new = ("#ifdef %s %s\n"
           "/* The kd rwlock is a qrwlock: same count word, bias and writer bits. */\n"
           "struct kd_rwlock;\n"
           "extern void kd_arch_read_lock(struct kd_rwlock *rw);\n"
           "extern void kd_arch_write_lock(struct kd_rwlock *rw);\n"
           "#define arch_read_lock(l)\t\tkd_arch_read_lock((struct kd_rwlock *)(l))\n"
           "#define arch_write_lock(l)\t\tkd_arch_write_lock((struct kd_rwlock *)(l))\n"
           "#else\n%s#endif\n" % (GUARD, MARK, m.group(0)))
    store("include/asm-generic/qrwlock.h", s[:m.start()] + new + s[m.end():])

# ---- spinlock_t, rwlock_t ---------------------------------------------------------
insert_before("include/linux/spinlock.h", "DEFINE_LOCK_GUARD_1(raw_spinlock, raw_spinlock_t,\n",
              "#include <kdlock/kd_all_spin.h>\n")

# ---- struct mutex -------------------------------------------------------------------
wrap("include/linux/mutex_types.h", "context_lock_struct(mutex) {\n\tatomic_long_t", "\n};\n",
     "#include <kdlock/kd_types.h>\n\n"
     "/* The kd mutex, 32 bytes as the native one; kdlock/kd_all_mutex.h. */\n"
     "context_lock_struct(mutex) {\n\tstruct kd_mutex\tkd;\n};\n")
# wrap() starts at the struct; the text before "context_lock_struct" stays.
insert_before("include/linux/mutex.h", "DEFINE_LOCK_GUARD_1(mutex, struct mutex,",
              "#include <kdlock/kd_all_mutex.h>\n")

# ---- struct rw_semaphore -----------------------------------------------------------
wrap("include/linux/rwsem.h", "context_lock_struct(rw_semaphore) {\n\tatomic_long_t count;",
     "#else /* !CONFIG_PREEMPT_RT */\n",
     "#include <kdlock/kd_all_rwsem.h>\n", end_inclusive=False)
s = load("include/linux/rwsem.h")
ops_mark = "<kdlock/kd_all_rwsem_ops.h>"
if ops_mark not in s:
    a = "DEFINE_LOCK_GUARD_1(rwsem_read, struct rw_semaphore,"
    once(s, a, "include/linux/rwsem.h")
    s = s.replace(a, "#ifdef %s\n#include %s\n#endif\n\n%s" % (GUARD, ops_mark, a))
    d = "extern void downgrade_write(struct rw_semaphore *sem)"
    once(s, d, "include/linux/rwsem.h")
    i = s.index(d)
    j = s.index(";\n", i) + 2
    s = (s[:i] + "#if !defined(%s) || defined(KD_ALL_NO_MAP)\n" % GUARD + s[i:j] +
         "#endif\n" + s[j:])
    store("include/linux/rwsem.h", s)

# ---- linux/sched.h: task->blocked_on helpers -----------------------------------------
# Only kernel/locking/mutex.c (and its ww_mutex part) sets ->blocked_on, under
# the native mutex's wait_lock. A kd mutex never sets it, and proxy execution,
# its one reader that follows it to the mutex owner, is off (KDLOCK_ALL is not
# built with SCHED_PROXY_EXEC; the field stays NULL).
rel = "include/linux/sched.h"
s = load(rel)
if MARK not in s:
    old = "#ifndef CONFIG_PREEMPT_RT\nstatic inline struct mutex *__get_task_blocked_on(struct task_struct *p)\n"
    once(s, old, rel)
    s = s.replace(old, """#if defined(CONFIG_KDLOCK_ALL) %s
/* A kd mutex records no blocked_on relation; the field stays NULL. */
static inline struct mutex *__get_task_blocked_on(struct task_struct *p)
{
	return READ_ONCE(p->blocked_on);
}

static inline void __clear_task_blocked_on(struct task_struct *p, struct mutex *m)
{
	WRITE_ONCE(p->blocked_on, NULL);
}

static inline void clear_task_blocked_on(struct task_struct *p, struct mutex *m)
{
	WRITE_ONCE(p->blocked_on, NULL);
}
#elif !defined(CONFIG_PREEMPT_RT)
static inline struct mutex *__get_task_blocked_on(struct task_struct *p)
""" % MARK)
    store(rel, s)

# ---- kernel/locking/mutex.h: __mutex_owner() ------------------------------------------
# kernel/sched/core.c includes this header for proxy execution, which
# KDLOCK_ALL excludes; the inline function must still compile. The kd mutex
# keeps its logical owner in ->owner (a spin heuristic, not exact).
wrap("kernel/locking/mutex.h", "static inline struct task_struct *__mutex_owner(struct mutex *lock)\n",
     "\n}\n",
     "static inline struct task_struct *__mutex_owner(struct mutex *lock)\n"
     "{\n\treturn lock ? (struct task_struct *)kd_mutex_get_owner(&lock->kd) : NULL;\n}\n")

# ---- kernel/locking/Makefile -------------------------------------------------------
rel = "kernel/locking/Makefile"
s = load(rel)
if "CONFIG_KDLOCK_ALL" not in s:
    old = "obj-y += mutex.o semaphore.o rwsem.o percpu-rwsem.o\n"
    once(s, old, rel)
    s = s.replace(old, "# kdlock: with the whole-kernel switch, kernel/locking/kdlock/kd_all.c\n"
                       "# defines the mutex and rwsem functions.\n"
                       "ifdef CONFIG_KDLOCK_ALL\nobj-y += semaphore.o percpu-rwsem.o\nelse\n"
                       + old + "endif\n")
    store(rel, s)

print("whole-kernel lock switch (CONFIG_KDLOCK_ALL) placed in", tree)
