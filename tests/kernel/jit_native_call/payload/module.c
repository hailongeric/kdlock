// SPDX-License-Identifier: GPL-2.0
/* Correctness-only: Native inner lock, reached CALL and exact native suffix. */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <asm/asm.h>
#include <asm/cpufeature.h>
#include <asm/nospec-branch.h>
#include "kd_mutex_api.h"
#include "kd_lock.h"
#include "api.h"

/* Same 4UL PICKUP bit as kd_mutex_local.c; observation, never routing. */
#define PROBE_OWNER_PICKUP 4UL

static DEFINE_KD_MUTEX(test_lock);
static DEFINE_RAW_SPINLOCK(native_lock);
static atomic_t control = ATOMIC_INIT(0), writers = ATOMIC_INIT(0);
static atomic_t failures = ATOMIC_INIT(0);
static unsigned int hot;
static u64 prefix __aligned(64), suffix, taken;
extern char jit_native_call_entry[], jit_native_call_site[];

struct call_result {
	unsigned long task, owner_before, owner_after;
	u32 cpu_aux;
	int acquired;
	u8 taken;
};

static __always_inline u32 cpu_aux(void)
{
	u32 value;
	asm volatile("rdtscp" : "=c" (value) : : "rax", "rdx", "memory");
	return value;
}

static bool probe_idle(void)
{
	return kd_mutex_is_idle(&test_lock) && !raw_spin_is_locked(&native_lock) &&
	       !atomic_read(&writers);
}

static __attribute__((noipa)) void native_call_body(struct call_result *result)
{
	struct call_result observed = {0};
	raw_spinlock_t *word = &native_lock;
	int acquired;

	kd_mutex_lock(&test_lock);
	asm volatile(".globl jit_native_call_entry\n.set jit_native_call_entry, 1b\n\t"
		     ".pushsection .discard.noendbr\n\t"
		     _ASM_PTR " jit_native_call_entry\n\t.popsection\n\t" : : : "memory");
	if (atomic_inc_return(&writers) != 1)
		atomic_inc(&failures);
	WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	if (READ_ONCE(hot)) {
		observed.taken = 1;
		observed.owner_before = atomic_long_read(&test_lock.owner);
		/* The ordinary C-call ABI preserves callee saves. Its only target is
		 * the exact exported Native function; no user controls this operand.
		 * Name the instruction itself for source/return-PC verification. */
		asm volatile(".globl jit_native_call_site\njit_native_call_site:\n\t"
			     ANNOTATE_NOENDBR
#ifdef NATIVE_CALL_INDIRECT
			     ANNOTATE_RETPOLINE_SAFE
			     "call *%[target]\n\t"
#else
			     "call _raw_spin_trylock\n\t"
#endif
			     : "=a" (acquired), "+D" (word), ASM_CALL_CONSTRAINT
#ifdef NATIVE_CALL_INDIRECT
			     : [target] "r" (&_raw_spin_trylock)
#else
			     :
#endif
			     : "rcx", "rdx", "rsi", "r8", "r9", "r10", "r11", "cc", "memory");
		observed.acquired = acquired;
		observed.owner_after = atomic_long_read(&test_lock.owner);
		/* These instructions belong to the native suffix, after the checked
		 * CALL. They must never become the first instruction-marker exit. */
		asm volatile("rdtscp\n\tmovl %%ecx, %[aux]\n\t"
			     "movq %%gs:current_task, %%rax\n\tmovq %%rax, %[task]\n\t"
			     : [aux] "=m" (observed.cpu_aux), [task] "=m" (observed.task)
			     : : "rax", "rcx", "rdx", "memory");
		if (acquired == 1)
			raw_spin_unlock(&native_lock);
		else
			atomic_inc(&failures);
		WRITE_ONCE(taken, READ_ONCE(taken) + 1);
	}
	WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
	if (atomic_dec_return(&writers))
		atomic_inc(&failures);
	kd_mutex_unlock(&test_lock);
	*result = observed;
}

static long probe_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct native_call_run run;
	struct native_call_snapshot snapshot = {0};
	struct call_result observed;
	unsigned int before_preempt, before_migration, i;
	u32 expected_aux;
	bool before_irqs;
	int ret = 0;

	(void)file;
	if (command == NATIVE_CALL_RUN) {
		if (copy_from_user(&run, user, sizeof(run))) return -EFAULT;
		if (!run.iterations || run.iterations > 1000000 || run.worker >= 64 ||
		    run.reserved[0] || run.reserved[1] || preempt_count() || irqs_disabled() ||
		    current->migration_disabled || cpumask_weight(current->cpus_ptr) != 1)
			return -EINVAL;
		if (!atomic_add_unless(&control, 1, -1)) return -EBUSY;
		before_preempt = preempt_count();
		before_migration = current->migration_disabled;
		before_irqs = irqs_disabled();
		expected_aux = cpu_aux();
		run.completed = run.errors = 0;
		for (i = 0; i < run.iterations; i++) {
			native_call_body(&observed);
			if (observed.taken != READ_ONCE(hot) ||
			    (observed.taken && (observed.acquired != 1 ||
			     observed.task != (unsigned long)current || observed.cpu_aux != expected_aux ||
			     !(observed.owner_before & ~KD_MUTEX_OWNER_FLAGS) ||
			     ((observed.owner_before | observed.owner_after) & PROBE_OWNER_PICKUP) ||
			     (observed.owner_before & ~KD_MUTEX_OWNER_FLAGS) !=
			     (observed.owner_after & ~KD_MUTEX_OWNER_FLAGS))) ||
			    preempt_count() != before_preempt || irqs_disabled() != before_irqs ||
			    current->migration_disabled != before_migration)
				run.errors++;
			run.completed++;
			if (!(i & 255)) cond_resched();
		}
		if (run.errors) atomic_inc(&failures);
		(void)atomic_dec_return_release(&control);
		return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
	}
	if (command != NATIVE_CALL_SNAPSHOT && command != NATIVE_CALL_PREPARE &&
	    command != NATIVE_CALL_HOT && command != NATIVE_CALL_COLD) return -ENOTTY;
	if (atomic_cmpxchg_acquire(&control, 0, -1)) return -EBUSY;
	if (command == NATIVE_CALL_PREPARE) {
		ret = kd_mutex_prepare(&test_lock, (unsigned long)jit_native_call_entry,
				       KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	} else if (command == NATIVE_CALL_HOT || command == NATIVE_CALL_COLD) {
		if (!probe_idle()) ret = -EBUSY;
		else WRITE_ONCE(hot, command == NATIVE_CALL_HOT);
	} else {
		snapshot.prefix = prefix; snapshot.suffix = suffix; snapshot.taken = taken;
		snapshot.lock_address = (unsigned long)&test_lock;
		snapshot.entry = (unsigned long)jit_native_call_entry;
		snapshot.call_site = (unsigned long)jit_native_call_site;
		snapshot.native_target = (unsigned long)&_raw_spin_trylock;
		snapshot.failures = atomic_read(&failures);
		snapshot.active = atomic_read(&writers);
		snapshot.hot = READ_ONCE(hot); snapshot.idle = probe_idle();
		ret = copy_to_user(user, &snapshot, sizeof(snapshot)) ? -EFAULT : 0;
	}
	atomic_set_release(&control, 0);
	return ret;
}

static const struct file_operations probe_fops = {.owner = THIS_MODULE, .unlocked_ioctl = probe_ioctl};
static struct miscdevice probe_device = {.minor = MISC_DYNAMIC_MINOR, .name = "kd_jit_native_call_test",
	.fops = &probe_fops, .mode = 0600};
static int __init probe_init(void)
{
	BUILD_BUG_ON(sizeof(struct native_call_run) != 32);
	BUILD_BUG_ON(sizeof(struct native_call_snapshot) != 88);
	if (!boot_cpu_has(X86_FEATURE_RDTSCP)) return -EOPNOTSUPP;
	return misc_register(&probe_device);
}
static void __exit probe_exit(void) { misc_deregister(&probe_device); }
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Reached Native CALL and repeated KD mutex delegation");
#ifdef NATIVE_CALL_INDIRECT
MODULE_INFO(kd_native_call_mode, "indirect");
#else
MODULE_INFO(kd_native_call_mode, "direct");
#endif
