/*
 * test_jit_call_policy.c — userspace model for JIT call and hostcall policy.
 *
 * The real kernel path handles these decisions in kd_exe_on_call_hl_entry().
 * This test keeps the high-risk rule explicit: only the outer mutex unlock
 * completes a delegated critical section; allowlisted hostcalls advance to the
 * saved return address through a separate exit path; unknown calls preserve
 * the CALL frame so the original waiter can continue at the native callee.
 */
#include "mock_kernel.h"
#include "test_harness.h"
#include "../../include/exe_info.h"

#define KD_EXE_RUN_ERROR 3
#define KD_EXE_RUN_TO_UNLOCK 4
#define KD_EXE_RUN_NATIVE 6
#define MAX_KNOWN_CONTINUATIONS 16

enum call_kind {
	CALL_UNKNOWN,
	CALL_MUTEX_LOCK,
	CALL_MUTEX_UNLOCK,
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
static bool inner_remote;

static enum call_kind call_kind(unsigned long ip)
{
	if (ip == mutex_lock_addr)
		return CALL_MUTEX_LOCK;
	if (ip == mutex_unlock_addr)
		return CALL_MUTEX_UNLOCK;
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
		if (inner_remote) {
			/* A B combiner ran through mutex_unlock(B), so the parent A
			 * frame resumes at the instruction after that unlock. */
			regs->ip = 0x7777UL;
			regs->sp = (unsigned long)&fake_stack[7];
			return 1;
		}
		inner_locked = 1;
		return advance_after_known_call(regs);
	case CALL_MUTEX_UNLOCK:
		if (regs->di == outer_mutex)
			return KD_EXE_RUN_TO_UNLOCK;
		if (regs->di != inner_mutex || !inner_locked)
			return 0;
		inner_locked = 0;
		return advance_after_known_call(regs);
	default:
		return 0;
	}
}

static int dispatch_hostcall(struct regs_model *regs)
{
	if (regs->ip != ktime_get_addr)
		return KD_EXE_RUN_ERROR;
	regs->ax = 1234;
	return advance_after_known_call(regs);
}

static int simulate_call_miss(struct regs_model *regs)
{
	int ret = handle_known_call(regs);

	if (ret == KD_EXE_RUN_TO_UNLOCK)
		return KD_EXE_RUN_TO_UNLOCK;
	if (ret > 0)
		return 0;

	return KD_EXE_RUN_NATIVE;
}

static int simulate_hostcall_continuation_loop(struct regs_model *regs)
{
	int hostcall_count = 0;
	int ret;

	for (;;) {
		if (hostcall_count >= MAX_KNOWN_CONTINUATIONS)
			return KD_EXE_RUN_ERROR;
		ret = dispatch_hostcall(regs);
		if (ret != 1)
			return ret;
		hostcall_count++;
	}
}

TEST(outer_unlock_completes)
{
	struct regs_model regs = {
		.ip = mutex_unlock_addr,
		.di = outer_mutex,
		.sp = (unsigned long)&fake_stack[3],
	};

	ASSERT_EQ(simulate_call_miss(&regs), KD_EXE_RUN_TO_UNLOCK);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[3]);
}

TEST(inner_lock_and_unlock_continue)
{
	struct regs_model regs = {
		.ip = mutex_lock_addr,
		.di = inner_mutex,
		.sp = (unsigned long)&fake_stack[3],
	};
	fake_stack[3] = 0x4444UL;
	inner_locked = 0;
	inner_remote = false;

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

TEST(contended_inner_lock_resumes_after_remote_unlock)
{
	struct regs_model regs = {
		.ip = mutex_lock_addr,
		.di = inner_mutex,
		.sp = (unsigned long)&fake_stack[3],
	};

	inner_locked = 0;
	inner_remote = true;
	ASSERT_EQ(simulate_call_miss(&regs), 0);
	ASSERT_EQ(regs.ip, 0x7777UL);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[7]);
	ASSERT_EQ(inner_locked, 0);
	inner_remote = false;
}

TEST(api_hostcall_continues)
{
	struct regs_model regs = {
		.ip = ktime_get_addr,
		.di = 0,
		.sp = (unsigned long)&fake_stack[1],
	};
	fake_stack[1] = 0x6666UL;

	ASSERT_NE(KD_EXE_HOSTCALL, KD_EXE_CALL_MISS);
	ASSERT_EQ(dispatch_hostcall(&regs), 1);
	ASSERT_EQ(regs.ip, 0x6666UL);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[2]);
	ASSERT_EQ(regs.ax, 1234UL);
}

TEST(unknown_hostcall_is_rejected_without_stack_change)
{
	struct regs_model regs = {
		.ip = 0xdead,
		.di = 0,
		.sp = (unsigned long)&fake_stack[2],
	};

	ASSERT_EQ(dispatch_hostcall(&regs), KD_EXE_RUN_ERROR);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[2]);
}

TEST(unknown_call_preserves_native_continuation)
{
	struct regs_model regs = {
		.ip = 0xdead,
		.di = 0,
		.sp = (unsigned long)&fake_stack[2],
	};

	fake_stack[2] = 0xbeef;
	ASSERT_EQ(simulate_call_miss(&regs), KD_EXE_RUN_NATIVE);
	ASSERT_EQ(regs.ip, 0xdeadUL);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[2]);
	ASSERT_EQ(*(unsigned long *)regs.sp, 0xbeefUL);
}

TEST(hostcall_continuation_is_bounded)
{
	struct regs_model regs = {
		.ip = ktime_get_addr,
		.di = 0,
		.sp = (unsigned long)&fake_stack[0],
	};
	int i;

	for (i = 0; i < MAX_KNOWN_CONTINUATIONS + 1; i++)
		fake_stack[i] = ktime_get_addr;

	ASSERT_EQ(simulate_hostcall_continuation_loop(&regs), KD_EXE_RUN_ERROR);
	ASSERT_EQ(regs.sp, (unsigned long)&fake_stack[MAX_KNOWN_CONTINUATIONS]);
}

int main(void)
{
	printf("=== test_jit_call_policy ===\n");
	RUN_TEST(outer_unlock_completes);
	RUN_TEST(inner_lock_and_unlock_continue);
	RUN_TEST(contended_inner_lock_resumes_after_remote_unlock);
	RUN_TEST(api_hostcall_continues);
	RUN_TEST(unknown_hostcall_is_rejected_without_stack_change);
	RUN_TEST(unknown_call_preserves_native_continuation);
	RUN_TEST(hostcall_continuation_is_bounded);
	REPORT();
}
