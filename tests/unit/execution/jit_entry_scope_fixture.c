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
/* This fixture executes one thread. The production frame's inline accessors
 * require these declarations before frame_types.h, including pointer reads. */
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x) = (value))

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

/* Query-only declaration for production branches outside this fixture's
 * legacy frame scope. No retained continuation is constructed here; its real
 * ownership and service transactions have separate live fixtures. */
struct kd_exec_continuation {
	enum kd_exec_cont_state state;
	const struct kd_exec_service_ops *service_ops;
	void *service_scope;
	bool body_reported;
	struct { enum kd_exec_service_api api; } service_call;
};

static unsigned long stack[16];
static struct task_struct executor = { .pid = 1 },
	waiter = { .pid = 2, .stack = stack }, stranger = { .pid = 3 };
static struct task_struct *current = &executor;
/* Built-in object bridges are absent from this execution-control fixture.
 * Their actual class/object predicate has a separate integration fixture. */
static bool kd_api_outer_unlock(unsigned long target, unsigned long lock,
				unsigned long outer, bool mutex_backend)
{
	(void)target; (void)lock; (void)outer; (void)mutex_backend;
	return false;
}
static struct kd_exec_frame active, parent;
static struct kd_exe_info entry_table[KD_MAX_EXE], *entry;
static int calls, known_calls, known_result, errors, warnings, checks, failures;
static unsigned int registry_lookups, readiness_acquires, current_frame_reads;
static bool source_open = true;
static struct kd_regs last_wrapper_output;
static unsigned long direct_mutex_lock_addr = 0x4130;
static unsigned long direct_mutex_unlock_addr = 0x4140;
static unsigned long clobber_spin_lock_addr = 0x3110;
static unsigned long clobber_spin_unlock_addr = 0x3120;
static unsigned long raw_spin_lock_addr = 0x3130;
static unsigned long pinned_spin_lock_addr = 0x3140;
static unsigned long cold_spin_unlock_addr = 0x3150;
static unsigned long rwlock_fast_unlock_addr = 0x3160;
static unsigned long mutex_lock_addr = 0x4110;
static unsigned long mutex_unlock_addr = 0x4120;
static unsigned long contended_mutex_lock_addr = 0x4150;
static unsigned long outer_mutex_lock_addr = 0x4160;
static bool root_escape_wrapper;
static void fixture_root_escape_wrapper(struct kd_jit_batch_call *call);
static void kd_jit_clobber_call_v1(struct kd_jit_batch_call *call)
{
	if (root_escape_wrapper) {
		fixture_root_escape_wrapper(call);
		return;
	}
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
static unsigned char escape_text[16];
static unsigned long kd_native_escape_count;
static unsigned long kd_address_guard_count;
static unsigned long kd_origin_instruction_count, kd_origin_reentry_count,
	kd_origin_suffix_count;
static bool kd_origin_instruction_force_suffix;
static int origin_result;
static unsigned int origin_calls;
static unsigned long origin_sequence;
static bool origin_wrapper;
#define STRING_IP 0xffff80000000c000UL
#define STRING_RETURN (STRING_IP + 0x1005)
#define STRING_LEFT (STRING_IP + 0x2000)
#define STRING_RIGHT (STRING_IP + 0x3000)
#define PAD_IP (STRING_IP + 0x5000)
#define PAD_RETURN (STRING_IP + 0x6005)
#define STRING_BYTES 512U
static unsigned char string_left[STRING_BYTES], string_right[STRING_BYTES];
static unsigned int string_calls;
static int string_result, string_read_error;
static bool string_change_return;
static bool string_wrapper;
static void *string_wrapper_code;
static unsigned int pad_calls, string_read_extent;
static long pad_result;
static bool pad_truncates;
static unsigned long pad_destination;
static unsigned int string_readable;
#define ESCAPE_IP 0xa000UL
#define THREAD_SIZE sizeof(stack)
#define task_stack_page(task) ((task)->stack)

/* Model nofault reads, not arbitrary host dereferences. Production bounds
 * must reject foreign/out-of-stack words before this primitive is called. */
static int copy_from_kernel_nofault(void *to, const void *from, size_t size)
{
	unsigned long address = (unsigned long)from;

	stack_reads++;
	if ((size == 1 || size == sizeof(unsigned long)) &&
	    ((address >= STRING_LEFT && address <= STRING_LEFT + sizeof(string_left) - size) ||
	     (address >= STRING_RIGHT && address <= STRING_RIGHT + sizeof(string_right) - size))) {
		unsigned int offset = address >= STRING_RIGHT ? address - STRING_RIGHT : address - STRING_LEFT;
		if (string_read_error || offset + size > string_readable)
			return -EFAULT;
		if (offset + size > string_read_extent)
			string_read_extent = offset + size;
		memcpy(to, (address >= STRING_RIGHT ? string_right : string_left) + offset, size);
		return 0;
	}
	if (address >= ESCAPE_IP && address < ESCAPE_IP + sizeof(escape_text) &&
	    size <= ESCAPE_IP + sizeof(escape_text) - address) {
		if (stack_error)
			return -EFAULT;
		memcpy(to, escape_text + address - ESCAPE_IP, size);
		return 0;
	}
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
static unsigned long kd_direct_strcmp, kd_direct_pad;

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
#define atomic64_add(v, p) (*(p) += (v))
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

/* These retained-runtime joins must remain unreachable for every legacy
 * scenario and negative control below. A call is a fixture failure, never a
 * fabricated validation or service result. */
static bool kd_exec_cont_frame_valid(const struct kd_exec_frame *frame)
{
	(void)frame;
	CHECK(false);
	return false;
}

static int kd_exec_cont_memory_prepare(struct kd_exec_frame *frame)
{
	(void)frame;
	CHECK(false);
	return -EOPNOTSUPP;
}

static int kd_jit_service_control(struct kd_exec_frame *frame, struct kd_regs *regs)
{
	(void)frame;
	(void)regs;
	CHECK(false);
	return -EOPNOTSUPP;
}

/* The backend handshake is tested separately. This double changes one scalar
 * result only when it reports execution; consumers must retain that effect. */
static int kd_mutex_origin_instruction(struct kd_exec_frame *frame,
				       unsigned int kind, unsigned long sequence)
{
	CHECK(frame == &active && kind == KD_ORIGIN_RDTSC && sequence);
	origin_calls++;
	origin_sequence = sequence;
	if (origin_result == 1)
		kd_exec_frame_regs(frame)->ax = 0x12345678;
	return origin_result;
}

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

static int fixture_strcmp(const char *left, const char *right)
{
	CHECK((unsigned long)left == STRING_LEFT && (unsigned long)right == STRING_RIGHT);
	string_calls++;
	if (string_change_return)
		stack[8] = 0xdead;
	return string_result;
}

static long fixture_strscpy_pad(char *destination, const char *source, unsigned long count)
{
	CHECK((unsigned long)destination == pad_destination && (unsigned long)source == STRING_RIGHT);
	CHECK(count == KD_STRSCPY_BYTES);
	pad_calls++;
	/* This is a primitive double, not a replacement implementation under test.
	 * Taskname checks live normal-copy padding but ignores the return value.
	 * Truncation and return propagation here cover the production adapter,
	 * without claiming actual-kernel truncation execution. */
	memset(destination, 0, count);
	memcpy(destination, string_right, pad_truncates ? count - 1 : 15);
	return pad_result;
}

struct step {
	unsigned long reason, ip, witness;
	long sp_delta;
};
static struct step steps[KD_EXE_HL_MAX_CONTINUATIONS + KD_EXE_HL_MAX_HOSTCALLS + KD_STRCMP_MAX_CALLS + 3];

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
	if (origin_wrapper) {
		CHECK(regs->orig_ax == KD_REG_ORIGIN_REENTRY_TAG && regs->ip == ESCAPE_IP + 2);
		CHECK(regs->ax == 0x12345678 && regs->ss == 7);
		/* The real generated dispatcher consumes this tag before its body. */
		regs->orig_ax = 0;
	}

	/* A test double reports boundary packets only. The separate machine-code
	 * suite verifies that a real failed predicate preserves the whole packet. */
	CHECK(args[0] == active.gsbase &&
	      args[1] == (unsigned long)active.logical_task);
	if (step->ip)
		regs->ip = step->ip;
	if (string_wrapper && regs->ip == 0x9000)
		regs->di = active.outer_lock_addr;
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

static void fixture_wrapper_dispatch(void (*wrapper)(struct kd_regs *, unsigned long *),
				     struct kd_regs *regs, unsigned long *args)
{
	if (string_wrapper || origin_wrapper) {
		CHECK((void *)wrapper == string_wrapper_code);
		translated(regs, args);
	} else {
		wrapper(regs, args);
	}
}

/* This double returns a scripted boundary packet, without executing a source
 * instruction. The generated-code/restore fixtures supply that separate proof. */
static void fixture_root_escape_wrapper(struct kd_jit_batch_call *call)
{
	CHECK(call->regs == &active.regs &&
	      call->code == (char *)active.image->code + KD_JIT_CLOBBER_OFFSET);
	translated(call->regs, call->args);
	if (call->args[0] != KD_EXE_ENTRY_REFUSED)
		*call->packet_state = call->args[0] == KD_EXE_CLOBBER_COMPLETE ?
			KD_PACKET_COMPLETE : KD_PACKET_FULL;
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
/* Publication is exercised by test_mutex_images; generic control/ACK routes
 * use one descriptor per fixture registry slot. */
const struct kd_jit_image *kd_image_current(const struct kd_exe_info *exe)
{
	static struct kd_jit_image image[KD_MAX_EXE];
	struct kd_jit_image *slot = &image[exe - kd_exes];
	*slot = (struct kd_jit_image){ .code = exe->code_block,
		.entry = (struct kd_exe_info *)exe, .entry_abi = exe->entry_abi,
		.requirements = exe->requirements, .generation = exe->generation,
		.immutable = exe->lock_kind == KD_EXE_LOCK_MUTEX || exe->requirements,
		.near_text = !!(exe->requirements & KD_IMAGE_REQUIRE_DIRECT_STRINGS) };
	return slot;
}
void kd_image_report(struct kd_exe_info *exe, const struct kd_jit_image *image,
                     int status, unsigned long target, unsigned long from)
{
	(void)image;
	exe->tgt_addr = target;
	exe->jump_from = from;
	kd_exe_publish_status(exe, status);
}
void kd_image_disable(struct kd_exe_info *exe)
{
	kd_exe_publish_status(exe, KD_EXE_NATIVE_ONLY);
}
static bool is_end_point(unsigned long ip)
{
	return ip == 0x9000 ||
	       (root_escape_wrapper && ip == clobber_spin_unlock_addr);
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
#ifdef KD_BENCH_COMPLETION_FIXTURE
#define KD_PR_ROUTINE(...) KD_PR_INFO(__VA_ARGS__)
#include "bench_code.h"
#endif
#include "frame_code.h"

/* Keep independent entry, service, timing and backend cases together by purpose. */
#include "jit_entry_scope/reset.inc"
#include "jit_entry_scope/entry.inc"
#include "jit_entry_scope/hostcalls.inc"
#include "jit_entry_scope/timing.inc"
#include "jit_entry_scope/spin.inc"
#include "jit_entry_scope/mutex.inc"
#include "jit_entry_scope/native_escape.inc"
#include "jit_entry_scope/origin_instruction.inc"
#include "jit_entry_scope/root_native_escape.inc"
#include "jit_entry_scope/native_calls.inc"
#include "jit_entry_scope/address_guard.inc"
#include "jit_entry_scope/strings.inc"
#include "jit_entry_scope/string_copy.inc"
#include "jit_entry_scope/direct_strings.inc"
#ifdef KD_BENCH_COMPLETION_FIXTURE
#include "jit_entry_scope/bench_completion.inc"
#endif

int main(void)
{
	check_native_escape();
	check_origin_instruction();
	check_terminal_and_indirect_calls();
	check_retained_indirect_tails();
	check_current_position_misses();
	check_root_native_escape();
	check_address_guard();
	check_string_services();
	check_string_copy();
	check_direct_strings();
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
#ifdef KD_BENCH_COMPLETION_FIXTURE
	check_bench_completions();
#endif
	printf("production JIT entry scope: %d checks, %d failures\n", checks,
	       failures);
	return failures != 0;
}
