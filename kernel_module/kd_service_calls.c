// SPDX-License-Identifier: GPL-2.0
/* Configuration is separate from acquisition. Immutable slots are not reused
 * within a provider lifetime, so a retained image never observes another API
 * at an earlier registration's address/cookie. */
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/kallsyms.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/string.h>
#include "kd_service_calls.h"
#include "kd_source.h"

#define KD_SERVICE_CALL_MAX 128U
#define KD_SERVICE_CALL_NAME 96U
struct kd_service_call_entry {
	unsigned long target;
	struct module *owner;
	u64 cookie;
	atomic_t users;
	unsigned char nargs, result_kind, context_kind;
	bool active;
	char symbol[KD_SERVICE_CALL_NAME];
};
static struct kd_service_call_entry kd_service_call_entries[KD_SERVICE_CALL_MAX];
static unsigned int kd_service_call_count;
static bool kd_service_call_frozen;
static DEFINE_MUTEX(kd_service_call_configuration);

static bool kd_service_call_requires_preempt_rcu(unsigned int context)
{
	return context >= KD_SERVICE_CALL_PTE_LOCK &&
		context <= KD_SERVICE_CALL_PTE_RCU;
}

static bool kd_service_call_context_valid(const struct kd_service_call_desc *desc)
{
	switch (desc->context_kind) {
	case KD_SERVICE_CALL_BALANCED_ORIGIN:
	case KD_SERVICE_CALL_ATOMIC_ORIGIN:
		return true;
	case KD_SERVICE_CALL_SCHEDULE_ORIGIN:
		return !desc->nargs && desc->result_kind == KD_SERVICE_CALL_VOID;
	case KD_SERVICE_CALL_NONRETURNING_ORIGIN:
		return !desc->nargs && desc->result_kind == KD_SERVICE_CALL_VOID &&
			desc->symbol && !strcmp(desc->symbol, "__stack_chk_fail");
	case KD_SERVICE_CALL_PTE_LOCK:
		return IS_ENABLED(CONFIG_PREEMPT_RCU) && desc->nargs == 4 &&
			desc->result_kind == KD_SERVICE_CALL_WORD;
	case KD_SERVICE_CALL_SPIN_LOCK:
	case KD_SERVICE_CALL_SPIN_UNLOCK:
		return IS_ENABLED(CONFIG_PREEMPT_RCU) && desc->nargs == 1 &&
			desc->result_kind == KD_SERVICE_CALL_VOID;
	case KD_SERVICE_CALL_SPIN_TRYLOCK:
		return IS_ENABLED(CONFIG_PREEMPT_RCU) && desc->nargs == 1 &&
			desc->result_kind == KD_SERVICE_CALL_WORD;
	case KD_SERVICE_CALL_RCU_LOCK:
	case KD_SERVICE_CALL_RCU_UNLOCK:
		return IS_ENABLED(CONFIG_PREEMPT_RCU) && !desc->nargs &&
			desc->result_kind == KD_SERVICE_CALL_VOID;
	case KD_SERVICE_CALL_PTE_RCU:
		return IS_ENABLED(CONFIG_PREEMPT_RCU) && desc->nargs >= 3 &&
			desc->nargs <= 5 && desc->result_kind == KD_SERVICE_CALL_WORD;
	default:
		return false;
	}
}

static bool kd_service_call_valid(const struct kd_service_call_desc *desc)
{
	return desc->symbol && *desc->symbol && desc->target && desc->nargs <= 6 &&
		!desc->reserved &&
		(desc->result_kind == KD_SERVICE_CALL_WORD ||
		 desc->result_kind == KD_SERVICE_CALL_VOID) &&
		kd_service_call_context_valid(desc) &&
		(desc->context_kind != KD_SERVICE_CALL_NONRETURNING_ORIGIN ||
		 desc->target == kallsyms_lookup_name("__stack_chk_fail")) &&
		strnlen(desc->symbol, KD_SERVICE_CALL_NAME) < KD_SERVICE_CALL_NAME &&
		!strpbrk(desc->symbol, " \t\r\n");
}

static int kd_service_call_format(char *buffer, size_t size, u64 cookie,
	unsigned long target, unsigned int nargs, unsigned int result_kind,
	unsigned int context_kind, const char *symbol)
{
	return snprintf(buffer, size, "%llx %lx %u %u %u %s\n",
		(unsigned long long)cookie, target, nargs, result_kind, context_kind, symbol);
}

/* Validate the exact exported snapshot before publishing any of this batch.
 * Internal slot capacity and one-page discovery capacity are separate bounds. */
static int kd_service_call_configuration_size(const struct kd_service_call_desc *descs,
	unsigned int count)
{
	char row[160];
	size_t bytes = 0;
	unsigned int i;
	int length;

	for (i = 0; i < kd_service_call_count; ++i) {
		const struct kd_service_call_entry *entry = &kd_service_call_entries[i];

		if (!entry->active)
			continue;
		length = kd_service_call_format(row, sizeof(row), entry->cookie,
			entry->target, entry->nargs, entry->result_kind,
			entry->context_kind, entry->symbol);
		if (length < 0 || (size_t)length >= sizeof(row))
			return -EOVERFLOW;
		bytes += length;
	}
	for (i = 0; i < count; ++i) {
		length = kd_service_call_format(row, sizeof(row), kd_service_call_count + i + 1,
			descs[i].target, descs[i].nargs, descs[i].result_kind,
			descs[i].context_kind, descs[i].symbol);
		if (length < 0 || (size_t)length >= sizeof(row))
			return -EOVERFLOW;
		bytes += length;
	}
	/* snprintf's final NUL occupies one byte in the fixed PAGE_SIZE buffer. */
	return bytes < PAGE_SIZE ? 0 : -ENOSPC;
}

int kd_service_call_register(const struct kd_service_call_desc *descs,
	unsigned int count, struct module *owner)
{
	unsigned int i, j;
	int result = 0;

	if (!descs || !count || count > KD_SERVICE_CALL_MAX)
		return -EINVAL;
	mutex_lock(&kd_service_call_configuration);
	if (kd_service_call_frozen) {
		result = -EBUSY;
		goto out;
	}
	if (count > KD_SERVICE_CALL_MAX - kd_service_call_count) {
		result = -ENOSPC;
		goto out;
	}
	for (i = 0; i < count; ++i) {
		if (!kd_service_call_valid(&descs[i])) {
			result = -EINVAL;
			goto out;
		}
		for (j = 0; j < kd_service_call_count; ++j)
			if (kd_service_call_entries[j].active &&
			    (kd_service_call_entries[j].target == descs[i].target ||
			     !strcmp(kd_service_call_entries[j].symbol, descs[i].symbol))) {
				result = -EEXIST;
				goto out;
			}
		for (j = 0; j < i; ++j)
			if (descs[j].target == descs[i].target ||
			    !strcmp(descs[j].symbol, descs[i].symbol)) {
				result = -EEXIST;
				goto out;
			}
	}
	result = kd_service_call_configuration_size(descs, count);
	if (result)
		goto out;
	for (i = 0; i < count; ++i) {
		struct kd_service_call_entry *entry =
			&kd_service_call_entries[kd_service_call_count];

		entry->target = descs[i].target;
		entry->owner = owner;
		entry->cookie = kd_service_call_count + 1;
		entry->nargs = descs[i].nargs;
		entry->result_kind = descs[i].result_kind;
		entry->context_kind = descs[i].context_kind;
		strscpy(entry->symbol, descs[i].symbol, sizeof(entry->symbol));
		atomic_set(&entry->users, 0);
		smp_store_release(&entry->active, true);
		/* A reader can only inspect fully initialized immutable entries. */
		smp_store_release(&kd_service_call_count, kd_service_call_count + 1);
	}
out:
	mutex_unlock(&kd_service_call_configuration);
	return result;
}
EXPORT_SYMBOL_GPL(kd_service_call_register);

int kd_service_call_unregister(struct module *owner)
{
	struct kd_source_info info;
	unsigned int i;
	int result = 0;

	if (!owner)
		return -EINVAL;
	mutex_lock(&kd_service_call_configuration);
	kd_source_info(&info);
	/* A later helper in a committed frame must remain callable. Closing new
	 * source admission is required before this exact no-reader check. */
	if (info.state == KD_SOURCE_OPEN || info.frames || info.writers) {
		result = -EBUSY;
		goto out;
	}
	for (i = 0; i < kd_service_call_count; ++i)
		if (kd_service_call_entries[i].owner == owner &&
		    atomic_read(&kd_service_call_entries[i].users)) {
			result = -EBUSY;
			goto out;
		}
	for (i = 0; i < kd_service_call_count; ++i)
		if (kd_service_call_entries[i].owner == owner)
			smp_store_release(&kd_service_call_entries[i].active, false);
out:
	mutex_unlock(&kd_service_call_configuration);
	return result;
}
EXPORT_SYMBOL_GPL(kd_service_call_unregister);

struct kd_service_call_entry *kd_service_call_get(unsigned long target)
{
	unsigned int i, count = smp_load_acquire(&kd_service_call_count);

	for (i = 0; i < count; ++i) {
		struct kd_service_call_entry *entry = &kd_service_call_entries[i];

		if (!smp_load_acquire(&entry->active) || entry->target != target)
			continue;
		if (entry->owner && !try_module_get(entry->owner))
			return NULL;
		atomic_inc(&entry->users);
		if (unlikely(!smp_load_acquire(&entry->active))) {
			kd_service_call_put(entry);
			return NULL;
		}
		return entry;
	}
	return NULL;
}

void kd_service_call_put(struct kd_service_call_entry *entry)
{
	struct module *owner;

	BUG_ON(!entry || atomic_read(&entry->users) <= 0);
	owner = entry->owner;
	atomic_dec(&entry->users);
	if (owner)
		module_put(owner);
}

bool kd_service_call_matches(const struct kd_service_call_entry *entry,
	unsigned long target)
{
	return entry && entry->target == target && atomic_read(&entry->users) > 0 &&
		smp_load_acquire(&entry->active);
}

unsigned int kd_service_call_context(const struct kd_service_call_entry *entry)
{
	BUG_ON(!entry || !atomic_read(&entry->users));
	return entry->context_kind;
}

int kd_service_calls_pin(void)
{
	unsigned int i;
	int result = 0;

	mutex_lock(&kd_service_call_configuration);
	/* The first helper image fixes this provider session's descriptor set.
	 * Later source closure cannot invalidate an already committed dependency. */
	kd_service_call_frozen = true;
	for (i = 0; i < kd_service_call_count; ++i) {
		if (!kd_service_call_entries[i].active)
			continue;
		result = kd_source_pin_root(kd_service_call_entries[i].target);
		if (result)
			break;
	}
	mutex_unlock(&kd_service_call_configuration);
	return result;
}

static int kd_service_call_table_get(char *buffer, const struct kernel_param *parameter)
{
	unsigned int i;
	int used = 0;

	(void)parameter;
	mutex_lock(&kd_service_call_configuration);
	for (i = 0; i < kd_service_call_count; ++i) {
		const struct kd_service_call_entry *entry = &kd_service_call_entries[i];
		int length;

		if (!entry->active)
			continue;
		length = kd_service_call_format(buffer + used, PAGE_SIZE - used,
			entry->cookie, entry->target, entry->nargs, entry->result_kind,
			entry->context_kind, entry->symbol);

		if (length < 0 || (size_t)length >= PAGE_SIZE - used) {
			used = -EOVERFLOW;
			break;
		}
		used += length;
	}
	mutex_unlock(&kd_service_call_configuration);
	return used;
}
static const struct kernel_param_ops kd_service_call_table_ops = {
	.get = kd_service_call_table_get,
};
module_param_cb(service_call_table, &kd_service_call_table_ops, NULL, 0444);
MODULE_PARM_DESC(service_call_table, "Exact returning primitive descriptors for the retained provider");

int kd_service_calls_init(void)
{
	struct kd_service_call_desc desc;
	int result;

#define KD_SERVICE_CONTEXT(name, args, result_type, context) do { \
	desc = (struct kd_service_call_desc){ .symbol = #name, \
		.target = kallsyms_lookup_name(#name), .nargs = args, \
		.result_kind = result_type, .context_kind = context }; \
	if (kd_service_call_requires_preempt_rcu(context) && \
	    !IS_ENABLED(CONFIG_PREEMPT_RCU)) \
		break; \
	if (desc.target) { \
		result = kd_service_call_register(&desc, 1, NULL); \
		if (result) return result; \
	} \
} while (0);
#define KD_SERVICE_CALL(name, args, result_type) \
	KD_SERVICE_CONTEXT(name, args, result_type, KD_SERVICE_CALL_BALANCED_ORIGIN)
#include "kd_service_calls.def"
#undef KD_SERVICE_CALL
#undef KD_SERVICE_CONTEXT
	return 0;
}

void kd_service_calls_exit(void)
{
	unsigned int i;

	for (i = 0; i < kd_service_call_count; ++i) {
		BUG_ON(atomic_read(&kd_service_call_entries[i].users));
		WRITE_ONCE(kd_service_call_entries[i].active, false);
	}
}
