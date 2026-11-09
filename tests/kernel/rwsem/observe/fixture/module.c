// SPDX-License-Identifier: GPL-2.0
#include <linux/atomic.h>
#include <linux/delay.h>
#include <linux/fs.h>
#include <linux/kprobes.h>
#include <linux/jiffies.h>
#include <linux/kernel.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/vmalloc.h>
#include <linux/workqueue.h>
#include "api.h"

#ifndef CONFIG_X86_64
#error "The observed first pointer argument and integer return ABI is x86-64"
#endif

static unsigned int capacity = 16384;
module_param(capacity, uint, 0400);
static unsigned int drain_ms = 100;
module_param(drain_ms, uint, 0400);
static unsigned int maxactive = 256;
module_param(maxactive, uint, 0400);
static char *api_symbols[KD_RWSEM_OBSERVE_APIS] = {
	"kd_down_write", "kd_down_write_killable", "kd_down_write_interruptible",
	"kd_down_write_trylock", "kd_down_read", "kd_down_read_killable",
	"kd_down_read_interruptible", "kd_down_read_trylock", "kd_downgrade_write",
	"kd_up_write", "kd_up_read",
};
static int symbols_count = KD_RWSEM_OBSERVE_APIS;
module_param_array(api_symbols, charp, &symbols_count, 0400);
MODULE_PARM_DESC(api_symbols, "Exact eleven positional API symbols; empty names disable slots");

struct api_probe {
	struct kretprobe probe;
	bool active;
	u32 api, category, return_kind;
};
struct call_record {
	u64 lock, pairing_id, task_start;
	u32 tid, tgid;
};
static struct api_probe probes[KD_RWSEM_OBSERVE_APIS];
static struct kd_rwsem_observe_symbol symbols[KD_RWSEM_OBSERVE_APIS];
static struct kd_rwsem_observe_event *events;
static struct kd_rwsem_observe_header snapshot;
static struct kd_rwsem_observe_arm selection;
static atomic64_t event_reserved = ATOMIC64_INIT(0);
static atomic64_t pairing = ATOMIC64_INIT(0);
static atomic64_t overflow = ATOMIC64_INIT(0);
static atomic64_t inflight = ATOMIC64_INIT(0);
static atomic64_t errors = ATOMIC64_INIT(0);
static DEFINE_MUTEX(control);
static bool armed, used;
static struct delayed_work stop_work;

static bool selected_tid(u32 tid)
{
	unsigned int i;

	for (i = 0; i < selection.nr_tids; i++)
		if (selection.tids[i] == tid)
			return true;
	return false;
}

static void record_event(const struct api_probe *api, const struct call_record *call,
			 u32 kind, s64 result)
{
	struct kd_rwsem_observe_event *event;
	u64 now = ktime_get_ns();
	u64 index = atomic64_fetch_inc(&event_reserved);

	if (index >= capacity) {
		atomic64_inc(&overflow);
		return;
	}
	event = &events[index];
	event->time_ns = now;
	event->lock = call->lock;
	event->pairing_id = call->pairing_id;
	event->task_start_boottime_ns = current->start_boottime;
	event->result = result;
	event->tid = task_pid_nr(current);
	event->tgid = task_tgid_nr(current);
	event->cpu = raw_smp_processor_id();
	event->event = kind;
	event->api = api->api;
	/* Sequence is the per-slot publication, not timestamp ordering across CPUs. */
	smp_store_release(&event->sequence, index + 1);
}

static int observe_entry(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct api_probe *api = container_of(get_kretprobe(instance), struct api_probe, probe);
	struct call_record *call = (struct call_record *)instance->data;
	u32 kind, tid = task_pid_nr(current);

	if (!smp_load_acquire(&armed) || !selected_tid(tid))
		return 1;
	call->lock = regs->di;
	call->pairing_id = atomic64_inc_return(&pairing);
	call->task_start = current->start_boottime;
	call->tid = tid;
	call->tgid = task_tgid_nr(current);
	atomic64_inc(&inflight);
	kind = api->category == KD_RWSEM_DOWNGRADE ? KD_RWSEM_DOWNGRADE_INVOKE :
		api->category >= KD_RWSEM_WRITE_RELEASE ? KD_RWSEM_RELEASE_INVOKE :
		KD_RWSEM_ACQUIRE_INVOKE;
	record_event(api, call, kind, 0);
	return 0;
}

static int observe_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct api_probe *api = container_of(get_kretprobe(instance), struct api_probe, probe);
	struct call_record *call = (struct call_record *)instance->data;
	s64 result = api->return_kind == KD_RWSEM_VOID ? 0 : (int)regs_return_value(regs);
	u32 kind;
	bool success;

	if (task_pid_nr(current) != call->tid || current->start_boottime != call->task_start)
		atomic64_inc(&errors);
	if (api->category == KD_RWSEM_DOWNGRADE)
		kind = KD_RWSEM_DOWNGRADE_RETURN;
	else if (api->category >= KD_RWSEM_WRITE_RELEASE)
		kind = KD_RWSEM_RELEASE_RETURN;
	else {
		success = api->return_kind == KD_RWSEM_VOID ||
			(api->return_kind == KD_RWSEM_ZERO_SUCCESS ? !result : !!result);
		kind = success ? KD_RWSEM_ACQUIRE_SUCCESS : KD_RWSEM_ACQUIRE_FAILURE;
	}
	/* Retain a selected invocation's return even if STOP has just begun. */
	record_event(api, call, kind, result);
	atomic64_dec(&inflight);
	return 0;
}
NOKPROBE_SYMBOL(observe_entry);
NOKPROBE_SYMBOL(observe_return);
NOKPROBE_SYMBOL(record_event);
NOKPROBE_SYMBOL(selected_tid);

static void update_snapshot(void)
{
	unsigned int i;

	snapshot.reserved = atomic64_read(&event_reserved);
	snapshot.count = min_t(u64, snapshot.reserved, capacity);
	snapshot.overflow = atomic64_read(&overflow);
	snapshot.inflight = atomic64_read(&inflight);
	snapshot.errors = atomic64_read(&errors);
	snapshot.armed = READ_ONCE(armed);
	snapshot.missed = 0;
	for (i = 0; i < KD_RWSEM_OBSERVE_APIS; i++)
		snapshot.missed += probes[i].probe.nmissed + probes[i].probe.kp.nmissed;
}

/* Caller holds control. Unregister synchronizes probe handlers; no retained
 * object/task pointers need a separate lifetime lock or reference transfer. */
static void stop_locked(void)
{
	unsigned long deadline;
	unsigned int i;

	if (snapshot.stopped)
		return;
	snapshot.cutoff_ns = ktime_get_ns();
	smp_store_release(&armed, false);
	/* Existing return handlers remain enabled while entry admission is closed.
	 * A long-running call is not forced to return or treated as completed. */
	deadline = jiffies + max_t(unsigned long, 1, msecs_to_jiffies(drain_ms));
	while (atomic64_read(&inflight) && time_before(jiffies, deadline))
		msleep(1);
	for (i = 0; i < KD_RWSEM_OBSERVE_APIS; i++) {
		if (probes[i].active) {
			unregister_kretprobe(&probes[i].probe);
			probes[i].active = false;
		}
	}
	snapshot.stop_ns = ktime_get_ns();
	snapshot.stopped = 1;
	update_snapshot();
	for (i = 0; i < snapshot.count; i++)
		if (smp_load_acquire(&events[i].sequence) != (u64)i + 1)
			snapshot.errors++;
}

static void automatic_stop(struct work_struct *work)
{
	(void)work;
	mutex_lock(&control);
	stop_locked();
	mutex_unlock(&control);
}

static int arm_locked(const struct kd_rwsem_observe_arm *arm)
{
	unsigned int i, j;
	int ret;

	if (used || snapshot.stopped)
		return -EALREADY;
	if (arm->abi != KD_RWSEM_OBSERVE_ABI || arm->reserved ||
	    !arm->nr_tids || arm->nr_tids > KD_RWSEM_OBSERVE_TIDS ||
	    !arm->duration_ms || arm->duration_ms > 1000)
		return -EINVAL;
	for (i = 0; i < KD_RWSEM_OBSERVE_TIDS; i++) {
		if (i >= arm->nr_tids) {
			if (arm->tids[i])
				return -EINVAL;
			continue;
		}
		if (!arm->tids[i] || arm->tids[i] > INT_MAX)
			return -EINVAL;
		for (j = 0; j < i; j++)
			if (arm->tids[i] == arm->tids[j])
				return -EINVAL;
	}
	selection = *arm;
	used = true;
	snapshot.duration_ms = arm->duration_ms;
	for (i = 0; i < KD_RWSEM_OBSERVE_APIS; i++) {
		if (!symbols[i].name[0])
			continue;
		ret = register_kretprobe(&probes[i].probe);
		if (ret) {
			atomic64_inc(&errors);
			stop_locked();
			return ret;
		}
		probes[i].active = true;
		symbols[i].registered = 1;
	}
	snapshot.start_ns = ktime_get_ns();
	smp_store_release(&armed, true);
	snapshot.armed = 1;
	schedule_delayed_work(&stop_work, max_t(unsigned long, 1,
					      msecs_to_jiffies(arm->duration_ms)));
	return 0;
}

static long observe_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	struct kd_rwsem_observe_arm arm;
	long ret = 0;

	(void)file;
	if (command == KD_RWSEM_OBSERVE_ARM && copy_from_user(&arm, (void __user *)arg, sizeof(arm)))
		return -EFAULT;
	/* Never wait for a work item while holding the lock it takes. */
	if (command == KD_RWSEM_OBSERVE_STOP)
		cancel_delayed_work_sync(&stop_work);
	mutex_lock(&control);
	switch (command) {
	case KD_RWSEM_OBSERVE_ARM:
		ret = arm_locked(&arm);
		break;
	case KD_RWSEM_OBSERVE_STOP:
		stop_locked();
		break;
	case KD_RWSEM_OBSERVE_HEADER:
		if (!snapshot.stopped)
			update_snapshot();
		if (copy_to_user((void __user *)arg, &snapshot, sizeof(snapshot)))
			ret = -EFAULT;
		break;
	default:
		ret = -ENOTTY;
	}
	mutex_unlock(&control);
	return ret;
}

static ssize_t observe_read(struct file *file, char __user *buffer, size_t count, loff_t *offset)
{
	const void *data;
	size_t size, available;
	loff_t local;
	ssize_t ret;

	(void)file;
	mutex_lock(&control);
	if (!snapshot.stopped) {
		ret = -EBUSY;
		goto out;
	}
	if (*offset < 0) {
		ret = -EINVAL;
		goto out;
	}
	local = *offset;
	if (local < sizeof(snapshot)) {
		data = &snapshot;
		size = sizeof(snapshot);
	} else if ((local -= sizeof(snapshot)) < sizeof(symbols)) {
		data = symbols;
		size = sizeof(symbols);
	} else {
		local -= sizeof(symbols);
		data = events;
		size = snapshot.count * sizeof(*events);
	}
	available = local < size ? size - local : 0;
	count = min(count, available);
	ret = count && copy_to_user(buffer, (const char *)data + local, count) ? -EFAULT : count;
	if (ret > 0)
		*offset += ret;
 out:
	mutex_unlock(&control);
	return ret;
}

static const struct file_operations observe_operations = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = observe_ioctl,
	.read = observe_read,
};
static struct miscdevice observe_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "kd_rwsem_observe",
	.fops = &observe_operations,
	.mode = 0600,
};

static int __init observe_init(void)
{
	static const u32 categories[] = {
		KD_RWSEM_WRITE, KD_RWSEM_WRITE, KD_RWSEM_WRITE, KD_RWSEM_WRITE,
		KD_RWSEM_READ, KD_RWSEM_READ, KD_RWSEM_READ, KD_RWSEM_READ,
		KD_RWSEM_DOWNGRADE, KD_RWSEM_WRITE_RELEASE, KD_RWSEM_READ_RELEASE,
	};
	static const u32 returns[] = {
		KD_RWSEM_VOID, KD_RWSEM_ZERO_SUCCESS, KD_RWSEM_ZERO_SUCCESS, KD_RWSEM_NONZERO_SUCCESS,
		KD_RWSEM_VOID, KD_RWSEM_ZERO_SUCCESS, KD_RWSEM_ZERO_SUCCESS, KD_RWSEM_NONZERO_SUCCESS,
		KD_RWSEM_VOID, KD_RWSEM_VOID, KD_RWSEM_VOID,
	};
	unsigned int i, j, enabled = 0;
	int ret;

	BUILD_BUG_ON(sizeof(snapshot) != 152);
	BUILD_BUG_ON(sizeof(symbols[0]) != 144);
	BUILD_BUG_ON(sizeof(*events) != 72);
	BUILD_BUG_ON(sizeof(struct kd_rwsem_observe_arm) != 288);
	if (!capacity || capacity > 262144 || !drain_ms || drain_ms > 1000 || !maxactive || maxactive > 4096 ||
	    symbols_count != KD_RWSEM_OBSERVE_APIS)
		return -EINVAL;
	for (i = 0; i < KD_RWSEM_OBSERVE_APIS; i++) {
		if (!api_symbols[i] || strlen(api_symbols[i]) >= KD_RWSEM_OBSERVE_NAME)
			return -EINVAL;
		for (j = 0; j < i; j++)
			if (api_symbols[i][0] && !strcmp(api_symbols[i], api_symbols[j]))
				return -EINVAL;
		strscpy(symbols[i].name, api_symbols[i], sizeof(symbols[i].name));
		symbols[i].api = probes[i].api = i + 1;
		symbols[i].category = probes[i].category = categories[i];
		symbols[i].return_kind = probes[i].return_kind = returns[i];
		probes[i].probe.kp.symbol_name = symbols[i].name;
		probes[i].probe.entry_handler = observe_entry;
		probes[i].probe.handler = observe_return;
		probes[i].probe.data_size = sizeof(struct call_record);
		probes[i].probe.maxactive = maxactive;
		enabled += !!api_symbols[i][0];
	}
	if (!enabled)
		return -EINVAL;
	events = kvcalloc(capacity, sizeof(*events), GFP_KERNEL);
	if (!events)
		return -ENOMEM;
	snapshot.abi = KD_RWSEM_OBSERVE_ABI;
	snapshot.header_bytes = sizeof(snapshot);
	snapshot.event_bytes = sizeof(*events);
	snapshot.symbol_bytes = sizeof(symbols[0]);
	snapshot.symbol_count = KD_RWSEM_OBSERVE_APIS;
	snapshot.capacity = capacity;
	/* API events deliberately expose no origin/executor execution claim. */
	snapshot.proxy_proof = 0;
	INIT_DELAYED_WORK(&stop_work, automatic_stop);
	ret = misc_register(&observe_device);
	if (ret)
		kvfree(events);
	return ret;
}

static void __exit observe_exit(void)
{
	misc_deregister(&observe_device);
	cancel_delayed_work_sync(&stop_work);
	mutex_lock(&control);
	stop_locked();
	mutex_unlock(&control);
	kvfree(events);
}
module_init(observe_init);
module_exit(observe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Generic bounded callable rwsem API observation; no proxy execution proof");
