/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_TARGET_H
#define KDLOCK_TARGET_H

#include <linux/kconfig.h>
#include <linux/version.h>

/* C-only build gates for the fixed target, not API/context admission. */
#if !defined(CONFIG_X86_64)
#error "kdlock rebuild requires CONFIG_X86_64"
#endif

#if defined(CONFIG_PREEMPT_RT)
#error "kdlock rebuild does not target CONFIG_PREEMPT_RT"
#endif

#if LINUX_VERSION_CODE < KERNEL_VERSION(7, 0, 0) || \
    LINUX_VERSION_CODE >= KERNEL_VERSION(7, 1, 0)
#error "kdlock rebuild targets the Linux 7.0 series"
#endif

#endif
