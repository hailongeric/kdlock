/*
 * test_jit_call_policy.c — userspace model for mutex JIT call-miss policy.
 *
 * The real kernel path handles these decisions in kd_exe_on_call_hl_entry().
 * This test keeps the high-risk rule explicit: only the outer mutex unlock
 * completes a delegated critical section; known safe calls may advance to the
 * saved return address; unknown calls must not leave a simulated CALL frame on
 * the waiter stack when falling back.
 */
#include "mock_kernel.h"
#include "test_harness.h"

#define KD_EXE_RUN_ERROR 3
#define KD_EXE_RUN_TO_UNLOCK 4
#define MAX_KNOWN_CONTINUATIONS 16

enum call_kind {
	CALL_UNKNOWN,
	CALL_MUTEX_LOCK,
	CALL_MUTEX_UNLOCK,
	CALL_KTIME_GET,
};

struct regs_model {
	unsigned long ip;
	unsigned long di;
	unsigned long sp;
	unsigned long ax;
};

static unsigned long fake_stack[32];
static unsigned long mutex_lock_addr = 0x1000;
static unsigned long mutex_unlock_addr = 0x2000;
static unsigned long ktime_get_addr = 0x3000;
static unsigned long outer_mutex = 0xaaa0;
static unsigned long inner_mutex = 0xbbb0;
static int inner_locked;

static enum call_kind call_kind(unsigned long ip)
{
	if (ip == mutex_lock_addr)
		return CALL_MUTEX_LOCK;
	if (ip == mutex_unlock_addr)
		return CALL_MUTEX_UNLOCK;
	if (ip == ktime_get_addr)
		return CALL_KTIME_GET;
	return CALL_UNKNOWN;
}

static int advance_after_known_call(struct regs_model *regs)
{
	regs->ip = *(unsigned long *)regs->sp;
	regs->sp += sizeof(unsigned long);
	return 1;
}

static int handle_known_call(struct regs_model *regs)
{
	switch (call_kind(regs->ip)) {
	case CALL_MUTEX_LOCK:
		if (regs->di != inner_mutex || inner_locked)
			return 0;
		inner_locked = 1;
		return advance_after_known_call(regs);
	case CALL_MUTEX_UNLOCK:
		if (regs->di == outer_mutex)
			return KD_EXE_RUN_TO_UNLOCK;
		if (regs->di != inner_mutex || !inner_locked)
			return 0;
		inner_locked = 0;
		return advance_after_known_call(regs);
	case CALL_KTIME_GET:
		regs->ax = 1234;
		return advance_after_known_call(regs);
	default:
		return 0;
	}
}

static int simulate_call_miss(struct regs_model *regs)
{
	int ret = handle_known_call(regs);

	if (ret == KD_EXE_RUN_TO_UNLOCK)
		return KD_EXE_RUN_TO_UNLOCK;
	if (ret > 0)
		return 0;

	/* Unknown-call miss stubs must undo the simulated call push before
	 * returning to the kernel fallback path. */
	regs->sp += sizeof(unsigned long);
	return KD_EXE_RUN_ERROR;
}

static int simulate_known_continuation_loop(struct regs_model *regs)
{
	int continuation_count = 0;
	int ret;

	for (;;) {
		if (continuation_count >= MAX_KNOWN_CONTINUATIONS)
			return KD_EXE_RUN_ERROR;
		ret = handle_known_call(regs);
		if (ret != 1)
			return ret;
		continuation_count++;
	}
}

TEST(outer_unlock_completes) {
	struct regs_model regs = {
		.ip = mutex_unlock_addr,
		.di = outer_mutex,
		.sp = (unsigned long)&fake_stack[3],
	};

	ASSERT_EQ(simulate_call_miss(&regs), KD_EXE_RUN_TO_UNLOCK);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[3]);
}

TEST(inner_lock_and_unlock_continue) {
	struct regs_model regs = {
		.ip = mutex_lock_addr,
		.di = inner_mutex,
		.sp = (unsigned long)&fake_stack[3],
	};
	fake_stack[3] = 0x4444UL;
	inner_locked = 0;

	ASSERT_EQ(simulate_call_miss(&regs), 0);
	ASSERT_EQ(regs.ip, 0x4444UL);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[4]);
	ASSERT_EQ(inner_locked, 1);

	regs.ip = mutex_unlock_addr;
	regs.di = inner_mutex;
	regs.sp = (unsigned long)&fake_stack[2];
	fake_stack[2] = 0x5555UL;

	ASSERT_EQ(simulate_call_miss(&regs), 0);
	ASSERT_EQ(regs.ip, 0x5555UL);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[3]);
	ASSERT_EQ(inner_locked, 0);
}

TEST(api_call_continues) {
	struct regs_model regs = {
		.ip = ktime_get_addr,
		.di = 0,
		.sp = (unsigned long)&fake_stack[1],
	};
	fake_stack[1] = 0x6666UL;

	ASSERT_EQ(simulate_call_miss(&regs), 0);
	ASSERT_EQ(regs.ip, 0x6666UL);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[2]);
	ASSERT_EQ(regs.ax, 1234UL);
}

TEST(unknown_call_fallback_unwinds_stack) {
	struct regs_model regs = {
		.ip = 0xdead,
		.di = 0,
		.sp = (unsigned long)&fake_stack[2],
	};

	ASSERT_EQ(simulate_call_miss(&regs), KD_EXE_RUN_ERROR);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[3]);
}

TEST(known_continuation_is_bounded) {
	struct regs_model regs = {
		.ip = ktime_get_addr,
		.di = 0,
		.sp = (unsigned long)&fake_stack[0],
	};
	int i;

	for (i = 0; i < MAX_KNOWN_CONTINUATIONS + 1; i++)
		fake_stack[i] = ktime_get_addr;

	ASSERT_EQ(simulate_known_continuation_loop(&regs), KD_EXE_RUN_ERROR);
	ASSERT_EQ(regs.sp,
		  (unsigned long)&fake_stack[MAX_KNOWN_CONTINUATIONS]);
}

int main(void)
{
	printf("=== test_jit_call_policy ===\n");
	RUN_TEST(outer_unlock_completes);
	RUN_TEST(inner_lock_and_unlock_continue);
	RUN_TEST(api_call_continues);
	RUN_TEST(unknown_call_fallback_unwinds_stack);
	RUN_TEST(known_continuation_is_bounded);
	REPORT();
}
