// SPDX-License-Identifier: GPL-2.0
/* Included by the workload module, never by the production lock module. */
#include <linux/hardirq.h>

static unsigned int context_lock_probe;
module_param(context_lock_probe, uint, 0444);
MODULE_PARM_DESC(
	context_lock_probe,
	"Mode 3 native-only probe: 1=IRQ-save, 2=BH, 3/4/5/6/7/8/9=direct/register/cross-block/CMOV/rotate/implicit/spill per-CPU offset; arm with mixed_lock_probe=2");
static atomic_t context_inside = ATOMIC_INIT(0);
static atomic_t context_checked = ATOMIC_INIT(0);
static atomic_t context_failures = ATOMIC_INIT(0);
static atomic_t context_cmov_false = ATOMIC_INIT(0);
static atomic_t context_cmov_true = ATOMIC_INIT(0);
static atomic_t context_rotate_zero = ATOMIC_INIT(0);
static atomic_t context_rotate_one = ATOMIC_INIT(0);

/* This observer executes natively only after the entry is rejected. Its GS
 * reads must not themselves be the reason the caller fails initial admission. */
static __attribute__((noipa)) noinline void kd_context_check(bool inside)
{
	bool valid;

	if (inside) {
		valid = context_lock_probe == 1 ?
				irqs_disabled() :
				softirq_count() && !irqs_disabled();
		atomic_inc(&context_inside);
	} else {
		valid = !irqs_disabled() && !preempt_count();
		atomic_inc(&context_checked);
	}
	if (!valid)
		atomic_inc(&context_failures);
}

/* Keep direct IRQ/BH calls in separate CS entries, so a plain spin CALL cannot
 * mask the context-policy check with a mixed-backend rejection first. */
static __attribute__((noipa)) noinline void
kd_context_mutex_irqsave(unsigned long work_load)
{
	unsigned long flags, j;
	volatile int work = 0;

	mutex_lock(&global_mutex);
	if (atomic_inc_return(&mutex_inside) != 1)
		atomic_inc(&mutex_overlaps);
	kd_cs_step(KD_CS_MUTEX_GLOBAL);
	if (READ_ONCE(mixed_lock_probe) == 2) {
		spin_lock_irqsave(&global_lock, flags);
		kd_context_check(true);
		kd_cs_step(KD_CS_SPIN_GLOBAL);
		for (j = 0; j < work_load; j++)
			work++;
		spin_unlock_irqrestore(&global_lock, flags);
	}
	atomic_dec(&mutex_inside);
	mutex_unlock(&global_mutex);
	kd_context_check(false);
}

static __attribute__((noipa)) noinline void
kd_context_mutex_bh(unsigned long work_load)
{
	unsigned long j;
	volatile int work = 0;

	mutex_lock(&global_mutex);
	if (atomic_inc_return(&mutex_inside) != 1)
		atomic_inc(&mutex_overlaps);
	kd_cs_step(KD_CS_MUTEX_GLOBAL);
	if (READ_ONCE(mixed_lock_probe) == 2) {
		spin_lock_bh(&global_lock);
		kd_context_check(true);
		kd_cs_step(KD_CS_SPIN_GLOBAL);
		for (j = 0; j < work_load; j++)
			work++;
		spin_unlock_bh(&global_lock);
	}
	atomic_dec(&mutex_inside);
	mutex_unlock(&global_mutex);
	kd_context_check(false);
}

static __attribute__((noipa)) noinline void
kd_context_percpu_check(unsigned long seen, unsigned long expected,
			struct task_struct *task, int cpu)
{
	atomic_inc(&context_inside);
	if (seen != expected || current != task ||
	    raw_smp_processor_id() != cpu || irqs_disabled() || preempt_count())
		atomic_inc(&context_failures);
}

static __always_inline void kd_context_percpu_body(unsigned long work_load,
						   unsigned int addressing)
{
	unsigned int offset_index =
		addressing == 5 || (addressing == 3 && (work_load & 1)) ? 0 : 1;
	unsigned long expected = READ_ONCE(__per_cpu_offset[offset_index]);
	struct task_struct *task = current;
	int cpu = raw_smp_processor_id();
	unsigned long seen, j;
	volatile int work = 0;

	mutex_lock(&global_mutex);
	if (atomic_inc_return(&mutex_inside) != 1)
		atomic_inc(&mutex_overlaps);
	kd_cs_step(KD_CS_MUTEX_GLOBAL);
	if (READ_ONCE(mixed_lock_probe) == 2) {
		if (addressing == 6) {
			unsigned long spill;

			/* A compiler-allocated stack slot forwards a table-exterior value.
			 * Only the reload-derived LODSQ may trigger this probe's refusal. */
			asm volatile("cld\n\t"
				     "leaq __per_cpu_offset-8(%%rip), %%rax\n\t"
				     "movq %%rax, %1\n\t"
				     "xorq %%rax, %%rax\n\t"
				     "movq %1, %%rsi\n\t"
				     "addq $16, %%rsi\n\t"
				     "lodsq\n\t"
				     "movq %%rax, %0"
				     : "=r"(seen), "=m"(spill)
				     :
				     : "rax", "rsi", "cc", "memory");
		} else if (addressing == 5) {
			/* The first load ends before the table; only the second implicit
			 * access reads it. Neither LODSQ has an explicit decoded operand. */
			asm volatile("cld\n\t"
				     "leaq __per_cpu_offset-8(%%rip), %%rsi\n\t"
				     "lodsq\n\t"
				     "lodsq\n\t"
				     "movq %%rax, %0"
				     : "=r"(seen)
				     :
				     : "rax", "rsi", "cc", "memory");
		} else if (addressing == 4) {
			/* A reversible pair keeps both native count paths valid. Admission
			 * must retain the zero-count address across both internal IR graphs. */
			asm volatile("leaq __per_cpu_offset-8(%%rip), %%rax\n\t"
				     "movq %1, %%rcx\n\t"
				     "andl $1, %%ecx\n\t"
				     "rolq %%cl, %%rax\n\t"
				     "rorq %%cl, %%rax\n\t"
				     "addq $16, %%rax\n\t"
				     "movq (%%rax), %0"
				     : "=r"(seen)
				     : "r"(work_load)
				     : "rax", "rcx", "cc", "memory");
			atomic_inc(work_load & 1 ? &context_rotate_one :
						   &context_rotate_zero);
		} else if (addressing == 3) {
			/* Both LEAs are outside the table. Either CMOV exit must retain
			 * its known base until ADD exposes the following sensitive read. */
			asm volatile(
				"leaq __per_cpu_offset-8(%%rip), %%rax\n\t"
				"leaq __per_cpu_offset-16(%%rip), %%rcx\n\t"
				"testq $1, %1\n\t"
				"cmovnz %%rcx, %%rax\n\t"
				"addq $16, %%rax\n\t"
				"movq (%%rax), %0"
				: "=r"(seen)
				: "r"(work_load)
				: "rax", "rcx", "cc", "memory");
			atomic_inc(work_load & 1 ? &context_cmov_true :
						   &context_cmov_false);
		} else if (addressing == 2) {
			/* A real block edge separates the known base from its use. */
			asm volatile("leaq __per_cpu_offset-8(%%rip), %%rax\n\t"
				     "jmp 1f\n\t"
				     "1: addq $16, %%rax\n\t"
				     "movq (%%rax), %0"
				     : "=r"(seen)
				     :
				     : "rax", "memory");
		} else if (addressing == 1) {
			/* The initial address lies outside the sensitive interval. Only
			 * tracking the following ADD exposes the actual memory access. */
			asm volatile("leaq __per_cpu_offset-8(%%rip), %%rax\n\t"
				     "addq $16, %%rax\n\t"
				     "movq (%%rax), %0"
				     : "=r"(seen)
				     :
				     : "rax", "memory");
		} else {
			asm volatile("movq __per_cpu_offset+8(%%rip), %0"
				     : "=r"(seen)
				     :
				     : "memory");
		}
		kd_context_percpu_check(seen, expected, task, cpu);
		for (j = 0; j < work_load; j++)
			work++;
	}
	atomic_dec(&mutex_inside);
	mutex_unlock(&global_mutex);
	kd_context_check(false);
}

/* Constant inline selection gives each probe its own CS entry, so the direct
 * reference cannot mask the register-derived admission test. */
static __attribute__((noipa)) noinline void
kd_context_mutex_percpu(unsigned long work_load)
{
	kd_context_percpu_body(work_load, 0);
}

static __attribute__((noipa)) noinline void
kd_context_mutex_percpu_regs(unsigned long work_load)
{
	kd_context_percpu_body(work_load, 1);
}

static __attribute__((noipa)) noinline void
kd_context_mutex_percpu_flow(unsigned long work_load)
{
	kd_context_percpu_body(work_load, 2);
}

static __attribute__((noipa)) noinline void
kd_context_mutex_percpu_cmov(unsigned long work_load)
{
	kd_context_percpu_body(work_load, 3);
}

static __attribute__((noipa)) noinline void
kd_context_mutex_percpu_rotate(unsigned long work_load)
{
	kd_context_percpu_body(work_load, 4);
}

static __attribute__((noipa)) noinline void
kd_context_mutex_percpu_implicit(unsigned long work_load)
{
	kd_context_percpu_body(work_load, 5);
}

static __attribute__((noipa)) noinline void
kd_context_mutex_percpu_spill(unsigned long work_load)
{
	kd_context_percpu_body(work_load, 6);
}

static void kd_context_report(void)
{
	if (context_lock_probe == 7)
		pr_info("kd_context rotate: zero=%d one=%d\n",
			atomic_read(&context_rotate_zero),
			atomic_read(&context_rotate_one));
	if (context_lock_probe == 6)
		pr_info("kd_context cmov: false=%d true=%d\n",
			atomic_read(&context_cmov_false),
			atomic_read(&context_cmov_true));
	if (context_lock_probe)
		pr_info("kd_context native: api=%u inside=%d checked=%d failures=%d outer=%lu inner=%lu\n",
			context_lock_probe, atomic_read(&context_inside),
			atomic_read(&context_checked),
			atomic_read(&context_failures),
			kd_cs_completed[KD_CS_MUTEX_GLOBAL],
			kd_cs_completed[KD_CS_SPIN_GLOBAL]);
}
