/* SPDX-License-Identifier: GPL-2.0 */
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

struct task_struct {
	int pid;
};
struct list_head {
	struct list_head *next, *prev;
};
typedef struct {
	int value;
} raw_spinlock_t;
#include "frame_types.h"

static struct task_struct executor = { 1 }, waiter = { 2 }, stranger = { 3 };
static struct task_struct *current = &executor;
static struct kd_exec_frame active, parent;
static struct kd_exe_info entry;
static unsigned long stack[16];
static int calls, known_calls, known_result, errors, warnings, checks, failures;
static int kd_jit_hl_fault_after_known_call;
static bool ready;
static unsigned long kd_hostcall_exits, kd_hostcall_executed,
	kd_hostcall_resumed;
static unsigned long kd_hostcall_limit, kd_hostcall_rejected,
	kd_hostcall_failed;

#define READ_ONCE(x) (x)
#define smp_load_acquire(p) (*(p))
#define atomic64_inc(p) (++*(p))
#define unlikely(x) (x)
#define mb() ((void)0)
#define xchg(p, value)                       \
	({                                   \
		__typeof__(*(p)) old = *(p); \
		*(p) = (value);              \
		old;                         \
	})
#define KD_PR_INFO(...)                      \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
#define pr_warn_ratelimited(...)         \
	do {                             \
		warnings++;              \
		KD_PR_INFO(__VA_ARGS__); \
	} while (0)
#define pr_err_ratelimited(...)          \
	do {                             \
		errors++;                \
		KD_PR_INFO(__VA_ARGS__); \
	} while (0)

struct step {
	unsigned long reason, ip, witness;
	long sp_delta;
};
static struct step steps[3];

static void translated(struct pt_regs *regs, unsigned long *args)
{
	struct step *step = &steps[calls++];

	/* A test double reports boundary packets only. The separate machine-code
	 * suite verifies that a real failed predicate preserves the whole packet. */
	if (args[0] != active.gsbase ||
	    args[1] != (unsigned long)active.logical_task)
		failures++;
	if (step->ip)
		regs->ip = step->ip;
	regs->sp += step->sp_delta;
	args[0] = step->reason;
	args[1] = step->witness;
}

struct kd_exec_frame *kd_exec_current_frame(void)
{
	return &active;
}
static struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip)
{
	(void)pid;
	return ip == entry.RIP ? &entry : NULL;
}
static bool kd_exe_is_ready(unsigned int pid, unsigned long ip)
{
	(void)pid;
	(void)ip;
	return ready;
}
static bool kd_exe_publish_status(struct kd_exe_info *exe, int status)
{
	exe->status_code = status;
	return true;
}
static bool is_end_point(unsigned long ip)
{
	return ip == 0x9000;
}
static bool is_outer_lock_unlock(struct pt_regs *regs, unsigned long lock)
{
	return is_end_point(regs->ip) && regs->di == lock;
}
static int advance_and_save_continuation(struct kd_exec_frame *frame,
					 struct pt_regs *regs)
{
	regs->ip = *(unsigned long *)regs->sp;
	regs->sp += sizeof(unsigned long);
	frame->continuation_ip = regs->ip;
	frame->continuation_sp = regs->sp;
	return 1;
}
static int handle_known_call(struct pt_regs *regs, unsigned long outer)
{
	known_calls++;
	if (is_outer_lock_unlock(regs, outer))
		return KD_EXE_KNOWN_OUTER_UNLOCK;
	if (known_result == 1)
		return advance_and_save_continuation(&active, regs);
	return known_result;
}
static int kd_hostcall_dispatch(struct pt_regs *regs)
{
	(void)regs;
	return 0;
}

#include "frame_code.h"

#define CHECK(expr)                                                     \
	do {                                                            \
		checks++;                                               \
		if (!(expr)) {                                          \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, \
				#expr);                                 \
			failures++;                                     \
		}                                                       \
	} while (0)

static void reset(void)
{
	active = (struct kd_exec_frame){
		.entry_ip = 0x1000,
		.outer_lock_addr = 0x8000,
		.gsbase = 0xFEED,
		.logical_task = &waiter,
		.jit_lock_addr = { 0x8000 },
		.jit_lock_kind = { KD_EXEC_LOCK_QUEUE_OWNER },
		.jit_lock_depth = 1,
		.held_lock_depth = 1,
		.outer_lock_depth = 1,
		.outer_lock_index = 0,
		.state = KD_EXEC_FRAME_RUNNING,
	};
	active.regs.ip = active.entry_ip;
	active.regs.sp = (unsigned long)&stack[9];
	active.regs.di = active.outer_lock_addr;
	stack[8] = 0x1005;
	memset(steps, 0, sizeof(steps));
	entry = (struct kd_exe_info){ .RIP = active.entry_ip,
				      .lock_kind = KD_EXE_LOCK_SPIN,
				      .code_block = translated,
				      .status_code = KD_EXE_NORMAL };
	calls = known_calls = errors = warnings =
		kd_jit_hl_fault_after_known_call = 0;
	known_result = 1;
	ready = true;
}

static int run(void)
{
	return kd_exe_on_call_hl_entry(&active.regs, active.entry_ip,
				       active.outer_lock_addr);
}

static void check_pristine_refusal(void)
{
	struct pt_regs before;

	reset();
	before = active.regs;
	steps[0].reason = KD_EXE_ENTRY_REFUSED;
	CHECK(run() == KD_EXE_NO_RUN);
	CHECK(calls == 1 && !active.executed && !known_calls);
	CHECK(memcmp(&before, &active.regs, sizeof(before)) == 0);
	CHECK(warnings == 1 && !errors && entry.status_code == KD_EXE_NORMAL);
	for (int bad = 0; bad < 4; bad++) {
		reset();
		steps[0].reason = KD_EXE_ENTRY_REFUSED;
		if (bad == 0)
			steps[0].witness = 1;
		if (bad == 1)
			steps[0].sp_delta = 8;
		if (bad == 2)
			steps[0].ip = 0x1001;
		if (bad == 3)
			steps[0].reason = KD_EXE_INST_LIMIT;
		CHECK(run() == KD_EXE_RUN_ERROR);
		CHECK(calls == 1 && active.executed && errors == 1);
	}
}

static void check_local_continuation(void)
{
	for (int witness = 0; witness <= 1; witness++) {
		reset();
		steps[0] =
			(struct step){ KD_EXE_CALL_MISS, 0x2000, witness, -8 };
		steps[1] = (struct step){ KD_EXE_ENTRY_REFUSED, 0x1000, 0, 0 };
		CHECK(run() == KD_EXE_RUN_ERROR);
		CHECK(active.executed && calls == 2 && known_calls == 1 &&
		      errors == 1);
		reset();
		steps[0] =
			(struct step){ KD_EXE_CALL_MISS, 0x2000, witness, -8 };
		steps[1] =
			(struct step){ KD_EXE_CALL_MISS, 0x9000, witness, 0 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		CHECK(active.executed && calls == 2 && known_calls == 2 &&
		      !errors);
	}
}

static void remote(void)
{
	reset();
	parent = active;
	active.regs.ip = 0x1005;
	active.outer_lock_addr = active.regs.di = 0x8100;
	active.outer_lock_index = 1;
	active.jit_lock_depth = active.held_lock_depth =
		active.outer_lock_depth = 2;
	active.jit_lock_addr[1] = 0x8100;
	active.jit_lock_kind[1] = KD_EXEC_LOCK_QUEUE_OWNER;
	active.resume_target = &parent;
	parent.regs = active.regs;
	parent.executed = true;
	parent.remote_result = KD_EXEC_REMOTE_WAITING;
	parent.control_call.phase = KD_CALL_ENTERED;
	parent.control_call.return_ip = active.regs.ip;
	parent.control_call.stack = active.regs.sp - 8;
}

static void check_remote_scope(void)
{
	struct kd_exec_frame before;

	remote();
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(active.executed && calls == 1 && !errors);
	remote();
	steps[0].reason = KD_EXE_ENTRY_REFUSED;
	CHECK(run() == KD_EXE_RUN_ERROR);
	CHECK(active.executed && calls == 1 && errors == 1);
	for (int bad = 0; bad < 14; bad++) {
		remote();
		switch (bad) {
		case 0:
			parent.executed = false;
			break;
		case 1:
			parent.entry_ip++;
			break;
		case 2:
			parent.gsbase++;
			break;
		case 3:
			parent.logical_task = &stranger;
			break;
		case 4:
			parent.control_call.phase = KD_CALL_PENDING;
			break;
		case 5:
			parent.remote_result = KD_EXEC_REMOTE_DONE;
			break;
		case 6:
			parent.control_call.return_ip++;
			break;
		case 7:
			parent.control_call.stack++;
			break;
		case 8:
			parent.regs.di++;
			break;
		case 9:
			active.parent = &parent;
			active.resume_target = NULL;
			break;
		case 10:
			parent.regs.sp++;
			break;
		case 11:
			parent.mutex_backend = true;
			break;
		case 12:
			parent.state = KD_EXEC_FRAME_ERROR;
			break;
		case 13:
			active.state = KD_EXEC_FRAME_ERROR;
			break;
		}
		before = parent;
		CHECK(run() == KD_EXE_NO_RUN);
		CHECK(!calls && !active.executed && errors == 1);
		CHECK(memcmp(&parent, &before, sizeof(parent)) == 0);
	}
}

int main(void)
{
	check_pristine_refusal();
	check_local_continuation();
	check_remote_scope();
	printf("production JIT entry scope: %d checks, %d failures\n", checks,
	       failures);
	return failures != 0;
}
