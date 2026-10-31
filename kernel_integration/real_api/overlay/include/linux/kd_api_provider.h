/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_KD_API_PROVIDER_H
#define _LINUX_KD_API_PROVIDER_H

/* First eight pointer offsets are consumed by the no-frame tail bridges.
 * The C implementation statically verifies every assembly-used offset. */
#define KD_API_OP_SPIN_LOCK 0
#define KD_API_OP_SPIN_UNLOCK 8
#define KD_API_OP_MUTEX_LOCK 16
#define KD_API_OP_MUTEX_UNLOCK 24
#define KD_API_OP_SPIN_LOCAL_LOCK 32
#define KD_API_OP_SPIN_LOCAL_UNLOCK 40
#define KD_API_OP_MUTEX_LOCAL_LOCK 48
#define KD_API_OP_MUTEX_LOCAL_UNLOCK 56

#ifndef __ASSEMBLER__
#include <linux/kd_api_control.h>
#include <linux/kd_api_lock_types.h>
struct module;
struct file;

struct kd_api_provider {
	void (*spin_lock)(kd_spinlock_t *, unsigned long, unsigned long, unsigned long);
	void (*spin_unlock)(kd_spinlock_t *, unsigned long, unsigned long, unsigned long);
	void (*mutex_lock)(struct kd_mutex *, unsigned long, unsigned long, unsigned long);
	void (*mutex_unlock)(struct kd_mutex *, unsigned long, unsigned long, unsigned long);
	void (*spin_local_lock)(kd_spinlock_t *);
	void (*spin_local_unlock)(kd_spinlock_t *);
	void (*mutex_local_lock)(struct kd_mutex *);
	void (*mutex_local_unlock)(struct kd_mutex *);
	void (*spin_init)(kd_spinlock_t *);
	bool (*spin_idle)(kd_spinlock_t *);
	void (*mutex_init)(struct kd_mutex *);
	bool (*mutex_idle)(struct kd_mutex *);
	struct module *owner;
	u32 version;
};
struct kd_api_site { unsigned long entry; u32 site; u32 reserved; };
int kd_api_register_provider(const struct kd_api_provider *ops);
void kd_api_unregister_provider(const struct kd_api_provider *ops);
int kd_api_select_current(struct file *token, const struct kd_api_provider *ops,
			  const struct kd_api_select *selection);
void kd_api_cancel_selector(struct file *token);
int kd_api_query_current(struct kd_api_query *query);
const struct kd_api_site *kd_api_sites(unsigned int *count);
#endif
#endif
