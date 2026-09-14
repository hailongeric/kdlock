/*
 * Critical-section registry and high-level JIT dispatcher (derived from BCD).
 * Read with sys.c for uploads and kd_exec.c for frame/owner lifetimes.
 *
 * Registration consumes one bounded code block; it does not compile text.
 * The daemon fills that block, then this file interprets wrapper exit packets:
 *   CALL_MISS: known lock control, or original-waiter native continuation;
 *   HOSTCALL: exact allowlisted service, then another wrapper invocation;
 *   ENTRY_REFUSED: native fallback only after validating an unstarted root;
 *   IJ_MISS / ERROR / INST_LIMIT: error, not generic native continuation.
 * The budget counts instrumented blocks, not retired instructions. NORMAL
 * remains a legacy syscall exit, unsupported for kernel critical sections.
 *
 * Only validated outer-unlock handling completes a delegated request. A miss
 * after stores never rolls them back or grants permission to replay the entry.
 * Code blocks are still overwritten in place; source pins are not versions.
 */
#include "exe.h"
#include "kd_exec.h"
#include "kd_source.h"

#include <asm/current.h>
#include <asm-generic/set_memory.h>
#include <linux/atomic.h>
#include <linux/kallsyms.h>
#include <linux/ktime.h>
#include <linux/limits.h>
#include <linux/math.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/ratelimit.h>
#include <linux/sched.h>
#include <linux/sched/task_stack.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/vmalloc.h>

#include "utils.h"
#include "kd_lock.h"
#include "kd_mutex.h"
#include "kd_spinlock.h"
#include "kd_hostcall.h"

/*
 * Pre-allocated pool of executable code blocks.  kd_exe_add() is called from
 * the lock hooks which may run with interrupts disabled, so vmalloc and
 * set_memory_x cannot be used there.  All blocks are allocated and marked
 * executable during kd_exe_init().
 */
#define KD_CODE_BLOCK_POOL 64
#define KD_CODE_BLOCK_PAGES (KD_CODE_BLOCK_SIZE / PAGE_SIZE)
#define KD_EXE_HL_MAX_CONTINUATIONS 16
#define KD_EXE_HL_MAX_HOSTCALLS 16

/* One-shot high-level JIT fault injection for nested recovery tests. */
static int kd_jit_hl_fault_after_known_call;
module_param_named(jit_hl_fault_after_known_call,
		   kd_jit_hl_fault_after_known_call, int, 0644);
MODULE_PARM_DESC(
	jit_hl_fault_after_known_call,
	"Inject after a known JIT call: 1=call miss, 2=IJ miss, 3=inst limit");

static void *kd_code_block_pool[KD_CODE_BLOCK_POOL];
static int kd_code_block_free;
static atomic_t kd_code_block_gate = ATOMIC_INIT(0);

static void kd_code_block_gate_lock(void)
{
	while (atomic_cmpxchg_acquire(&kd_code_block_gate, 0, 1))
		cpu_relax();
}

static void kd_code_block_gate_unlock(void)
{
	atomic_set_release(&kd_code_block_gate, 0);
}

static unsigned long end_points[4];
static int end_point_count;
static unsigned long raw_spin_lock_addr;
static unsigned long raw_spin_unlock_addr;
static unsigned long mutex_lock_addr;
static unsigned long mutex_unlock_addr;

struct kd_hostcall_desc {
	enum kd_hostcall_id id;
	const char *symbol;
	unsigned long addr;
	unsigned int flags;
	int (*invoke)(struct pt_regs *regs);
};

static atomic64_t kd_hostcall_exits;
static atomic64_t kd_hostcall_executed;
static atomic64_t kd_hostcall_resumed;
static atomic64_t kd_hostcall_rejected;
static atomic64_t kd_hostcall_failed;
static atomic64_t kd_hostcall_limit;

/* The same-device capability authorizes only bounded mutex stack facts, not
 * arbitrary callee memory preservation. Exclude the consumed CALL word, whose
 * identity is checked separately before JIT may resume. */
#define KD_MUTEX_CALL_STACK_BYTES KD_JIT_MUTEX_STACK_BYTES
struct kd_mutex_call_stack {
	struct kd_call_state call;
	unsigned char bytes[KD_MUTEX_CALL_STACK_BYTES];
};
static atomic64_t kd_mutex_stack_equal;
static atomic64_t kd_mutex_stack_changed;
static atomic64_t kd_mutex_stack_unavailable;

static int kd_hostcall_invoke_ktime_get(struct pt_regs *regs)
{
	regs->ax = (unsigned long)ktime_to_ns(ktime_get());
	return 0;
}

static int kd_hostcall_invoke_ktime_get_ns(struct pt_regs *regs)
{
	regs->ax = (unsigned long)ktime_get_ns();
	return 0;
}

/* x86-64 unsigned long: consume the full saved RDI and replace only RAX.
 * The native helper has at most 32 scalar iterations and no external memory,
 * sleeping or task/CPU-context dependency; it does not run on the waiter stack.
 * This CALL boundary requires no new flags or memory-access recovery contract.
 */
static int kd_hostcall_invoke_int_sqrt(struct pt_regs *regs)
{
	regs->ax = int_sqrt(regs->di);
	return 0;
}

static struct kd_hostcall_desc kd_hostcalls[] = {
#define KD_HOSTCALL(name, service_id, service_symbol, service_flags) \
	{ KD_HOSTCALL_##name, #service_symbol, 0, service_flags,     \
	  kd_hostcall_invoke_##service_symbol },
#include "kd_hostcalls.def"
#undef KD_HOSTCALL
};

static const struct kd_hostcall_desc *kd_hostcall_lookup(unsigned long addr)
{
	int i;

	for (i = 0; i < ARRAY_SIZE(kd_hostcalls); i++)
		if (kd_hostcalls[i].addr && kd_hostcalls[i].addr == addr)
			return &kd_hostcalls[i];
	return NULL;
}

/* Quota exits must validate the same service contract without invoking it. */
static int kd_hostcall_validate(const struct kd_hostcall_desc *service)
{
	const unsigned int required_flags = KD_HOSTCALL_F_ATOMIC_SAFE |
					    KD_HOSTCALL_F_NO_TASK_CONTEXT |
					    KD_HOSTCALL_F_RETRY_SAFE;

	if (!service)
		return -ENOENT;
	if ((service->flags & required_flags) != required_flags)
		return -EPERM;
	return 0;
}

static int kd_hostcall_dispatch(struct pt_regs *regs)
{
	const struct kd_hostcall_desc *service = kd_hostcall_lookup(regs->ip);
	int ret = kd_hostcall_validate(service);

	if (ret)
		return ret;
	return service->invoke(regs);
}

/* Optional inclusive C-boundary timings, not instruction or CPU time.
 * Load-time selection keeps every invocation in one session under the same
 * policy. Disabled invocations take no extra clock samples or atomic updates.
 * Nested dispatch/control intervals may overlap; never sum them as wall time.
 * Measurement failure cannot change an execution, replay or owner decision. */
enum kd_jit_timing_phase {
	KD_JIT_TIME_DISPATCH,
	KD_JIT_TIME_WRAPPER,
	KD_JIT_TIME_HOSTCALL,
	KD_JIT_TIME_CONTROL,
	KD_JIT_TIME_NATIVE_SPIN_WAIT,
	KD_JIT_TIME_NATIVE_MUTEX_WAIT,
	KD_JIT_TIME_SPIN_QUEUE,
	KD_JIT_TIME_MUTEX_QUEUE,
	KD_JIT_TIME_NATIVE_SPIN_HANDOFF,
	KD_JIT_TIME_NATIVE_MUTEX_HANDOFF,
	KD_JIT_TIME_COUNT,
};
static bool kd_jit_timing;
module_param_named(jit_timing, kd_jit_timing, bool, 0444);
MODULE_PARM_DESC(jit_timing, "Collect inclusive JIT boundary timings at unload");

static struct kd_jit_timing_stat {
	atomic64_t samples;
	atomic64_t ns;
	atomic_t invalid;
} kd_jit_times[KD_JIT_TIME_COUNT];

static inline u64 kd_jit_timing_start(void)
{
	return unlikely(kd_jit_timing) ? ktime_get_ns() : 0;
}

/* Keep overflow visible without wrapping signed counters or failing a CS. */
static inline void kd_jit_timing_add(struct kd_jit_timing_stat *stat,
				     atomic64_t *counter, u64 amount)
{
	s64 old = atomic64_read(counter);

	for (;;) {
		if (old < 0 || amount > (u64)(S64_MAX - old)) {
			atomic_set(&stat->invalid, 1);
			return;
		}
		if (atomic64_try_cmpxchg(counter, &old, old + (s64)amount))
			return;
	}
}

/* Queue service is confirmed only after dispatch returns. Accept the saved
 * pre-dispatch endpoint so the generated body is not charged as queue wait. */
static inline void kd_jit_timing_record(enum kd_jit_timing_phase phase,
				       u64 start, u64 end)
{
	struct kd_jit_timing_stat *stat = &kd_jit_times[phase];

	kd_jit_timing_add(stat, &stat->samples, 1);
	if (end < start) {
		atomic_set(&stat->invalid, 1);
		return;
	}
	kd_jit_timing_add(stat, &stat->ns, end - start);
}

static inline void kd_jit_timing_end(enum kd_jit_timing_phase phase, u64 start)
{
	if (likely(!kd_jit_timing))
		return;
	kd_jit_timing_record(phase, start, ktime_get_ns());
}

static inline void kd_jit_timing_reset(void)
{
	int i;

	for (i = 0; i < KD_JIT_TIME_COUNT; i++) {
		atomic64_set(&kd_jit_times[i].samples, 0);
		atomic64_set(&kd_jit_times[i].ns, 0);
		atomic_set(&kd_jit_times[i].invalid, 0);
	}
}

/* Teardown follows drain: paired readers require exactly one row per phase,
 * including zero rows for a native-only session with measurement enabled. */
static inline void kd_jit_timing_report(void)
{
	/* Bind log labels to their counters explicitly: declaration order must
	 * not silently relabel an interval consumed by the evidence observer. */
	static const char * const names[KD_JIT_TIME_COUNT] = {
		[KD_JIT_TIME_DISPATCH] = "dispatch",
		[KD_JIT_TIME_WRAPPER] = "wrapper",
		[KD_JIT_TIME_HOSTCALL] = "hostcall",
		[KD_JIT_TIME_CONTROL] = "control",
		[KD_JIT_TIME_NATIVE_SPIN_WAIT] = "native_spin_wait",
		[KD_JIT_TIME_NATIVE_MUTEX_WAIT] = "native_mutex_wait",
		[KD_JIT_TIME_SPIN_QUEUE] = "spin_queue",
		[KD_JIT_TIME_MUTEX_QUEUE] = "mutex_queue",
		[KD_JIT_TIME_NATIVE_SPIN_HANDOFF] = "native_spin_handoff",
		[KD_JIT_TIME_NATIVE_MUTEX_HANDOFF] = "native_mutex_handoff",
	};
	int i;

	if (!kd_jit_timing)
		return;
	for (i = 0; i < KD_JIT_TIME_COUNT; i++)
		KD_PR_INFO("kd_jit timing: phase=%s samples=%lld ns=%lld invalid=%d\n",
			   names[i],
			   (long long)atomic64_read(&kd_jit_times[i].samples),
			   (long long)atomic64_read(&kd_jit_times[i].ns),
			   atomic_read(&kd_jit_times[i].invalid));
}

/* Keep metrics private to the executor. The shared owner wait uses only a
 * local timestamp/backend, never waiter storage that the final ACK releases. */
u64 kd_exe_native_timing_start(void)
{
	return kd_jit_timing_start();
}

void kd_exe_native_timing_end(bool mutex, u64 start)
{
	kd_jit_timing_end(mutex ? KD_JIT_TIME_NATIVE_MUTEX_WAIT :
				 KD_JIT_TIME_NATIVE_SPIN_WAIT, start);
}

/* This contains, rather than adds to, the owner-wait interval. The caller
 * captures start before either remote or local waiter publication and supplies
 * no waiter/node pointer after ACK. Nested remote envelopes may overlap. */
void kd_exe_native_handoff_timing_end(bool mutex, u64 start)
{
	kd_jit_timing_end(mutex ? KD_JIT_TIME_NATIVE_MUTEX_HANDOFF :
				 KD_JIT_TIME_NATIVE_SPIN_HANDOFF, start);
}

u64 kd_exe_queue_timing_start(void)
{
	return kd_jit_timing_start();
}

/* The queue owner and waiter consume this field in protocol order, not
 * concurrently: dispatch finishes before wake; acquisition precedes node reuse.
 * Zero means disabled, not queued or already accounted. Module-loaded clocks
 * use nonzero monotonic uptime. Measurements never decide ownership or replay. */
void kd_exe_queue_timing_end(bool mutex, u64 *queued_at, u64 end)
{
	u64 start;

	if (likely(!kd_jit_timing) || !*queued_at)
		return;
	start = *queued_at;
	*queued_at = 0;
	kd_jit_timing_record(mutex ? KD_JIT_TIME_MUTEX_QUEUE :
				    KD_JIT_TIME_SPIN_QUEUE, start, end);
}

static struct kd_exe_info *kd_exes;

struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip)
{
	int pos;
	int probes;

	if (!kd_exes)
		return NULL;
	pos = zz_hash(pid, ip) % KD_MAX_EXE;
	for (probes = 0; probes < KD_MAX_EXE; probes++) {
		struct kd_exe_info *exe = &kd_exes[pos];

		if (READ_ONCE(exe->status_code) == KD_EXE_UNUSED ||
		    (READ_ONCE(exe->pid) == pid && READ_ONCE(exe->RIP) == ip))
			return exe;
		pos = (pos + 1) % KD_MAX_EXE;
	}
	return NULL;
}

const struct kd_exe_info *kd_exe_get_slot(unsigned int index)
{
	if (!kd_exes || index >= KD_MAX_EXE)
		return NULL;
	return &kd_exes[index];
}

/* Policy rejection is terminal even if an older executor reports a miss. */
bool kd_exe_publish_status(struct kd_exe_info *exe, int status)
{
	int old = smp_load_acquire(&exe->status_code);

	for (;;) {
		if (old == KD_EXE_NATIVE_ONLY)
			return status == KD_EXE_NATIVE_ONLY;
		if (try_cmpxchg(&exe->status_code, &old, status))
			return true;
	}
}

bool kd_exe_is_ready(unsigned int pid, unsigned long ip)
{
	struct kd_exe_info *exe;

	if (!kd_exes || !ip || !kd_source_is_open())
		return false;
	exe = kd_get_exe(pid, ip);
	if (!exe)
		return false;
	if (smp_load_acquire(&exe->status_code) != KD_EXE_NORMAL)
		return false;
	return READ_ONCE(exe->pid) == pid && READ_ONCE(exe->RIP) == ip &&
	       READ_ONCE(exe->code_block) != NULL;
}

int kd_exe_init(void)
{
	int i, ret;

	kd_jit_timing_reset();
	/* Resolve unlock function addresses dynamically */
	end_point_count = 0;
	raw_spin_lock_addr = kallsyms_lookup_name("_raw_spin_lock");
	raw_spin_unlock_addr = kallsyms_lookup_name("_raw_spin_unlock");
	end_points[end_point_count] = raw_spin_unlock_addr;
	if (raw_spin_unlock_addr)
		end_point_count++;
	mutex_lock_addr = kallsyms_lookup_name("mutex_lock");
	mutex_unlock_addr = kallsyms_lookup_name("mutex_unlock");
	end_points[end_point_count] = mutex_unlock_addr;
	if (mutex_unlock_addr)
		end_point_count++;
	for (i = 0; i < end_point_count; i++)
		KD_PR_INFO("end_point[%d] = %lx", i, end_points[i]);
	if (mutex_lock_addr)
		KD_PR_INFO("mutex_lock addr = %lx", mutex_lock_addr);

	atomic64_set(&kd_hostcall_exits, 0);
	atomic64_set(&kd_hostcall_executed, 0);
	atomic64_set(&kd_hostcall_resumed, 0);
	atomic64_set(&kd_hostcall_rejected, 0);
	atomic64_set(&kd_hostcall_failed, 0);
	atomic64_set(&kd_hostcall_limit, 0);
	atomic64_set(&kd_mutex_stack_equal, 0);
	atomic64_set(&kd_mutex_stack_changed, 0);
	atomic64_set(&kd_mutex_stack_unavailable, 0);
	for (i = 0; i < ARRAY_SIZE(kd_hostcalls); i++) {
		kd_hostcalls[i].addr =
			kallsyms_lookup_name(kd_hostcalls[i].symbol);
		if (kd_hostcalls[i].addr)
			KD_PR_INFO(
				"hostcall service id=%u symbol=%s addr=%lx flags=%x\n",
				kd_hostcalls[i].id, kd_hostcalls[i].symbol,
				kd_hostcalls[i].addr, kd_hostcalls[i].flags);
		else
			KD_PR_INFO(
				"hostcall service unavailable id=%u symbol=%s\n",
				kd_hostcalls[i].id, kd_hostcalls[i].symbol);
	}

	kd_exes = vzalloc(sizeof(struct kd_exe_info) * KD_MAX_EXE);
	if (!kd_exes)
		return -ENOMEM;
	for (i = 0; i < KD_MAX_EXE; i++) {
		kd_exes[i].status_code = KD_EXE_UNUSED;
		kd_exes[i].code_block = NULL;
	}

	/* Lock hooks cannot allocate executable memory with IRQs disabled. */
	atomic_set(&kd_code_block_gate, 0);
	kd_code_block_free = 0;
	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		void *block = vmalloc(KD_CODE_BLOCK_SIZE);

		if (!block)
			continue;
		ret = set_memory_x((unsigned long)block, KD_CODE_BLOCK_PAGES);
		if (ret) {
			vfree(block);
			continue;
		}
		kd_code_block_pool[kd_code_block_free++] = block;
	}
	KD_PR_INFO("JIT code block pool ready: %d/%d\n", kd_code_block_free,
		   KD_CODE_BLOCK_POOL);
	if (!kd_code_block_free) {
		vfree(kd_exes);
		kd_exes = NULL;
		return -ENOMEM;
	}

	return 0;
}

void kd_exe_exit(void)
{
	int i;

	kd_jit_timing_report();
	KD_PR_INFO(
		"kd_hostcall stats: exits=%lld executed=%lld resumed=%lld rejected=%lld failed=%lld limit=%lld\n",
		(long long)atomic64_read(&kd_hostcall_exits),
		(long long)atomic64_read(&kd_hostcall_executed),
		(long long)atomic64_read(&kd_hostcall_resumed),
		(long long)atomic64_read(&kd_hostcall_rejected),
		(long long)atomic64_read(&kd_hostcall_failed),
		(long long)atomic64_read(&kd_hostcall_limit));
	KD_PR_INFO(
		"kd_mutex stack checks: bytes=%u equal=%lld changed=%lld unavailable=%lld\n",
		KD_MUTEX_CALL_STACK_BYTES,
		(long long)atomic64_read(&kd_mutex_stack_equal),
		(long long)atomic64_read(&kd_mutex_stack_changed),
		(long long)atomic64_read(&kd_mutex_stack_unavailable));

	vfree(kd_exes);
	kd_exes = NULL;

	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		vfree(kd_code_block_pool[i]);
		kd_code_block_pool[i] = NULL;
	}
	kd_code_block_free = 0;
}

static int is_end_point(unsigned long addr)
{
	int i;

	for (i = 0; i < end_point_count; i++)
		if (addr == end_points[i])
			return 1;
	return 0;
}

static int is_outer_lock_unlock(struct pt_regs *regs,
				unsigned long outer_lock_addr)
{
	if (regs->ip != raw_spin_unlock_addr && regs->ip != mutex_unlock_addr)
		return 0;
	if (!outer_lock_addr)
		return 1;
	return regs->di == outer_lock_addr;
}

static int advance_after_known_call(struct pt_regs *regs)
{
	unsigned long return_ip;

	if (regs->sp == 0)
		return -EINVAL;

	return_ip = READ_ONCE(*(unsigned long *)regs->sp);
	regs->sp += sizeof(unsigned long);
	regs->ip = return_ip;
	return 1;
}

static int advance_and_save_continuation(struct kd_exec_frame *frame,
					 struct pt_regs *regs)
{
	int ret = advance_after_known_call(regs);

	if (ret > 0 && frame)
		kd_exec_frame_save_continuation(frame, regs);
	return ret;
}

static int finish_acquired_spin_call(struct kd_exec_frame *frame,
				     struct pt_regs *regs, int result)
{
	const struct kd_call_state *call;
	unsigned long base, end, return_ip, lock;
	unsigned int index;

	/* Only the local post-acquisition EIO boundary can use this path. A
	 * generic ACQUIRED tag is insufficient: partial ledger publication,
	 * remote requests, a changed CALL word or another owner stay fail-stop.
	 * Nothing is undone and B must never be acquired a second time. */
	if (result != -EIO || !frame || frame->mutex_backend ||
	    !kd_exec_frame_can_borrow_locks(frame) ||
	    frame->logical_task == current ||
	    kd_exec_frame_remote_pending(frame) || frame->remote_request ||
	    frame->jit_lock_depth <= frame->outer_lock_index + 1)
		return result;
	call = &frame->control_call;
	if (call->phase != KD_CALL_ACQUIRED ||
	    call->target != raw_spin_lock_addr ||
	    !kd_call_after_matches(call, regs->ip, regs->sp))
		return result;
	index = frame->jit_lock_depth - 1;
	lock = frame->jit_lock_addr[index];
	if (!lock || lock != regs->di || frame->jit_lock_released[index] ||
	    frame->jit_lock_node[index] ||
	    (frame->jit_lock_kind[index] != KD_EXEC_LOCK_FAST &&
	     frame->jit_lock_kind[index] != KD_EXEC_LOCK_QUEUE_OWNER) ||
	    kd_spin_debug_owner((raw_spinlock_t *)lock) !=
		    (unsigned long)current ||
	    !(kd_spin_debug_word((raw_spinlock_t *)lock) & 0xff))
		return result;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return result;
	end = base + THREAD_SIZE;
	if (call->stack < base || call->stack > end - sizeof(return_ip) ||
	    copy_from_kernel_nofault(&return_ip, (void *)call->stack,
				     sizeof(return_ip)) ||
	    return_ip != call->return_ip)
		return result;
	frame->control_call.phase = KD_CALL_SPIN_NATIVE;
	kd_exec_frame_save_continuation(frame, regs);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=SPIN_ACQUIRED_NATIVE entry=0x%lx target=0x%lx lock=0x%lx ip=0x%lx sp=0x%lx call_sp=0x%lx return=0x%lx owner=0x%lx task=%d\n",
		frame->entry_ip, call->target, lock, regs->ip, regs->sp,
		call->stack, return_ip, (unsigned long)current,
		frame->logical_task->pid);
	return KD_EXE_KNOWN_NATIVE;
}

static int finish_known_lock_call(struct kd_exec_frame *frame,
				  struct pt_regs *regs, int result)
{
	unsigned long staged_ip = regs->ip, staged_sp = regs->sp;
	int acquired = finish_acquired_spin_call(frame, regs, result);

	if (acquired != result)
		return acquired;

	if (result >= 0 || !kd_exec_frame_can_borrow_locks(frame) ||
	    !kd_call_resume_pending(&frame->control_call, result, &regs->ip,
				    &regs->sp))
		return result;
	kd_exec_frame_save_continuation(frame, regs);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=PENDING_LOCK_NATIVE entry=0x%lx target=0x%lx sp=0x%lx return=0x%lx staged_ip=0x%lx staged_sp=0x%lx mutex=%u error=%d outer_released=%u task=%d\n",
		frame->entry_ip, regs->ip, regs->sp,
		frame->control_call.return_ip, staged_ip, staged_sp,
		frame->mutex_backend, result, frame->outer_unlock_seen,
		frame->logical_task->pid);
	return KD_EXE_KNOWN_NATIVE;
}

static int kd_mutex_stack_prepare(struct kd_exec_frame *frame,
				  struct pt_regs *regs,
				  struct kd_mutex_call_stack *saved)
{
	unsigned long base, end, return_ip;

	/* The waiter cannot retire its kernel stack before this delegated request
	 * completes. Bound every read to that stack, not the combiner's shadow
	 * stack, and do not infer that the range is private to the waiter. */
	if (!kd_exec_frame_can_borrow_locks(frame) || !frame->mutex_backend ||
	    frame->logical_task == current)
		return -EINVAL;
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	if (regs->sp < base || regs->sp > end - sizeof(return_ip) ||
	    copy_from_kernel_nofault(&return_ip, (void *)regs->sp,
				     sizeof(return_ip)))
		return -EFAULT;
	if (kd_call_begin(&saved->call, regs->ip, regs->sp, return_ip))
		return -EINVAL;
	frame->control_call = saved->call;
	if (end - regs->sp - sizeof(return_ip) < sizeof(saved->bytes)) {
		/* No control side effect yet: use the real PENDING packet, not a
		 * fabricated allocation failure or an entry replay. */
		kd_exec_frame_save_continuation(frame, regs);
		atomic64_inc(&kd_mutex_stack_unavailable);
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=MUTEX_STACK_UNAVAILABLE entry=0x%lx target=0x%lx sp=0x%lx task=%d\n",
			frame->entry_ip, regs->ip, regs->sp,
			frame->logical_task->pid);
		return KD_EXE_KNOWN_NATIVE;
	}
	return copy_from_kernel_nofault(saved->bytes,
					(void *)(regs->sp + sizeof(return_ip)),
					sizeof(saved->bytes)) ?
		       -EFAULT :
		       0;
}

static int kd_mutex_stack_finish(struct kd_exec_frame *frame,
				 struct pt_regs *regs,
				 const struct kd_mutex_call_stack *saved)
{
	unsigned char after[KD_MUTEX_CALL_STACK_BYTES];
	unsigned long return_ip;
	const struct kd_call_state *call = &frame->control_call;

	/* Compare after the real operation, never restore its writes. A changed
	 * CALL token or post-CALL packet is not an authorized native continuation. */
	if (call->phase != KD_CALL_COMPLETE ||
	    call->target != saved->call.target ||
	    call->stack != saved->call.stack ||
	    call->return_ip != saved->call.return_ip ||
	    !kd_call_after_matches(call, regs->ip, regs->sp) ||
	    copy_from_kernel_nofault(&return_ip, (void *)call->stack,
				     sizeof(return_ip)) ||
	    return_ip != call->return_ip ||
	    copy_from_kernel_nofault(after, (void *)regs->sp, sizeof(after)))
		return -EINVAL;
	if (!memcmp(saved->bytes, after, sizeof(after))) {
		atomic64_inc(&kd_mutex_stack_equal);
		return 1;
	}
	if (!kd_exec_frame_can_borrow_locks(frame))
		return -EINVAL;
	frame->control_call.phase = KD_CALL_STACK_CHANGED;
	kd_exec_frame_save_continuation(frame, regs);
	atomic64_inc(&kd_mutex_stack_changed);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=MUTEX_STACK_CHANGED entry=0x%lx target=0x%lx ip=0x%lx sp=0x%lx task=%d\n",
		frame->entry_ip, call->target, regs->ip, regs->sp,
		frame->logical_task->pid);
	return KD_EXE_KNOWN_NATIVE;
}

static int handle_known_mutex_call(struct kd_exec_frame *frame,
				   struct pt_regs *regs,
				   unsigned long outer_lock_addr)
{
	struct kd_mutex_call_stack saved;
	int ret;

	/* Final outer completion does not resume this JIT, so needs no memory
	 * preservation check. All other local mutex controls use one checkpoint. */
	if (regs->ip == mutex_unlock_addr && regs->di == outer_lock_addr &&
	    !kd_exec_frame_has_unreleased_nested(frame))
		return KD_EXE_KNOWN_OUTER_UNLOCK;
	ret = kd_mutex_stack_prepare(frame, regs, &saved);
	if (ret)
		return ret;
	if (regs->ip == mutex_lock_addr) {
		ret = kd_mutex_jit_nested_lock_ctx((struct mutex *)regs->di,
						   regs, frame);
		ret = finish_known_lock_call(frame, regs, ret);
	} else {
		frame->control_call.phase = KD_CALL_ENTERED;
		if (regs->di == outer_lock_addr) {
			/* Opening A may let another batch run while B stays owned. */
			ret = kd_exec_frame_record_event(
				frame, KD_EXEC_EVENT_OUTER_UNLOCK, regs);
		} else {
			ret = kd_mutex_jit_nested_unlock_ctx(
				(struct mutex *)regs->di, frame);
			if (!ret)
				kd_mutex_note_nested_jit();
		}
		if (ret)
			return ret;
		/* The waiter's completion trampoline consumes the final B CALL. */
		if (kd_exec_frame_can_complete(frame))
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		ret = advance_and_save_continuation(frame, regs);
		if (ret > 0)
			frame->control_call.phase = KD_CALL_COMPLETE;
	}
	if (ret != 1)
		return ret;
	return kd_mutex_stack_finish(frame, regs, &saved);
}

static int handle_known_call(struct pt_regs *regs,
			     unsigned long outer_lock_addr)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();
	int ret;

	if (frame)
		frame->control_call.phase = KD_CALL_NONE;

	/* Backend-specific lock stacks cannot represent mixed spin/mutex nesting.
	 * In particular, never enter a sleeping mutex service from a spin frame. */
	if (frame &&
	    ((frame->mutex_backend && (regs->ip == raw_spin_lock_addr ||
				       regs->ip == raw_spin_unlock_addr)) ||
	     (!frame->mutex_backend && mutex_lock_addr && mutex_unlock_addr &&
	      (regs->ip == mutex_lock_addr || regs->ip == mutex_unlock_addr))))
		return -EOPNOTSUPP;

	if (regs->ip == raw_spin_lock_addr) {
		ret = kd_spin_jit_nested_lock_ctx((raw_spinlock_t *)regs->di,
						  regs, frame);
		return finish_known_lock_call(frame, regs, ret);
	}

	if (regs->ip == raw_spin_unlock_addr) {
		if (regs->di == outer_lock_addr) {
			/* An early outer unlock is a real OOO release.  Keep executing
			 * until every nested lock has released, then finish A once. */
			if (frame &&
			    kd_exec_frame_has_unreleased_nested(frame)) {
				ret = kd_spin_jit_outer_unlock_ooo_ctx(
					(raw_spinlock_t *)regs->di, regs,
					frame);
				if (ret)
					return ret;
				return advance_and_save_continuation(frame,
								     regs);
			}
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		}
		ret = kd_spin_jit_nested_unlock_ctx((raw_spinlock_t *)regs->di,
						    frame);
		return ret ? ret : advance_and_save_continuation(frame, regs);
	}

	if (!mutex_lock_addr || !mutex_unlock_addr)
		return 0;

	if (regs->ip != mutex_lock_addr && regs->ip != mutex_unlock_addr)
		return 0;

	return handle_known_mutex_call(frame, regs, outer_lock_addr);
}

/* Include control classification, blocking and nested execution, but not the
 * backend's later original-waiter native suffix/ACK wait after dispatch exits. */
static int kd_jit_timed_control(struct pt_regs *regs, unsigned long outer)
{
	u64 start = kd_jit_timing_start();
	int ret = handle_known_call(regs, outer);

	kd_jit_timing_end(KD_JIT_TIME_CONTROL, start);
	return ret;
}

void kd_exe_add(int pid, unsigned long rip, enum kd_exe_lock_kind kind)
{
	void *mem = NULL;
	struct kd_exe_info *exe;
	int ret;

	if (kind != KD_EXE_LOCK_SPIN && kind != KD_EXE_LOCK_MUTEX)
		return;
	kd_code_block_gate_lock();
	ret = kd_source_pin_root(rip);
	if (ret) {
		kd_code_block_gate_unlock();
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=SOURCE_ROOT_REFUSED entry=0x%lx error=%d\n",
			rip, ret);
		return;
	}
	exe = kd_get_exe(pid, rip);
	if (!exe) {
		kd_code_block_gate_unlock();
		KD_PR_ERR("kd_exe_add: translation table exhausted\n");
		return;
	}
	if (exe->pid == pid && exe->RIP == rip) {
		/* A RIP may be shared by locks, but not by incompatible backends. */
		if (exe->lock_kind != kind) {
			kd_exe_publish_status(exe, KD_EXE_NATIVE_ONLY);
			pr_warn_ratelimited(
				"[KD_JIT][WARN] reason=ENTRY_LOCK_KIND_CONFLICT entry=0x%lx registered=%d requested=%d\n",
				rip, exe->lock_kind, kind);
		}
		kd_code_block_gate_unlock();
		return;
	}

	if (exe->status_code != KD_EXE_UNUSED)
		KD_PR_ERR(
			"translation slot collision: status=%d old=%d/%lx new=%d/%lx\n",
			exe->status_code, exe->pid, exe->RIP, pid, rip);

	/* The pool makes registration safe while a lock hook has IRQs disabled. */
	if (kd_code_block_free > 0)
		mem = kd_code_block_pool[--kd_code_block_free];

	if (!mem) {
		kd_code_block_gate_unlock();
		/* Identify the rejected root without publishing a partial entry or
		 * evicting an image still used by an older execution/native frame. */
		KD_PR_ERR(
			"kd_exe_add: code block pool exhausted entry=%lx task=%d kind=%d\n",
			rip, current->pid, kind);
		return;
	}

	exe->pid = pid;
	exe->RIP = rip;
	exe->tgid = current->tgid;
	exe->lock_kind = kind;
	exe->code_block = mem;

	smp_store_release(&exe->status_code, KD_EXE_UNINIT);
	kd_code_block_gate_unlock();
	KD_PR_INFO("exe added %d %lx %d lock_kind=%d\n", pid, rip,
		   current->tgid, kind);
}

void kd_exe_retire_all(void)
{
	unsigned int i;

	/* Closing precedes this gate, so a racing registration either finishes
	 * before invalidation or refuses. Slots/images are not reused in-session. */
	kd_code_block_gate_lock();
	for (i = 0; kd_exes && i < KD_MAX_EXE; i++)
		if (READ_ONCE(kd_exes[i].status_code) != KD_EXE_UNUSED)
			kd_exe_publish_status(&kd_exes[i], KD_EXE_NATIVE_ONLY);
	kd_code_block_gate_unlock();
}

/* Only abnormal exits log here. Saved flags are not live execution evidence. */
static void kd_jit_log_hl_error(const char *reason,
				const struct kd_exec_frame *frame,
				const struct pt_regs *regs,
				unsigned long raw_exit, long detail,
				int continuations, int hostcalls)
{
	pr_err_ratelimited(
		"[KD_JIT][ERROR] reason=%s path=high entry=0x%lx rip=0x%lx executor_pid=%d waiter_pid=%d outer=0x%lx depth=%u raw_exit=0x%lx detail=%ld continuations=%d hostcalls=%d continuation_limit=%d hostcall_limit=%d control_phase=%u\n",
		reason, frame->entry_ip, regs->ip, current->pid,
		frame->logical_task->pid, frame->outer_lock_addr, frame->depth,
		raw_exit, detail, continuations, hostcalls,
		KD_EXE_HL_MAX_CONTINUATIONS, KD_EXE_HL_MAX_HOSTCALLS,
		frame->control_call.phase);
}

/* A non-root first dispatch is valid only for the published logical child of
 * a root invocation which already returned through a known lock CALL. A CPU-
 * local physical parent is not that proof. This establishes logical scope,
 * not immutable code identity; in-place publication remains a separate limit.
 */
static bool kd_jit_entry_has_scope(const struct kd_exec_frame *frame,
				   const struct pt_regs *regs,
				   unsigned long entry_ip)
{
	const struct kd_exec_frame *parent = frame->resume_target;

	if (!entry_ip || !regs->sp || frame->executed ||
	    kd_exec_frame_state(frame) != KD_EXEC_FRAME_RUNNING ||
	    frame->outer_unlock_seen || frame->entry_ip != entry_ip ||
	    frame->control_call.phase != KD_CALL_NONE)
		return false;
	if (!parent)
		return regs->ip == entry_ip;
	if (parent == frame || frame->mutex_backend ||
	    smp_load_acquire(&parent->remote_result) != KD_EXEC_REMOTE_WAITING)
		return false;
	return kd_exec_frame_validate(parent) && !parent->mutex_backend &&
	       !parent->completion_seen &&
	       kd_exec_frame_state(parent) != KD_EXEC_FRAME_ERROR &&
	       parent->executed && parent->entry_ip == entry_ip &&
	       parent->logical_task == frame->logical_task &&
	       parent->gsbase == frame->gsbase &&
	       parent->control_call.phase == KD_CALL_ENTERED &&
	       parent->control_call.return_ip == regs->ip &&
	       parent->control_call.stack + sizeof(unsigned long) == regs->sp &&
	       parent->regs.ip == regs->ip && parent->regs.sp == regs->sp &&
	       parent->regs.di == frame->outer_lock_addr &&
	       parent->outer_lock_index < frame->outer_lock_index;
}

/* The excess CALL has not executed: retain its pushed return word and let the
 * original waiter run this callee and the native suffix. This is not an exit
 * from an arbitrary instruction/budget trap and needs no new flags contract. */
static int kd_jit_call_limit_native(struct kd_exec_frame *frame,
				    struct pt_regs *regs, bool hostcall)
{
	unsigned long base, end, return_ip;
	int ret;

	if (!regs || !regs->ip || !kd_exec_frame_can_borrow_locks(frame) ||
	    !frame->executed || frame->logical_task == current ||
	    kd_exec_frame_remote_pending(frame) || frame->remote_request ||
	    frame->native_request ||
	    (frame->control_call.phase != KD_CALL_NONE &&
	     frame->control_call.phase != KD_CALL_COMPLETE))
		return -EINVAL;
	if (hostcall) {
		ret = kd_hostcall_validate(kd_hostcall_lookup(regs->ip));
		if (ret)
			return ret;
	}
	base = (unsigned long)task_stack_page(frame->logical_task);
	if (!base || base > ~0UL - THREAD_SIZE)
		return -EFAULT;
	end = base + THREAD_SIZE;
	if (regs->sp < base || regs->sp > end - sizeof(return_ip) ||
	    copy_from_kernel_nofault(&return_ip, (void *)regs->sp,
				     sizeof(return_ip)) || !return_ip)
		return -EFAULT;
	ret = kd_source_pin_target(regs->ip);
	if (!ret)
		ret = kd_source_pin_target(return_ip);
	if (ret)
		return ret;

	/* A previous control CALL may be COMPLETE; it does not describe this new
	 * unexecuted CALL. Do not pop the word, replay stores or request learning. */
	frame->control_call.phase = KD_CALL_NONE;
	kd_exec_frame_save_continuation(frame, regs);
	pr_warn_ratelimited(
		"[KD_JIT][WARN] reason=CALL_LIMIT_NATIVE entry=0x%lx ip=0x%lx sp=0x%lx return=0x%lx lock=0x%lx task=%d hostcall=%u\n",
		frame->entry_ip, regs->ip, regs->sp, return_ip,
		frame->outer_lock_addr, frame->logical_task->pid, hostcall);
	return 0;
}

/* One logical invocation may cross several control/hostcall wrapper returns.
 * Keep exit classification here: backends must not infer replay permission
 * from an error number or from the optional generated-body witness. */
int kd_exe_on_call_hl_entry(struct pt_regs *regs, unsigned long entry_ip,
			    unsigned long outer_lock_addr)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();
	void (*translated)(struct pt_regs *regs, unsigned long *args);
	struct kd_exe_info *exe;
	unsigned long args[2];
	int continuation_count = 0;
	int hostcall_count = 0;
	bool resume_after_hostcall = false;
	bool body_reported = false;
	bool pristine_root;
	u64 dispatch_start;
	int ret_flag;

	if (!regs || !frame || !kd_exec_frame_validate(frame) ||
	    !frame->gsbase || !frame->logical_task)
		return KD_EXE_RUN_ERROR;

	/* Kernel critical sections share translations by RIP, independent of PID. */
	exe = kd_get_exe(0, entry_ip);
	if (!exe || !kd_exe_is_ready(0, entry_ip)) {
		if (!exe) {
			KD_PR_INFO("translation table exhausted: entry=%lx\n",
				   entry_ip);
			return KD_EXE_NO_RUN;
		}
		KD_PR_INFO(
			"translation not ready: exe=%px status=%d entry=%lx ip=%lx pid=%d\n",
			exe, exe->status_code, exe->RIP, regs->ip, exe->pid);
		return KD_EXE_NO_RUN;
	}

	if (READ_ONCE(exe->lock_kind) !=
	    (frame->mutex_backend ? KD_EXE_LOCK_MUTEX : KD_EXE_LOCK_SPIN)) {
		kd_exe_publish_status(exe, KD_EXE_NATIVE_ONLY);
		pr_warn_ratelimited(
			"[KD_JIT][WARN] reason=FRAME_LOCK_KIND_MISMATCH entry=0x%lx registered=%d mutex_frame=%d\n",
			entry_ip, exe->lock_kind, frame->mutex_backend);
		return KD_EXE_NO_RUN;
	}
	if (!kd_jit_entry_has_scope(frame, regs, entry_ip)) {
		kd_jit_log_hl_error("ENTRY_SCOPE_MISMATCH", frame, regs, 0,
				    -EINVAL, 0, 0);
		return KD_EXE_NO_RUN;
	}
	/* Exclude pre-entry rejections and the caller's frame setup/teardown. */
	dispatch_start = kd_jit_timing_start();
	pristine_root = !frame->resume_target && regs->ip == entry_ip;
	translated = exe->code_block;
	for (;;) {
		int call_ret;
		int fault_kind;
		unsigned long entry_sp = regs->sp;
		u64 boundary_start;

		args[0] = frame->gsbase;
		args[1] = (unsigned long)frame->logical_task;
		fault_kind =
			continuation_count > 0 ?
				xchg(&kd_jit_hl_fault_after_known_call, 0) :
				0;
		if (unlikely(fault_kind)) {
			KD_PR_INFO(
				"JIT injected runtime fault: kind=%d entry=%lx ip=%lx outer=%lx\n",
				fault_kind, entry_ip, regs->ip,
				outer_lock_addr);
			switch (fault_kind) {
			case 1:
				args[0] = KD_EXE_CALL_MISS;
				break;
			case 2:
				args[0] = entry_ip;
				break;
			case 3:
				args[0] = KD_EXE_INST_LIMIT;
				break;
			default:
				args[0] = KD_EXE_NORMAL;
				break;
			}
		} else {
			frame->executed = true;
			boundary_start = kd_jit_timing_start();
			translated(regs, args);
			kd_jit_timing_end(KD_JIT_TIME_WRAPPER, boundary_start);
			if (args[0] == KD_EXE_ENTRY_REFUSED) {
				/* Only this explicit pre-body exit can undo our conservative
				 * executed mark. A zero witness by itself never permits replay.
				 * Root packet preservation is part of the generated guard ABI.
				 */
				if (pristine_root && !continuation_count &&
				    !hostcall_count && regs->ip == entry_ip &&
				    regs->sp == entry_sp && args[1] == 0) {
					frame->executed = false;
					pr_warn_ratelimited(
						"[KD_JIT][WARN] reason=ENTRY_GUARD_REFUSED entry=0x%lx waiter_pid=%d lock=0x%lx action=native_unstarted\n",
						entry_ip,
						frame->logical_task->pid,
						outer_lock_addr);
					kd_jit_timing_end(KD_JIT_TIME_DISPATCH,
							  dispatch_start);
					return KD_EXE_NO_RUN;
				}
				kd_jit_log_hl_error("INVALID_ENTRY_REFUSAL",
						    frame, regs, args[0],
						    -EINVAL, continuation_count,
						    hostcall_count);
				kd_jit_timing_end(KD_JIT_TIME_DISPATCH, dispatch_start);
				return KD_EXE_RUN_ERROR;
			}
			/* Observational only: never use missing evidence to replay work. */
			if (!body_reported && args[1] == 1) {
				KD_PR_INFO(
					"JIT body witness: entry=%lx lock=%lx body=%lu\n",
					entry_ip, outer_lock_addr, args[1]);
				body_reported = true;
			}
			if (resume_after_hostcall)
				atomic64_inc(&kd_hostcall_resumed);
		}
		resume_after_hostcall = false;

		if (args[0] == KD_EXE_NORMAL) {
			kd_jit_log_hl_error("UNSUPPORTED_SYSCALL", frame, regs,
					    args[0], regs->ax,
					    continuation_count, hostcall_count);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (args[0] == KD_EXE_HOSTCALL) {
			atomic64_inc(&kd_hostcall_exits);
			if (hostcall_count >= KD_EXE_HL_MAX_HOSTCALLS ||
			    continuation_count >= KD_EXE_HL_MAX_CONTINUATIONS) {
				atomic64_inc(&kd_hostcall_limit);
				call_ret = fault_kind ? -EINVAL :
					kd_jit_call_limit_native(frame, regs, true);
				if (call_ret)
					kd_jit_log_hl_error("HOSTCALL_LIMIT", frame,
							    regs, args[0], call_ret,
							    continuation_count,
							    hostcall_count);
				ret_flag = call_ret ? KD_EXE_RUN_ERROR :
						     KD_EXE_RUN_NATIVE;
				break;
			}

			boundary_start = kd_jit_timing_start();
			call_ret = kd_hostcall_dispatch(regs);
			kd_jit_timing_end(KD_JIT_TIME_HOSTCALL, boundary_start);
			if (call_ret) {
				if (call_ret == -ENOENT || call_ret == -EPERM)
					atomic64_inc(&kd_hostcall_rejected);
				else
					atomic64_inc(&kd_hostcall_failed);
				kd_jit_log_hl_error("HOSTCALL_FAILED", frame,
						    regs, args[0], call_ret,
						    continuation_count,
						    hostcall_count);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}
			atomic64_inc(&kd_hostcall_executed);

			call_ret = advance_and_save_continuation(
				kd_exec_current_frame(), regs);
			if (call_ret <= 0) {
				atomic64_inc(&kd_hostcall_failed);
				kd_jit_log_hl_error(
					"HOSTCALL_CONTINUATION_FAILED", frame,
					regs, args[0], call_ret,
					continuation_count, hostcall_count);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}

			hostcall_count++;
			continuation_count++;
			resume_after_hostcall = true;
			continue;
		} else if (args[0] == KD_EXE_CALL_MISS) {
			if (outer_lock_addr &&
			    is_outer_lock_unlock(regs, outer_lock_addr)) {
				call_ret = kd_jit_timed_control(regs, outer_lock_addr);
				if (call_ret == KD_EXE_KNOWN_OUTER_UNLOCK) {
					ret_flag = KD_EXE_RUN_TO_UNLOCK;
					break;
				}
				if (call_ret == KD_EXE_KNOWN_NATIVE) {
					ret_flag = KD_EXE_RUN_NATIVE;
					break;
				}
				if (call_ret > 0) {
					continuation_count++;
					continue;
				}
				kd_jit_log_hl_error("OUTER_UNLOCK_FAILED",
						    frame, regs, args[0],
						    call_ret,
						    continuation_count,
						    hostcall_count);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}
			if (!outer_lock_addr && is_end_point(regs->ip)) {
				ret_flag = KD_EXE_RUN_TO_UNLOCK;
			} else {
				if (continuation_count >=
				    KD_EXE_HL_MAX_CONTINUATIONS) {
					call_ret = fault_kind ? -EINVAL :
						kd_jit_call_limit_native(frame, regs, false);
					if (call_ret)
						kd_jit_log_hl_error(
							"CONTINUATION_LIMIT", frame,
							regs, args[0], call_ret,
							continuation_count,
							hostcall_count);
					ret_flag = call_ret ? KD_EXE_RUN_ERROR :
							     KD_EXE_RUN_NATIVE;
					break;
				}

				call_ret =
					outer_lock_addr ?
						kd_jit_timed_control(
							regs, outer_lock_addr) :
						0;
				if (call_ret == KD_EXE_KNOWN_NATIVE) {
					ret_flag = KD_EXE_RUN_NATIVE;
					break;
				}
				if (call_ret == KD_EXE_KNOWN_OUTER_UNLOCK) {
					ret_flag = KD_EXE_RUN_TO_UNLOCK;
					break;
				}
				if (call_ret > 0) {
					continuation_count++;
					continue;
				}
				if (call_ret < 0) {
					kd_jit_log_hl_error("KNOWN_CALL_FAILED",
							    frame, regs,
							    args[0], call_ret,
							    continuation_count,
							    hostcall_count);
					ret_flag = KD_EXE_RUN_ERROR;
					break;
				}

				/* An ordinary callee runs on the original waiter from this
				 * saved CALL state, including the remaining native suffix.
				 * Learning this target only benefits future invocations; do
				 * not loop back into this JIT after waiter-side execution.
				 */
				call_ret =
					fault_kind ?
						0 :
						kd_source_pin_target(regs->ip);
				if (call_ret) {
					kd_jit_log_hl_error(
						"SOURCE_TARGET_REFUSED", frame,
						regs, args[0], call_ret,
						continuation_count,
						hostcall_count);
					ret_flag = KD_EXE_RUN_ERROR;
					break;
				}
				exe->tgt_addr = regs->ip;
				if (!is_end_point(exe->tgt_addr))
					kd_exe_publish_status(exe,
							      KD_EXE_CALL_MISS);
				/* Synthetic faults have no CALL frame and are not resumable. */
				ret_flag = fault_kind ? KD_EXE_RUN_ERROR :
							KD_EXE_RUN_NATIVE;
			}
		} else if (args[0] == KD_EXE_ERROR_INST) {
			kd_jit_log_hl_error("UNSUPPORTED_INSTRUCTION", frame,
					    regs, args[0], -EILSEQ,
					    continuation_count, hostcall_count);
			kd_exe_publish_status(exe, KD_EXE_ERROR_INST);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (args[0] == KD_EXE_INST_LIMIT) {
			kd_jit_log_hl_error("BUDGET_LIMIT", frame, regs,
					    args[0], 0, continuation_count,
					    hostcall_count);
			ret_flag = KD_EXE_RUN_ERROR;
		} else {
			kd_jit_log_hl_error("IJ_MISS", frame, regs, args[0], 0,
					    continuation_count, hostcall_count);
			exe->tgt_addr = regs->ip;
			exe->jump_from = args[0];
			if (!is_end_point(exe->tgt_addr) &&
			    !is_end_point(exe->jump_from))
				kd_exe_publish_status(exe, KD_EXE_IJ_MISS);
			ret_flag = KD_EXE_RUN_ERROR;
		}
		break;
	}

	mb();
	kd_jit_timing_end(KD_JIT_TIME_DISPATCH, dispatch_start);
	return ret_flag;
}
