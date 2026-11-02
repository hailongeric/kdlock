// SPDX-License-Identifier: GPL-2.0
/* A safe instruction exit with exact effects before and after native resume. */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/uaccess.h>
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
#include <asm/cpufeature.h>
#include "kd_regs.h"
#if defined(JIT_CONTINUATION_SPIN) || defined(JIT_CONTINUATION_RWLOCK) || defined(JIT_CONTINUATION_RWSEM) || defined(JIT_CONTINUATION_MIXED_SPIN)
#error "Original-task instruction probe requires a sole outer mutex"
#endif
#endif
#if defined(JIT_CONTINUATION_RWLOCK) || defined(JIT_CONTINUATION_RWSEM)
#define JIT_CONTINUATION_SHARED
#endif
#if defined(JIT_CONTINUATION_SPIN) || defined(JIT_CONTINUATION_RWLOCK)
#define JIT_CONTINUATION_SPINNING
#include <asm/cpufeature.h>
#include "kd_regs.h"
#ifdef JIT_CONTINUATION_RWLOCK
#include "kd_rwlock.h"
static DEFINE_KD_RWLOCK(test_lock);
#else
#include "kd_spin_direct.h"
static DEFINE_KD_SPINLOCK(test_lock);
#endif
#elif defined(JIT_CONTINUATION_RWSEM)
#include "kd_rwsem_api.h"
static DEFINE_KD_RWSEM(test_lock);
#else
#include "kd_mutex_api.h"
static DEFINE_KD_MUTEX(test_lock);
#endif
#include "api.h"
#ifdef JIT_CONTINUATION_MIXED_SPIN
#if defined(JIT_CONTINUATION_SPIN) || defined(JIT_CONTINUATION_SHARED)
#error "The mixed probe requires a mutex outer lock"
#endif
#include "kd_spin_api.h"
static DEFINE_KD_SPINLOCK(inner_spin);
#endif
#if !defined(JIT_CONTINUATION_SPINNING) && !defined(JIT_CONTINUATION_MIXED_SPIN)
/* Prepared rwsem writers expose this same ABI2 mutex gate to the executor. */
#define JIT_CONTINUATION_CAN_ORIGIN
#endif

static atomic_t control = ATOMIC_INIT(0);
static atomic_t writers = ATOMIC_INIT(0);
#ifdef JIT_CONTINUATION_SHARED
static atomic_t readers = ATOMIC_INIT(0);
static atomic_t read_attempts = ATOMIC_INIT(0);
static atomic_t read_completions = ATOMIC_INIT(0);
#endif
static atomic_t failures = ATOMIC_INIT(0);
static unsigned int hot;
static u64 prefix __aligned(64);
static u64 suffix;
static u64 hot_taken;
extern char jit_continuation_entry[], jit_continuation_marker[];
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
static u64 origin_effects[4];
extern char jit_origin_rdtscp_first[], jit_origin_cpuid[], jit_origin_rdtscp_second[];
#endif

struct continuation_result {
	u8 taken;
	u8 carry, parity, zero, sign, overflow;
	u32 ah;
	u32 tsc_low, tsc_high;
	unsigned long task;
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
	u32 timestamp_low[2], timestamp_high[2], auxiliary[2];
	u32 cpuid[4];
	u8 stage_carry[3], stage_parity[3], stage_zero[3], stage_sign[3];
	u8 stage_overflow[3], stage_branch[3];
#endif
#ifdef JIT_CONTINUATION_SPINNING
	u32 cpu_aux;
#endif
#ifdef JIT_CONTINUATION_SHARED
	u8 reader_pending;
	u32 read_completed_before;
#endif
};

/* These observations stay outside the admitted critical section. The worker
 * has singleton affinity; compare raw TSC_AUX without assuming its CPU encoding. */
#if defined(JIT_CONTINUATION_SPINNING) || defined(JIT_CONTINUATION_ORIGIN_INSTRUCTIONS)
static __always_inline u32 native_cpu_aux(void)
{
	u32 aux;

	asm volatile("rdtscp" : "=c" (aux) : : "rax", "rdx", "memory");
	return aux;
}

static __always_inline unsigned long native_control_flags(void)
{
	unsigned long flags;

	asm volatile("pushfq; popq %0" : "=r" (flags) : : "memory");
	return flags & ~KD_REG_ARITHMETIC_FLAGS;
}
#endif

#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
static __always_inline void native_cpuid_leaf1(u32 *value)
{
	asm volatile("cpuid" : "=a"(value[0]), "=b"(value[1]),
		     "=c"(value[2]), "=d"(value[3]) : "0"(1U), "2"(0U) : "memory");
}
#endif

static bool continuation_idle(void)
{
#ifdef JIT_CONTINUATION_RWLOCK
	return !atomic_read(&test_lock.cnts) &&
	       !atomic_read(&test_lock.gate.val) && !atomic_read(&readers) &&
	       atomic_read(&read_attempts) == atomic_read(&read_completions);
#elif defined(JIT_CONTINUATION_RWSEM)
	return kd_rwsem_is_idle(&test_lock) && !atomic_read(&readers) &&
	       atomic_read(&read_attempts) == atomic_read(&read_completions);
#elif defined(JIT_CONTINUATION_SPIN)
	return !atomic_read(&test_lock.val);
#else
	return kd_mutex_is_idle(&test_lock)
#ifdef JIT_CONTINUATION_MIXED_SPIN
	       && !atomic_read(&inner_spin.val)
#endif
	       ;
#endif
}

#ifdef JIT_CONTINUATION_KILLABLE
#include "killable.inc"
#else
static __attribute__((noipa)) void continuation_body(struct continuation_result *result)
{
	struct continuation_result observed = { 0 };
#ifdef JIT_CONTINUATION_SHARED
	unsigned int reader_tries;
	u32 read_completed_before;
#endif
#ifdef JIT_CONTINUATION_RWLOCK
	KD_RWLOCK_DIRECT_WRITE_LOCK(&test_lock, kd_rwlock_direct_cookie,
		".globl jit_continuation_entry\njit_continuation_entry:\n\t" ANNOTATE_NOENDBR);
#elif defined(JIT_CONTINUATION_RWSEM)
	kd_down_write(&test_lock);
	asm volatile(".globl jit_continuation_entry\n.set jit_continuation_entry, 1b\n\t"
	             ".pushsection .discard.noendbr\n\t"
	             _ASM_PTR " jit_continuation_entry\n\t.popsection\n\t" : : : "memory");
#elif defined(JIT_CONTINUATION_SPIN)
	KD_SPIN_DIRECT_LOCK(&test_lock, kd_spin_direct_cookie,
		".globl jit_continuation_entry\njit_continuation_entry:\n\t" ANNOTATE_NOENDBR);
#elif defined(JIT_CONTINUATION_PUBLIC_API)
	kd_mutex_lock(&test_lock);
	/* Alias the actual DIRECT continuation; the runner checks the emitted
	 * capture/CALL bytes before loading this source. */
	asm volatile(".globl jit_continuation_entry\n.set jit_continuation_entry, 1b\n\t"
		     ".pushsection .discard.noendbr\n\t"
		     _ASM_PTR " jit_continuation_entry\n\t.popsection\n\t"
		     : : : "memory");
#else
	struct kd_mutex_outer_cookie cookie;

	KD_MUTEX_OUTER_LOCK(&test_lock, cookie,
		".globl jit_continuation_entry\njit_continuation_entry:\n\t" ANNOTATE_NOENDBR);
#endif
#ifdef JIT_CONTINUATION_MIXED_SPIN
	/* The ordinary unpinned CALL is the nested contract. No inline preemption
	 * or native CAS is hidden from the executor's exact mixed owner ledger. */
	kd_spin_lock(&inner_spin);
#endif
	if (atomic_inc_return(&writers) != 1)
		atomic_inc(&failures);
#ifdef JIT_CONTINUATION_SHARED
	/* Keep a bounded exclusion-observation window on both cold and hot
	 * writes. A nearly empty cold body can repeatedly win the ungated
	 * writer path and never qualify for delegation, even with many callers.
	 * Exercise real queue contention without changing any admission gate. */
	for (reader_tries = 0; reader_tries < 32; reader_tries++) {
		if (atomic_read(&readers))
			atomic_inc(&failures);
		cpu_relax();
	}
#endif
#ifdef JIT_CONTINUATION_RWSEM
	/* Other outer writers may reserve the same phase. Rejected readers can
	 * transiently publish speculative counts, but cannot enter their body. */
	if (atomic_long_read(&test_lock.admission) <= 0)
		atomic_inc(&failures);
#endif
	WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	observed.taken = 0;
	if (READ_ONCE(hot)) {
		observed.taken = 1;
#ifdef JIT_CONTINUATION_SHARED
		/* Require an actual competing read attempt at every hot marker.
		 * Completions are recorded inside the shared lock, so once this
		 * writer sees an outstanding attempt it cannot complete until the
		 * writer admission and gate are released. Bound the probe wait; failure
		 * is observable after return, never permission to replay a body. */
		for (reader_tries = 0; reader_tries < 100000; reader_tries++) {
			if (atomic_read(&read_attempts) != atomic_read(&read_completions))
				break;
			cpu_relax();
		}
		read_completed_before = (u32)atomic_read(&read_completions);
#endif
		/* CMP defines CF/PF/AF/ZF/SF/OF: 1 - 2 gives status mask 0x95.
		 * The unconditional branch tests flag preservation across a JIT
		 * block boundary. RDTSC is safe on this guest and leaves flags
		 * unchanged. The native suffix observes each condition immediately;
		 * Native-suffix families retain LAHF to expose AF. Eligible ABI2
		 * writer builds omit that second marker so reentry reaches unlock.
		 * Read actual current_task here, after RDTSC, and compare only after
		 * returning to the original caller. No unsafe privileged operation
		 * is used to exercise the escape mechanism. */
		asm volatile("movl $1, %%eax\n\t"
			     "cmpl $2, %%eax\n\t"
			     "jmp jit_continuation_marker\n\t"
			     ".globl jit_continuation_marker\njit_continuation_marker:\n\t"
			     "rdtsc\n\t"
			     "movl %%eax, %[low]\n\t"
			     "movl %%edx, %[high]\n\t"
			     "setc %[carry]\n\t"
			     "setp %[parity]\n\t"
			     "setz %[zero]\n\t"
			     "sets %[sign]\n\t"
			     "seto %[overflow]\n\t"
#ifndef JIT_CONTINUATION_CAN_ORIGIN
			     "lahf\n\t"
			     "movzbl %%ah, %%eax\n\t"
			     "movl %%eax, %[ah]\n\t"
#endif
#ifdef JIT_CONTINUATION_SPINNING
			     /* Arithmetic observations precede this second safe
			      * instruction; RDTSC remains the named first marker. */
			     "rdtscp\n\t"
			     "movl %%ecx, %[aux]\n\t"
#endif
			     "movq %%gs:current_task, %%rax\n\t"
			     "movq %%rax, %[task]\n\t"
			     : [low] "=m" (observed.tsc_low),
			       [high] "=m" (observed.tsc_high),
			       [carry] "=m" (observed.carry),
			       [parity] "=m" (observed.parity),
			       [zero] "=m" (observed.zero),
			       [sign] "=m" (observed.sign),
			       [overflow] "=m" (observed.overflow),
#ifndef JIT_CONTINUATION_CAN_ORIGIN
			       [ah] "=m" (observed.ah),
#endif
			       [task] "=m" (observed.task)
#ifdef JIT_CONTINUATION_SPINNING
			       , [aux] "=m" (observed.cpu_aux)
#endif
			     : : "rax", "rdx",
#ifdef JIT_CONTINUATION_SPINNING
			     "rcx",
#endif
			     "cc", "memory");
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
#include "origin_body.inc"
#endif
		WRITE_ONCE(hot_taken, READ_ONCE(hot_taken) + 1);
#ifdef JIT_CONTINUATION_MIXED_SPIN
		/* This is after the real native marker and before B's physical ACK.
		 * A correct waiter resume restores the logical spin pin. */
		if (!(preempt_count() & PREEMPT_MASK))
			atomic_inc(&failures);
#endif
#ifdef JIT_CONTINUATION_SHARED
		/* Sample before the marker, then carry those exact live values
		 * through the restored native continuation. */
		observed.reader_pending = reader_tries != 100000;
		observed.read_completed_before = read_completed_before;
		/* Keep the competing-reader observation through the suffix write
		 * on the native branch. The cold path needs no loop-carried
		 * snapshot. Both paths increment suffix once before release. */
		WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
		if (observed.read_completed_before != (u32)atomic_read(&read_completions))
			atomic_inc(&failures);
	} else {
		WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
#endif
	}
#ifndef JIT_CONTINUATION_SHARED
	WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
#endif
#ifdef JIT_CONTINUATION_SHARED
	if (atomic_read(&readers))
		atomic_inc(&failures);
#endif
#ifdef JIT_CONTINUATION_RWSEM
	if (atomic_long_read(&test_lock.admission) <= 0)
		atomic_inc(&failures);
#endif
	if (atomic_dec_return(&writers))
		atomic_inc(&failures);
#ifdef JIT_CONTINUATION_MIXED_SPIN
	kd_spin_unlock(&inner_spin);
#endif
#ifdef JIT_CONTINUATION_RWLOCK
	KD_RWLOCK_DIRECT_WRITE_UNLOCK(&test_lock, kd_rwlock_direct_cookie);
#elif defined(JIT_CONTINUATION_RWSEM)
	kd_up_write(&test_lock);
#elif defined(JIT_CONTINUATION_SPIN)
	KD_SPIN_DIRECT_UNLOCK(&test_lock, kd_spin_direct_cookie);
#elif defined(JIT_CONTINUATION_PUBLIC_API)
	kd_mutex_unlock(&test_lock);
#else
	KD_MUTEX_OUTER_UNLOCK(&test_lock, cookie);
#endif
	/* The admitted body uses frame-relative observations. Copy to the
	 * caller only after the exact unlock continuation has returned; the
	 * private frame remains live and cannot race another lock holder. */
	*result = observed;
}

#ifdef JIT_CONTINUATION_SHARED
static __attribute__((noipa)) bool reader_body(void)
{
	bool bad;

	atomic_inc(&read_attempts);
#ifdef JIT_CONTINUATION_RWSEM
	kd_down_read(&test_lock);
#else
	kd_read_lock(&test_lock);
#endif
	atomic_inc(&readers);
	/* A writer retains admission throughout native continuation and ACK.
	 * A reader must never observe its active interval or partial effects. */
	bad = atomic_read(&writers) || READ_ONCE(prefix) != READ_ONCE(suffix);
	atomic_inc(&read_completions);
	atomic_dec(&readers);
#ifdef JIT_CONTINUATION_RWSEM
	kd_up_read(&test_lock);
#else
	kd_read_unlock(&test_lock);
#endif
	return bad;
}
#endif
#endif /* JIT_CONTINUATION_KILLABLE */

static long continuation_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
#ifdef JIT_CONTINUATION_KILLABLE
	(void)file;
	return killable_ioctl(cmd, (void __user *)arg);
#else
	void __user *user = (void __user *)arg;
	struct jit_continuation_snapshot snapshot = { 0 };
	struct jit_continuation_run run;
	struct continuation_result result;
	unsigned int before_preempt, i;
	bool before_irqs;
#if defined(JIT_CONTINUATION_SPINNING) || defined(JIT_CONTINUATION_ORIGIN_INSTRUCTIONS)
	unsigned int before_cpu;
	unsigned long before_flags;
	u32 expected_aux;
#endif
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
	u32 expected_cpuid[4];
	unsigned int stage;
#endif
	int ret = 0;

	(void)file;
	if (cmd == JIT_CONTINUATION_RUN
#ifdef JIT_CONTINUATION_SHARED
	    || cmd == JIT_CONTINUATION_READ
#endif
	   ) {
		if (copy_from_user(&run, user, sizeof(run)))
			return -EFAULT;
		if (!run.iterations || run.iterations > 10000000 ||
		    run.worker >= 64 || run.reserved[0] || run.reserved[1])
			return -EINVAL;
#if defined(JIT_CONTINUATION_SPINNING) || defined(JIT_CONTINUATION_ORIGIN_INSTRUCTIONS)
		/* Only ordinary task-context root acquisitions are under test. */
		if (preempt_count() || irqs_disabled() ||
		    cpumask_weight(current->cpus_ptr) != 1)
			return -EINVAL;
		before_cpu = raw_smp_processor_id();
		expected_aux = native_cpu_aux();
#endif
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
		native_cpuid_leaf1(expected_cpuid);
#endif
		if (!atomic_add_unless(&control, 1, -1))
			return -EBUSY;
		before_preempt = preempt_count();
		before_irqs = irqs_disabled();
		run.completed = run.errors = 0;
		for (i = 0; i < run.iterations; i++) {
#if defined(JIT_CONTINUATION_SPINNING) || defined(JIT_CONTINUATION_ORIGIN_INSTRUCTIONS)
			before_flags = native_control_flags();
#endif
#ifdef JIT_CONTINUATION_SHARED
			if (cmd == JIT_CONTINUATION_READ) {
				if (reader_body())
					run.errors++;
			} else
#endif
			{
				continuation_body(&result);
				/* Compare outside the translated critical section. A logical
				 * GS task read alone is not physical-CPU evidence; extended
				 * services additionally compare Native TSC_AUX and CPUID. */
				if (result.taken != READ_ONCE(hot) ||
				    (result.taken &&
				     (result.task != (unsigned long)current ||
				      result.carry != 1 || result.parity != 1 ||
				      result.zero != 0 || result.sign != 1 ||
				      result.overflow != 0
#ifndef JIT_CONTINUATION_CAN_ORIGIN
				      || (result.ah & 0xd5) != 0x95
#endif
				      )))
					run.errors++;
#ifdef JIT_CONTINUATION_SPINNING
				if (result.taken && result.cpu_aux != expected_aux)
					run.errors++;
#endif
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
				if (result.taken) {
					if (result.auxiliary[0] != expected_aux ||
					    result.auxiliary[1] != expected_aux)
						run.errors++;
					for (stage = 0; stage < 4; stage++)
						if (result.cpuid[stage] != expected_cpuid[stage])
							run.errors++;
					for (stage = 0; stage < 3; stage++)
						if (result.stage_carry[stage] != 1 || result.stage_parity[stage] != 1 ||
						    result.stage_zero[stage] || result.stage_sign[stage] != 1 ||
						    result.stage_overflow[stage] || !result.stage_branch[stage])
							run.errors++;
				}
#endif
#ifdef JIT_CONTINUATION_SHARED
				if (result.taken && !result.reader_pending)
					run.errors++;
#endif
			}
#if defined(JIT_CONTINUATION_SPINNING) || defined(JIT_CONTINUATION_ORIGIN_INSTRUCTIONS)
			if (native_control_flags() != before_flags ||
			    raw_smp_processor_id() != before_cpu ||
			    preempt_count() != before_preempt ||
			    irqs_disabled() != before_irqs)
				run.errors++;
#endif
			run.completed++;
			if ((i & 255) == 0)
				cond_resched();
		}
		if (preempt_count() != before_preempt || irqs_disabled() != before_irqs)
			run.errors++;
		if (run.errors)
			atomic_inc(&failures);
		(void)atomic_dec_return_release(&control);
		return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
	}
	if (cmd != JIT_CONTINUATION_SNAPSHOT && cmd != JIT_CONTINUATION_PREPARE &&
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
	    cmd != JIT_CONTINUATION_ORIGIN_SNAPSHOT &&
#endif
	    cmd != JIT_CONTINUATION_HOT && cmd != JIT_CONTINUATION_COLD)
		return -ENOTTY;
	/* Phase changes and inspection require every workload caller to join. */
	if (atomic_cmpxchg_acquire(&control, 0, -1))
		return -EBUSY;
	if (cmd == JIT_CONTINUATION_PREPARE) {
#ifdef JIT_CONTINUATION_RWLOCK
		ret = kd_rwlock_prepare(&test_lock, (unsigned long)jit_continuation_entry,
				       KD_ENTRY_ABI_RWLOCK_CLOBBER_V1);
#elif defined(JIT_CONTINUATION_RWSEM)
		ret = kd_rwsem_prepare(&test_lock, (unsigned long)jit_continuation_entry,
				      KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#elif defined(JIT_CONTINUATION_SPIN)
		ret = kd_spin_prepare(&test_lock, (unsigned long)jit_continuation_entry,
				     KD_ENTRY_ABI_SPIN_CLOBBER_V1);
#else
		ret = kd_mutex_prepare(&test_lock, (unsigned long)jit_continuation_entry,
				       KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#endif
	} else if (cmd == JIT_CONTINUATION_HOT || cmd == JIT_CONTINUATION_COLD) {
		if (!continuation_idle())
			ret = -EBUSY;
		else
			WRITE_ONCE(hot, cmd == JIT_CONTINUATION_HOT);
	}
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
	else if (cmd == JIT_CONTINUATION_ORIGIN_SNAPSHOT) {
		struct jit_origin_snapshot state = {
			.effects = { origin_effects[0], origin_effects[1], origin_effects[2], origin_effects[3] },
			.instructions = { (unsigned long)jit_continuation_marker, (unsigned long)jit_origin_rdtscp_first,
				(unsigned long)jit_origin_cpuid, (unsigned long)jit_origin_rdtscp_second },
		};

		ret = copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
	}
#endif
	else {
		snapshot.prefix = prefix;
		snapshot.suffix = suffix;
		snapshot.hot_taken = hot_taken;
#ifdef JIT_CONTINUATION_SHARED
		snapshot.lock_address = (unsigned long)&test_lock.gate;
#else
		snapshot.lock_address = (unsigned long)&test_lock;
#endif
		snapshot.entry = (unsigned long)jit_continuation_entry;
		snapshot.marker = (unsigned long)jit_continuation_marker;
		snapshot.failures = atomic_read(&failures);
		snapshot.active = atomic_read(&writers);
#ifdef JIT_CONTINUATION_SHARED
		snapshot.active += atomic_read(&readers);
#endif
		snapshot.hot = READ_ONCE(hot);
		snapshot.idle = continuation_idle();
		ret = copy_to_user(user, &snapshot, sizeof(snapshot)) ? -EFAULT : 0;
	}
	atomic_set_release(&control, 0);
	return ret;
#endif
}

static const struct file_operations continuation_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = continuation_ioctl,
};
static struct miscdevice continuation_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "kd_jit_continuation_test",
	.fops = &continuation_fops,
	.mode = 0600,
};
static int __init continuation_init(void)
{
#ifdef JIT_CONTINUATION_HELPER
	int result;
#endif
	BUILD_BUG_ON(sizeof(struct jit_continuation_run) != 32);
	BUILD_BUG_ON(sizeof(struct jit_continuation_snapshot) != 80);
	BUILD_BUG_ON(sizeof(struct jit_origin_snapshot) != 64);
#ifdef JIT_CONTINUATION_KILLABLE
	BUILD_BUG_ON(sizeof(struct jit_killable_run) != 32);
	BUILD_BUG_ON(sizeof(struct jit_killable_snapshot) != 872);
	killable_init();
#endif
#ifdef JIT_CONTINUATION_HELPER
	BUILD_BUG_ON(sizeof(struct jit_helper_snapshot) != 1496);
	BUILD_BUG_ON(sizeof(struct jit_native_snapshot) != 1976);
	BUILD_BUG_ON(sizeof(struct jit_memory_snapshot) != 312);
#endif
#if defined(JIT_CONTINUATION_SPINNING) || defined(JIT_CONTINUATION_ORIGIN_INSTRUCTIONS)
	if (!boot_cpu_has(X86_FEATURE_RDTSCP))
		return -EOPNOTSUPP;
#endif
#ifdef JIT_CONTINUATION_HELPER
	result = misc_register(&continuation_device);
	if (result)
		return result;
	result = helper_register();
	if (result)
		misc_deregister(&continuation_device);
	return result;
#else
	return misc_register(&continuation_device);
#endif
}
static void __exit continuation_exit(void)
{
#ifdef JIT_CONTINUATION_HELPER
	/* The registration pin permits unload only after explicit unregister. */
	WARN_ON(READ_ONCE(helper_registered));
#endif
	misc_deregister(&continuation_device);
}
module_init(continuation_init);
module_exit(continuation_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("JIT continuation and exact original-task instruction service");
#ifdef JIT_CONTINUATION_HELPER
MODULE_INFO(kd_continuation_mode, "helper");
#elif defined(JIT_CONTINUATION_KILLABLE)
MODULE_INFO(kd_continuation_mode, "killable");
#else
MODULE_INFO(kd_continuation_mode, "continuation");
#endif
#ifdef JIT_CONTINUATION_ORIGIN_INSTRUCTIONS
MODULE_INFO(kd_origin_instructions, "4");
#else
MODULE_INFO(kd_origin_instructions, "0");
#endif
#ifdef JIT_CONTINUATION_RWLOCK
MODULE_INFO(kd_continuation_family, "rwlock");
MODULE_INFO(kd_mutex_api, "not_applicable");
#elif defined(JIT_CONTINUATION_RWSEM)
MODULE_INFO(kd_continuation_family, "rwsem");
MODULE_INFO(kd_mutex_api, "not_applicable");
#elif defined(JIT_CONTINUATION_SPIN)
MODULE_INFO(kd_continuation_family, "spin");
MODULE_INFO(kd_mutex_api, "not_applicable");
#else
MODULE_INFO(kd_continuation_family, "mutex");
#ifdef JIT_CONTINUATION_PUBLIC_API
MODULE_INFO(kd_mutex_api, "public");
#else
MODULE_INFO(kd_mutex_api, "outer");
#endif
#endif
