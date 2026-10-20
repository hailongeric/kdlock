/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_MUTEX_COMPAT_H
#define KD_MUTEX_COMPAT_H
/*
 * Source-level ordinary mutex API replacement, for an exclusively KD build.
 * Include after Linux headers; rebuild every containing object and caller.
 * Never apply these aliases to an existing Linux struct mutex, including
 * embedded fields in a kernel built without the replacement. ww_mutex, RT
 * and lockdep are separate integration work, not covered by these aliases.
 * Ordinary source lock/unlock calls use DIRECT. Address-taking retains a local
 * conventional C acquisition and the same exact public unlock router.
 */
#include <linux/mutex.h>
#include "kd_mutex_api.h"
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
#undef devm_mutex_init
#define mutex kd_mutex
#define __MUTEX_INITIALIZER(name) KD_MUTEX_INITIALIZER(name)
#define DEFINE_MUTEX(name) DEFINE_KD_MUTEX(name)
#define mutex_init kd_mutex_init
#define __mutex_init __kd_mutex_init
#define devm_mutex_init kd_devm_mutex_init
#define __devm_mutex_init __kd_devm_mutex_init
#define mutex_destroy kd_mutex_destroy
#define mutex_lock kd_mutex_lock
#define mutex_unlock kd_mutex_unlock
#define mutex_trylock kd_mutex_trylock
#define mutex_is_locked kd_mutex_is_locked
#define mutex_lock_interruptible kd_mutex_lock_interruptible
#define mutex_lock_killable kd_mutex_lock_killable
#define mutex_lock_io kd_mutex_lock_io
#define mutex_lock_nested kd_mutex_lock_nested
#define mutex_lock_interruptible_nested kd_mutex_lock_interruptible_nested
#define mutex_lock_killable_nested kd_mutex_lock_killable_nested
#define mutex_lock_io_nested kd_mutex_lock_io_nested
#define mutex_lock_nest_lock kd_mutex_lock_nest_lock
#define atomic_dec_and_mutex_lock kd_atomic_dec_and_mutex_lock
/* CLASS and __free paste their argument before expanding the mutex type alias.
 * Redirect these tokens too, so native cleanup helpers never see KD objects. */
#define class_mutex_t class_kd_mutex_t
#define class_mutex_constructor class_kd_mutex_constructor
#define class_mutex_destructor class_kd_mutex_destructor
#define __free_mutex __free_kd_mutex
#endif
