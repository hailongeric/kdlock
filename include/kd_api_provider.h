/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_API_PROVIDER_H
#define KD_API_PROVIDER_H
#include <linux/errno.h>
#include <linux/types.h>
#include "kd_api_control.h"
struct file;
#ifdef CONFIG_KD_API_LOCKS
extern unsigned long kd_api_spin_unlock_target, kd_api_mutex_unlock_target;
int kd_api_provider_init(void);
void kd_api_provider_exit(void);
long kd_api_provider_ioctl(struct file *, unsigned int, unsigned long);
void kd_api_provider_release(struct file *);
static inline bool kd_api_unlock_target(unsigned long target)
{
	return target && (target == kd_api_spin_unlock_target ||
			  target == kd_api_mutex_unlock_target);
}
static inline bool kd_api_outer_unlock(unsigned long target, unsigned long lock,
				       unsigned long outer, bool mutex_backend)
{
	return outer && lock == outer && target &&
	       target == (mutex_backend ? kd_api_mutex_unlock_target : kd_api_spin_unlock_target);
}
#else
static inline int kd_api_provider_init(void) { return 0; }
static inline void kd_api_provider_exit(void) { }
static inline long kd_api_provider_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{ return -EOPNOTSUPP; }
static inline void kd_api_provider_release(struct file *file) { }
static inline bool kd_api_unlock_target(unsigned long target) { return false; }
static inline bool kd_api_outer_unlock(unsigned long target, unsigned long lock,
				       unsigned long outer, bool mutex_backend)
{ return false; }
#endif
#endif
