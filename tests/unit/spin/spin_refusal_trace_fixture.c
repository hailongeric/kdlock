// SPDX-License-Identifier: GPL-2.0
/* Extracted SELFTEST observer only, with deterministic CPU/lock/frame inputs. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#define noinline __attribute__((noinline))
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, y) ((x) = (y))
#define pr_info(...) ((void)printf(__VA_ARGS__))
#define ATOMIC_INIT(x) (x)
#define KD_SPIN_CONT_ROOT 0
#define KD_SPIN_CONT_VIRTUAL 1
#define KD_SPIN_RES_RETRY 1
#define KD_SPIN_RES_NATIVE_READY 2
#define KD_EXE_NO_RUN 2
#define KD_EXE_RUN_ERROR 3
#define KD_EXE_RUN_TO_UNLOCK 4
#define KD_EXEC_REMOTE_IDLE 0
#define KD_EXEC_REMOTE_WAITING 1
#define KD_EXEC_REMOTE_DONE 3
#define KD_CALL_ENTERED 2
#define KD_EXEC_MAX_LOCK_DEPTH 8
#define NUMA_AWARE
#define this_cpu_ptr(p) (p)

typedef int atomic_t;
typedef struct {
	bool held;
	unsigned long owner;
} raw_spinlock_t;
#include "../../../include/kd_regs.h"
struct task_struct {
	int pid;
};
struct kd_exec_frame {
	struct kd_exec_frame *resume_target;
	struct kd_regs regs;
	struct kd_regs *regs_ref;
	struct task_struct *logical_task;
	unsigned long entry_ip, outer_lock_addr, gsbase;
	int logical_pid, remote_result;
	unsigned int jit_lock_depth;
	unsigned long jit_lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	bool jit_lock_released[KD_EXEC_MAX_LOCK_DEPTH];
	struct {
		int phase;
	} control_call;
	bool executed, valid;
	unsigned char spin_kind;
};
/* Stable request owns the packet; the reusable queue node only references it. */
struct kd_spin_request {
    struct kd_exec_frame frame;
    int result;
};
static struct kd_regs *kd_exec_frame_regs(const struct kd_exec_frame *frame)
{
    return frame->regs_ref ? frame->regs_ref : (struct kd_regs *)&frame->regs;
}
struct kd_spin_node {
    struct kd_spin_request *execution;
	bool completed;
};
static struct {
	struct kd_spin_node *local_queue_head, *local_queue_tail;
} kd_spin_cpu;
static struct task_struct tasks[3];
static struct task_struct *current;
static unsigned int cpu;
static unsigned int raw_smp_processor_id(void)
{
	return cpu;
}
static int atomic_read(const atomic_t *p)
{
	return *p;
}
static int atomic_cmpxchg(atomic_t *p, int old, int value)
{
	int before = *p;
	if (before == old)
		*p = value;
	return before;
}
static bool kd_exec_frame_validate(const struct kd_exec_frame *p)
{
	return p->valid;
}
static bool raw_spin_is_locked(const raw_spinlock_t *p)
{
	return p->held;
}
static unsigned long kd_spin_debug_owner(const raw_spinlock_t *p)
{
	return p->owner;
}

#include "refusal_observer.h"

static void test_readmit(void)
{
	unsigned int count, fault;

	for (count = 1; count <= 2; count++) {
		for (fault = 0; fault < 8; fault++) {
			raw_spinlock_t a = { .held = true },
				       b = { .held = true };
			struct kd_exec_frame parent = {
				.regs = { .ip = 0x1000,
					  .sp = 0x2000,
					  .r15 = 0x1234 },
				.logical_task = &tasks[0],
				.gsbase = 0x8000,
				.outer_lock_addr = (unsigned long)&a,
				.logical_pid = 1,
				.remote_result = KD_EXEC_REMOTE_WAITING,
				.control_call.phase = KD_CALL_ENTERED,
				.executed = true,
				.valid = true,
			};
			struct kd_exec_frame child = parent;
			struct kd_spin_request request = { .frame = { .regs = parent.regs, .regs_ref = &request.frame.regs, .spin_kind = KD_SPIN_CONT_VIRTUAL } };
			struct kd_spin_node node = { .execution = &request };
			int ret = -1;
			request.frame.regs_ref = &request.frame.regs;
			memset(&kd_readmit, 0, sizeof(kd_readmit));
			kd_readmit_refusals = count;
			kd_readmit_lock = (unsigned long)&b;
			child.outer_lock_addr = (unsigned long)&b;
			request.frame.outer_lock_addr = child.outer_lock_addr;
			child.entry_ip = 0x9000;
			child.executed = false;
			child.resume_target = &parent;
			current = &tasks[1];
			cpu = 1;
			kd_spin_cpu.local_queue_head = &node;
			kd_spin_cpu.local_queue_tail = &node;
			assert(kd_spin_selftest_refuse(&child, &node, &ret));
			assert(ret == KD_EXE_NO_RUN && kd_readmit.initial[0]);
			kd_spin_selftest_refusal_end(&child, ret);
			child.resume_target = NULL;
			kd_spin_selftest_refusal_cancel(&child);
			assert(kd_readmit.cancel_valid[0]);
			child.resume_target = &parent;
			current = &tasks[2];
			cpu = 2;
			kd_spin_cpu.local_queue_head = NULL;
			kd_spin_cpu.local_queue_tail = NULL;
			if (fault == 1)
				parent.regs.ss ^= 1;
			if (fault == 2)
				request.frame.regs.flags ^= 1;
			if (fault == 3)
				child.gsbase ^= 1;
			assert(kd_spin_selftest_refuse(&child, &node, &ret) ==
			       (count == 2));
			assert(kd_readmit.initial[1] ==
			       !(fault >= 1 && fault <= 3));
			if (fault == 1)
				parent.regs.ss ^= 1;
			if (fault == 2)
				request.frame.regs.flags ^= 1;
			if (fault == 3)
				child.gsbase ^= 1;
			child.executed = count == 1;
			kd_spin_selftest_refusal_end(
				&child, count == 2 ? KD_EXE_NO_RUN :
						     KD_EXE_RUN_TO_UNLOCK);
			child.resume_target = NULL;
			kd_spin_selftest_refusal_cancel(&child);
			assert(kd_readmit.cancelled == count);
			current = &tasks[0];
			cpu = 0;
			b.owner = (unsigned long)current;
			node.completed = count == 1;
			parent.remote_result = count == 2 ?
						       KD_EXEC_REMOTE_WAITING :
						       KD_EXEC_REMOTE_DONE;
			if (fault == 4)
				node.completed = !node.completed;
			if (fault == 5)
				parent.remote_result = KD_EXEC_REMOTE_IDLE;
			ret = fault == 6 ? 4 : count == 2 ? 2 : 3;
			kd_spin_selftest_refusal_return(&parent, &node, ret);
			assert(kd_readmit.return_valid ==
			       !(fault >= 4 && fault <= 6));
			parent.remote_result = count == 2 ?
						       KD_EXEC_REMOTE_IDLE :
						       KD_EXEC_REMOTE_DONE;
			if (fault == 7)
				parent.gsbase ^= 1;
			kd_spin_selftest_refusal_end(&parent,
						     KD_EXE_RUN_TO_UNLOCK);
			assert(kd_readmit.end_valid == (fault != 7));
			kd_spin_selftest_readmit_report();
		}
	}
	kd_readmit_refusals = 0;
	puts("readmission observer: two outcomes and seven independent corruptions PASS");
}

static void test_readmit_follow(void)
{
	unsigned int depth, fault;

	for (depth = 2; depth <= 3; depth++) {
		for (fault = 0; fault <= 9; fault++) {
			raw_spinlock_t a = {
				.held = true, .owner = (unsigned long)&tasks[0]
			};
			raw_spinlock_t b = a, c = a;
			struct kd_exec_frame parent = {
				.outer_lock_addr = (unsigned long)&a,
				.logical_task = &tasks[0],
				.logical_pid = 1,
				.gsbase = 0x8000,
				.executed = true,
				.valid = true,
				.remote_result = KD_EXEC_REMOTE_WAITING,
				.control_call.phase = KD_CALL_ENTERED,
				.jit_lock_depth = depth,
			};
			struct kd_exec_frame child = parent;
			struct kd_spin_request request = { .frame = { .regs = parent.regs, .regs_ref = &request.frame.regs, .spin_kind = KD_SPIN_CONT_VIRTUAL } };
			struct kd_spin_node node = { .execution = &request };
			int ret = -1;
			request.frame.regs_ref = &request.frame.regs;
			parent.jit_lock_addr[depth - 1] = (unsigned long)&b;
			child.resume_target = &parent;
			child.outer_lock_addr = (unsigned long)&c;
			request.frame.outer_lock_addr = child.outer_lock_addr;
			child.executed = false;
			child.regs.ip = 0x3000;
			child.regs.sp = 0x4000;
			memset(&kd_readmit, 0, sizeof(kd_readmit));
			kd_readmit_refusals = 2;
			kd_readmit_lock = (unsigned long)&b;
			kd_readmit.parent = &parent;
			kd_readmit.returned = kd_readmit.return_valid = 1;
			kd_readmit.lock = (unsigned long)&b;
			kd_readmit.outer = (unsigned long)&a;
			kd_readmit.pid = 1;
			kd_readmit.gs = 0x8000;
			kd_readmit.task = kd_readmit.return_owner =
				(unsigned long)&tasks[0];
			kd_readmit.return_cpu = 0;
			current = &tasks[2];
			cpu = 2;
			if (fault == 1)
				parent.jit_lock_depth = 0;
			if (fault == 2)
				parent.jit_lock_addr[depth - 1] =
					(unsigned long)&a;
			if (fault == 3)
				parent.jit_lock_released[depth - 1] = true;
			if (fault == 4)
				b.owner = (unsigned long)current;
			if (fault == 5)
				a.owner = (unsigned long)current;
			if (fault == 6)
				child.gsbase ^= 1;
			if (fault == 7)
				parent.remote_result = KD_EXEC_REMOTE_IDLE;
			if (fault == 8)
				b.held = false;
			if (fault == 9)
				child.logical_task = current;
			assert(!kd_spin_selftest_readmit_attempt(&child, &node,
								 &ret));
			assert(ret == -1 && kd_readmit.followed == 1);
			assert(kd_readmit.follow_valid == !fault);
			assert(kd_readmit.follow_ip == child.regs.ip &&
			       kd_readmit.follow_sp == child.regs.sp);
			current = &tasks[0];
			cpu = 0;
			parent.remote_result = KD_EXEC_REMOTE_IDLE;
			kd_spin_selftest_readmit_end(&parent,
						     KD_EXE_RUN_TO_UNLOCK);
			assert(!kd_readmit.end_valid);
			parent.remote_result = KD_EXEC_REMOTE_DONE;
			kd_spin_selftest_readmit_end(&parent,
						     KD_EXE_RUN_TO_UNLOCK);
			assert(kd_readmit.end_valid);
		}
	}
	puts("middle readmission follow: two ledger depths and nine independent corruptions PASS");
	memset(&kd_readmit, 0, sizeof(kd_readmit));
	kd_readmit_refusals = 0;
}

int main(void)
{
	unsigned int kind, rejected;
	for (kind = 1; kind <= 2; kind++) {
		for (rejected = 0; rejected < 7; rejected++) {
			raw_spinlock_t a = { .held = true },
				       b = { .held = true };
			struct kd_exec_frame parent = {
				.regs = { .ip = 0x1000,
					  .sp = 0x2000,
					  .r15 = 0x1234 },
				.logical_task = &tasks[0],
				.gsbase = 0x8000,
				.outer_lock_addr = (unsigned long)&a,
				.logical_pid = 1,
				.remote_result = KD_EXEC_REMOTE_WAITING,
				.control_call.phase = KD_CALL_ENTERED,
				.executed = true,
				.valid = true,
			};
			struct kd_exec_frame child = parent;
			struct kd_spin_request request = { .frame = { .regs = parent.regs, .regs_ref = &request.frame.regs, .spin_kind = KD_SPIN_CONT_VIRTUAL } };
			struct kd_spin_node node = { .execution = &request };
			int ret = -1;
			request.frame.regs_ref = &request.frame.regs;
			memset(&kd_refusal, 0, sizeof(kd_refusal));
			kd_refusal_claimed = 0;
			kd_refusal_kind = kind;
			kd_refusal_lock = (unsigned long)&b;
			child.outer_lock_addr = (unsigned long)&b;
			request.frame.outer_lock_addr = child.outer_lock_addr;
			child.entry_ip = 0x9000;
			child.executed = false;
			child.resume_target = &parent;
			current = &tasks[1];
			cpu = 1;
			if (rejected == 1)
				kd_refusal_kind = 0;
			if (rejected == 2)
				kd_refusal_kind = 3;
			if (rejected == 3)
				request.frame.spin_kind = KD_SPIN_CONT_ROOT;
			if (rejected == 4)
				kd_refusal_lock = (unsigned long)&a;
			if (rejected == 5)
				child.executed = true;
			if (rejected == 6)
				parent.executed = false;
			assert(kd_spin_selftest_refuse(&child, &node, &ret) ==
			       !rejected);
			assert(kd_refusal_claimed == !rejected);
			if (rejected) {
				assert(ret == -1);
				continue;
			}
			assert(ret == (int)kind + 1 && kd_refusal.initial);
			assert(!kd_spin_selftest_refuse(&child, &node, &ret));
			child.resume_target = NULL;
			kd_spin_selftest_refusal_cancel(&child);
			assert(kd_refusal.cancelled == 1 &&
			       kd_refusal.cancel_valid);
			parent.remote_result = KD_EXEC_REMOTE_IDLE;
			kd_spin_selftest_refusal_cancel(&child);
			assert(!kd_refusal.cancel_valid);
			parent.remote_result = KD_EXEC_REMOTE_WAITING;
			parent.regs.ss ^= 1;
			kd_spin_selftest_refusal_cancel(&child);
			assert(!kd_refusal.cancel_valid);
			parent.regs.ss ^= 1;
			current = &tasks[2];
			cpu = 2;
			b.owner = (unsigned long)current;
			kd_spin_selftest_refusal_return(&parent, &node, 2);
			assert(kd_refusal.acquired == 1 &&
			       kd_refusal.acquire_valid);
			kd_spin_selftest_refusal_return(&parent, &node, 4);
			assert(!kd_refusal.acquire_valid);
			request.frame.regs.flags ^= 1;
			kd_spin_selftest_refusal_return(&parent, &node, 2);
			assert(!kd_refusal.acquire_valid);
			request.frame.regs.flags ^= 1;
			kd_refusal.acquired = 1;
			parent.remote_result = KD_EXEC_REMOTE_IDLE;
			kd_spin_selftest_refusal_end(&parent,
						     KD_EXE_RUN_TO_UNLOCK);
			assert(kd_refusal.finished == 1 &&
			       kd_refusal.end_valid);
			kd_refusal.finished = 0;
			kd_spin_selftest_refusal_end(&parent, KD_EXE_RUN_ERROR);
			assert(!kd_refusal.end_valid);
			kd_spin_selftest_refusal_report();
		}
	}
	test_readmit();
	test_readmit_follow();
	puts("refusal observer guards, full storage comparisons and return/end checks: PASS");
	return 0;
}
