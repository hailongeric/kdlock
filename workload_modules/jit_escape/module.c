// SPDX-License-Identifier: GPL-2.0
/* A safe instruction exit with exact effects before and after native resume. */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/preempt.h>
#include <linux/sched.h>
#include <linux/uaccess.h>
#if defined(JIT_ESCAPE_RWLOCK) || defined(JIT_ESCAPE_RWSEM)
#define JIT_ESCAPE_SHARED
#endif
#if defined(JIT_ESCAPE_SPIN) || defined(JIT_ESCAPE_RWLOCK)
#define JIT_ESCAPE_SPINNING
#include <asm/cpufeature.h>
#include "kd_regs.h"
#ifdef JIT_ESCAPE_RWLOCK
#include "kd_rwlock.h"
static DEFINE_KD_RWLOCK(test_lock);
#else
#include "kd_spin_direct.h"
static DEFINE_KD_SPINLOCK(test_lock);
#endif
#elif defined(JIT_ESCAPE_RWSEM)
#include "kd_rwsem_direct.h"
static DEFINE_KD_RWSEM(test_lock);
#else
#include "kd_mutex_api.h"
static DEFINE_KD_MUTEX(test_lock);
#endif
#include "api.h"

static atomic_t control = ATOMIC_INIT(0);
static atomic_t writers = ATOMIC_INIT(0);
#ifdef JIT_ESCAPE_SHARED
static atomic_t readers = ATOMIC_INIT(0);
static atomic_t read_attempts = ATOMIC_INIT(0);
static atomic_t read_completions = ATOMIC_INIT(0);
#endif
static atomic_t failures = ATOMIC_INIT(0);
static unsigned int hot;
static u64 prefix __aligned(64);
static u64 suffix;
static u64 hot_taken;
extern char jit_escape_entry[], jit_escape_marker[];

struct escape_result {
	u8 taken;
	u8 carry, parity, zero, sign, overflow;
	u32 ah;
	u32 tsc_low, tsc_high;
	unsigned long task;
#ifdef JIT_ESCAPE_SPINNING
	u32 cpu_aux;
#endif
#ifdef JIT_ESCAPE_SHARED
	u8 reader_pending;
	u32 read_completed_before;
#endif
};

/* These observations stay outside the admitted critical section. The worker
 * has singleton affinity; compare raw TSC_AUX without assuming its CPU encoding. */
#ifdef JIT_ESCAPE_SPINNING
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

static bool escape_idle(void)
{
#ifdef JIT_ESCAPE_RWLOCK
	return !atomic_read(&test_lock.cnts) &&
	       !atomic_read(&test_lock.gate.val) && !atomic_read(&readers) &&
	       atomic_read(&read_attempts) == atomic_read(&read_completions);
#elif defined(JIT_ESCAPE_RWSEM)
	return kd_rwsem_is_idle(&test_lock) && !atomic_read(&readers) &&
	       atomic_read(&read_attempts) == atomic_read(&read_completions);
#elif defined(JIT_ESCAPE_SPIN)
	return !atomic_read(&test_lock.val);
#else
	return kd_mutex_is_idle(&test_lock);
#endif
}

static __attribute__((noipa)) void escape_body(struct escape_result *result)
{
#ifdef JIT_ESCAPE_RWLOCK
	KD_RWLOCK_DIRECT_WRITE_LOCK(&test_lock, kd_rwlock_direct_cookie,
		".globl jit_escape_entry\njit_escape_entry:\n\t" ANNOTATE_NOENDBR);
#elif defined(JIT_ESCAPE_RWSEM)
	struct kd_rwsem_outer_cookie cookie;

	KD_RWSEM_OUTER_WRITE_LOCK(&test_lock, cookie,
		".globl jit_escape_entry\njit_escape_entry:\n\t" ANNOTATE_NOENDBR);
#elif defined(JIT_ESCAPE_SPIN)
	KD_SPIN_DIRECT_LOCK(&test_lock, kd_spin_direct_cookie,
		".globl jit_escape_entry\njit_escape_entry:\n\t" ANNOTATE_NOENDBR);
#elif defined(JIT_ESCAPE_PUBLIC_API)
	kd_mutex_lock(&test_lock);
	/* Alias the actual DIRECT continuation; the runner checks the emitted
	 * capture/CALL bytes before loading this source. */
	asm volatile(".globl jit_escape_entry\n.set jit_escape_entry, 1b\n\t"
		     ".pushsection .discard.noendbr\n\t"
		     _ASM_PTR " jit_escape_entry\n\t.popsection\n\t"
		     : : : "memory");
#else
	struct kd_mutex_outer_cookie cookie;

	KD_MUTEX_OUTER_LOCK(&test_lock, cookie,
		".globl jit_escape_entry\njit_escape_entry:\n\t" ANNOTATE_NOENDBR);
#endif
	if (atomic_inc_return(&writers) != 1)
		atomic_inc(&failures);
#ifdef JIT_ESCAPE_SHARED
	if (atomic_read(&readers))
		atomic_inc(&failures);
#endif
#ifdef JIT_ESCAPE_RWSEM
	/* Other outer writers may reserve the same phase. Rejected readers can
	 * transiently publish speculative counts, but cannot enter their body. */
	if (atomic_long_read(&test_lock.admission) <= 0)
		atomic_inc(&failures);
#endif
	WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
	result->taken = 0;
	if (READ_ONCE(hot)) {
		result->taken = 1;
#ifdef JIT_ESCAPE_SHARED
		/* Require an actual competing read attempt at every hot marker.
		 * Completions are recorded inside the shared lock, so once this
		 * writer sees an outstanding attempt it cannot complete until the
		 * writer admission and gate are released. Bound the probe wait; failure
		 * is observable after return, never permission to replay a body. */
		{
			unsigned int tries;

			for (tries = 0; tries < 100000; tries++) {
				if (atomic_read(&read_attempts) != atomic_read(&read_completions))
					break;
				cpu_relax();
			}
			result->reader_pending = tries != 100000;
			result->read_completed_before = (u32)atomic_read(&read_completions);
		}
#endif
		/* CMP defines CF/PF/AF/ZF/SF/OF: 1 - 2 gives status mask 0x95.
		 * The unconditional branch tests flag preservation across a JIT
		 * block boundary. RDTSC is safe on this guest and leaves flags
		 * unchanged. The native suffix observes each condition immediately;
		 * LAHF additionally exposes AF, which has no SETcc instruction.
		 * Read actual current_task here, after RDTSC, and compare only after
		 * returning to the original caller. No unsafe privileged operation
		 * is used to exercise the escape mechanism. */
		asm volatile("movl $1, %%eax\n\t"
			     "cmpl $2, %%eax\n\t"
			     "jmp jit_escape_marker\n\t"
			     ".globl jit_escape_marker\njit_escape_marker:\n\t"
			     "rdtsc\n\t"
			     "movl %%eax, %[low]\n\t"
			     "movl %%edx, %[high]\n\t"
			     "setc %[carry]\n\t"
			     "setp %[parity]\n\t"
			     "setz %[zero]\n\t"
			     "sets %[sign]\n\t"
			     "seto %[overflow]\n\t"
			     "lahf\n\t"
			     "movzbl %%ah, %%eax\n\t"
			     "movl %%eax, %[ah]\n\t"
#ifdef JIT_ESCAPE_SPINNING
			     /* Arithmetic observations precede this second safe
			      * instruction; RDTSC remains the named first marker. */
			     "rdtscp\n\t"
			     "movl %%ecx, %[aux]\n\t"
#endif
			     "movq %%gs:current_task, %%rax\n\t"
			     "movq %%rax, %[task]\n\t"
			     : [low] "=m" (result->tsc_low),
			       [high] "=m" (result->tsc_high),
			       [carry] "=m" (result->carry),
			       [parity] "=m" (result->parity),
			       [zero] "=m" (result->zero),
			       [sign] "=m" (result->sign),
			       [overflow] "=m" (result->overflow),
			       [ah] "=m" (result->ah),
			       [task] "=m" (result->task)
#ifdef JIT_ESCAPE_SPINNING
			       , [aux] "=m" (result->cpu_aux)
#endif
			     : : "rax", "rdx",
#ifdef JIT_ESCAPE_SPINNING
			     "rcx",
#endif
			     "cc", "memory");
		WRITE_ONCE(hot_taken, READ_ONCE(hot_taken) + 1);
	}
	WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
#ifdef JIT_ESCAPE_SHARED
	if (atomic_read(&readers))
		atomic_inc(&failures);
	if (result->taken && result->read_completed_before != (u32)atomic_read(&read_completions))
		atomic_inc(&failures);
#endif
#ifdef JIT_ESCAPE_RWSEM
	if (atomic_long_read(&test_lock.admission) <= 0)
		atomic_inc(&failures);
#endif
	if (atomic_dec_return(&writers))
		atomic_inc(&failures);
#ifdef JIT_ESCAPE_RWLOCK
	KD_RWLOCK_DIRECT_WRITE_UNLOCK(&test_lock, kd_rwlock_direct_cookie);
#elif defined(JIT_ESCAPE_RWSEM)
	KD_RWSEM_OUTER_WRITE_UNLOCK(&test_lock, cookie);
#elif defined(JIT_ESCAPE_SPIN)
	KD_SPIN_DIRECT_UNLOCK(&test_lock, kd_spin_direct_cookie);
#elif defined(JIT_ESCAPE_PUBLIC_API)
	kd_mutex_unlock(&test_lock);
#else
	KD_MUTEX_OUTER_UNLOCK(&test_lock, cookie);
#endif
}

#ifdef JIT_ESCAPE_SHARED
static __attribute__((noipa)) bool reader_body(void)
{
	bool bad;

	atomic_inc(&read_attempts);
#ifdef JIT_ESCAPE_RWSEM
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
#ifdef JIT_ESCAPE_RWSEM
	kd_up_read(&test_lock);
#else
	kd_read_unlock(&test_lock);
#endif
	return bad;
}
#endif

static long escape_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct jit_escape_snapshot snapshot = { 0 };
	struct jit_escape_run run;
	struct escape_result result;
	unsigned int before_preempt, i;
	bool before_irqs;
#ifdef JIT_ESCAPE_SPINNING
	unsigned int before_cpu;
	unsigned long before_flags;
	u32 expected_aux;
#endif
	int ret = 0;

	(void)file;
	if (cmd == JIT_ESCAPE_RUN
#ifdef JIT_ESCAPE_SHARED
	    || cmd == JIT_ESCAPE_READ
#endif
	   ) {
		if (copy_from_user(&run, user, sizeof(run)))
			return -EFAULT;
		if (!run.iterations || run.iterations > 10000000 ||
		    run.worker >= 64 || run.reserved[0] || run.reserved[1])
			return -EINVAL;
#ifdef JIT_ESCAPE_SPINNING
		/* Only ordinary task-context root acquisitions are under test. */
		if (preempt_count() || irqs_disabled() ||
		    cpumask_weight(current->cpus_ptr) != 1)
			return -EINVAL;
		before_cpu = raw_smp_processor_id();
		expected_aux = native_cpu_aux();
#endif
		if (!atomic_add_unless(&control, 1, -1))
			return -EBUSY;
		before_preempt = preempt_count();
		before_irqs = irqs_disabled();
		run.completed = run.errors = 0;
		for (i = 0; i < run.iterations; i++) {
#ifdef JIT_ESCAPE_SPINNING
			before_flags = native_control_flags();
#endif
#ifdef JIT_ESCAPE_SHARED
			if (cmd == JIT_ESCAPE_READ) {
				if (reader_body())
					run.errors++;
			} else
#endif
			{
				escape_body(&result);
				/* Compare outside the translated critical section.
				 * A delegated GS read cannot replace execution of
				 * the suffix on this exact original task. */
				if (result.taken != READ_ONCE(hot) ||
				    (result.taken &&
				     (result.task != (unsigned long)current ||
				      result.carry != 1 || result.parity != 1 ||
				      result.zero != 0 || result.sign != 1 ||
				      result.overflow != 0 || (result.ah & 0xd5) != 0x95)))
					run.errors++;
#ifdef JIT_ESCAPE_SPINNING
				if (result.taken && result.cpu_aux != expected_aux)
					run.errors++;
#endif
#ifdef JIT_ESCAPE_SHARED
				if (result.taken && !result.reader_pending)
					run.errors++;
#endif
			}
#ifdef JIT_ESCAPE_SPINNING
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
	if (cmd != JIT_ESCAPE_SNAPSHOT && cmd != JIT_ESCAPE_PREPARE &&
	    cmd != JIT_ESCAPE_HOT)
		return -ENOTTY;
	/* Phase changes and inspection require every workload caller to join. */
	if (atomic_cmpxchg_acquire(&control, 0, -1))
		return -EBUSY;
	if (cmd == JIT_ESCAPE_PREPARE) {
#ifdef JIT_ESCAPE_RWLOCK
		ret = kd_rwlock_prepare(&test_lock, (unsigned long)jit_escape_entry,
				       KD_ENTRY_ABI_RWLOCK_CLOBBER_V1);
#elif defined(JIT_ESCAPE_RWSEM)
		ret = kd_mutex_prepare(&test_lock.gate, (unsigned long)jit_escape_entry,
				      KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#elif defined(JIT_ESCAPE_SPIN)
		ret = kd_spin_prepare(&test_lock, (unsigned long)jit_escape_entry,
				     KD_ENTRY_ABI_SPIN_CLOBBER_V1);
#else
		ret = kd_mutex_prepare(&test_lock, (unsigned long)jit_escape_entry,
				       KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
#endif
	} else if (cmd == JIT_ESCAPE_HOT) {
		if (!escape_idle())
			ret = -EBUSY;
		else
			WRITE_ONCE(hot, 1);
	} else {
		snapshot.prefix = prefix;
		snapshot.suffix = suffix;
		snapshot.hot_taken = hot_taken;
#ifdef JIT_ESCAPE_SHARED
		snapshot.lock_address = (unsigned long)&test_lock.gate;
#else
		snapshot.lock_address = (unsigned long)&test_lock;
#endif
		snapshot.entry = (unsigned long)jit_escape_entry;
		snapshot.marker = (unsigned long)jit_escape_marker;
		snapshot.failures = atomic_read(&failures);
		snapshot.active = atomic_read(&writers);
#ifdef JIT_ESCAPE_SHARED
		snapshot.active += atomic_read(&readers);
#endif
		snapshot.hot = READ_ONCE(hot);
		snapshot.idle = escape_idle();
		ret = copy_to_user(user, &snapshot, sizeof(snapshot)) ? -EFAULT : 0;
	}
	atomic_set_release(&control, 0);
	return ret;
}

static const struct file_operations escape_fops = {
	.owner = THIS_MODULE,
	.unlocked_ioctl = escape_ioctl,
};
static struct miscdevice escape_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "kd_jit_escape_test",
	.fops = &escape_fops,
	.mode = 0600,
};
static int __init escape_init(void)
{
	BUILD_BUG_ON(sizeof(struct jit_escape_run) != 32);
	BUILD_BUG_ON(sizeof(struct jit_escape_snapshot) != 80);
#ifdef JIT_ESCAPE_SPINNING
	if (!boot_cpu_has(X86_FEATURE_RDTSCP))
		return -EOPNOTSUPP;
#endif
	return misc_register(&escape_device);
}
static void __exit escape_exit(void) { misc_deregister(&escape_device); }
module_init(escape_init);
module_exit(escape_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Conditional JIT instruction escape and exact native continuation");
#ifdef JIT_ESCAPE_RWLOCK
MODULE_INFO(kd_escape_family, "rwlock");
MODULE_INFO(kd_mutex_api, "not_applicable");
#elif defined(JIT_ESCAPE_RWSEM)
MODULE_INFO(kd_escape_family, "rwsem");
MODULE_INFO(kd_mutex_api, "not_applicable");
#elif defined(JIT_ESCAPE_SPIN)
MODULE_INFO(kd_escape_family, "spin");
MODULE_INFO(kd_mutex_api, "not_applicable");
#else
MODULE_INFO(kd_escape_family, "mutex");
#ifdef JIT_ESCAPE_PUBLIC_API
MODULE_INFO(kd_mutex_api, "public");
#else
MODULE_INFO(kd_mutex_api, "outer");
#endif
#endif
