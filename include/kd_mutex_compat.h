/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_COMPAT_H
#define KD_MUTEX_COMPAT_H
/*
 * Source-level ordinary mutex API replacement, for an exclusively KD build.
 * Include after Linux headers; rebuild every containing object and caller.
 * Never apply these aliases to an existing Linux struct mutex, including
 * embedded fields in a kernel built without the replacement. ww_mutex, RT
 * and lockdep are separate integration work, not covered by these aliases.
 * Ordinary C calls execute locally. Explicit clobber callers may delegate via
 * kd_mutex_direct.h, using the same KD object and physical owner word.
 */
#include <linux/mutex.h>
#include "kd_mutex.h"
#undef mutex_init
#undef mutex_lock
#undef mutex_unlock
#undef mutex_lock_nested
#undef mutex_lock_interruptible_nested
#undef mutex_lock_killable_nested
#undef mutex_lock_io_nested
#undef mutex_lock_nest_lock
#undef DEFINE_MUTEX
#undef __MUTEX_INITIALIZER
#define mutex kd_mutex
#define __MUTEX_INITIALIZER(name) KD_MUTEX_INITIALIZER(name)
#define DEFINE_MUTEX(name) DEFINE_KD_MUTEX(name)
#define mutex_init kd_mutex_init
#define mutex_destroy kd_mutex_destroy
#define mutex_lock kd_mutex_local_lock
#define mutex_unlock kd_mutex_local_unlock
#define mutex_trylock kd_mutex_trylock
#define mutex_is_locked kd_mutex_is_locked
#define mutex_lock_interruptible kd_mutex_lock_interruptible
#define mutex_lock_killable kd_mutex_lock_killable
#define mutex_lock_io kd_mutex_lock_io
#define mutex_lock_nested(lock, subclass) kd_mutex_local_lock(lock)
#define mutex_lock_interruptible_nested(lock, subclass) kd_mutex_lock_interruptible(lock)
#define mutex_lock_killable_nested(lock, subclass) kd_mutex_lock_killable(lock)
#define mutex_lock_io_nested(lock, subclass) kd_mutex_lock_io(lock)
#define mutex_lock_nest_lock(lock, nest) kd_mutex_local_lock(lock)
#define atomic_dec_and_mutex_lock kd_atomic_dec_and_mutex_lock
#endif
