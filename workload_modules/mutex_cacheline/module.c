// SPDX-License-Identifier: GPL-2.0
#include <linux/build_bug.h>
#include <linux/atomic.h>
#include <linux/fs.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/uaccess.h>
#include "api.h"
#include "post_work.h"

#ifndef SC_SCENARIO
#define SC_SCENARIO 0
#endif
#if SC_SCENARIO && !defined(SC_DIRECT_KDLOCK)
#error "Mutex nested/early scenarios require owned-v1"
#endif

/* Distinct compiled workload functions, sharing the payload's source only. */
#define SC_MUTEX_WORKLOAD 1
#define SC_LOCK_KIND 2
#define SC_DEVICE_NAME "mutex_cacheline"
#define sc_body_0 mc_body_0
#define sc_body_1 mc_body_1
#define sc_body_2 mc_body_2
#define sc_body_4 mc_body_4
#define sc_body_8 mc_body_8
#define sc_body_16 mc_body_16
#define sc_entry_0 mc_entry_0
#define sc_entry_1 mc_entry_1
#define sc_entry_2 mc_entry_2
#define sc_entry_4 mc_entry_4
#define sc_entry_8 mc_entry_8
#define sc_entry_16 mc_entry_16

#if defined(SC_DIRECT_KDLOCK)
#include <linux/objtool.h>
#define SC_MUTEX_OWNED 1
#include "kd_owned_mutex_direct.h"
static struct kd_mutex sc_lock __aligned(SC_LINE_BYTES);
#if SC_SCENARIO
static struct kd_mutex sc_inner __aligned(SC_LINE_BYTES);
#endif
#define SC_LOCK(n) struct kd_owned_mutex_outer_cookie sc_outer_cookie; \
	KD_OWNED_MUTEX_OUTER_LOCK(&sc_lock, sc_outer_cookie, \
	".globl mc_entry_" #n "\nmc_entry_" #n ":\n\t" ANNOTATE_NOENDBR)
#define SC_UNLOCK() KD_OWNED_MUTEX_OUTER_UNLOCK(&sc_lock, sc_outer_cookie)
static void sc_lock_init(void)
{
	BUILD_BUG_ON(sizeof(struct kd_mutex) != 128);
	kd_mutex_init(&sc_lock);
#if SC_SCENARIO
	kd_mutex_init(&sc_inner);
#endif
}
MODULE_INFO(mutex_implementation, "owned-v1");
#if KD_OWNED_MUTEX_CABI
MODULE_INFO(owned_caller_policy, "c_abi_v2");
MODULE_INFO(owned_entry_abi, "4");
MODULE_INFO(owned_preflight_policy, "not_applicable");
#else
MODULE_INFO(owned_caller_policy, "clobber_v1");
MODULE_INFO(owned_entry_abi, "2");
#if KD_OWNED_MUTEX_PREFLIGHT
MODULE_INFO(owned_preflight_policy, "c_abi_v1");
#else
MODULE_INFO(owned_preflight_policy, "capture_first");
#endif
#endif
extern char mc_entry_0[], mc_entry_1[], mc_entry_2[], mc_entry_4[];
extern char mc_entry_8[], mc_entry_16[];
#elif defined(SC_DIRECT_TCLOCK)
#include "mutex/komb_mutex.h"
static struct komb_mutex sc_lock __aligned(SC_LINE_BYTES);
int tc_mutex_worker_register(void);
int tc_mutex_workers_drain(void);
#define SC_LOCK(n) komb_mutex_lock(&sc_lock)
#define SC_UNLOCK() komb_mutex_unlock(&sc_lock)
static void sc_lock_init(void) { komb_mutex_init(&sc_lock); }
MODULE_INFO(mutex_implementation, "tclock");
#else
static struct mutex sc_lock __aligned(SC_LINE_BYTES);
/* Parentheses deliberately bypass the experiment kernel's clobber macros. */
#define SC_LOCK(n) (mutex_lock)(&sc_lock)
#define SC_UNLOCK() (mutex_unlock)(&sc_lock)
static void sc_lock_init(void) { mutex_init(&sc_lock); }
MODULE_INFO(mutex_implementation, "native");
#endif

static int sc_worker_register(void)
{
#ifdef SC_DIRECT_TCLOCK
	return tc_mutex_worker_register();
#else
	return 0;
#endif
}
static int sc_workers_drain(void)
{
#ifdef SC_DIRECT_TCLOCK
	return tc_mutex_workers_drain();
#elif defined(SC_MUTEX_OWNED)
	if (!kd_owned_mutex_is_idle(&sc_lock))
		return -EBUSY;
#if SC_SCENARIO
	if (!kd_owned_mutex_is_idle(&sc_inner))
		return -EBUSY;
#endif
	return 0;
#else
	/* SC_WORKERS_DRAIN holds the snapshot gate after all workers return.
	 * No owner flags, sleeping waiters or optimistic spinner may survive. */
	if (atomic_long_read(&sc_lock.owner) || !list_empty(&sc_lock.wait_list))
		return -EBUSY;
#ifdef CONFIG_MUTEX_SPIN_ON_OWNER
	if (osq_is_locked(&sc_lock.osq))
		return -EBUSY;
#endif
	return 0;
#endif
}
#include "payload.h"
#include "runner.inc"
