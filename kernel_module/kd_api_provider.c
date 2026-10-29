// SPDX-License-Identifier: GPL-2.0
/* One provider serves both conventional local callers and selected clobber
 * callers on each bound object. The kernel binding holds exact module refs. */
#include "kd_api_provider.h"
#ifdef CONFIG_KD_API_LOCKS
#include <linux/capability.h>
#include <linux/kallsyms.h>
#include <linux/kd_api_provider.h>
#include <linux/module.h>
#include <linux/uaccess.h>
#include "exe.h"
#include "kd_mutex.h"
#include "kd_mutex_direct.h"
#include "kd_source.h"
#include "kd_spin_direct.h"

unsigned long kd_api_spin_unlock_target, kd_api_mutex_unlock_target;
static bool kd_api_registered;
static bool api_bind;
module_param(api_bind, bool, 0444);
MODULE_PARM_DESC(api_bind, "Enable explicit syscall object binding and its three prepared entries");

static void kd_api_spin_local_lock(kd_spinlock_t *lock)
{
	preempt_disable();
	kd_spin_direct_native_lock_inline(lock);
}
static bool kd_api_spin_idle(kd_spinlock_t *lock)
{
	return atomic_read(&lock->val) == 0;
}
static const struct kd_api_provider kd_api_ops = {
	.spin_lock = kd_spin_lock_clobber_v1,
	.spin_unlock = kd_spin_unlock_clobber_v1,
	.mutex_lock = kd_mutex_direct_lock_clobber_v1,
	.mutex_unlock = kd_mutex_direct_unlock_clobber_v1,
	.spin_local_lock = kd_api_spin_local_lock,
	.spin_local_unlock = kd_spin_direct_native_unlock,
	.mutex_local_lock = kd_mutex_local_lock,
	.mutex_local_unlock = kd_mutex_api_unlock,
	.spin_init = kd_spin_init,
	.spin_idle = kd_api_spin_idle,
	.mutex_init = kd_mutex_init,
	.mutex_idle = kd_mutex_is_idle,
	.owner = THIS_MODULE,
	.version = KD_API_VERSION,
};

int kd_api_provider_init(void)
{
	const struct kd_api_site *sites;
	unsigned int count, i;
	unsigned long seen = 0;
	int ret;

	/* Ordinary provider workloads keep their own exact source-entry set. */
	if (!api_bind)
		return 0;
	kd_api_spin_unlock_target = kallsyms_lookup_name("kd_api_files_unlock_clobber");
	kd_api_mutex_unlock_target = kallsyms_lookup_name("kd_api_pipe_unlock_clobber");
	if (!kd_api_spin_unlock_target || !kd_api_mutex_unlock_target)
		return -ENOENT;
	sites = kd_api_sites(&count);
	if (count != KD_API_SITE_COUNT)
		return -EINVAL;
	for (i = 0; i < count; i++) {
		struct kd_exe_info *exe;
		unsigned int kind, abi;

		if (!sites[i].entry || !sites[i].site || sites[i].site > KD_API_SITE_COUNT ||
		    sites[i].reserved || (seen & BIT(sites[i].site)))
			return -EINVAL;
		seen |= BIT(sites[i].site);
		/* Kernel text is permanent; preparation still uses the normal exact
		 * source registry and its immutable image/retirement protocol. */
		kind = sites[i].site == KD_API_SITE_SETFD ? KD_EXE_LOCK_SPIN : KD_EXE_LOCK_MUTEX;
		abi = sites[i].site == KD_API_SITE_SETFD ? KD_ENTRY_ABI_SPIN_CLOBBER_V1 : KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
		kd_exe_add_abi(0, sites[i].entry, kind, abi);
		exe = kd_get_exe(0, sites[i].entry);
		if (!exe || READ_ONCE(exe->status_code) == KD_EXE_UNUSED ||
		    READ_ONCE(exe->RIP) != sites[i].entry ||
		    READ_ONCE(exe->lock_kind) != kind || READ_ONCE(exe->entry_abi) != abi)
			return -ENOMEM;
	}
	ret = kd_api_register_provider(&kd_api_ops);
	if (!ret)
		kd_api_registered = true;
	return ret;
}

void kd_api_provider_exit(void)
{
	if (kd_api_registered) {
		kd_api_unregister_provider(&kd_api_ops);
		kd_api_registered = false;
	}
}

void kd_api_provider_release(struct file *file)
{
	kd_api_cancel_selector(file);
}

long kd_api_provider_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	struct kd_api_select select;
	struct kd_api_query query;
	int ret;

	if (!capable(CAP_SYS_ADMIN))
		return -EPERM;
	if (!kd_api_registered)
		return -ENODEV;
	switch (command) {
	case KD_API_SELECT:
		if (!kd_source_is_open())
			return -ESHUTDOWN;
		if (copy_from_user(&select, (void __user *)arg, sizeof(select)))
			return -EFAULT;
		return kd_api_select_current(file, &kd_api_ops, &select);
	case KD_API_CANCEL:
		kd_api_cancel_selector(file);
		return 0;
	case KD_API_QUERY:
		if (copy_from_user(&query, (void __user *)arg, sizeof(query)))
			return -EFAULT;
		ret = kd_api_query_current(&query);
		return ret ?: (copy_to_user((void __user *)arg, &query, sizeof(query)) ? -EFAULT : 0);
	default:
		return -ENOTTY;
	}
}
#endif
