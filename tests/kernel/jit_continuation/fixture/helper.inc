/* SPDX-License-Identifier: GPL-2.0 */
/* Declared C primitives return to the retained executor; the body continues
 * there after this original-task transaction has finished. */
#include <linux/sched/task_stack.h>
#include <asm/nospec-branch.h>
#include "kd_service_calls.h"

#define JIT_HELPER_A1 0x1122334455667788UL
#define JIT_HELPER_A2 0x89abcdef01234567UL
#define JIT_HELPER_A3 0x1020304050607080UL
#define JIT_HELPER_A4 0x55aa00ff88776611UL
#define JIT_HELPER_A5 0xdeadbeef2468ace0UL
#define JIT_HELPER_RESULT(index) \
	(0x7edcba9876543210UL ^ (index) ^ (JIT_HELPER_A1 + 3 * JIT_HELPER_A2 + \
	 5 * JIT_HELPER_A3 + 7 * JIT_HELPER_A4 + 11 * JIT_HELPER_A5))

static DEFINE_KD_MUTEX(helper_child);
static struct jit_helper_slot helper_slots[JIT_KILLABLE_SLOTS];
static bool helper_registered;

static struct jit_helper_slot *helper_enter(unsigned long index, unsigned long a1,
	unsigned long a2, unsigned long a3, unsigned long a4, unsigned long a5)
{
	unsigned long stack_marker;
	struct jit_helper_slot *slot;

	if (index >= JIT_KILLABLE_SLOTS) {
		atomic_inc(&failures);
		return NULL;
	}
	slot = &helper_slots[index];
	WRITE_ONCE(slot->pid, current->pid);
	WRITE_ONCE(slot->stack_address, (unsigned long)&stack_marker);
	WRITE_ONCE(slot->stack_low, (unsigned long)task_stack_page(current));
	WRITE_ONCE(slot->stack_high, (unsigned long)task_stack_page(current) + THREAD_SIZE);
	WRITE_ONCE(slot->preempt_before, preempt_count());
	WRITE_ONCE(slot->irqs_before, irqs_disabled());
	WRITE_ONCE(slot->arguments[0], index);
	WRITE_ONCE(slot->arguments[1], a1);
	WRITE_ONCE(slot->arguments[2], a2);
	WRITE_ONCE(slot->arguments[3], a3);
	WRITE_ONCE(slot->arguments[4], a4);
	WRITE_ONCE(slot->arguments[5], a5);
	smp_store_release(&slot->calls, READ_ONCE(slot->calls) + 1);
	if (current->pid != READ_ONCE(killable_slots[index].pid) ||
	    READ_ONCE(slot->origin_stack) != (unsigned long)task_stack_page(current) ||
	    (unsigned long)&stack_marker < (unsigned long)task_stack_page(current) ||
	    (unsigned long)&stack_marker >= (unsigned long)task_stack_page(current) + THREAD_SIZE ||
	    preempt_count() || irqs_disabled() || a1 != JIT_HELPER_A1 || a2 != JIT_HELPER_A2 ||
	    a3 != JIT_HELPER_A3 || a4 != JIT_HELPER_A4 || a5 != JIT_HELPER_A5) {
		atomic_inc(&failures);
		return NULL;
	}
	return slot;
}

static __attribute__((noipa)) noinline notrace unsigned long
jit_test_call_scalar(unsigned long index, unsigned long a1, unsigned long a2,
	unsigned long a3, unsigned long a4, unsigned long a5)
{
	struct jit_helper_slot *slot = helper_enter(index, a1, a2, a3, a4, a5);
	unsigned long result = 0x7edcba9876543210UL ^ index ^ (a1 + 3 * a2 + 5 * a3 + 7 * a4 + 11 * a5);

	if (!slot)
		return 0;
	WRITE_ONCE(slot->result, result);
	return result;
}

/* This ordinary callee is translated, not registered as a Native primitive.
 * Its register JMP retains the caller's existing CALL word. Only the scalar
 * target below is serviced on the original task. */
unsigned long jit_test_call_tail(unsigned long index, unsigned long a1,
	unsigned long a2, unsigned long a3, unsigned long a4, unsigned long a5);
asm(".pushsection .text\n"
    ".balign 16\n"
    ".globl jit_test_call_tail\n"
    ".type jit_test_call_tail,@function\n"
    "jit_test_call_tail:\n"
    ".byte 0xf3,0x0f,0x1e,0xfa\n"
    "lea jit_test_call_scalar(%rip),%rax\n"
    ANNOTATE_RETPOLINE_SAFE "\n"
    "jmp *%rax\n"
    ".size jit_test_call_tail,.-jit_test_call_tail\n"
    ".popsection\n");

static __attribute__((noipa)) noinline notrace unsigned long
jit_test_call_wait(unsigned long index, unsigned long a1, unsigned long a2,
	unsigned long a3, unsigned long a4, unsigned long a5)
{
	struct jit_helper_slot *slot = helper_enter(index, a1, a2, a3, a4, a5);
	unsigned long before_jiffies, before_switches, deadline, result;

	if (!slot)
		return 0;
	/* This ordinary child is acquired by the original task, with its native
	 * stack/context, and is released before the primitive returns. */
	(kd_mutex_lock)(&helper_child);
	if ((atomic_long_read(&helper_child.owner) & ~7UL) != (unsigned long)current)
		atomic_inc(&failures);
	WRITE_ONCE(slot->child_acquired, READ_ONCE(slot->child_acquired) + 1);
	before_jiffies = jiffies;
	before_switches = current->nvcsw;
	deadline = jiffies + 30 * HZ;
	do {
		smp_store_release(&slot->sleep_calls, READ_ONCE(slot->sleep_calls) + 1);
		schedule_timeout_uninterruptible(1);
		if (time_after(jiffies, deadline)) {
			atomic_inc(&failures);
			break;
		}
	} while (!(READ_ONCE(killable_release) & JIT_KILLABLE_RELEASE_HELPER));
	WRITE_ONCE(slot->jiffies_delta, jiffies - before_jiffies);
	WRITE_ONCE(slot->switches_delta, current->nvcsw - before_switches);
	WRITE_ONCE(slot->signal_seen, fatal_signal_pending(current));
	(kd_mutex_unlock)(&helper_child);
	WRITE_ONCE(slot->child_released, READ_ONCE(slot->child_released) + 1);
	result = 0x7edcba9876543210UL ^ index ^ (a1 + 3 * a2 + 5 * a3 + 7 * a4 + 11 * a5);
	WRITE_ONCE(slot->result, result);
	return result;
}

#include "helper_mapped.inc"
#include "helper_native.inc"
#include "helper_native_write.inc"
#include "helper_memory.inc"

static int helper_register(void)
{
	static const struct kd_service_call_desc descriptors[] = {
		{ .symbol = "jit_test_call_scalar", .target = (unsigned long)jit_test_call_scalar,
		  .nargs = 6, .result_kind = KD_SERVICE_CALL_WORD, .context_kind = KD_SERVICE_CALL_BALANCED_ORIGIN },
		{ .symbol = "jit_test_call_wait", .target = (unsigned long)jit_test_call_wait,
		  .nargs = 6, .result_kind = KD_SERVICE_CALL_WORD, .context_kind = KD_SERVICE_CALL_BALANCED_ORIGIN },
		{ .symbol = "jit_test_native_spin_lock", .target = (unsigned long)jit_test_native_spin_lock,
		  .nargs = 1, .result_kind = KD_SERVICE_CALL_VOID, .context_kind = KD_SERVICE_CALL_SPIN_LOCK },
		{ .symbol = "jit_test_native_spin_try", .target = (unsigned long)jit_test_native_spin_try,
		  .nargs = 1, .result_kind = KD_SERVICE_CALL_WORD, .context_kind = KD_SERVICE_CALL_SPIN_TRYLOCK },
		{ .symbol = "jit_test_native_spin_unlock", .target = (unsigned long)jit_test_native_spin_unlock,
		  .nargs = 1, .result_kind = KD_SERVICE_CALL_VOID, .context_kind = KD_SERVICE_CALL_SPIN_UNLOCK },
		{ .symbol = "jit_test_native_rcu_lock", .target = (unsigned long)jit_test_native_rcu_lock,
		  .nargs = 0, .result_kind = KD_SERVICE_CALL_VOID, .context_kind = KD_SERVICE_CALL_RCU_LOCK },
		{ .symbol = "jit_test_native_rcu_unlock", .target = (unsigned long)jit_test_native_rcu_unlock,
		  .nargs = 0, .result_kind = KD_SERVICE_CALL_VOID, .context_kind = KD_SERVICE_CALL_RCU_UNLOCK },
		{ .symbol = "jit_test_memory_observe", .target = (unsigned long)jit_test_memory_observe,
		  .nargs = 1, .result_kind = KD_SERVICE_CALL_VOID, .context_kind = KD_SERVICE_CALL_ATOMIC_ORIGIN },
		{ .symbol = "jit_test_native_write_lock", .target = (unsigned long)jit_test_native_write_lock,
		  .nargs = 1, .result_kind = KD_SERVICE_CALL_VOID, .context_kind = KD_SERVICE_CALL_RWSEM_WRITE_LOCK },
		{ .symbol = "jit_test_native_write_unlock", .target = (unsigned long)jit_test_native_write_unlock,
		  .nargs = 1, .result_kind = KD_SERVICE_CALL_VOID, .context_kind = KD_SERVICE_CALL_RWSEM_WRITE_UNLOCK },
	};
	int result = kd_service_call_register(descriptors, ARRAY_SIZE(descriptors), THIS_MODULE);

	if (!result) {
		__module_get(THIS_MODULE);
		WRITE_ONCE(helper_registered, true);
	}
	return result;
}

static int helper_unregister(void)
{
	int result;

	if (!READ_ONCE(helper_registered))
		return 0;
	result = kd_service_call_unregister(THIS_MODULE);
	if (!result) {
		WRITE_ONCE(helper_registered, false);
		WRITE_ONCE(helper_mapped_registered, false);
		module_put(THIS_MODULE);
	}
	return result;
}

static noinline long helper_snapshot(void __user *user)
{
	struct jit_helper_snapshot state = {
		.version = 1, .registered = READ_ONCE(helper_registered), .errors = atomic_read(&failures),
	};
	unsigned int i, j;

	for (i = 0; i < JIT_KILLABLE_SLOTS; ++i) {
		struct jit_helper_slot *from = &helper_slots[i], *to = &state.slots[i];

		to->calls = smp_load_acquire(&from->calls);
#define HELPER_COPY(name) to->name = READ_ONCE(from->name)
		HELPER_COPY(origin_stack); HELPER_COPY(pid); HELPER_COPY(stack_address);
		HELPER_COPY(stack_low); HELPER_COPY(stack_high); HELPER_COPY(preempt_before);
		HELPER_COPY(irqs_before); HELPER_COPY(result); HELPER_COPY(body_result); HELPER_COPY(body_after);
		HELPER_COPY(sleep_calls); HELPER_COPY(jiffies_delta); HELPER_COPY(switches_delta);
		HELPER_COPY(child_acquired); HELPER_COPY(child_released); HELPER_COPY(signal_seen);
		for (j = 0; j < 6; ++j)
			to->arguments[j] = READ_ONCE(from->arguments[j]);
#undef HELPER_COPY
	}
	return copy_to_user(user, &state, sizeof(state)) ? -EFAULT : 0;
}
