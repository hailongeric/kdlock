/* SPDX-License-Identifier: GPL-2.0 */
/* The actual GS instructions stay in the translated body. This ordinary
 * observation primitive only reads O's task/CPU/stack and local counter. */
#include <linux/percpu.h>

static DEFINE_PER_CPU(u64, helper_memory_counter);
static struct jit_memory_observation helper_memory_events[JIT_MEMORY_EVENTS];
static u64 helper_memory_count, helper_memory_body_after;
static u64 helper_memory_cf_checks, helper_memory_reg_checks, helper_memory_sp_checks;
static u64 helper_memory_read_value, helper_memory_read_checks;

static __attribute__((noipa)) noinline notrace void
jit_test_memory_observe(unsigned long stage)
{
	struct jit_memory_observation *event;
	unsigned long stack_marker;
	u64 index = READ_ONCE(helper_memory_count);

	if (index >= JIT_MEMORY_EVENTS) {
		atomic_inc(&failures);
		return;
	}
	event = &helper_memory_events[index];
	event->stage = stage;
	event->pid = current->pid;
	event->cpu = raw_smp_processor_id();
	event->stack_address = (unsigned long)&stack_marker;
	event->preempt = preempt_count();
	event->irqs = irqs_disabled();
	event->counter = this_cpu_read(helper_memory_counter);
	if (current->pid != READ_ONCE(killable_slots[1].pid) ||
	    (unsigned long)&stack_marker < READ_ONCE(helper_slots[1].origin_stack) ||
	    (unsigned long)&stack_marker >= READ_ONCE(helper_slots[1].origin_stack) + THREAD_SIZE)
		atomic_inc(&failures);
	smp_store_release(&helper_memory_count, index + 1);
}

#define JIT_MEMORY_WITNESS 0x73519ace2468bdf0UL
/* R10/R11 and CF are source state across the instruction transaction, not
 * across an ordinary C CALL. The source SP must also remain unchanged. */
#define JIT_MEMORY_INSTRUCTION(instruction, variable) do { \
	unsigned long before, after, witness; \
	unsigned char carry; \
	asm volatile("movq %%rsp, %%r11\n\t" \
		"movabsq $0x73519ace2468bdf0, %%r10\n\t" \
		"stc\n\t" instruction " " __percpu_arg([word]) "\n\t" \
		"setc %[carry]\n\t" \
		"movq %%r10, %[witness]\n\t" \
		"movq %%r11, %[before]\n\t" \
		"movq %%rsp, %[after]\n\t" \
		: [word] "+m" (__my_cpu_var(variable)), [carry] "=qm" (carry), \
		  [witness] "=r" (witness), [before] "=r" (before), [after] "=r" (after) \
		: : "r10", "r11", "cc", "memory"); \
	if (carry != 1 || witness != JIT_MEMORY_WITNESS || before != after) \
		atomic_inc(&failures); \
	WRITE_ONCE(helper_memory_cf_checks, READ_ONCE(helper_memory_cf_checks) + (carry == 1)); \
	WRITE_ONCE(helper_memory_reg_checks, READ_ONCE(helper_memory_reg_checks) + (witness == JIT_MEMORY_WITNESS)); \
	WRITE_ONCE(helper_memory_sp_checks, READ_ONCE(helper_memory_sp_checks) + (before == after)); \
} while (0)

/* The source MOV32 must import O's Native count without the runtime pin.
 * A high-word witness also checks the architecture's 32-bit zero extension. */
#define JIT_MEMORY_PREEMPT_READ() do { \
	unsigned long before, after, witness, value; \
	unsigned char carry; \
	bool valid; \
	asm volatile("movq %%rsp, %%r11\n\t" \
		"movabsq $0x73519ace2468bdf0, %%r10\n\t" \
		"movabsq $0xfedcba9800000000, %[value]\n\t" \
		"stc\n\t" \
		"movl " __percpu_arg([word]) ", %k[value]\n\t" \
		"setc %[carry]\n\t" \
		"movq %%r10, %[witness]\n\t" \
		"movq %%r11, %[before]\n\t" \
		"movq %%rsp, %[after]\n\t" \
		: [value] "=&r" (value), [carry] "=qm" (carry), \
		  [witness] "=r" (witness), [before] "=r" (before), [after] "=r" (after) \
		: [word] "m" (__my_cpu_var(__preempt_count)) \
		: "r10", "r11", "cc", "memory"); \
	valid = !(value >> 32) && (value & ~((unsigned long)PREEMPT_NEED_RESCHED)) == 1; \
	if (!valid || carry != 1 || witness != JIT_MEMORY_WITNESS || before != after) \
		atomic_inc(&failures); \
	WRITE_ONCE(helper_memory_read_value, value); \
	WRITE_ONCE(helper_memory_read_checks, READ_ONCE(helper_memory_read_checks) + valid); \
	WRITE_ONCE(helper_memory_cf_checks, READ_ONCE(helper_memory_cf_checks) + (carry == 1)); \
	WRITE_ONCE(helper_memory_reg_checks, READ_ONCE(helper_memory_reg_checks) + (witness == JIT_MEMORY_WITNESS)); \
	WRITE_ONCE(helper_memory_sp_checks, READ_ONCE(helper_memory_sp_checks) + (before == after)); \
} while (0)

static void helper_memory_reset(void)
{
	int cpu;

	memset(helper_memory_events, 0, sizeof(helper_memory_events));
	WRITE_ONCE(helper_memory_count, 0);
	WRITE_ONCE(helper_memory_body_after, 0);
	WRITE_ONCE(helper_memory_cf_checks, 0);
	WRITE_ONCE(helper_memory_reg_checks, 0);
	WRITE_ONCE(helper_memory_sp_checks, 0);
	WRITE_ONCE(helper_memory_read_value, 0);
	WRITE_ONCE(helper_memory_read_checks, 0);
	for_each_possible_cpu(cpu)
		per_cpu(helper_memory_counter, cpu) = 0;
}

static noinline long helper_memory_snapshot(void __user *user)
{
	struct jit_memory_snapshot state = {
		.version = 1, .errors = atomic_read(&failures),
		.count = smp_load_acquire(&helper_memory_count),
		.origin_stack = READ_ONCE(helper_slots[1].origin_stack),
		.origin_stack_high = READ_ONCE(helper_slots[1].origin_stack) + THREAD_SIZE,
		.body_after = READ_ONCE(helper_memory_body_after),
		.cf_checks = READ_ONCE(helper_memory_cf_checks),
		.reg_checks = READ_ONCE(helper_memory_reg_checks),
		.sp_checks = READ_ONCE(helper_memory_sp_checks),
		.read_value = READ_ONCE(helper_memory_read_value),
		.read_checks = READ_ONCE(helper_memory_read_checks),
	};
	unsigned int i;

	if (state.count > JIT_MEMORY_EVENTS)
		return -EOVERFLOW;
	for (i = 0; i < state.count; ++i) {
#define MEMORY_COPY(name) state.events[i].name = READ_ONCE(helper_memory_events[i].name)
		MEMORY_COPY(stage); MEMORY_COPY(pid); MEMORY_COPY(cpu); MEMORY_COPY(stack_address);
		MEMORY_COPY(preempt); MEMORY_COPY(irqs); MEMORY_COPY(counter);
#undef MEMORY_COPY
	}
	return copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
}
