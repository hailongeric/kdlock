/* SPDX-License-Identifier: GPL-2.0 */
/* The logical CALL word stays on the source stack. Only the separately
 * registered Native target receives the five mapped argument words. */
#include <linux/slab.h>

#define JIT_MAPPED_WORD 0x1122334455667788UL
#define JIT_MAPPED_RESULT (JIT_MAPPED_WORD ^ 0x6ae35d09c4b27180UL ^ 1UL)
#define JIT_MAPPED_ALLOC_BYTES 53UL
static struct jit_mapped_snapshot helper_mapped;
static bool helper_mapped_registered;
extern char jit_test_mapped_return[];

static __attribute__((noipa)) noinline notrace unsigned long
jit_test_call_mapped(unsigned long index, unsigned long word)
{
	/* A serviced logical target must not execute its Native body as well. */
	WRITE_ONCE(helper_mapped.logical_calls, READ_ONCE(helper_mapped.logical_calls) + 1);
	atomic_inc(&failures);
	return index ^ word;
}

static __attribute__((noipa)) noinline notrace unsigned long
jit_test_call_mapped_native(unsigned long index, unsigned long zero,
	unsigned long word, unsigned long node, unsigned long return_ip)
{
	unsigned long stack_marker;

	WRITE_ONCE(helper_mapped.pid, current->pid);
	WRITE_ONCE(helper_mapped.stack_address, (unsigned long)&stack_marker);
	WRITE_ONCE(helper_mapped.stack_low, (unsigned long)task_stack_page(current));
	WRITE_ONCE(helper_mapped.stack_high, (unsigned long)task_stack_page(current) + THREAD_SIZE);
	WRITE_ONCE(helper_mapped.preempt, preempt_count());
	WRITE_ONCE(helper_mapped.irqs, irqs_disabled());
	WRITE_ONCE(helper_mapped.arguments[0], index);
	WRITE_ONCE(helper_mapped.arguments[1], zero);
	WRITE_ONCE(helper_mapped.arguments[2], word);
	WRITE_ONCE(helper_mapped.arguments[3], node);
	WRITE_ONCE(helper_mapped.arguments[4], return_ip);
	if (index != 1 || zero || word != JIT_MAPPED_WORD || node != ~0UL ||
	    return_ip != (unsigned long)jit_test_mapped_return ||
	    current->pid != READ_ONCE(killable_slots[1].pid) ||
	    READ_ONCE(helper_slots[1].origin_stack) != (unsigned long)task_stack_page(current) ||
	    (unsigned long)&stack_marker < (unsigned long)task_stack_page(current) ||
	    (unsigned long)&stack_marker >= (unsigned long)task_stack_page(current) + THREAD_SIZE ||
	    preempt_count() || irqs_disabled())
		atomic_inc(&failures);
	WRITE_ONCE(helper_mapped.result, JIT_MAPPED_RESULT);
	smp_store_release(&helper_mapped.calls, READ_ONCE(helper_mapped.calls) + 1);
	return JIT_MAPPED_RESULT;
}

static int helper_mapped_register(void)
{
	static const struct kd_service_call_mapped_desc descriptor = {
		.source = { .symbol = "jit_test_call_mapped", .target = (unsigned long)jit_test_call_mapped,
			.nargs = 2, .result_kind = KD_SERVICE_CALL_WORD,
			.context_kind = KD_SERVICE_CALL_BALANCED_ORIGIN },
		.execution_target = (unsigned long)jit_test_call_mapped_native,
		.version = KD_SERVICE_CALL_MAP_V1, .execution_nargs = 5,
		.arguments = { KD_SERVICE_ARG_SOURCE0, KD_SERVICE_ARG_ZERO, KD_SERVICE_ARG_SOURCE1,
			KD_SERVICE_ARG_MINUS_ONE, KD_SERVICE_ARG_RETURN_IP, KD_SERVICE_ARG_UNUSED },
	};
	int result;

	if (READ_ONCE(helper_mapped_registered))
		return -EALREADY;
	result = kd_service_call_register_mapped(&descriptor, 1, THIS_MODULE);
	if (!result)
		WRITE_ONCE(helper_mapped_registered, true);
	return result;
}

static __always_inline void helper_mapped_body(void)
{
	unsigned long value, flags, index = 1, word = JIT_MAPPED_WORD;
	unsigned char carry, parity, zero, sign, overflow;

	/* The label is the actual CALL end, before any flag-changing instruction.
	 * Inputs are read/write because an ordinary C CALL may clobber DI and SI. */
	asm volatile("call jit_test_call_mapped\n\t"
		".globl jit_test_mapped_return\njit_test_mapped_return:\n\t"
		"setc %[carry]\n\tsetp %[parity]\n\tsetz %[zero]\n\t"
		"sets %[sign]\n\tseto %[overflow]\n\t"
		: "=a" (value), [carry] "=m" (carry), [parity] "=m" (parity),
		  [zero] "=m" (zero), [sign] "=m" (sign), [overflow] "=m" (overflow),
		  "+D" (index), "+S" (word), ASM_CALL_CONSTRAINT
		: : "rcx", "rdx", "r8", "r9", "r10", "r11", "cc", "memory");
	/* SETcc preserves flags and uses the supported source instruction path.
	 * The transaction trace separately compares the full done/resume flags. */
	flags = carry | (parity << 2) | (zero << 6) | (sign << 7) | (overflow << 11);
	WRITE_ONCE(helper_mapped.body_flags, flags);
	WRITE_ONCE(helper_mapped.body_result, value);
	WRITE_ONCE(helper_mapped.source_return, (unsigned long)jit_test_mapped_return);
	if (value != JIT_MAPPED_RESULT)
		atomic_inc(&failures);
	WRITE_ONCE(helper_mapped.body_after, READ_ONCE(helper_mapped.body_after) + 1);
}

static __always_inline void helper_allocation_body(void)
{
	unsigned char *allocation;
	unsigned int i;
	unsigned long size = JIT_MAPPED_ALLOC_BYTES, flags = GFP_KERNEL | __GFP_ZERO;

	WRITE_ONCE(helper_mapped.allocation_size, size);
	WRITE_ONCE(helper_mapped.allocation_flags, flags);
	/* A real source CALL to the registered production API, without replacing
	 * the allocation by a test function or compiling a constant-size frontend. */
	asm volatile("call __kmalloc_noprof\n\t"
		: "=a" (allocation), "+D" (size), "+S" (flags), ASM_CALL_CONSTRAINT
		: : "rcx", "rdx", "r8", "r9", "r10", "r11", "cc", "memory");
	WRITE_ONCE(helper_mapped.allocation_pointer, (unsigned long)allocation);
	if (!allocation) {
		atomic_inc(&failures);
		return;
	}
	for (i = 0; i < JIT_MAPPED_ALLOC_BYTES; ++i) {
		if (READ_ONCE(allocation[i]))
			atomic_inc(&failures);
		else
			WRITE_ONCE(helper_mapped.allocation_zero_bytes,
				READ_ONCE(helper_mapped.allocation_zero_bytes) + 1);
		WRITE_ONCE(allocation[i], (unsigned char)(i ^ 0x5a));
	}
	for (i = 0; i < JIT_MAPPED_ALLOC_BYTES; ++i) {
		if (READ_ONCE(allocation[i]) != (unsigned char)(i ^ 0x5a))
			atomic_inc(&failures);
		else
			WRITE_ONCE(helper_mapped.allocation_written_bytes,
				READ_ONCE(helper_mapped.allocation_written_bytes) + 1);
	}
	kfree(allocation);
	WRITE_ONCE(helper_mapped.allocation_freed, READ_ONCE(helper_mapped.allocation_freed) + 1);
	WRITE_ONCE(helper_mapped.allocation_body_after, READ_ONCE(helper_mapped.allocation_body_after) + 1);
}

static noinline long helper_mapped_snapshot(void __user *user)
{
	struct jit_mapped_snapshot state = {
		.version = 1, .errors = atomic_read(&failures),
		.registered = READ_ONCE(helper_mapped_registered),
		.source_target = (unsigned long)jit_test_call_mapped,
		.execution_target = (unsigned long)jit_test_call_mapped_native,
	};
	unsigned int i;

#define MAPPED_COPY(name) state.name = READ_ONCE(helper_mapped.name)
	MAPPED_COPY(logical_calls); MAPPED_COPY(calls); MAPPED_COPY(pid);
	MAPPED_COPY(stack_address); MAPPED_COPY(stack_low); MAPPED_COPY(stack_high);
	MAPPED_COPY(preempt); MAPPED_COPY(irqs); MAPPED_COPY(result); MAPPED_COPY(body_result);
	MAPPED_COPY(body_after); MAPPED_COPY(body_flags); MAPPED_COPY(source_return);
	MAPPED_COPY(allocation_size); MAPPED_COPY(allocation_flags); MAPPED_COPY(allocation_pointer);
	MAPPED_COPY(allocation_zero_bytes); MAPPED_COPY(allocation_written_bytes);
	MAPPED_COPY(allocation_freed); MAPPED_COPY(allocation_body_after);
	for (i = 0; i < 5; ++i)
		state.arguments[i] = READ_ONCE(helper_mapped.arguments[i]);
#undef MAPPED_COPY
	return copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
}
