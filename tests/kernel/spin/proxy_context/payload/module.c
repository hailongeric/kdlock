// SPDX-License-Identifier: GPL-2.0
/* External ordinary-API probe. No private queue mutation or context repair. */
#include <linux/bottom_half.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include "kd_spin_api.h"
#include "kd_regs.h"
#include "api.h"

#ifndef CONFIG_PREEMPT_RCU
#error "The RCU root-refusal case requires the declared PREEMPT_RCU kernel"
#endif

static DEFINE_KD_SPINLOCK(test_lock);
static atomic_t control = ATOMIC_INIT(0);
static atomic_t writers = ATOMIC_INIT(0);
static atomic_t failures = ATOMIC_INIT(0);
static atomic_t worker_active[64];
static u64 prefix __aligned(64), suffix, hot_taken;
static unsigned int phase;
static unsigned long entry;
extern char proxy_body_end[];
struct body_record { unsigned long task; };
static struct body_record records[64];

/* This is the ordinary macro, with its original anonymous continuation.
 * Keep physical context probes outside this translated source interval. */
static __attribute__((noipa)) void proxy_body(struct body_record *record)
{
	unsigned int hint;

	kd_spin_lock(&test_lock);
	if (atomic_inc_return(&writers) != 1)
		atomic_inc(&failures);
	WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	for (hint = 0; hint < 8; hint++)
		cpu_relax();
	asm volatile("movq %%gs:current_task, %%rax\n\t"
		     "movq %%rax, %0\n\t"
		     : "=m" (record->task) : : "rax", "memory");
	/* Weighted mode count makes every phase's exact body effects checkable
	 * through the existing source/session observer format. */
	WRITE_ONCE(hot_taken, READ_ONCE(hot_taken) + READ_ONCE(phase));
	WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
	if (atomic_dec_return(&writers))
		atomic_inc(&failures);
	kd_spin_unlock(&test_lock);
	asm volatile(".globl proxy_body_end\nproxy_body_end:\n\t"
		     ANNOTATE_NOENDBR : : : "memory");
}

struct context_state {
	unsigned int preempt, bh, migration, native;
	int rcu, cpu;
	unsigned long flags, task, fast_held, fast_owner;
};

static struct context_state capture_context(void)
{
	struct context_state state;
	unsigned long flags;

	asm volatile("pushfq; popq %0" : "=r" (flags) : : "memory");
	state.flags = flags & ~KD_REG_ARITHMETIC_FLAGS;
	state.preempt = preempt_count();
	state.bh = softirq_count();
	state.migration = current->migration_disabled;
	state.native = this_cpu_read(kd_spin_fast_cpu.nondelegated);
	state.fast_held = (unsigned long)this_cpu_read(kd_spin_fast_cpu.held);
	state.fast_owner = (unsigned long)this_cpu_read(kd_spin_fast_cpu.owner);
	state.rcu = READ_ONCE(current->rcu_read_lock_nesting);
	state.cpu = raw_smp_processor_id();
	state.task = (unsigned long)current;
	return state;
}

static bool same_context(const struct context_state *a, const struct context_state *b)
{
	return a->preempt == b->preempt && a->bh == b->bh &&
		a->migration == b->migration && a->rcu == b->rcu &&
		a->cpu == b->cpu && a->flags == b->flags && a->task == b->task &&
		a->native == b->native && a->fast_held == b->fast_held && a->fast_owner == b->fast_owner;
}

static long run_worker(void __user *user)
{
	struct proxy_run run;
	struct context_state initial, before, configured, after;
	unsigned long flags = 0;
	unsigned int mode, i;
	bool irq_off;

	if (copy_from_user(&run, user, sizeof(run)))
		return -EFAULT;
	if (!run.iterations || run.iterations > 1000000 || run.worker >= 64 ||
	    run.reserved[0] || run.reserved[1] || preempt_count() ||
	    irqs_disabled() || current->migration_disabled ||
	    READ_ONCE(current->rcu_read_lock_nesting) || cpumask_weight(current->cpus_ptr) != 1)
		return -EINVAL;
	if (atomic_cmpxchg(&worker_active[run.worker], 0, 1))
		return -EBUSY;
	if (!atomic_add_unless(&control, 1, -1)) {
		atomic_set_release(&worker_active[run.worker], 0);
		return -EBUSY;
	}
	mode = READ_ONCE(phase);
	if (!entry || mode >= PROXY_MODE_COUNT || (mode && run.iterations > 4096)) {
		atomic_set_release(&worker_active[run.worker], 0);
		(void)atomic_dec_return_release(&control);
		return -EINVAL;
	}
	initial = capture_context();
	run.completed = run.errors = 0;
	for (i = 0; i < run.iterations; i++) {
		before = capture_context();
		irq_off = mode == PROXY_IF_OFF ||
			(mode == PROXY_MIXED_IF && (run.worker & 1));
		if (irq_off)
			local_irq_save(flags);
		else if (mode == PROXY_BH)
			local_bh_disable();
		else if (mode == PROXY_RCU)
			rcu_read_lock();
		else if (mode == PROXY_PREEMPT)
			preempt_disable();
		else if (mode == PROXY_MIGRATION)
			migrate_disable();
		configured = capture_context();
		proxy_body(&records[run.worker]);
		after = capture_context();
		if (!same_context(&configured, &after) ||
		    records[run.worker].task != (unsigned long)current)
			run.errors++;
		/* Perform only the matching Native exit. A failure is recorded,
		 * never hidden by assigning preempt/RCU/migration state manually. */
		if (irq_off)
			local_irq_restore(flags);
		else if (mode == PROXY_BH)
			local_bh_enable();
		else if (mode == PROXY_RCU)
			rcu_read_unlock();
		else if (mode == PROXY_PREEMPT)
			preempt_enable();
		else if (mode == PROXY_MIGRATION)
			migrate_enable();
		after = capture_context();
		if (!same_context(&before, &after))
			run.errors++;
		run.completed++;
		if (!(i & 31))
			cond_resched();
	}
	after = capture_context();
	if (!same_context(&initial, &after))
		run.errors++;
	if (run.errors)
		atomic_inc(&failures);
	atomic_set_release(&worker_active[run.worker], 0);
	(void)atomic_dec_return_release(&control);
	return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
}

static long proxy_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct proxy_snapshot snapshot = { 0 };
	u64 selected;
	u32 mode;
	s32 displacement;
	long result = 0;

	(void)file;
	if (command == PROXY_RUN)
		return run_worker(user);
	if (command != PROXY_SNAPSHOT && command != PROXY_PREPARE &&
	    command != PROXY_MODE && command != PROXY_BIND)
		return -ENOTTY;
	if (atomic_cmpxchg_acquire(&control, 0, -1))
		return -EBUSY;
	if (command == PROXY_BIND) {
		if (copy_from_user(&selected, user, sizeof(selected))) {
			result = -EFAULT;
			goto out;
		}
		if (entry || selected < (unsigned long)proxy_body + 5 ||
		    selected >= (unsigned long)proxy_body_end ||
		    READ_ONCE(*(u8 *)(unsigned long)(selected - 5)) != 0xe8) {
			result = -EINVAL;
			goto out;
		}
		memcpy(&displacement, (void *)(unsigned long)(selected - 4), sizeof(displacement));
		if (selected + displacement != (unsigned long)kd_spin_lock_clobber_v1) {
			result = -EINVAL;
			goto out;
		}
		entry = selected;
	} else if (command == PROXY_PREPARE) {
		result = entry ? kd_spin_prepare(&test_lock, entry, KD_ENTRY_ABI_SPIN_CLOBBER_V1) : -EINVAL;
	} else if (command == PROXY_MODE) {
		if (copy_from_user(&mode, user, sizeof(mode)))
			result = -EFAULT;
		else if (mode >= PROXY_MODE_COUNT || atomic_read(&test_lock.val))
			result = -EINVAL;
		else
			WRITE_ONCE(phase, mode);
	} else {
		snapshot.prefix = prefix;
		snapshot.suffix = suffix;
		snapshot.hot_taken = hot_taken;
		snapshot.lock_address = (unsigned long)&test_lock;
		snapshot.entry = entry ? entry : (unsigned long)proxy_body;
		snapshot.marker = (unsigned long)proxy_body_end;
		snapshot.failures = atomic_read(&failures);
		snapshot.active = atomic_read(&writers);
		snapshot.hot = READ_ONCE(phase);
		snapshot.idle = !atomic_read(&test_lock.val);
		result = copy_to_user(user, &snapshot, sizeof(snapshot)) ? -EFAULT : 0;
	}
out:
	atomic_set_release(&control, 0);
	return result;
}

static const struct file_operations proxy_operations = {
	.owner = THIS_MODULE, .unlocked_ioctl = proxy_ioctl,
};
static struct miscdevice proxy_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_spin_proxy_context",
	.fops = &proxy_operations, .mode = 0600,
};
static int __init proxy_init(void)
{
	BUILD_BUG_ON(sizeof(struct proxy_run) != 32);
	BUILD_BUG_ON(sizeof(struct proxy_snapshot) != 80);
	return misc_register(&proxy_device);
}
static void __exit proxy_exit(void) { misc_deregister(&proxy_device); }
module_init(proxy_init);
module_exit(proxy_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Ordinary spin root-context delegation and local fallback probe");
