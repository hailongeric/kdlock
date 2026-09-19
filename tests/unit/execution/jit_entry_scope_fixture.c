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
typedef long long atomic64_t;
typedef int atomic_t;
#define S64_MAX LLONG_MAX
#define module_param_named(...)
#define MODULE_PARM_DESC(...)

struct task_struct {
	int pid;
	void *stack;
};
struct list_head {
	struct list_head *next, *prev;
};
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
static unsigned int registry_lookups, readiness_acquires;
static bool source_open = true;
static struct pt_regs last_wrapper_output;
static unsigned long clobber_mutex_lock_addr = 0x4110;
static unsigned long clobber_mutex_unlock_addr = 0x4120;
static unsigned long clobber_spin_lock_addr = 0x3110;
static unsigned long clobber_spin_unlock_addr = 0x3120;
static void kd_jit_clobber_call_v1(struct kd_jit_batch_call *call)
{
	(void)call;
	abort(); /* Minimal machine code is exercised by test_clobber_abi. */
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
static int failing_service(struct pt_regs *regs)
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

static void translated(struct pt_regs *regs, unsigned long *args)
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
static bool is_end_point(unsigned long ip)
{
	return ip == 0x9000;
}
static bool is_outer_lock_unlock(struct pt_regs *regs, unsigned long lock)
{
	return is_end_point(regs->ip) && regs->di == lock;
}
static int advance_and_save_continuation(struct kd_exec_frame *frame,
					 struct pt_regs *regs);
static int handle_known_call(struct pt_regs *regs, unsigned long outer)
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

static void reset(void)
{
	static struct kd_hostcall_desc original[ARRAY_SIZE(kd_hostcalls)];
	static bool captured;

	kd_jit_timing = false;
	complex_preparations = 0;
	kd_jit_timing_reset();
	timing_clock_active = false;
	timing_clock = timing_reads = 0;
	/* Restore actual manifest entries after deliberate flags/target failures. */
	if (!captured) {
		memcpy(original, kd_hostcalls, sizeof(original));
		captured = true;
	}
	memcpy(kd_hostcalls, original, sizeof(original));
	for (unsigned int i = 0; i < ARRAY_SIZE(kd_hostcalls); i++)
		kd_hostcalls[i].addr = 0x3000 + 8 * i;
	memset(service_calls, 0, sizeof(service_calls));
	scalar_argument = 0;
	memset(last_error, 0, sizeof(last_error));
	failed_service_calls = 0;
	kd_hostcall_exits = kd_hostcall_executed = kd_hostcall_resumed = 0;
	kd_hostcall_limit = kd_hostcall_rejected = kd_hostcall_failed = 0;
	active = (struct kd_exec_frame){
		.complex_ready = true,
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
	memset(stack, 0, sizeof(stack));
	stack[8] = 0x1005;
	waiter.stack = stack;
	memset(steps, 0, sizeof(steps));
	kd_exes = entry_table;
	memset(entry_table, 0, sizeof(entry_table));
	for (int i = 0; i < KD_MAX_EXE; i++)
		entry_table[i].status_code = KD_EXE_UNUSED;
	entry = kd_get_exe(0, active.entry_ip);
	*entry = (struct kd_exe_info){ .RIP = active.entry_ip,
				       .lock_kind = KD_EXE_LOCK_SPIN,
				       .code_block = translated,
				       .status_code = KD_EXE_NORMAL };
	source_open = true;
	registry_lookups = readiness_acquires = 0;
	calls = known_calls = errors = warnings =
		kd_jit_hl_fault_after_known_call = 0;
	known_result = 1;
	source_error = source_calls = source_fail_at = stack_error = stack_reads = 0;
	memset(source_targets, 0, sizeof(source_targets));
}

static int run(void)
{
	struct kd_exe_info *exe = kd_exe_find_ready(0, active.entry_ip);

	return kd_exe_on_call_hl_entry(exe, kd_exec_frame_regs(&active), active.entry_ip,
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
	CHECK(warnings == 1 && !errors && entry->status_code == KD_EXE_NORMAL);
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
	parent.delegated_lock_addr = active.outer_lock_addr;
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
			parent.delegated_lock_addr++;
			break;
		case 9:
			active.parent = &parent;
			active.resume_target = NULL;
			break;
		case 10:
			active.regs.sp++;
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

static void check_registry_refusal(void)
{
	struct kd_exec_frame before;
	unsigned long stack_before[16];
	struct kd_exe_info table_before[KD_MAX_EXE];

	/* These are unstarted spin/mutex roots, not post-progress recovery. Check
	 * the full packet, virtual stack and owner ledger, not just executed=false. */
	for (int backend = 0; backend < 2; backend++) {
		for (int state = 0; state < 7; state++) {
			reset();
			active.mutex_backend = backend;
			entry->lock_kind = backend ? KD_EXE_LOCK_MUTEX :
						     KD_EXE_LOCK_SPIN;
			memset(&active.regs, 0x51, sizeof(active.regs));
			active.regs.ip = active.entry_ip;
			active.regs.sp = (unsigned long)&stack[9];
			active.regs.di = active.outer_lock_addr;
			switch (state) {
			case 0:
				kd_exes = NULL;
				break;
			case 1:
				entry->status_code = KD_EXE_UNUSED;
				break;
			case 2:
				entry->status_code = KD_EXE_UNINIT;
				break;
			case 3:
				entry->status_code = KD_EXE_CALL_MISS;
				break;
			case 4:
				entry->status_code = KD_EXE_NATIVE_ONLY;
				break;
			case 5:
				entry->code_block = NULL;
				break;
			case 6:
				for (int i = 0; i < KD_MAX_EXE; i++) {
					entry_table[i].status_code =
						KD_EXE_UNINIT;
					entry_table[i].pid = 1;
				}
				break;
			}
			before = active;
			memcpy(stack_before, stack, sizeof(stack));
			memcpy(table_before, entry_table, sizeof(entry_table));
			CHECK(run() == KD_EXE_NO_RUN);
			CHECK(!calls && !known_calls && !errors &&
			      !active.executed);
			CHECK(memcmp(&before, &active, sizeof(active)) == 0);
			CHECK(memcmp(stack_before, stack, sizeof(stack)) == 0);
			CHECK(memcmp(table_before, entry_table,
				     sizeof(entry_table)) == 0);
		}
	}
}

/* Model the setup gap between execute_cs's lookup and dispatcher entry.
 * The pointer is stable, but publication/readiness can change during the gap.
 * Source frame leasing itself is exercised by test_source_lifetime. */
static void check_cached_entry(void)
{
	for (int backend = 0; backend < 2; backend++) {
		for (int change = -1; change < 9; change++) {
			struct kd_exe_info *cached;
			struct kd_exec_frame before;
			unsigned int acquires;

			reset();
			active.mutex_backend = backend;
			entry->lock_kind = backend ? KD_EXE_LOCK_MUTEX : KD_EXE_LOCK_SPIN;
			CHECK(kd_exe_is_ready(0, active.entry_ip));
			registry_lookups = 0;
			cached = kd_exe_find_ready(0, active.entry_ip);
			CHECK(cached == entry && registry_lookups == 1);
			steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
			switch (change) {
			case 0: source_open = false; break; /* DRAINING before invalidation */
			case 1: kd_exe_publish_status(entry, KD_EXE_UNINIT); break;
			case 2: kd_exe_publish_status(entry, KD_EXE_CALL_MISS); break;
			case 3: kd_exe_publish_status(entry, KD_EXE_NATIVE_ONLY); break;
			case 4: entry->code_block = NULL; break;
			case 5: entry->pid = 1; break;
			case 6: entry->RIP += 8; break;
			case 7: entry->lock_kind = backend ? KD_EXE_LOCK_SPIN : KD_EXE_LOCK_MUTEX; break;
			case 8: cached = NULL; break;
			}
			before = active;
			acquires = readiness_acquires;
			CHECK(kd_exe_on_call_hl_entry(cached, &active.regs,
				active.entry_ip, active.outer_lock_addr) ==
			      (change < 0 ? KD_EXE_RUN_TO_UNLOCK : KD_EXE_NO_RUN));
			CHECK(registry_lookups == 1); /* no second/third hash in dispatch */
			if (change < 0) {
				CHECK(calls == 1 && active.executed);
				CHECK(readiness_acquires > acquires);
			} else {
				CHECK(!calls && !known_calls && !active.executed);
				CHECK(!memcmp(&before, &active, sizeof(active)));
				if (change == 7)
					CHECK(entry->status_code == KD_EXE_NATIVE_ONLY);
			}
		}
	}
}

static void check_source_target_refusal(void)
{
	for (int error = 0; error < 2; error++) {
		reset();
		known_result = 0;
		source_error = error ? -ESTALE : 0;
		steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x2000, 1, -8 };
		CHECK(run() == (error ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE));
		CHECK(calls == 1 && source_calls == 1 && active.executed);
		CHECK(active.regs.ip == 0x2000 &&
		      active.regs.sp == (unsigned long)&stack[8]);
		CHECK(entry->status_code ==
		      (error ? KD_EXE_NORMAL : KD_EXE_CALL_MISS));
		CHECK(!memcmp(&active.regs, &last_wrapper_output, sizeof(active.regs)));
		CHECK(stack[8] == 0x1005 && !service_calls[0] &&
		      !service_calls[1] && !service_calls[2]);
		CHECK(errors == error);
	}
}

static void service_packet(void)
{
	reset();
	memset(&active.regs, 0x5A, sizeof(active.regs));
	active.regs.ip = active.entry_ip;
	active.regs.sp = (unsigned long)&stack[9];
	active.regs.di = active.outer_lock_addr;
}

/* Check the producer's real flags/address gates independently of the high-level
 * exit marker. Refused services must not consume CALL words or change GPRs. */
static void check_service_dispatch(void)
{
	const unsigned int required = KD_HOSTCALL_F_ATOMIC_SAFE |
		KD_HOSTCALL_F_NO_TASK_CONTEXT | KD_HOSTCALL_F_RETRY_SAFE;

	CHECK(ARRAY_SIZE(kd_hostcalls) == ARRAY_SIZE(service_calls));
	for (unsigned int i = 0; i < ARRAY_SIZE(kd_hostcalls); i++) {
		for (unsigned int flags = 0; flags <= required; flags++) {
			struct pt_regs expected;

			service_packet();
			active.regs.ip = kd_hostcalls[i].addr;
			kd_hostcalls[i].flags = flags;
			expected = active.regs;
			CHECK(kd_hostcall_dispatch(&active.regs) ==
			      (flags == required ? 0 : -EPERM));
			if (flags == required)
				expected.ax = service_values[i];
			CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
			for (unsigned int j = 0; j < ARRAY_SIZE(service_calls); j++)
				CHECK(service_calls[j] == (j == i && flags == required));
			if (i == 2 && flags == required)
				CHECK(scalar_argument == expected.di);
		}
	}
	for (unsigned int zero = 0; zero < 2; zero++) {
		struct pt_regs before;

		service_packet();
		for (unsigned int i = 0; i < ARRAY_SIZE(kd_hostcalls); i++)
			kd_hostcalls[i].addr = 0;
		active.regs.ip = zero ? 0 : 0xDEAD;
		before = active.regs;
		CHECK(kd_hostcall_dispatch(&active.regs) == -ENOENT);
		CHECK(!memcmp(&active.regs, &before, sizeof(before)));
		CHECK(!service_calls[0] && !service_calls[1] && !service_calls[2]);
	}
}

/* Distinguish the real adapter's register choice and width, independently of
 * the wrapper double. Preserve the entire software packet except return RAX. */
static void check_scalar_arguments(void)
{
	const unsigned long arguments[] = {
		0, 1, 0x7fffffffUL, 0xffffffffUL, 0x100000000UL,
		0x4000000080000001UL, 0x8000000000000000UL, ~0UL,
	};

	for (unsigned int i = 0; i < ARRAY_SIZE(arguments); i++) {
		struct pt_regs expected;

		service_packet();
		active.regs.ip = kd_hostcalls[2].addr;
		active.regs.di = arguments[i];
		active.regs.si = ~arguments[i];
		expected = active.regs;
		expected.ax = service_values[2];
		CHECK(kd_hostcall_dispatch(&active.regs) == 0);
		CHECK(scalar_argument == arguments[i]);
		CHECK(service_calls[2] == 1 && !service_calls[0] && !service_calls[1]);
		CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
		CHECK(stack[8] == 0x1005);
	}
}

/* Script service returns, not machine code. The actual high-level consumer must
 * reinitialize both wrapper words, preserve non-return GPRs and consume one CALL. */
static void check_service_returns(void)
{
	const unsigned int counts[] = { 1, KD_EXE_HL_MAX_HOSTCALLS - 1,
					KD_EXE_HL_MAX_HOSTCALLS };

	for (unsigned int n = 0; n < ARRAY_SIZE(counts); n++) {
		struct pt_regs expected;
		unsigned long before_stack[ARRAY_SIZE(stack)];
		unsigned int count = counts[n];

		service_packet();
		expected = active.regs;
		memcpy(before_stack, stack, sizeof(stack));
		for (unsigned int i = 0; i < count; i++)
			steps[i] = (struct step){ KD_EXE_HOSTCALL,
				kd_hostcalls[i % ARRAY_SIZE(kd_hostcalls)].addr, 1, -8 };
		steps[count] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
		CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
		expected.ip = 0x9000;
		expected.sp -= 8;
		expected.ax = service_values[(count - 1) % ARRAY_SIZE(service_values)];
		CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
		CHECK(!memcmp(stack, before_stack, sizeof(stack)));
		CHECK(active.continuation_ip == stack[8] &&
		      active.continuation_sp == (unsigned long)&stack[9]);
		CHECK(active.executed && calls == (int)count + 1 && known_calls == 1);
		CHECK(kd_hostcall_exits == count && kd_hostcall_executed == count &&
		      kd_hostcall_resumed == count);
		for (unsigned int i = 0; i < ARRAY_SIZE(service_calls); i++)
			CHECK(service_calls[i] == count / ARRAY_SIZE(service_calls) +
			      (i < count % ARRAY_SIZE(service_calls)));
		CHECK(!errors && !source_calls && !kd_hostcall_failed &&
		      !kd_hostcall_rejected && !kd_hostcall_limit);
	}
}

static void check_service_errors(void)
{
	for (unsigned int bad = 0; bad < 6; bad++) {
		struct pt_regs expected;

		service_packet();
		if (bad >= 1 && bad <= 3)
			kd_hostcalls[0].flags &= ~(1U << (bad - 1));
		if (bad == 4)
			kd_hostcalls[0].invoke = failing_service;
		/* Keep entry admission valid; the bad continuation belongs to the
		 * wrapper's exit packet, after a service request has been produced. */
		steps[0] = (struct step){ KD_EXE_HOSTCALL,
			bad ? kd_hostcalls[0].addr : 0xDEAD, 1,
			bad == 5 ? -(long)active.regs.sp : -8 };
		CHECK(run() == KD_EXE_RUN_ERROR);
		expected = last_wrapper_output;
		if (bad == 5)
			expected.ax = service_values[0];
		CHECK(!memcmp(&active.regs, &expected, sizeof(expected)));
		/* Invoke/return failure after entry never authorizes unstarted replay. */
		CHECK(active.executed && calls == 1 && errors == 1);
		CHECK(kd_hostcall_exits == 1 && !kd_hostcall_resumed && !kd_hostcall_limit);
		CHECK(kd_hostcall_rejected == (bad < 4) &&
		      kd_hostcall_failed == (bad >= 4));
		CHECK(kd_hostcall_executed == (bad == 5) && service_calls[0] == (bad == 5));
		CHECK(!service_calls[1] && !service_calls[2] &&
		      failed_service_calls == (bad == 4));
		CHECK(!source_calls && !known_calls && entry->status_code == KD_EXE_NORMAL);
		CHECK(strstr(last_error, bad == 5 ? "HOSTCALL_CONTINUATION_FAILED" :
							 "HOSTCALL_FAILED"));
	}
	/* A CALL_MISS for an allowlisted address is still an ordinary native
	 * suffix. Only the explicit HOSTCALL exit requests a service and return. */
	service_packet();
	known_result = 0;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, kd_hostcalls[0].addr, 1, -8 };
	CHECK(run() == KD_EXE_RUN_NATIVE);
	CHECK(calls == 1 && source_calls == 1 && !kd_hostcall_exits &&
	      !service_calls[0] && !service_calls[1] && !service_calls[2]);
	CHECK(!memcmp(&active.regs, &last_wrapper_output, sizeof(active.regs)));
}

/* Known lock controls and services share the invocation budget. Mixing them
 * must stop before the excess operation, with its CALL packet still intact. */
static void check_shared_budget(void)
{
	const unsigned int prefixes[] = { 0, 1, KD_EXE_HL_MAX_CONTINUATIONS };

	/* A remote child shares the image but not the parent's active CALL packet.
	 * Quota handling must leave that waiting parent untouched for native relay. */
	for (unsigned int n = 0; n < 2 * ARRAY_SIZE(prefixes); n++) {
		for (unsigned int service = 0; service < 2; service++) {
			bool child = n >= ARRAY_SIZE(prefixes);
			unsigned int known = prefixes[n % ARRAY_SIZE(prefixes)];
			unsigned int accepted = KD_EXE_HL_MAX_CONTINUATIONS;
			unsigned int services = accepted - known;
			struct kd_exec_frame saved_parent;

			if (child)
				remote();
			else
				service_packet();
			saved_parent = parent;
			for (unsigned int i = 0; i < accepted; i++)
				steps[i] = (struct step){ i < known ? KD_EXE_CALL_MISS :
					KD_EXE_HOSTCALL, i < known ? 0x2000 : kd_hostcalls[0].addr,
					1, -8 };
			steps[accepted] = (struct step){ service ? KD_EXE_HOSTCALL :
				KD_EXE_CALL_MISS, service ? kd_hostcalls[0].addr : 0x2000,
				1, -8 };
			CHECK(run() == KD_EXE_RUN_NATIVE);
			CHECK(calls == (int)accepted + 1 && known_calls == (int)known);
			CHECK(service_calls[0] == services && !service_calls[1] && !service_calls[2]);
			CHECK(kd_hostcall_exits == services + service &&
			      kd_hostcall_executed == services && kd_hostcall_resumed == services);
			CHECK(kd_hostcall_limit == service && !kd_hostcall_rejected &&
			      !kd_hostcall_failed);
			CHECK(!memcmp(&active.regs, &last_wrapper_output, sizeof(active.regs)));
			CHECK(active.regs.sp == (unsigned long)&stack[8] && stack[8] == 0x1005);
			CHECK(active.executed && !errors && warnings == 1 && source_calls == 2);
			CHECK(source_targets[0] == active.regs.ip && source_targets[1] == stack[8]);
			CHECK(active.continuation_ip == active.regs.ip &&
			      active.continuation_sp == active.regs.sp &&
			      active.control_call.phase == KD_CALL_NONE &&
			      active.state == KD_EXEC_FRAME_RESUME);
			CHECK(entry->status_code == KD_EXE_NORMAL && !entry->tgt_addr);
			CHECK(active.resume_target == (child ? &parent : NULL));
			if (child)
				CHECK(!memcmp(&parent, &saved_parent, sizeof(parent)));
		}
	}
}

/* Validate the exact pre-dispatch boundary independently of counter setup.
 * Corrupted packets must leave every frame/stack byte untouched. This is not
 * evidence for concurrent stack privacy or live hardware flags preservation. */
static void check_quota_packets(void)
{
	for (int backend = 0; backend < 2; backend++) {
		for (int service = 0; service < 2; service++) {
			for (int bad = 0; bad < 23; bad++) {
				struct kd_exec_frame before;
				struct kd_exe_info registered;
				unsigned long saved_stack[ARRAY_SIZE(stack)];
				int ret;

				service_packet();
				active.mutex_backend = backend;
				active.executed = true;
				active.control_call.phase = KD_CALL_COMPLETE;
				active.regs.ip = kd_hostcalls[0].addr;
				active.regs.sp = (unsigned long)&stack[8];
				switch (bad) {
				case 1:
					active.regs.ip = 0;
					break;
				case 2:
					active.regs.sp = 0;
					break;
				case 3:
					active.executed = false;
					break;
				case 4:
					active.logical_task = current;
					break;
				case 5:
					active.logical_task = NULL;
					break;
				case 6:
					active.state = KD_EXEC_FRAME_ERROR;
					break;
				case 7:
					active.control_call.phase = KD_CALL_ENTERED;
					break;
				case 8:
					active.control_call.phase = KD_CALL_PENDING;
					break;
				case 9:
					active.remote_result = KD_EXEC_REMOTE_WAITING;
					break;
				case 10:
					active.remote_request = (void *)1;
					break;
				case 11:
					active.native_request = (void *)1;
					break;
				case 12:
					waiter.stack = NULL;
					break;
				case 13:
					waiter.stack = (void *)(~0UL - THREAD_SIZE + 1);
					break;
				case 14:
					active.regs.sp = (unsigned long)stack - 1;
					break;
				case 15:
					active.regs.sp = (unsigned long)stack + sizeof(stack) - 7;
					break;
				case 16:
					stack[8] = 0;
					break;
				case 17:
					stack_error = 1;
					break;
				case 18:
				case 19:
					source_error = -ESTALE;
					source_fail_at = bad - 17;
					break;
				case 20:
					kd_hostcalls[0].addr = 0;
					break;
				case 21:
					kd_hostcalls[0].flags = 0;
					break;
				case 22:
					active.outer_unlock_seen = true;
					active.jit_lock_released[0] = true;
					break;
				}
				before = active;
				registered = *entry;
				memcpy(saved_stack, stack, sizeof(stack));
				ret = kd_jit_call_limit_native(&active, &active.regs, service);
				if (!bad || (!service && (bad == 20 || bad == 21))) {
					CHECK(ret == 0 && source_calls == 2 && stack_reads == 1);
					before.control_call.phase = KD_CALL_NONE;
					before.continuation_ip = before.regs.ip;
					before.continuation_sp = before.regs.sp;
					before.state = KD_EXEC_FRAME_RESUME;
				} else {
					CHECK(ret < 0 && !warnings);
					if (bad >= 12 && bad <= 15)
						CHECK(!stack_reads && !source_calls);
					if (bad == 18 || bad == 19)
						CHECK(source_calls == source_fail_at);
				}
				CHECK(!memcmp(&before, &active, sizeof(active)));
				CHECK(!memcmp(saved_stack, stack, sizeof(stack)));
				CHECK(!memcmp(&registered, entry, sizeof(registered)));
				CHECK(!service_calls[0] && !service_calls[1] &&
				      !service_calls[2] && !known_calls && !calls);
			}
		}
	}
	/* Released A with retained B and a remote child both keep their ledger.
	 * Parent completion/unlock routing remains the backend's existing duty. */
	for (int scope = 0; scope < 3; scope++) {
		struct kd_exec_frame expected;

		remote();
		active.executed = true;
		active.regs.ip = 0x2000;
		active.regs.sp = (unsigned long)&stack[8];
		if (scope) {
			active.resume_target = NULL;
			active.outer_lock_addr = 0x8000;
			active.outer_lock_index = 0;
			active.outer_unlock_seen = true;
			active.jit_lock_released[0] = true;
			active.mutex_backend = scope == 2;
		}
		expected = active;
		expected.continuation_ip = active.regs.ip;
		expected.continuation_sp = active.regs.sp;
		expected.state = KD_EXEC_FRAME_RESUME;
		CHECK(kd_jit_call_limit_native(&active, &active.regs, false) == 0);
		CHECK(!memcmp(&expected, &active, sizeof(active)));
		CHECK(stack[8] == 0x1005 && source_calls == 2);
	}
}

/* Re-run the same scripted packets with timing off/on. The complete frame,
 * table entry and stack must agree, including refusal, progressed error and
 * native decisions. These are software-boundary checks, not hardware flags. */
static void check_timing_boundaries(void)
{
	const unsigned int wrappers[] = { 3, 1, 1, 1, 1, 1, 17, 1, 0, 1, 1 };
	const unsigned int services[] = { 2, 0, 0, 1, 0, 0, 16, 0, 0, 0, 1 };
	const unsigned int controls[] = { 1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0 };
	const int results[] = { KD_EXE_RUN_TO_UNLOCK, KD_EXE_NO_RUN,
		KD_EXE_RUN_ERROR, KD_EXE_RUN_ERROR, KD_EXE_RUN_NATIVE,
		KD_EXE_RUN_NATIVE, KD_EXE_RUN_NATIVE, KD_EXE_RUN_ERROR,
		KD_EXE_NO_RUN, KD_EXE_RUN_ERROR, KD_EXE_RUN_ERROR };

	for (unsigned int scenario = 0; scenario < ARRAY_SIZE(results); scenario++) {
		struct kd_exec_frame expected;
		struct kd_exe_info registered;
		unsigned long saved_stack[ARRAY_SIZE(stack)];

		for (int enabled = 0; enabled < 2; enabled++) {
			unsigned int inner = wrappers[scenario] + services[scenario] +
				controls[scenario];
			unsigned int samples[KD_JIT_TIME_COUNT] = {
				scenario != 8, wrappers[scenario], services[scenario],
				controls[scenario],
			};

			service_packet();
			timing_clock_active = true;
			kd_jit_timing = enabled;
			steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x2000, 1, -8 };
			switch (scenario) {
			case 0:
				steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
				steps[1] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[2].addr, 1, -8 };
				steps[2] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, -8 };
				break;
			case 1:
			case 2:
				steps[0] = (struct step){ KD_EXE_ENTRY_REFUSED, 0, scenario == 2, 0 };
				break;
			case 3:
				kd_hostcalls[0].invoke = failing_service;
				steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
				break;
			case 4:
				known_result = KD_EXE_KNOWN_NATIVE;
				break;
			case 5:
				known_result = 0;
				break;
			case 6:
				for (int i = 0; i <= KD_EXE_HL_MAX_HOSTCALLS; i++)
					steps[i] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
				break;
			case 7:
				kd_jit_hl_fault_after_known_call = 3;
				break;
			case 8:
				entry->status_code = KD_EXE_UNINIT;
				break;
			case 9:
				known_result = -EIO;
				break;
			case 10:
				steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1,
					-(long)active.regs.sp };
				break;
			}
			CHECK(run() == results[scenario]);
			CHECK(timing_reads == (enabled && scenario != 8 ? 2 * (inner + 1) : 0));
			for (int phase = 0; phase < KD_JIT_TIME_COUNT; phase++) {
				u64 ns = samples[phase] * 10;

				if (phase == KD_JIT_TIME_DISPATCH && scenario != 8)
					ns = (2 * inner + 1) * 10;
				CHECK(kd_jit_times[phase].samples == enabled * samples[phase]);
				CHECK(kd_jit_times[phase].ns == (s64)(enabled * ns));
				CHECK(!kd_jit_times[phase].invalid);
			}
			if (!enabled) {
				expected = active;
				registered = *entry;
				memcpy(saved_stack, stack, sizeof(stack));
			} else {
				CHECK(!memcmp(&active, &expected, sizeof(active)));
				CHECK(!memcmp(entry, &registered, sizeof(registered)));
				CHECK(!memcmp(stack, saved_stack, sizeof(stack)));
			}
		}
	}
	/* Invalid clocks and saturated counters poison only telemetry, never the
	 * execution packet or later valid counter updates. Start at zero is valid. */
	for (int bad = 0; bad < 4; bad++) {
		struct kd_exec_frame before;
		struct kd_jit_timing_stat *stat = &kd_jit_times[KD_JIT_TIME_WRAPPER];

		reset();
		before = active;
		kd_jit_timing = timing_clock_active = true;
		if (bad == 1)
			stat->samples = S64_MAX;
		if (bad == 2)
			stat->ns = S64_MAX;
		timing_clock = bad == 2 ? 1 : 0;
		kd_jit_timing_end(KD_JIT_TIME_WRAPPER, bad == 0 ? 1 : 0);
		CHECK(stat->invalid == (bad != 3));
		CHECK(stat->samples == (bad == 1 ? S64_MAX : 1));
		CHECK(stat->ns == (bad == 2 ? S64_MAX : 0));
		CHECK(!memcmp(&active, &before, sizeof(active)));
	}
	reset();
}

/* Verify the actual counter API separately from queue/clock substitutes in
 * the producer fixtures: saved endpoints exclude body time, reuse counts once,
 * and disabled measurement changes neither clocks nor execution packets. */
static void check_queue_timings(void)
{
	for (int mutex = 0; mutex < 2; mutex++) {
		for (int enabled = 0; enabled < 2; enabled++) {
			u64 queued_at;
			u64 endpoint;
			int phase = mutex ? KD_JIT_TIME_MUTEX_QUEUE : KD_JIT_TIME_SPIN_QUEUE;
			struct kd_exec_frame before;

			reset();
			before = active;
			kd_jit_timing = enabled;
			timing_clock_active = true;
			timing_clock = 100;
			for (int request = 1; request <= 2; request++) {
				queued_at = kd_exe_queue_timing_start();
				endpoint = kd_exe_queue_timing_start();
				timing_clock += 1000; /* Substituted body elapsed time. */
				kd_exe_queue_timing_end(mutex, &queued_at, endpoint);
				CHECK(queued_at == 0);
				kd_exe_queue_timing_end(mutex, &queued_at, endpoint);
				CHECK(timing_reads == (unsigned int)(enabled * request * 2));
				for (int i = 0; i < KD_JIT_TIME_COUNT; i++) {
					int count = enabled && i == phase ? request : 0;

					CHECK(kd_jit_times[i].samples == count);
					CHECK(kd_jit_times[i].ns == count * 10);
					CHECK(!kd_jit_times[i].invalid);
				}
				CHECK(!memcmp(&active, &before, sizeof(active)));
			}
		}
	}
	reset();
}

/* The wider native envelope must contain the inner wait without adding their
 * times together. Clock/backend selection never changes the saved packet. */
static void check_native_handoff_timings(void)
{
	for (int mutex = 0; mutex < 2; mutex++) {
		for (int enabled = 0; enabled < 2; enabled++) {
			struct kd_exec_frame before;
			u64 handoff, wait;
			int outer = mutex ? KD_JIT_TIME_NATIVE_MUTEX_HANDOFF :
					    KD_JIT_TIME_NATIVE_SPIN_HANDOFF;
			int inner = mutex ? KD_JIT_TIME_NATIVE_MUTEX_WAIT :
					    KD_JIT_TIME_NATIVE_SPIN_WAIT;

			reset();
			before = active;
			kd_jit_timing = enabled;
			timing_clock_active = true;
			handoff = kd_exe_native_timing_start();
			wait = kd_exe_native_timing_start();
			kd_exe_native_timing_end(mutex, wait);
			kd_exe_native_handoff_timing_end(mutex, handoff);
			CHECK(timing_reads == (unsigned int)(enabled * 4));
			for (int i = 0; i < KD_JIT_TIME_COUNT; i++) {
				int count = enabled && (i == outer || i == inner);

				CHECK(kd_jit_times[i].samples == count);
				CHECK(kd_jit_times[i].ns == count * (i == outer ? 30 : 10));
				CHECK(!kd_jit_times[i].invalid);
			}
			CHECK(!memcmp(&active, &before, sizeof(active)));
		}
	}
	reset();
}

static void check_simple_spin(void)
{
	struct pt_regs packet, before;

	reset();
	active.spin_simple = true;
	packet = active.regs;
	active.borrowed_regs = &packet;
	active.regs_borrowed = true;
	memset(&active.regs, 0xa5, sizeof(active.regs));
	before = active.regs;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(active.executed && active.spin_simple && calls == 1 &&
	      !known_calls && !complex_preparations);
	CHECK(packet.ip == 0x9000 && active.borrowed_regs == &packet &&
	      !memcmp(&active.regs, &before, sizeof(before)));

	/* A service promotes once, before the service runs; its eventual outer
	 * unlock uses the generic continuation path even when the ledger is 1. */
	reset();
	active.spin_simple = true;
	packet = active.regs;
	active.borrowed_regs = &packet;
	active.regs_borrowed = true;
	memset(&active.regs, 0xa5, sizeof(active.regs));
	steps[0] = (struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
	steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_TO_UNLOCK);
	CHECK(!active.spin_simple && complex_preparations == 1 &&
	      calls == 2 && known_calls == 1 && service_calls[0] == 1);
	CHECK(!active.regs_borrowed && active.regs.ip == 0x9000 &&
	      active.regs.ax == service_values[0]);
	/* After promotion the old node packet stops changing, including the CALL
	 * return advance and the resumed wrapper. */
	CHECK(packet.ip == kd_hostcalls[0].addr && packet.sp != active.regs.sp);

	/* The CALL target alone is insufficient; a different lock must take the
	 * existing control/error handling instead of completing this frame. */
	reset();
	active.spin_simple = true;
	active.regs.di++;
	known_result = -EINVAL;
	steps[0] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
	CHECK(run() == KD_EXE_RUN_ERROR);
	CHECK(!active.spin_simple && complex_preparations == 1 && known_calls == 1);

	reset();
	active.spin_simple = true;
	steps[0].reason = KD_EXE_ENTRY_REFUSED;
	packet = before = active.regs;
	active.borrowed_regs = &packet;
	active.regs_borrowed = true;
	CHECK(run() == KD_EXE_NO_RUN);
	CHECK(active.spin_simple && !active.executed && !complex_preparations);
	CHECK(active.borrowed_regs == &packet &&
	      !memcmp(&packet, &before, sizeof(packet)));
}

/* A batch exit has already executed its prefix. Import it once, then permit
 * only the required continuation wrapper call; a refusal remains unstarted. */
static void check_batch_admission(void)
{
	unsigned char code[64] = { 0 };
	struct kd_jit_batch_call call;

	reset();
	active.spin_simple = active.request_frame = true;
	active.complex_ready = false;
	entry->code_block = code;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	memcpy(code + 9, "KDWB001", 7);
	CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
	CHECK(call.code == code + KD_JIT_BATCH_OFFSET && call.regs == &active.regs &&
	      call.args[0] == active.gsbase && call.args[1] == (unsigned long)&waiter);
	source_open = false;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	source_open = true;
	entry->status_code = KD_EXE_CALL_MISS;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	entry->status_code = KD_EXE_NORMAL;
	active.executed = true;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	active.executed = false;
	active.regs.sp = 0;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	active.regs.sp = (unsigned long)&stack[9];
	active.complex_ready = true;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
}

/* Entry identity and materialization state are independent of publication.
 * None of these mismatches may invoke the wrapper or read the absent GPRs. */
static void check_clobber_identity(void)
{
	unsigned char code[64] = { 0 };
	struct kd_jit_batch_call call;

	reset();
	active.spin_simple = active.request_frame = true;
	active.complex_ready = false;
	entry->code_block = code;
	memcpy(code + 9, "KDWB001", 7);
	active.entry_abi = entry->entry_abi = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	active.packet_state = KD_PACKET_MINIMAL;
	active.regs.di = 0xdead; /* deliberately not the root lock */
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	memcpy(code + 25, "KDWC001", 7);
	memcpy(code + 41, "KDAB", 4);
	code[45] = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	CHECK(kd_exe_spin_batch_prepare(entry, &active, &call));
	CHECK(call.code == code + KD_JIT_CLOBBER_OFFSET && call.complete);
	CHECK(call.packet_state == &active.packet_state && call.entry_abi == 1);
	for (unsigned int bad = 0; bad < 4; bad++) {
		if (bad == 0) entry->entry_abi = KD_ENTRY_ABI_LEGACY;
		if (bad == 1) code[45] = KD_ENTRY_ABI_LEGACY;
		if (bad == 2) active.packet_state = KD_PACKET_FULL;
		if (bad == 3) active.packet_state = KD_PACKET_COMPLETE;
		CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
		entry->entry_abi = code[45] = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
		active.packet_state = KD_PACKET_MINIMAL;
	}
	active.entry_abi = entry->entry_abi = KD_ENTRY_ABI_LEGACY;
	active.packet_state = KD_PACKET_FULL;
	CHECK(!kd_exe_spin_batch_prepare(entry, &active, &call));
	CHECK(calls == 0 && !active.executed);
	active.entry_abi = entry->entry_abi = code[45] = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	active.mutex_backend = true;
	active.spin_simple = false;
	active.jit_lock_depth = 1;
	active.outer_lock_index = 0;
	active.jit_lock_released[0] = false;
	CHECK(kd_jit_image_matches(entry, &active));
	kd_jit_prepare_clobber(&call, &active, code);
	CHECK(call.complete && call.unlock == clobber_mutex_unlock_addr);
	CHECK(call.entry_abi == 2 && call.regs == kd_exec_frame_regs(&active));
	active.jit_lock_depth = 2;
	CHECK(!kd_jit_minimal_complete_allowed(&active));
	active.jit_lock_depth = 1;
	active.outer_unlock_seen = true;
	CHECK(!kd_jit_minimal_complete_allowed(&active));
	active.outer_unlock_seen = false;
	active.mutex_backend = false;
	CHECK(!kd_jit_minimal_complete_allowed(&active));
	code[45] = KD_ENTRY_ABI_SPIN_CLOBBER_V1;
	CHECK(!kd_jit_image_matches(entry, &active));
}

static void check_pending_batch_exit(void)
{
	struct kd_jit_batch_call pending;

	for (int refuse = 0; refuse < 2; refuse++) {
		reset();
		active.spin_simple = true;
		pending = (struct kd_jit_batch_call){
			.regs = &active.regs, .entry_sp = active.regs.sp,
			.args = { active.gsbase, (unsigned long)&waiter },
		};
		steps[0] = refuse ? (struct step){ KD_EXE_ENTRY_REFUSED, 0, 0, 0 } :
			(struct step){ KD_EXE_HOSTCALL, kd_hostcalls[0].addr, 1, -8 };
		steps[1] = (struct step){ KD_EXE_CALL_MISS, 0x9000, 1, 0 };
		active.executed = true;
		translated(pending.regs, pending.args);
		CHECK(calls == 1);
		int result = kd_exe_spin_batch_resume(entry, &pending);
		CHECK(result == (refuse ? KD_EXE_NO_RUN : KD_EXE_RUN_TO_UNLOCK));
		CHECK(calls == (refuse ? 1 : 2));
		CHECK(service_calls[0] == (refuse ? 0U : 1U));
		CHECK(active.executed == !refuse && complex_preparations == 1);
	}
}

int main(void)
{
	check_batch_admission();
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
