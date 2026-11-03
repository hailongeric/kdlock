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
#include "kd_mutex_api.h"
/* Preserve this workload's deliberate separation from its business payload. */
static struct kd_mutex sc_lock __aligned(SC_LINE_BYTES);
#ifdef SC_MUTEX_PUBLIC_API
/* Observe DIRECT's saved continuation without adding a named argument to the
 * public call. The runner must verify this alias against the compiled CALL:
 * a label after the macro could otherwise skip compiler restore instructions.
 */
#define SC_LOCK(n) kd_mutex_lock(&sc_lock); \
	asm volatile(".globl mc_entry_" #n "\n.set mc_entry_" #n ", 1b\n\t" \
		     ".pushsection .discard.noendbr\n\t" \
		     _ASM_PTR " mc_entry_" #n "\n\t.popsection\n\t" \
		     : : : "memory")
#define SC_UNLOCK() kd_mutex_unlock(&sc_lock)
MODULE_INFO(kd_mutex_api, "public");
#else
#define SC_LOCK(n) struct kd_mutex_outer_cookie sc_outer_cookie; \
	KD_MUTEX_OUTER_LOCK(&sc_lock, sc_outer_cookie, \
	".globl mc_entry_" #n "\nmc_entry_" #n ":\n\t" ANNOTATE_NOENDBR)
#define SC_UNLOCK() KD_MUTEX_OUTER_UNLOCK(&sc_lock, sc_outer_cookie)
MODULE_INFO(kd_mutex_api, "outer");
#endif
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
#include "body.h"
#include "runner.inc"
