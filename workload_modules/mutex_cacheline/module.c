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
#include "kd_mutex_direct.h"
static struct kd_mutex sc_lock;
#define SC_LOCK(n) struct kd_mutex_outer_cookie sc_outer_cookie; \
	KD_MUTEX_OUTER_LOCK(&sc_lock, sc_outer_cookie, \
	".globl mc_entry_" #n "\nmc_entry_" #n ":\n\t" ANNOTATE_NOENDBR)
#define SC_UNLOCK() KD_MUTEX_OUTER_UNLOCK(&sc_lock, sc_outer_cookie)
extern char mc_entry_0[], mc_entry_1[], mc_entry_2[], mc_entry_4[];
extern char mc_entry_8[], mc_entry_16[];
static void sc_lock_init(void) { kd_mutex_init(&sc_lock); }
#elif defined(SC_DIRECT_TCLOCK)
#include "mutex/komb_mutex.h"
static struct komb_mutex sc_lock __aligned(SC_LINE_BYTES);
int tc_mutex_worker_register(void);
int tc_mutex_workers_drain(void);
#define SC_LOCK(n) komb_mutex_lock(&sc_lock)
#define SC_UNLOCK() komb_mutex_unlock(&sc_lock)
static void sc_lock_init(void) { komb_mutex_init(&sc_lock); }
#else
static struct mutex sc_lock __aligned(SC_LINE_BYTES);
/* Parentheses deliberately bypass the experiment kernel's clobber macros. */
#define SC_LOCK(n) (mutex_lock)(&sc_lock)
#define SC_UNLOCK() (mutex_unlock)(&sc_lock)
static void sc_lock_init(void) { mutex_init(&sc_lock); }
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
#elif defined(SC_DIRECT_KDLOCK)
	return kd_mutex_is_idle(&sc_lock) ? 0 : -EBUSY;
#else
	return 0;
#endif
}
#include "payload.h"
#include "runner.inc"
