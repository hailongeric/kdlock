// SPDX-License-Identifier: GPL-2.0
/* Unscored observation only: no native MM body or lock API is changed. */
#include <linux/fs.h>
#include <linux/atomic.h>
#include <linux/err.h>
#include <linux/kprobes.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mman.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/sched/mm.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include "api.h"

#ifndef CONFIG_X86_64
#error "The captured mmap syscall-wrapper argument contract is x86-64 only"
#endif

static char target[TASK_COMM_LEN];
module_param_string(target, target, sizeof(target), 0444);
static DEFINE_MUTEX(control);
static DEFINE_RAW_SPINLOCK(records_lock);
static struct kd_mmap1_identity_snapshot snapshot;
static struct mm_struct *held_mm[KD_MMAP1_IDENTITY_CAPACITY];
static bool registered;

/* __x64_sys_mmap receives one pointer to the userspace syscall register
 * frame. The fifth argument is a C int at the unchanged application's call
 * boundary, so either upper-half representation of fd=-1 is accepted. */
static bool mmap1_arguments(const struct pt_regs *entry)
{
	const struct pt_regs *args = (const void *)entry->di;

	return args && !args->di && args->si == 128UL * 1024 * 1024 &&
	       args->dx == (PROT_READ | PROT_WRITE) &&
	       args->r10 == (MAP_PRIVATE | MAP_ANONYMOUS) &&
	       (u32)args->r8 == (u32)-1 && !args->r9;
}

static int record_mapping(struct pt_regs *regs)
{
	struct kd_mmap1_identity_record *row;
	struct mm_struct *mm;
	unsigned long flags;
	unsigned int i;
	pid_t tid;
	u64 start;
	bool use_kd = false;
	void *backing;
	const void *provider = NULL;
	u64 route = 0;
	int index = -1;

	/* Observe the real syscall before its MM helper is entered. Keep this
	 * instrumentation outside the translated MM call graph and exclude
	 * loader/harness mappings with the unchanged application's exact tuple. */
	if (strncmp(current->comm, target, TASK_COMM_LEN) || !mmap1_arguments(regs))
		return -1;
	mm = current->mm;
	if (!mm)
		return -1;
	tid = task_pid_nr(current);
	start = current->start_boottime;
#ifdef CONFIG_KDLOCK_MMAP
	use_kd = READ_ONCE(mm->mmap_lock.use_kd);
	backing = use_kd ? (void *)&mm->mmap_lock.kd : (void *)&mm->mmap_lock.native;
	provider = READ_ONCE(mm->mmap_lock.provider);
	route = use_kd ? (provider ? 2 : 1) : 0;
#else
	backing = &mm->mmap_lock;
#endif
	raw_spin_lock_irqsave(&records_lock, flags);
	for (i = 0; i < snapshot.count; i++) {
		row = &snapshot.records[i];
		if (row->tid != (u64)tid || row->start_boottime_ns != start)
			continue;
		if (row->mm != (unsigned long)mm || row->lock != (unsigned long)&mm->mmap_lock ||
		    row->backing != (unsigned long)backing || row->use_kd != use_kd ||
		    row->provider != (unsigned long)provider || row->route != route)
			snapshot.errors++;
		else
			index = i;
		goto out;
	}
	if (snapshot.count == KD_MMAP1_IDENTITY_CAPACITY) {
		snapshot.overflow++;
		goto out;
	}
	/* Retain the exact allocation while the table contains its address.
	 * The original task owns mm_users here. Teardown drops these mm_count
	 * references only after unregister_kprobe has excluded every handler. */
	mmgrab(mm);
	held_mm[i] = mm;
	row = &snapshot.records[i];
	row->tid = tid;
	row->tgid = task_tgid_nr(current);
	row->start_boottime_ns = start;
	row->mm = (unsigned long)mm;
	row->lock = (unsigned long)&mm->mmap_lock;
	row->backing = (unsigned long)backing;
	row->use_kd = use_kd;
	row->cpu = raw_smp_processor_id();
	row->provider = (unsigned long)provider;
	row->route = route;
	snapshot.refs_acquired++;
	snapshot.count++;
	index = i;
out:
	raw_spin_unlock_irqrestore(&records_lock, flags);
	return index;
}

static int observe(struct kprobe *probe, struct pt_regs *regs)
{
	(void)probe;
	record_mapping(regs);
	return 0;
}

static struct kprobe mapping_probe = {
	.symbol_name = "__x64_sys_mmap",
	.pre_handler = observe,
};

/* Optional outer-wrapper observations; no handler enters a Native MM body. */
static unsigned int pair_limit;
module_param(pair_limit, uint, 0400);
MODULE_PARM_DESC(pair_limit, "Complete syscall pairs per task, zero disables, maximum eight");

enum pair_phase { PAIR_IDLE, PAIR_MMAP, PAIR_MAPPED, PAIR_MUNMAP, PAIR_BROKEN };
struct pair_state {
	u64 sequence, address;
	u32 completed, phase;
};
struct pair_call {
	struct kd_mmap1_identity_record identity;
	u64 args[6], sequence;
	u32 index, pair, unmap;
};
static struct pair_state pair_states[KD_MMAP1_IDENTITY_CAPACITY];
static atomic64_t pair_inflight = ATOMIC64_INIT(0);
static atomic64_t pair_errors = ATOMIC64_INIT(0);
static bool pair_armed, pair_registered[2];

static void pair_error(void)
{
	/* Every call site is serialized by records_lock or follows unregister. */
	snapshot.errors++;
	atomic64_inc(&pair_errors);
}

static void pair_marker(const struct pair_call *call, const char *event, unsigned long result)
{
	const struct kd_mmap1_identity_record *row = &call->identity;

	pr_info("kd_mm_pair: event=%s op=%s tid=%llu tgid=%llu start=%llu mm=%llx lock=%llx backing=%llx provider=%llx route=%llu sequence=%llu pair=%u cpu=%u time=%llu args=%llx,%llx,%llx,%llx,%llx,%llx result=%lx\n",
		event, call->unmap ? "munmap" : "mmap", row->tid, row->tgid,
		row->start_boottime_ns, row->mm, row->lock, row->backing, row->provider,
		row->route, call->sequence, call->pair, raw_smp_processor_id(), ktime_get_ns(),
		call->args[0], call->args[1], call->args[2], call->args[3],
		call->args[4], call->args[5], result);
}

static int pair_entry(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct pair_call *call = (struct pair_call *)instance->data;
	const struct pt_regs *args = (const void *)regs->di;
	struct pair_state *state;
	unsigned long flags;
	unsigned int index;
	bool unmap;
	int found;

	if (!smp_load_acquire(&pair_armed) || !args ||
	    strncmp(current->comm, target, TASK_COMM_LEN))
		return 1;
	/* Compare the exact configured symbol, without a source-offset guess. */
	unmap = !strcmp(get_kretprobe(instance)->kp.symbol_name, "__x64_sys_munmap");
	if (!unmap) {
		found = record_mapping(regs);
		if (found < 0)
			return 1;
		index = found;
	} else {
		if (args->si != 128UL * 1024 * 1024)
			return 1;
		index = KD_MMAP1_IDENTITY_CAPACITY;
	}
	raw_spin_lock_irqsave(&records_lock, flags);
	if (!READ_ONCE(pair_armed))
		goto skip;
	if (unmap) {
		for (index = 0; index < snapshot.count; index++)
			if (snapshot.records[index].tid == (u64)task_pid_nr(current) &&
			    snapshot.records[index].start_boottime_ns == current->start_boottime)
				break;
		if (index == snapshot.count)
			goto skip;
	}
	state = &pair_states[index];
	if (state->completed >= pair_limit || state->phase == PAIR_BROKEN)
		goto skip;
	if (snapshot.records[index].mm != (unsigned long)current->mm) {
		pair_error();
		state->phase = PAIR_BROKEN;
		goto skip;
	}
	if (unmap) {
		if (state->phase != PAIR_MAPPED || state->address != args->di)
			goto skip;
		state->phase = PAIR_MUNMAP;
	} else {
		if (state->phase != PAIR_IDLE) {
			pair_error();
			state->phase = PAIR_BROKEN;
			goto skip;
		}
		state->phase = PAIR_MMAP;
	}
	call->identity = snapshot.records[index];
	call->args[0] = args->di;
	call->args[1] = args->si;
	call->args[2] = args->dx;
	call->args[3] = args->r10;
	call->args[4] = args->r8;
	call->args[5] = args->r9;
	call->sequence = ++state->sequence;
	call->index = index;
	call->pair = state->completed + 1;
	call->unmap = unmap;
	atomic64_inc(&pair_inflight);
	raw_spin_unlock_irqrestore(&records_lock, flags);
	pair_marker(call, "enter", 0);
	return 0;
skip:
	raw_spin_unlock_irqrestore(&records_lock, flags);
	return 1;
}

static int pair_return(struct kretprobe_instance *instance, struct pt_regs *regs)
{
	struct pair_call *call = (struct pair_call *)instance->data;
	struct pair_state *state = &pair_states[call->index];
	unsigned long result = regs_return_value(regs), flags;

	raw_spin_lock_irqsave(&records_lock, flags);
	if (call->identity.tid != (u64)task_pid_nr(current) ||
	    call->identity.start_boottime_ns != current->start_boottime ||
	    call->identity.mm != (unsigned long)current->mm ||
	    state->sequence != call->sequence ||
	    state->phase != (call->unmap ? PAIR_MUNMAP : PAIR_MMAP)) {
		pair_error();
		state->phase = PAIR_BROKEN;
	} else if (call->unmap) {
		if (result) {
			pair_error();
			state->phase = PAIR_BROKEN;
		} else {
			state->completed++;
			state->phase = PAIR_IDLE;
		}
	} else if (IS_ERR_VALUE(result) || (result & ~PAGE_MASK)) {
		pair_error();
		state->phase = PAIR_BROKEN;
	} else {
		state->address = result;
		state->phase = PAIR_MAPPED;
	}
	raw_spin_unlock_irqrestore(&records_lock, flags);
	/* An admitted return remains recorded after STOP closes new admission. */
	pair_marker(call, "return", result);
	atomic64_dec(&pair_inflight);
	return 0;
}

static struct kretprobe pair_probes[2] = {
	{ .kp.symbol_name = "__x64_sys_mmap", .entry_handler = pair_entry,
	  .handler = pair_return, .data_size = sizeof(struct pair_call), .maxactive = 256 },
	{ .kp.symbol_name = "__x64_sys_munmap", .entry_handler = pair_entry,
	  .handler = pair_return, .data_size = sizeof(struct pair_call), .maxactive = 256 },
};

static void stop_pairs(void)
{
	u64 missed[2], suppressed[2], completed = 0, unfinished = 0;
	unsigned int i, tasks = 0;

	if (!pair_limit)
		return;
	smp_store_release(&pair_armed, false);
	for (i = 0; i < 2; i++) {
		if (pair_registered[i]) {
			unregister_kretprobe(&pair_probes[i]);
			pair_registered[i] = false;
		}
		missed[i] = pair_probes[i].nmissed;
		suppressed[i] = pair_probes[i].kp.nmissed;
	}
	for (i = 0; i < snapshot.count; i++) {
		struct pair_state *state = &pair_states[i];

		tasks += !!state->sequence;
		completed += state->completed;
		unfinished += state->phase != PAIR_IDLE;
	}
	if (mapping_probe.nmissed || missed[0] || missed[1] || suppressed[0] || suppressed[1] ||
	    unfinished || atomic64_read(&pair_inflight))
		pair_error();
	pr_info("kd_mm_pair: event=stop limit=%u tasks=%u pairs=%llu unfinished=%llu inflight=%lld errors=%lld identity_missed=%lu mmap_missed=%llu mmap_suppressed=%llu munmap_missed=%llu munmap_suppressed=%llu\n",
		pair_limit, tasks, completed, unfinished, atomic64_read(&pair_inflight),
		atomic64_read(&pair_errors), mapping_probe.nmissed, missed[0], suppressed[0], missed[1], suppressed[1]);
}

static int start_pairs(void)
{
	unsigned int i;
	int result;

	if (!pair_limit)
		return 0;
	for (i = 0; i < 2; i++) {
		result = register_kretprobe(&pair_probes[i]);
		if (result)
			return result;
		pair_registered[i] = true;
	}
	smp_store_release(&pair_armed, true);
	return 0;
}
NOKPROBE_SYMBOL(pair_entry);
NOKPROBE_SYMBOL(pair_return);
NOKPROBE_SYMBOL(pair_marker);

static void stop_observation(void)
{
	unsigned int i;

	if (snapshot.stopped)
		return;
	smp_store_release(&pair_armed, false);
	if (registered) {
		unregister_kprobe(&mapping_probe);
		registered = false;
	}
	stop_pairs();
	for (i = 0; i < snapshot.count; i++) {
		struct mm_struct *mm = held_mm[i];

		if (!mm)
			continue;
		held_mm[i] = NULL;
		mmdrop(mm);
		snapshot.refs_released++;
	}
	snapshot.stopped = 1;
}

static long observation_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	long result = 0;

	(void)file;
	if (command != KD_MMAP1_IDENTITY_STOP)
		return -ENOTTY;
	mutex_lock(&control);
	stop_observation();
	if (copy_to_user((void __user *)arg, &snapshot, sizeof(snapshot)))
		result = -EFAULT;
	mutex_unlock(&control);
	return result;
}

static const struct file_operations observation_operations = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = observation_ioctl,
};
static struct miscdevice observation_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "kd_mmap1_identity",
	.fops = &observation_operations,
	.mode = 0600,
};

static int __init observation_init(void)
{
	int result;

	if (strcmp(target, "mmap1_threads") && strcmp(target, "mmap1_processes"))
		return -EINVAL;
	if (pair_limit > 8)
		return -EINVAL;
	snapshot.abi = 2;
	result = register_kprobe(&mapping_probe);
	if (result)
		return result;
	registered = true;
	result = start_pairs();
	if (result) {
		stop_observation();
		return result;
	}
	result = misc_register(&observation_device);
	if (result)
		stop_observation();
	return result;
}

static void __exit observation_exit(void)
{
	misc_deregister(&observation_device);
	mutex_lock(&control);
	stop_observation();
	mutex_unlock(&control);
}
module_init(observation_init);
module_exit(observation_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Unscored unchanged mmap1 task/mm/mmap_lock identity observer");
