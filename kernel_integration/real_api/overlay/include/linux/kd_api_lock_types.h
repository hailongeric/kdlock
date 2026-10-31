/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_KD_API_LOCK_TYPES_H
#define _LINUX_KD_API_LOCK_TYPES_H
#include <linux/spinlock.h>
#include <linux/mutex.h>
#ifdef CONFIG_KD_API_LOCKS
#include <linux/kd_api/kd_spin_type.h>
#include <linux/kd_api/kd_mutex_types.h>
#endif

/* A backend is chosen once before publication. Never mix these protocols. */
typedef union kd_api_spinlock {
	spinlock_t native;
#ifdef CONFIG_KD_API_LOCKS
	kd_spinlock_t kd;
#endif
} kd_api_spinlock_t;
typedef union kd_api_mutex {
	struct mutex native;
#ifdef CONFIG_KD_API_LOCKS
	struct kd_mutex kd;
#endif
} kd_api_mutex_t;
struct kd_api_provider;
#define KD_API_SPIN_INITIALIZER(name) \
	{ .native = __SPIN_LOCK_UNLOCKED(name.native) }
#endif
