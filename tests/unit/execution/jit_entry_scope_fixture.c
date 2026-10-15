/* SPDX-License-Identifier: GPL-2.0 */
/* Drive production entry/refusal and hostcall decisions with a wrapper double.
 * Keep full packets, real service policy and bounded continuation counters;
 * native service primitives and locks are substitutes, not kernel-JIT evidence. */
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef long long s64;
typedef unsigned long long u64;
typedef unsigned short u16;
typedef unsigned char u8;
typedef long long atomic64_t;
typedef int atomic_t;
#define S64_MAX LLONG_MAX
#define module_param_named(...)
#define MODULE_PARM_DESC(...)

/* Kernel asm/unaligned.h uses packed scalar loads. Keep this userspace
 * substitute independent of host alignment and byte order, reading four bytes. */
static unsigned int get_unaligned_le32(const void *address)
{
	const unsigned char *bytes = address;

	return (unsigned int)bytes[0] | (unsigned int)bytes[1] << 8 |
	       (unsigned int)bytes[2] << 16 | (unsigned int)bytes[3] << 24;
}

struct task_struct {
	int pid;
	void *stack;
};
struct list_head {
	struct list_head *next, *prev;
};
#define INIT_LIST_HEAD(head) do { (head)->next = (head)->prev = (head); } while (0)
typedef struct {
	int value;
} raw_spinlock_t;
#include "frame_types.h"

static unsigned long stack[16];
static struct task_struct executor = { .pid = 1 },
	waiter = { .pid = 2, .stack = stack }, stranger = { .pid = 3 };
static struct task_struct *current = &executor;
static struct kd_exec_frame active, parent;
static struct kd_exe_info entry_table[KD_MAX_EXE], *entry;
static int calls, known_calls, known_result, errors, warnings, checks, failures;
static unsigned int registry_lookups, readiness_acquires, current_frame_reads;
static bool source_open = true;
static struct kd_regs last_wrapper_output;
static unsigned long direct_mutex_lock_addr = 0x4130;
static unsigned long direct_mutex_unlock_addr = 0x4140;
static unsigned long owned_direct_lock_addr = 0x4150;
static unsigned long owned_direct_unlock_addr = 0x4160;
static unsigned long owned_cabi_lock_addr = 0x4170, owned_cabi_unlock_addr = 0x4180;
static unsigned long clobber_spin_lock_addr = 0x3110;
static unsigned long clobber_spin_unlock_addr = 0x3120;
static void kd_jit_clobber_call_v1(struct kd_jit_batch_call *call)
{
	(void)call;
	/* Real MINIMAL code belongs to test_clobber_abi. A readiness mutation
	 * can reach this forbidden boundary; report an assertion, not a signal. */
	fprintf(stderr, "FAIL line %d: unexpected clobber wrapper invocation\n",
		__LINE__);
	exit(1);
}
static char last_error[1024];
static unsigned int service_calls[3], failed_service_calls;
static const unsigned long service_values[] = {
	0x12345678, 0x98765432, 0x80000001UL,
};
static unsigned long scalar_argument;
/* Timing-only scenarios use services other than ktime_get_ns, allowing exact
 * observation of metric clock calls without conflating the typed service. */
static bool timing_clock_active;
static u64 timing_clock;
static unsigned int timing_reads;
/* Residency is substituted here; exercise the consumer's no-replay decision. */
static int source_error, source_calls, source_fail_at;
static unsigned long source_targets[2];
static int stack_error, stack_reads;
#define THREAD_SIZE sizeof(stack)
#define task_stack_page(task) ((task)->stack)

/* Model nofault reads, not arbitrary host dereferences. Production bounds
 * must reject foreign/out-of-stack words before this primitive is called. */
static int copy_from_kernel_nofault(void *to, const void *from, size_t size)
{
	unsigned long address = (unsigned long)from;

	stack_reads++;
	if (stack_error || size != sizeof(unsigned long) ||
	    address < (unsigned long)stack ||
	    address > (unsigned long)stack + sizeof(stack) - size)
		return -EFAULT;
	memcpy(to, from, size);
	return 0;
}
static bool kd_source_is_open(void)
{
	return source_open;
}
static int kd_source_pin_target(unsigned long address)
{
	if (source_calls < 2)
		source_targets[source_calls] = address;
	source_calls++;
	return !source_fail_at || source_fail_at == source_calls ? source_error : 0;
}
static int kd_jit_hl_fault_after_known_call;
static unsigned long kd_hostcall_exits, kd_hostcall_executed,
	kd_hostcall_resumed;
static unsigned long kd_hostcall_limit, kd_hostcall_rejected,
	kd_hostcall_failed;

#define READ_ONCE(x) (x)
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
/* Count the real status acquire separately from the frame-state reads. */
#define smp_load_acquire(p)                                                \
	({                                                                \
		if (entry && (const void *)(p) == &entry->status_code)      \
			readiness_acquires++;                            \
		__atomic_load_n((p), __ATOMIC_ACQUIRE);                    \
	})
#define smp_store_release(p, value) (*(p) = (value))
#define try_cmpxchg(p, old, value)                                          \
	__atomic_compare_exchange_n(p, old, value, false, __ATOMIC_SEQ_CST, \
				    __ATOMIC_SEQ_CST)
#define atomic64_inc(p) (++*(p))
#define atomic64_read(p) (*(p))
#define atomic64_set(p, v) (*(p) = (v))
#define atomic_set(p, v) (*(p) = (v))
#define atomic_read(p) (*(p))
#define atomic64_try_cmpxchg(p, old, v) try_cmpxchg(p, old, v)
#define unlikely(x) (x)
#define likely(x) (x)
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
#define pr_err_ratelimited(...)                                        \
	do {                                                           \
		errors++;                                              \
		snprintf(last_error, sizeof(last_error), __VA_ARGS__); \
	} while (0)

/* A detected mutant must stop before a later synthetic invalid-pointer case;
 * a crash is never accepted as invariant detection by the Python driver. */
#ifdef KD_ENTRY_MUTATION
#define STOP_MUTATION() exit(1)
#else
#define STOP_MUTATION() ((void)0)
#endif
#define CHECK(expr)                                                     \
	do {                                                            \
		checks++;                                               \
		if (!(expr)) {                                          \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, \
				#expr);                                 \
			failures++;                                     \
			STOP_MUTATION();                                \
		}                                                       \
	} while (0)

/* Native primitives are doubles; production adapters still choose the service
 * and transport its ABI. The scalar double records the full argument, not a
 * copied sqrt algorithm. Actual numeric results belong to the live workload. */
static long long ktime_get(void)
{
	service_calls[0]++;
	return service_values[0];
}
static long long ktime_to_ns(long long value)
{
	return value;
}
static unsigned long long ktime_get_ns(void)
{
	if (timing_clock_active) {
		timing_reads++;
		return timing_clock++ * 10;
	}
	service_calls[1]++;
	return service_values[1];
}
static unsigned long int_sqrt(unsigned long argument)
{
	service_calls[2]++;
	scalar_argument = argument;
	return service_values[2];
}
static int failing_service(struct kd_regs *regs)
{
	(void)regs;
	failed_service_calls++;
	return -EIO;
}

struct step {
	unsigned long reason, ip, witness;
	long sp_delta;
};
static struct step steps[KD_EXE_HL_MAX_CONTINUATIONS + KD_EXE_HL_MAX_HOSTCALLS + 3];

static void translated(struct kd_regs *regs, unsigned long *args)
{
	struct step *step;

	/* Budget mutants must end with a reported assertion, not an out-of-bounds
	 * script read or an unbounded fake wrapper loop. */
	CHECK((unsigned int)calls < ARRAY_SIZE(steps));
	if ((unsigned int)calls >= ARRAY_SIZE(steps)) {
		args[0] = KD_EXE_ERROR_INST;
		args[1] = 0;
		return;
	}
	step = &steps[calls++];

	/* A test double reports boundary packets only. The separate machine-code
	 * suite verifies that a real failed predicate preserves the whole packet. */
	CHECK(args[0] == active.gsbase &&
	      args[1] == (unsigned long)active.logical_task);
	if (step->ip)
		regs->ip = step->ip;
	regs->sp += step->sp_delta;
	args[0] = step->reason;
	args[1] = step->witness;
	CHECK(!regs->sp || (regs->sp >= (unsigned long)stack &&
			   regs->sp <= (unsigned long)&stack[ARRAY_SIZE(stack) - 1]));
	if (regs->sp && (regs->sp < (unsigned long)stack ||
			regs->sp > (unsigned long)&stack[ARRAY_SIZE(stack) - 1]))
		args[0] = KD_EXE_ERROR_INST;
	last_wrapper_output = *regs;
}

struct kd_exec_frame *kd_exec_current_frame(void)
{
	current_frame_reads++;
	return &active;
}
/* Retain Kbuild's comparison policy for the unmodified lookup functions. A
 * real empty/full/unready registry must stop before invoking the wrapper. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#include "registry_lookup.h"
#include "hostcall_code.h"
#include "timing_code.h"
#pragma GCC diagnostic pop
/* Owned descriptor and claim races execute in test_owned_images. This fixture
 * covers legacy generic/ACK routes; an unexpected owned lookup must refuse. */
const struct kd_jit_image *kd_image_current(const struct kd_exe_info *exe)
{
	(void)exe;
	CHECK(false);
	return NULL;
}
void kd_image_report(struct kd_exe_info *exe, const struct kd_jit_image *image,
		     int status, unsigned long target, unsigned long from)
{
	CHECK(!image);
	exe->tgt_addr = target;
	exe->jump_from = from;
	kd_exe_publish_status(exe, status);
}
#define preempt_count() 1
#define raw_smp_processor_id() 0
static bool is_end_point(unsigned long ip)
{
	return ip == 0x9000;
}
static bool is_outer_lock_unlock(struct kd_regs *regs, unsigned long lock)
{
	return is_end_point(regs->ip) && regs->di == lock;
}
static int advance_and_save_continuation(struct kd_exec_frame *frame,
					 struct kd_regs *regs);
static int handle_known_call(struct kd_regs *regs, unsigned long outer)
{
	known_calls++;
	if (is_outer_lock_unlock(regs, outer))
		return KD_EXE_KNOWN_OUTER_UNLOCK;
	if (known_result == 1) {
		/* The production control handler leaves a completed prior CALL;
		 * quota recovery must not treat that tag as the new pending CALL. */
		active.control_call.phase = KD_CALL_COMPLETE;
		return advance_and_save_continuation(&active, regs);
	}
	return known_result;
}
static unsigned int complex_preparations;
static unsigned long raw_spin_unlock_addr = 0x9000;
/* CPU combiner storage belongs to the backend fixture. Observe its transition
 * here; all wrapper classification and continuation decisions are production. */
void kd_spin_jit_prepare_complex(struct kd_exec_frame *frame)
{
	CHECK(frame->spin_simple && !frame->mutex_backend);
	complex_preparations++;
	kd_exec_frame_own_regs(frame);
	frame->spin_simple = false;
}
#include "frame_code.h"

/* Keep independent entry, service, timing and backend cases together by purpose. */
#include "jit_entry_scope/reset.inc"
#include "jit_entry_scope/entry.inc"
#include "jit_entry_scope/hostcalls.inc"
#include "jit_entry_scope/timing.inc"
#include "jit_entry_scope/spin.inc"
#include "jit_entry_scope/mutex.inc"

int main(void)
{
	check_mutex_batch();
	check_batch_admission();
	check_batch_metadata();
	check_batch_completion_timings();
	check_clobber_identity();
	check_pending_batch_exit();
	check_simple_spin();
	check_pristine_refusal();
	check_local_continuation();
	check_remote_scope();
	check_registry_refusal();
	check_cached_entry();
	check_source_target_refusal();
	check_service_dispatch();
	check_scalar_arguments();
	check_service_returns();
	check_service_errors();
	check_shared_budget();
	check_quota_packets();
	check_timing_boundaries();
	check_queue_timings();
	check_native_handoff_timings();
	printf("production JIT entry scope: %d checks, %d failures\n", checks,
	       failures);
	return failures != 0;
}
