// SPDX-License-Identifier: GPL-2.0
/* Independent external module: native arm loads without kdlock symbols. */
#include <linux/build_bug.h>
#include <linux/atomic.h>
#include <linux/fs.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include "api.h"
#include "payload.h"
#include "post_work.h"

#define SC_DEVICE_NAME "spin_cacheline"
#define SC_LOCK_KIND 1
#ifdef SC_DIRECT_KDLOCK
#ifdef SC_SPIN_PUBLIC_API
MODULE_INFO(kd_spin_api, "public");
#else
MODULE_INFO(kd_spin_api, "direct");
#endif
#endif
static int sc_worker_register(void) { return 0; }
static int sc_workers_drain(void) { return 0; }
static void sc_lock_init(void)
{
	BUILD_BUG_ON(offsetof(spinlock_t, rlock) != 0);
#ifdef SC_DIRECT_KDLOCK
	kd_spin_init(&sc_lock);
#else
	spin_lock_init(&sc_lock);
#endif
}
#include "runner.inc"
