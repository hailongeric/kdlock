// SPDX-License-Identifier: GPL-2.0
/* Owned mutex delegation. Included by kd_spin_runtime.c so the checked batch
 * wrapper and frame retirement stay visible to the compiler. The public object
 * has one owner and one FIFO; private snapshots exist only while that owner is
 * retained. There is no Linux mutex API or address-to-shadow lookup here. */
#include <linux/rcuwait.h>
#include <linux/vmalloc.h>
#include <linux/topology.h>
#include <linux/objtool.h>
#include <asm/asm.h>
#include "kd_owned_mutex_internal.h"
#include "kd_owned_mutex_direct.h"
#include "kd_comm.h"
#include "kd_segment.h"
#include "kd_source.h"
#include "kd_jit_batch.h"

extern struct kd_comm_key kd_spin_target;

#define KD_OWNED_MUTEX_SLOTS 4
#define KD_OWNED_MUTEX_STACK_SIZE 8192UL

/* The common FIFO header is also used by allocation-free stack SELF waiters.
 * Keep the existing packet/result offsets: ABI2 never initializes absent GPRs. */
struct kd_owned_mutex_node {
	struct kd_owned_mutex_waiter waiter;
	unsigned long gsbase;
	unsigned long rsp;
	void *shadow_stack_base;
	unsigned long shadow_stack_ptr;
	u8 entry_abi;
	unsigned int packet_state;
	struct kd_mutex *lock;
	unsigned long saved_ret_addr;
	struct rcuwait *wait;
	int slot;
	int numa_node;
	struct kd_regs regs __aligned(64);
	u64 queued_at_ns;
	u32 outcome;
};

/* One executor per CPU is sufficient: the frame context itself forbids a
 * second live executor. This reservation survives scheduling and is separate
 * from all producer slots, including a producer sleeping on this same CPU. */
struct kd_owned_mutex_executor {
	void *stack_base;
	unsigned long stack_ptr;
	unsigned long rsp;
	bool busy;
};

/* Large packet/stack identities use dynamic per-CPU storage. The kernel's
 * reserved module-percpu arena is shared with the existing protocol families;
 * extending it with another static packet array can prevent module loading. */
struct kd_owned_mutex_cpu {
	struct kd_owned_mutex_node nodes[KD_OWNED_MUTEX_SLOTS];
	struct rcuwait waits[KD_OWNED_MUTEX_SLOTS];
	struct kd_owned_mutex_executor executor;
	unsigned long slots;
	int active_waiters;
};
static struct kd_owned_mutex_cpu __percpu *kd_owned_mutex_cpus;
static DEFINE_PER_CPU(unsigned long, kd_owned_mutex_parks);
static DEFINE_PER_CPU(unsigned long, kd_owned_mutex_wakes);
static DEFINE_PER_CPU(unsigned long, kd_owned_mutex_bodies);
static DEFINE_PER_CPU(unsigned long, kd_owned_mutex_batches);
static DEFINE_PER_CPU(unsigned long, kd_owned_mutex_refusals);
static DEFINE_PER_CPU(unsigned long, kd_owned_mutex_early_releases);

/* One bounded grace after an unqueued release can preserve owner locality.
 * Zero keeps the exact Linux optimistic retry cadence. */
unsigned int owned_mutex_reuse_spins;
module_param(owned_mutex_reuse_spins, uint, 0444);
MODULE_PARM_DESC(owned_mutex_reuse_spins,
	"One unqueued-release grace per OSQ acquisition: 0, 8, 32 or 128 polls");

bool owned_mutex_self_route;
module_param(owned_mutex_self_route, bool, 0444);
MODULE_PARM_DESC(owned_mutex_self_route,
	"Use only the owned SELF core for new acquisitions (diagnostic control)");
/* A getter-only identity cannot be overridden at module load to misdescribe
 * the acquisition policy implemented by this provider. */
static int kd_owned_mutex_protocol_get(char *buffer,
				       const struct kernel_param *kp)
{
	(void)kp;
	return scnprintf(buffer, PAGE_SIZE, "linux_local_first_v1");
}
static const struct kernel_param_ops kd_owned_mutex_protocol_ops = {
	.get = kd_owned_mutex_protocol_get,
};
module_param_cb(owned_mutex_protocol, &kd_owned_mutex_protocol_ops, NULL, 0444);
MODULE_PARM_DESC(owned_mutex_protocol, "Owned acquisition/release protocol identity");
static bool owned_mutex_refill;
module_param(owned_mutex_refill, bool, 0444);
MODULE_PARM_DESC(owned_mutex_refill,
	"Refill exhausted owned FIFO snapshots within the original batch quota");
/* Zero isolates the C admission gate from optimistic retry. This candidate
 * changes execution placement only; it never alters existing queued work. */
static unsigned int owned_mutex_preflight_spins;
module_param(owned_mutex_preflight_spins, uint, 0444);
MODULE_PARM_DESC(owned_mutex_preflight_spins,
	"Owned outer pre-capture owner polls: 0, 64, 256, 1024 or 4096");
static bool owned_mutex_preflight_queue;
module_param(owned_mutex_preflight_queue, bool, 0444);
MODULE_PARM_DESC(owned_mutex_preflight_queue,
	"Allow preflight OSQ queueing within the shared queue/owner poll budget");

static bool kd_owned_mutex_preflight_spins_valid(unsigned int spins)
{
	return spins == 0 || spins == 64 || spins == 256 ||
		spins == 1024 || spins == 4096;
}

static unsigned int owned_mutex_spin_limit = 4096;
module_param(owned_mutex_spin_limit, uint, 0444);
MODULE_PARM_DESC(owned_mutex_spin_limit,
	"Maximum owned delegation result polls before sleeping");

static int kd_owned_mutex_wait_stats_get(char *buffer,
				       const struct kernel_param *kp)
{
	u64 parks = 0, wakes = 0;
	int cpu;

	(void)kp;
	for_each_possible_cpu(cpu) {
		parks += READ_ONCE(per_cpu(kd_owned_mutex_parks, cpu));
		wakes += READ_ONCE(per_cpu(kd_owned_mutex_wakes, cpu));
	}
	return scnprintf(buffer, PAGE_SIZE, "%llu %llu 0\n", parks, wakes);
}
static const struct kernel_param_ops kd_owned_mutex_wait_stats_ops = {
	.get = kd_owned_mutex_wait_stats_get,
};
module_param_cb(owned_mutex_wait_stats, &kd_owned_mutex_wait_stats_ops, NULL, 0444);

static struct kd_owned_mutex_node *kd_owned_mutex_reserve(struct kd_mutex *lock)
{
	struct kd_owned_mutex_cpu *cpu = this_cpu_ptr(kd_owned_mutex_cpus);
	unsigned long slots = cpu->slots;
	int i;

	for (i = 0; i < KD_OWNED_MUTEX_SLOTS; i++)
		if ((slots & BIT(i)) &&
		    READ_ONCE(cpu->nodes[i].lock) == lock)
			return NULL;
	for (i = 0; i < KD_OWNED_MUTEX_SLOTS; i++) {
		struct kd_owned_mutex_node *node;

		if (slots & BIT(i))
			continue;
		node = &cpu->nodes[i];
		if (!node->shadow_stack_base)
			continue;
		WRITE_ONCE(cpu->slots, slots | BIT(i));
		return node;
	}
	return NULL;
}

static void kd_owned_mutex_unreserve(struct kd_owned_mutex_node *node)
{
	struct kd_owned_mutex_cpu *cpu = this_cpu_ptr(kd_owned_mutex_cpus);
	unsigned long slots = cpu->slots;

	BUG_ON(node->slot < 0 || node->slot >= KD_OWNED_MUTEX_SLOTS ||
	       !(slots & BIT(node->slot)) || !list_empty(&node->waiter.list));
	WRITE_ONCE(node->lock, NULL);
	node->waiter.task = NULL;
	WRITE_ONCE(cpu->slots, slots & ~BIT(node->slot));
}

/* Result publication is the last packet access. Only provider-lifetime wake
 * objects may be used after a waiter is allowed to reuse its slot. */
static void kd_owned_mutex_flush_wakes(struct rcuwait **wake, unsigned int *count)
{
	unsigned int i, n = *count;

	if (!n)
		return;
	*count = 0;
	smp_mb();
	for (i = 0; i < n; i++)
		if (rcuwait_active(wake[i]) && rcuwait_wake_up(wake[i]))
			this_cpu_inc(kd_owned_mutex_wakes);
}

static void kd_owned_mutex_notify(struct kd_owned_mutex_node *node, bool complete)
{
	struct rcuwait *wait = node->wait;

	smp_store_release(&node->outcome, complete ? KD_OWNED_MUTEX_COMPLETE :
			  KD_OWNED_MUTEX_FULL);
	smp_mb();
	if (rcuwait_active(wait) && rcuwait_wake_up(wait))
		this_cpu_inc(kd_owned_mutex_wakes);
}

static void kd_owned_mutex_defer(struct kd_owned_mutex_node *node,
				 struct rcuwait **wake, unsigned int *count)
{
	wake[(*count)++] = node->wait;
	smp_store_release(&node->outcome, KD_OWNED_MUTEX_COMPLETE);
	if (*count == 16)
		kd_owned_mutex_flush_wakes(wake, count);
}

static bool kd_owned_mutex_result_ready(struct kd_owned_mutex_node *node)
{
	return smp_load_acquire(&node->outcome) != KD_OWNED_MUTEX_QUEUED;
}

static void kd_owned_mutex_wait_result(struct kd_owned_mutex_node *node)
{
	struct rcuwait *wait = node->wait;
	unsigned int left = owned_mutex_spin_limit;

	while (!kd_owned_mutex_result_ready(node)) {
		if (!left || (!(left & 63) && need_resched()))
			break;
		left--;
		cpu_relax();
	}
	if (kd_owned_mutex_result_ready(node))
		return;
	prepare_to_rcuwait(wait);
	for (;;) {
		set_current_state(TASK_UNINTERRUPTIBLE);
		if (kd_owned_mutex_result_ready(node))
			break;
		this_cpu_inc(kd_owned_mutex_parks);
		preempt_enable();
		/* Also bounds deferred completion notification. The state barrier
		 * precedes the single grant/COMPLETE/FULL outcome observation. */
		schedule_timeout(1);
		preempt_disable();
	}
	finish_rcuwait(wait);
}

static __attribute__((noipa)) noinline notrace int
kd_owned_mutex_wait_on_stack(struct kd_mutex *lock, struct kd_owned_mutex_node *node)
{
	int ret;

	node->queued_at_ns = kd_exe_queue_timing_start();
	this_cpu_ptr(kd_owned_mutex_cpus)->active_waiters++;
	if (kd_owned_mutex_publish(lock, &node->waiter)) {
		ret = 2;
		goto acquired;
	}
	for (;;) {
		u32 outcome;

		kd_owned_mutex_wait_result(node);
		outcome = smp_load_acquire(&node->outcome);
		if (outcome == KD_OWNED_MUTEX_COMPLETE || outcome == KD_OWNED_MUTEX_FULL) {
			ret = outcome == KD_OWNED_MUTEX_FULL ? 5 : 3;
			break;
		}
		BUG_ON(outcome != KD_OWNED_MUTEX_GRANTED);
		if (kd_owned_mutex_pickup(lock, &node->waiter)) {
			ret = 2;
			goto acquired;
		}
		cpu_relax();
	}
	this_cpu_ptr(kd_owned_mutex_cpus)->active_waiters--;
	return ret;
acquired:
	kd_exe_queue_timing_end(true, &node->queued_at_ns, kd_exe_queue_timing_start());
	this_cpu_ptr(kd_owned_mutex_cpus)->active_waiters--;
	return ret;
}

static __attribute__((noipa, used, noreturn)) noinline notrace void
kd_owned_mutex_resume(struct kd_owned_mutex_node *node)
{
	struct kd_regs full;
	struct kd_owned_mutex_cabi_state callee;
	u32 outcome = READ_ONCE(node->outcome);
	bool native = outcome == KD_OWNED_MUTEX_FULL;
	bool cabi = node->entry_abi == KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2;
	bool reduced = node->packet_state == kd_complete_packet_state(node->entry_abi);
	unsigned long sp = node->regs.sp, ip = node->regs.ip, bp = node->regs.bp;

	BUG_ON(!kd_entry_abi_mutex_reduced(node->entry_abi));
	BUG_ON(native ? reduced : outcome != KD_OWNED_MUTEX_COMPLETE);
	BUG_ON(!reduced && node->packet_state != KD_PACKET_FULL);
	if (cabi && reduced) {
		callee.ip = ip; callee.sp = sp; callee.bp = bp;
		callee.bx = node->regs.bx; callee.r12 = node->regs.r12;
		callee.r13 = node->regs.r13; callee.r14 = node->regs.r14;
		callee.r15 = node->regs.r15;
	}
	if (!reduced)
		full = node->regs;
	kd_owned_mutex_unreserve(node);
	preempt_enable();
	migrate_enable();
	if (native)
		jump_to_saved_regs_in_cs(&full);
	kd_mutex_task_put(current);
	if (!reduced)
		jump_to_saved_regs(&full);
	if (cabi)
		kd_owned_mutex_resume_cabi(&callee);
	asm volatile("movq %%rax, %%rsp\n\t"
		     "movq %%rcx, %%rbp\n\t"
		     "pushq %%rdx\n\t"
#ifdef CONFIG_RETHUNK
		     "jmp __x86_return_thunk\n\t"
#else
		     "ret\n\t"
#endif
		     : : "a"(sp), "c"(bp), "d"(ip) : "memory");
	__builtin_unreachable();
}

static __always_inline int
kd_owned_mutex_clobber_wait(struct kd_mutex *lock, struct kd_owned_mutex_node *node)
{
	int result;

	asm volatile(UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_SAVE, 0)
		     "pushq %%rbp\n\t"
		     "movq %%rsp, %c[saved](%%rsi)\n\t"
		     "movq %%rsi, %%r12\n\t"
		     "movq %c[shadow](%%rsi), %%rsp\n\t"
		     "andq $-16, %%rsp\n\t"
		     "xorq %%rbp, %%rbp\n\t"
		     "callq %P[wait]\n\t"
		     "cmpl $3, %%eax\n\t"
		     "je 1f\n\t"
		     "cmpl $5, %%eax\n\t"
		     "je 1f\n\t"
		     "movq %c[saved](%%r12), %%rsp\n\t"
		     "popq %%rbp\n\t"
		     "jmp 2f\n\t"
		     "1: movq %c[saved](%%r12), %%rax\n\t"
		     "cmpq %c[sp](%%r12), %%rax\n\t"
		     "cmovaq %c[sp](%%r12), %%rax\n\t"
		     "andq $-16, %%rax\n\t"
		     "movq %%rax, %%rsp\n\t"
		     "movq %%r12, %%rdi\n\t"
		     "xorq %%rbp, %%rbp\n\t"
		     "callq %P[resume]\n\t"
		     "ud2\n\t2:\n\t"
		     UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_RESTORE, 0)
		     : "=a"(result), "+D"(lock), "+S"(node), ASM_CALL_CONSTRAINT
		     : [saved] "i"(offsetof(struct kd_owned_mutex_node, rsp)),
		       [shadow] "i"(offsetof(struct kd_owned_mutex_node, shadow_stack_ptr)),
		       [sp] "i"(offsetof(struct kd_owned_mutex_node, regs.sp)),
		       [wait] "i"(kd_owned_mutex_wait_on_stack),
		       [resume] "i"(kd_owned_mutex_resume)
		     : "rbx", "rcx", "rdx", "r8", "r9", "r10", "r11",
		       "r12", "r13", "r14", "r15", "cc", "memory");
	return result;
}

static bool kd_owned_mutex_delegation_eligible(void)
{
	return kd_source_is_open() &&
		kd_comm_matches(&kd_spin_target, current->comm) &&
		!kd_mutex_task_active(current);
}

/* Ordinary C ABI: no captured stack or resource lease exists yet. The outer
 * failed probe reaches this exactly once, irrespective of the execution route.
 * A false return only permits ABI2 capture; it grants neither delegation nor
 * an eligibility lease. The prepared entry checks eligibility before resources.
 * A physical SELF acquisition is valid even when delegation is prohibited. */
__attribute__((noipa)) noinline notrace bool
kd_owned_mutex_outer_preflight_v1(struct kd_mutex *lock)
{
	enum kd_owned_mutex_preflight_result result = KD_OWNED_MUTEX_PREFLIGHT_BUSY;
	bool admitted;

	preempt_disable();
	kd_hotlock_owned_mutex_entry();
	admitted = kd_hotlock_record_owned_mutex_pinned((unsigned long)lock);
	if (admitted && !owned_mutex_self_route)
		result = kd_owned_mutex_try_optimistic_pinned(lock,
							    owned_mutex_preflight_spins,
							    owned_mutex_preflight_queue);
	preempt_enable();
	if (result == KD_OWNED_MUTEX_PREFLIGHT_ACQUIRED)
		return true;
	if (admitted && !owned_mutex_self_route &&
	    result == KD_OWNED_MUTEX_PREFLIGHT_BUSY)
		return false;
	kd_owned_mutex_lock_self(lock);
	return true;
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_outer_preflight_v1);

/* The hardware post-CALL PC is the ABI4 identity. The exported continuation
 * label follows one fixed, explicitly encoded nine-byte test/branch prefix.
 * This is a format check, never a scan through a compiler-generated prologue. */
static bool kd_owned_mutex_cabi_stub_valid(unsigned long ip)
{
	u8 bytes[KD_CABI_CALL_STUB_SIZE], tail[2];
	s32 displacement;
	unsigned long target;

	if (!ip || copy_from_kernel_nofault(bytes, (void *)ip, sizeof(bytes)) ||
	    bytes[0] != 0x48 || bytes[1] != 0x85 || bytes[2] != 0xc0 ||
	    bytes[3] != 0x0f || bytes[4] != 0x85)
		return false;
	memcpy(&displacement, bytes + 5, sizeof(displacement));
	if (displacement < 2 || ip > ~0UL - sizeof(bytes) - displacement)
		return false;
	target = ip + sizeof(bytes) + displacement;
	return !copy_from_kernel_nofault(tail, (void *)(target - 2), sizeof(tail)) &&
	       tail[0] == 0x31 && tail[1] == 0xc0;
}


unsigned long kd_owned_mutex_outer_cabi_capture(struct kd_mutex *lock,
		const struct kd_owned_mutex_cabi_state *saved)
{
	struct kd_owned_mutex_node *node;

	if (owned_mutex_self_route || !kd_owned_mutex_delegation_eligible() ||
	    !kd_owned_mutex_cabi_stub_valid(saved->ip))
		goto self;
	if (!kd_mutex_task_get(current))
		goto self;
	kd_exe_add_abi(0, saved->ip, KD_EXE_LOCK_OWNED_MUTEX,
		       KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2);
	migrate_disable();
	preempt_disable();
	node = kd_owned_mutex_reserve(lock);
	if (!node) {
		this_cpu_inc(kd_owned_mutex_refusals);
		preempt_enable();
		migrate_enable();
		kd_mutex_task_put(current);
		goto self;
	}
	INIT_LIST_HEAD(&node->waiter.list);
	node->waiter.task = current;
	node->waiter.kind = KD_OWNED_MUTEX_DELEGATE;
	node->regs.ip = saved->ip; node->regs.sp = saved->sp; node->regs.bp = saved->bp;
	node->regs.bx = saved->bx; node->regs.r12 = saved->r12;
	node->regs.r13 = saved->r13; node->regs.r14 = saved->r14;
	node->regs.r15 = saved->r15;
	node->regs.ax = 0;
	node->entry_abi = KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2;
	node->packet_state = KD_PACKET_CALLEE_ENTRY;
	node->lock = lock;
	node->saved_ret_addr = saved->ip;
	node->gsbase = kd_read_kernel_gsbase();
	/* Once execution starts, COMPLETE/FULL bypass these native frames. */
	BUG_ON(kd_owned_mutex_clobber_wait(lock, node) != 2);
	kd_owned_mutex_unreserve(node);
	preempt_enable();
	migrate_enable();
	kd_mutex_task_put(current);
	return (unsigned long)current;
self:
	/* The C gate already exhausted local optimism. Source/resource refusal
	 * commits to SELF waiting instead of repeating the initial OSQ phase. */
	kd_owned_mutex_lock_self_wait(lock);
	return (unsigned long)current;
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_outer_lock_cabi_v2);

/* The assembly leaf tail-calls this unchanged slow contract. The cookie is
 * required on physical returns; a FULL borrowed continuation uses exact ACK
 * routing before the ordinary owner path is allowed to touch L. Rechecking
 * physical ownership here also preserves flag handling after a failed CAS. */
void kd_owned_mutex_outer_cabi_unlock_slow(struct kd_mutex *lock, unsigned long owner)
{
	if (!owner) {
		BUG_ON(!kd_mutex_task_reroute(current) ||
		       !kd_exec_native_unlock((unsigned long)lock, true));
		return;
	}
	BUG_ON(owner != (unsigned long)current);
	kd_owned_mutex_outer_unlock_v1(lock);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_outer_unlock_cabi_v2);

static unsigned long kd_owned_mutex_contended(struct kd_mutex *lock,
		unsigned long sp, unsigned long ip, unsigned long bp)
{
	struct kd_owned_mutex_node *node;

	/* The selected outer endpoint already made the exact heat observation.
	 * That decision holds no lease; check eligibility before acquiring resources.
	 * Cooling affects future attempts, never ownership of published requests. */
	if (owned_mutex_self_route || !kd_owned_mutex_delegation_eligible())
		goto self;
	if (!kd_mutex_task_get(current))
		goto self;
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_OWNED_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	migrate_disable();
	preempt_disable();
	node = kd_owned_mutex_reserve(lock);
	if (!node) {
		this_cpu_inc(kd_owned_mutex_refusals);
		preempt_enable();
		migrate_enable();
		kd_mutex_task_put(current);
		goto self;
	}
	INIT_LIST_HEAD(&node->waiter.list);
	node->waiter.task = current;
	node->waiter.kind = KD_OWNED_MUTEX_DELEGATE;
	node->regs.ip = ip;
	node->regs.sp = sp;
	node->regs.bp = bp;
	node->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	node->packet_state = KD_PACKET_MINIMAL;
	node->lock = lock;
	node->saved_ret_addr = ip;
	node->gsbase = kd_read_kernel_gsbase();
	/* COMPLETE/FULL never returns through native frames lent to the JIT. */
	BUG_ON(kd_owned_mutex_clobber_wait(lock, node) != 2);
	kd_owned_mutex_unreserve(node);
	preempt_enable();
	migrate_enable();
	kd_mutex_task_put(current);
	return (unsigned long)current;
self:
	kd_owned_mutex_lock_self(lock);
	return (unsigned long)current;
}

__attribute__((noipa)) noinline notrace unsigned long
kd_owned_mutex_outer_contended_clobber_v1(struct kd_mutex *lock,
		unsigned long sp, unsigned long ip, unsigned long bp)
{
	bool admitted;

	preempt_disable();
	kd_hotlock_owned_mutex_entry();
	admitted = kd_hotlock_record_owned_mutex_pinned((unsigned long)lock);
	preempt_enable();
	/* Original capture-first route: configured preflight polling is irrelevant
	 * to callers that did not opt in. Cold attempts use the same owned core. */
	if (!admitted) {
		kd_owned_mutex_lock_self(lock);
		return (unsigned long)current;
	}
	return kd_owned_mutex_contended(lock, sp, ip, bp);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_outer_contended_clobber_v1);

__attribute__((noipa)) noinline notrace unsigned long
kd_owned_mutex_outer_prepared_clobber_v1(struct kd_mutex *lock,
		unsigned long sp, unsigned long ip, unsigned long bp)
{
	/* Paired only with false from the C gate; never sample this attempt again. */
	return kd_owned_mutex_contended(lock, sp, ip, bp);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_outer_prepared_clobber_v1);

__attribute__((noipa)) noinline notrace void
kd_owned_mutex_direct_contended_clobber_v1(struct kd_mutex *lock,
		unsigned long sp, unsigned long ip, unsigned long bp)
{
	(void)sp; (void)ip; (void)bp;
	kd_mutex_lock(lock);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_direct_contended_clobber_v1);

__attribute__((noipa)) noinline notrace void
kd_owned_mutex_direct_lock_clobber_v1(struct kd_mutex *lock,
		unsigned long sp, unsigned long ip, unsigned long bp)
{
	/* Ordinary direct controls are nestable SELF acquisitions. Delegation
	 * admission belongs to the explicit outer-cookie boundary; translated
	 * nested controls are serviced through the frame's ownership ledger. */
	(void)sp; (void)ip; (void)bp;
	kd_mutex_lock(lock);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_direct_lock_clobber_v1);

__attribute__((noipa)) noinline notrace void
kd_owned_mutex_direct_unlock_clobber_v1(struct kd_mutex *lock,
		unsigned long sp, unsigned long ip, unsigned long bp)
{
	(void)sp;
	(void)ip;
	(void)bp;
	if (kd_mutex_task_reroute(current) &&
	    kd_exec_native_unlock((unsigned long)lock, true))
		return;
	kd_mutex_unlock(lock);
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_direct_unlock_clobber_v1);

int kd_owned_mutex_prepare(struct kd_mutex *lock, unsigned long ip, unsigned int abi)
{
	struct kd_exe_info *exe;

	if (!lock || !ip || !kd_entry_abi_mutex_reduced(abi))
		return -EINVAL;
	if (abi == KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2 &&
	    !kd_owned_mutex_cabi_stub_valid(ip))
		return -EINVAL;
	if (!kd_source_is_open())
		return -ESHUTDOWN;
	kd_exe_add_abi(0, ip, KD_EXE_LOCK_OWNED_MUTEX, abi);
	exe = kd_get_exe(0, ip);
	if (!exe || smp_load_acquire(&exe->status_code) == KD_EXE_UNUSED ||
	    exe->RIP != ip || exe->entry_abi != abi ||
	    exe->lock_kind != KD_EXE_LOCK_OWNED_MUTEX)
		return -EINVAL;
	return READ_ONCE(exe->status_code) == KD_EXE_NATIVE_ONLY ? -EOPNOTSUPP : 0;
}
EXPORT_SYMBOL_GPL(kd_owned_mutex_prepare);

struct kd_owned_mutex_batch {
	struct kd_exec_outer_unlock outer;
	struct list_head pending;
	struct kd_owned_mutex_node *current_node;
	bool current_retired;
	struct kd_mutex *lock;
	struct kd_exe_info *exe;
	struct rcuwait *wake[16];
	unsigned int wake_count;
};

static void kd_owned_mutex_retire_current(struct kd_owned_mutex_batch *batch)
{
	if (batch->current_retired)
		return;
	BUG_ON(!batch->current_node);
	list_del_init(&batch->current_node->waiter.list);
	batch->current_retired = true;
}

static void kd_owned_mutex_rejoin(struct kd_owned_mutex_batch *batch)
{
	unsigned long flags;
	struct kd_mutex *lock = batch->lock;

	raw_spin_lock_irqsave(&lock->wait_lock, flags);
	BUG_ON(!kd_owned_mutex_owned(lock, current));
	/* Older private requests precede arrivals published during execution.
	 * WAITERS has remained set throughout the detached interval. */
	list_splice_init(&batch->pending, &lock->wait_list);
	raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
}

static int kd_owned_mutex_release_outer(struct kd_exec_frame *frame,
				      struct kd_exec_outer_unlock *hook)
{
	struct kd_owned_mutex_batch *batch =
		container_of(hook, struct kd_owned_mutex_batch, outer);
	struct kd_mutex *lock = batch->lock;

	if (!frame->owned_mutex || frame->outer_lock_addr != (unsigned long)lock ||
	    frame->jit_lock_kind[frame->outer_lock_index] != KD_EXEC_LOCK_QUEUE_OWNER ||
	    frame->jit_lock_node[frame->outer_lock_index] != lock ||
	    !kd_owned_mutex_owned(lock, current))
		return -EINVAL;
	kd_owned_mutex_retire_current(batch);
	kd_owned_mutex_rejoin(batch);
	kd_owned_mutex_flush_wakes(batch->wake, &batch->wake_count);
	/* The owner's own critical section ended before this batch began.
	 * After this release we never reacquire A or inspect its queue again. */
	this_cpu_inc(kd_owned_mutex_early_releases);
	kd_owned_mutex_release(lock);
	return 0;
}

static __attribute__((noipa)) noinline notrace int
kd_owned_mutex_execute(struct kd_owned_mutex_node *node,
			struct kd_owned_mutex_batch *batch)
{
	struct kd_mutex *lock = batch->lock;
	struct kd_exec_frame *frame;
	struct kd_exe_info *exe = batch->exe;
	struct kd_jit_batch_call call;
	struct kd_regs *regs;
	unsigned int entry_abi = node->entry_abi;
	u64 queue_end;
	int ret, clean;

	BUG_ON(!kd_owned_mutex_owned(lock, current));
	BUG_ON(!kd_entry_abi_mutex_reduced(entry_abi) ||
	       node->packet_state != kd_entry_packet_state(entry_abi));
	if (!node->regs.sp || !node->regs.ip || node->regs.ip != node->saved_ret_addr)
		return KD_EXE_NO_RUN;
	if (!exe || READ_ONCE(exe->RIP) != node->regs.ip ||
	    READ_ONCE(exe->lock_kind) != KD_EXE_LOCK_OWNED_MUTEX) {
		exe = kd_get_exe(0, node->regs.ip);
		batch->exe = exe;
	}
	if (!kd_exe_entry_is_ready(exe, 0, node->regs.ip) ||
	    READ_ONCE(exe->lock_kind) != KD_EXE_LOCK_OWNED_MUTEX ||
	    kd_exec_context_occupied())
		return KD_EXE_NO_RUN;
	frame = kd_exec_frame_push_owned_mutex_batch(&node->regs, node->regs.ip,
		node->gsbase, node->waiter.task, lock, &batch->outer, entry_abi);
	if (!frame)
		return KD_EXE_NO_RUN;
	queue_end = kd_exe_queue_timing_start();
	regs = kd_exec_frame_regs(frame);
	if (kd_exe_mutex_batch_prepare(exe, frame, &call)) {
		frame->executed = true;
		kd_jit_clobber_call_v1(&call);
		if (kd_exe_mutex_batch_completed(&call, frame)) {
			kd_exe_queue_timing_end(true, &node->queued_at_ns, queue_end);
			BUG_ON(kd_exec_frame_retire_owned_mutex_batch(frame, lock));
			node->packet_state = kd_complete_packet_state(node->entry_abi);
			return 0;
		}
		kd_owned_mutex_flush_wakes(batch->wake, &batch->wake_count);
		ret = kd_exe_mutex_batch_resume(exe, &call);
	} else {
		kd_owned_mutex_flush_wakes(batch->wake, &batch->wake_count);
		ret = kd_exe_on_call_hl_entry(exe, regs, frame->entry_ip,
					    frame->outer_lock_addr);
	}
	regs = kd_exec_frame_regs(frame);
	if (frame->executed)
		kd_exe_queue_timing_end(true, &node->queued_at_ns, queue_end);
	if (ret == KD_EXE_RUN_NATIVE) {
		u64 handoff_start = kd_exe_native_timing_start();

		BUG_ON(kd_exec_native_begin(frame, true));
		BUG_ON(frame->regs_borrowed || frame->packet_state != KD_PACKET_FULL);
		node->regs = *kd_exec_frame_regs(frame);
		node->packet_state = KD_PACKET_FULL;
		kd_owned_mutex_retire_current(batch);
		kd_owned_mutex_notify(node, false);
		/* Node and caller stack now belong to the logical waiter. */
		BUG_ON(kd_exec_native_wait(frame));
		kd_exe_native_handoff_timing_end(true, handoff_start);
		BUG_ON(kd_exec_frame_complete(frame));
		BUG_ON(kd_exec_frame_pop(frame, NULL));
		return KD_EXE_NATIVE_DONE;
	}
	if (ret != KD_EXE_RUN_TO_UNLOCK && frame->executed) {
		pr_err("kd_owned_mutex: progressed non-continuable exit entry=%lx ret=%d\n",
		       frame->entry_ip, ret);
		BUG();
	}
	if (ret == KD_EXE_RUN_TO_UNLOCK) {
		clean = frame->outer_unlock_seen ? 0 : kd_exec_frame_record_event(
			frame, KD_EXEC_EVENT_OUTER_UNLOCK,
			frame->packet_state == kd_complete_packet_state(frame->entry_abi) ? NULL : regs);
		BUG_ON(clean || kd_exec_frame_complete(frame));
	} else {
		BUG_ON(kd_owned_mutex_jit_abort_cleanup(frame));
		BUG_ON(kd_exec_frame_abort(frame));
	}
	node->packet_state = frame->packet_state;
	BUG_ON(kd_exec_frame_pop(frame, &node->regs));
	return ret == KD_EXE_RUN_TO_UNLOCK ? 0 : ret;
}

/* Optional owner reuse across adjacent FIFO snapshots. No request survives
 * privately from the previous snapshot, and the original total body quota is
 * never reset. Wake completed producers before checking arrivals; a single
 * empty/public-SELF observation ends the batch without waiting for new work. */
static bool kd_owned_mutex_refill_batch(struct kd_owned_mutex_batch *batch,
				       unsigned int count)
{
	struct kd_mutex *lock = batch->lock;
	struct kd_owned_mutex_waiter *first;
	unsigned long flags;
	bool refilled = false;

	/* Check released before touching the public object: after an early release
	 * its new physical owner controls the public queue independently. */
	if (!owned_mutex_refill || batch->outer.released ||
	    count >= KDLOCK_SPIN_BATCH || need_resched())
		return false;
	BUG_ON(!list_empty(&batch->pending));
	if (atomic_long_read(&lock->owner) & KD_OWNED_MUTEX_FLAG_HANDOFF)
		return false;
	kd_owned_mutex_flush_wakes(batch->wake, &batch->wake_count);
	raw_spin_lock_irqsave(&lock->wait_lock, flags);
	BUG_ON(!kd_owned_mutex_owned(lock, current));
	/* A new SELF head can request HANDOFF while the completed wakeups are
	 * flushed or while wait_lock is acquired. It still ends this batch. */
	if (need_resched() ||
	    (atomic_long_read(&lock->owner) & KD_OWNED_MUTEX_FLAG_HANDOFF) ||
	    list_empty(&lock->wait_list))
		goto out;
	first = list_first_entry(&lock->wait_list, struct kd_owned_mutex_waiter, list);
	if (first->kind != KD_OWNED_MUTEX_DELEGATE)
		goto out;
	list_splice_init(&lock->wait_list, &batch->pending);
	refilled = true;
out:
	raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
	return refilled;
}

static __attribute__((noipa)) noinline notrace void
kd_owned_mutex_run_batch(struct kd_owned_mutex_batch *batch)
{
	unsigned int count = 0;

	this_cpu_inc(kd_owned_mutex_batches);
	while (!list_empty(&batch->pending) || kd_owned_mutex_refill_batch(batch, count)) {
		struct kd_owned_mutex_waiter *waiter = list_first_entry(
			&batch->pending, struct kd_owned_mutex_waiter, list);
		struct kd_owned_mutex_node *node;
		int ret;

		if (waiter->kind != KD_OWNED_MUTEX_DELEGATE ||
		    count >= KDLOCK_SPIN_BATCH || need_resched() ||
		    (atomic_long_read(&batch->lock->owner) & KD_OWNED_MUTEX_FLAG_HANDOFF))
			break;
		node = container_of(waiter, struct kd_owned_mutex_node, waiter);
		batch->current_node = node;
		batch->current_retired = false;
		ret = kd_owned_mutex_execute(node, batch);
		if (ret && ret != KD_EXE_NATIVE_DONE) {
			this_cpu_inc(kd_owned_mutex_refusals);
			break;
		}
		count++;
		if (ret != KD_EXE_NATIVE_DONE) {
			kd_owned_mutex_retire_current(batch);
			this_cpu_inc(kd_owned_mutex_bodies);
			kd_owned_mutex_defer(node, batch->wake, &batch->wake_count);
		}
		if (batch->outer.released) {
			kd_owned_mutex_flush_wakes(batch->wake, &batch->wake_count);
			return;
		}
		if (ret == KD_EXE_NATIVE_DONE)
			break;
	}
	kd_owned_mutex_rejoin(batch);
	kd_owned_mutex_flush_wakes(batch->wake, &batch->wake_count);
	kd_owned_mutex_release(batch->lock);
	batch->outer.released = true;
}

/* The executor has its own reserved stack. It never reuses an acquisition
 * packet or lends the physical owner's native unlock frames to another task. */
static __always_inline void
kd_owned_mutex_executor_call(struct kd_owned_mutex_batch *batch,
			     struct kd_owned_mutex_executor *executor)
{
	asm volatile(UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_SAVE, 0)
		     "pushq %%rbp\n\t"
		     "movq %%rsp, %c[saved](%%rsi)\n\t"
		     "movq %%rsi, %%r12\n\t"
		     "movq %c[stack](%%rsi), %%rsp\n\t"
		     "andq $-16, %%rsp\n\t"
		     "xorq %%rbp, %%rbp\n\t"
		     "callq %P[run]\n\t"
		     "movq %c[saved](%%r12), %%rsp\n\t"
		     "popq %%rbp\n\t"
		     UNWIND_HINT(0, 0, UNWIND_HINT_TYPE_RESTORE, 0)
		     : "+D"(batch), "+S"(executor), ASM_CALL_CONSTRAINT
		     : [saved] "i"(offsetof(struct kd_owned_mutex_executor, rsp)),
		       [stack] "i"(offsetof(struct kd_owned_mutex_executor, stack_ptr)),
		       [run] "i"(kd_owned_mutex_run_batch)
		     : "rax", "rbx", "rcx", "rdx", "r8", "r9", "r10", "r11",
		       "r12", "r13", "r14", "r15", "cc", "memory");
}

bool kd_owned_mutex_combine(struct kd_mutex *lock)
{
	struct kd_owned_mutex_batch batch = {
		.outer.release = kd_owned_mutex_release_outer,
		.lock = lock,
	};
	struct kd_owned_mutex_executor *executor;
	struct kd_owned_mutex_waiter *first;
	unsigned long flags;
	bool detached = false;

	if (preempt_count() || irqs_disabled() || !kd_owned_mutex_task_can_combine())
		return false;
	migrate_disable();
	preempt_disable();
	executor = &this_cpu_ptr(kd_owned_mutex_cpus)->executor;
	if (executor->busy || !executor->stack_base || kd_exec_context_occupied())
		goto unpin;
	/* Check the FIFO under its only mutation lock before taking residency and
	 * routing references. Existing delegates survive cooling/source closing. */
	raw_spin_lock_irqsave(&lock->wait_lock, flags);
	if (list_empty(&lock->wait_list) ||
	    (atomic_long_read(&lock->owner) & KD_OWNED_MUTEX_FLAG_HANDOFF)) {
		raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
		goto unpin;
	}
	first = list_first_entry(&lock->wait_list, struct kd_owned_mutex_waiter, list);
	if (first->kind != KD_OWNED_MUTEX_DELEGATE) {
		raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
		goto unpin;
	}
	raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
	if (!kd_source_frame_get())
		goto unpin;
	if (!kd_mutex_task_get(current)) {
		kd_source_frame_put();
		goto unpin;
	}
	executor->busy = true;
	INIT_LIST_HEAD(&batch.pending);
	raw_spin_lock_irqsave(&lock->wait_lock, flags);
	BUG_ON(!kd_owned_mutex_owned(lock, current));
	/* Owner retention makes the previously observed head stable. Enqueue is
	 * append-only and v1 SELF waiters cannot cancel while another task owns. */
	list_splice_init(&lock->wait_list, &batch.pending);
	raw_spin_unlock_irqrestore(&lock->wait_lock, flags);
	detached = true;
	kd_owned_mutex_executor_call(&batch, executor);
	BUG_ON(!batch.outer.released || !list_empty(&batch.pending));
	executor->busy = false;
	kd_mutex_task_put(current);
	kd_source_frame_put();
unpin:
	preempt_enable();
	migrate_enable();
	return detached;
}

void kd_owned_mutex_exit(void)
{
	int cpu, slot;
	u64 bodies = 0, batches = 0, refusals = 0, early = 0;

	if (!kd_owned_mutex_cpus)
		return;
	for_each_possible_cpu(cpu) {
		struct kd_owned_mutex_cpu *pool = per_cpu_ptr(kd_owned_mutex_cpus, cpu);
		struct kd_owned_mutex_executor *executor =
			&pool->executor;

		bodies += per_cpu(kd_owned_mutex_bodies, cpu);
		batches += per_cpu(kd_owned_mutex_batches, cpu);
		refusals += per_cpu(kd_owned_mutex_refusals, cpu);
		early += per_cpu(kd_owned_mutex_early_releases, cpu);

		for (slot = 0; slot < KD_OWNED_MUTEX_SLOTS; slot++) {
			struct kd_owned_mutex_node *node =
				&pool->nodes[slot];

			vfree(node->shadow_stack_base);
			node->shadow_stack_base = NULL;
			node->shadow_stack_ptr = 0;
		}
		vfree(executor->stack_base);
		executor->stack_base = NULL;
		executor->stack_ptr = 0;
	}
	free_percpu(kd_owned_mutex_cpus);
	kd_owned_mutex_cpus = NULL;
	pr_info("kd_owned_mutex: bodies=%llu batches=%llu refusals=%llu early_releases=%llu\n",
		bodies, batches, refusals, early);
}

int kd_owned_mutex_init_percpu(void)
{
	int cpu, slot;

	if (owned_mutex_spin_limit > 1048576 ||
	    (owned_mutex_preflight_queue && !owned_mutex_preflight_spins) ||
	    !kd_owned_mutex_preflight_spins_valid(owned_mutex_preflight_spins) ||
	    (owned_mutex_reuse_spins != 0 && owned_mutex_reuse_spins != 8 &&
	     owned_mutex_reuse_spins != 32 && owned_mutex_reuse_spins != 128))
		return -EINVAL;
	BUILD_BUG_ON(sizeof(struct kd_owned_mutex_waiter) != 40);
	BUILD_BUG_ON(sizeof(struct kd_owned_mutex_node) != 320);
	BUILD_BUG_ON(offsetof(struct kd_owned_mutex_node, regs) != 128);
	BUILD_BUG_ON(offsetof(struct kd_owned_mutex_node, outcome) != 304);
	kd_owned_mutex_cpus = alloc_percpu(struct kd_owned_mutex_cpu);
	if (!kd_owned_mutex_cpus)
		return -ENOMEM;
	for_each_possible_cpu(cpu) {
		struct kd_owned_mutex_cpu *pool = per_cpu_ptr(kd_owned_mutex_cpus, cpu);
		struct kd_owned_mutex_executor *executor =
			&pool->executor;

		for (slot = 0; slot < KD_OWNED_MUTEX_SLOTS; slot++) {
			struct kd_owned_mutex_node *node =
				&pool->nodes[slot];

			node->slot = slot;
			node->numa_node = cpu_to_node(cpu);
			node->wait = &pool->waits[slot];
			node->waiter.outcome = &node->outcome;
			rcuwait_init(node->wait);
			INIT_LIST_HEAD(&node->waiter.list);
			node->shadow_stack_base = vzalloc_node(KD_OWNED_MUTEX_STACK_SIZE,
							  cpu_to_node(cpu));
			if (!node->shadow_stack_base)
				goto fail;
			node->shadow_stack_ptr = (unsigned long)node->shadow_stack_base +
				KD_OWNED_MUTEX_STACK_SIZE - 8;
		}
		executor->stack_base = vzalloc_node(KD_OWNED_MUTEX_STACK_SIZE,
						  cpu_to_node(cpu));
		if (!executor->stack_base)
			goto fail;
		executor->stack_ptr = (unsigned long)executor->stack_base +
			KD_OWNED_MUTEX_STACK_SIZE - 8;
	}
	return 0;
fail:
	kd_owned_mutex_exit();
	return -ENOMEM;
}

bool kd_owned_mutex_check_idle(void)
{
	int cpu, slot;

	if (!kd_owned_mutex_cpus)
		return true;
	for_each_possible_cpu(cpu) {
		struct kd_owned_mutex_cpu *pool = per_cpu_ptr(kd_owned_mutex_cpus, cpu);

		if (READ_ONCE(pool->slots) || READ_ONCE(pool->active_waiters) ||
		    READ_ONCE(pool->executor.busy))
			return false;
		for (slot = 0; slot < KD_OWNED_MUTEX_SLOTS; slot++)
			if (rcuwait_active(&pool->waits[slot]))
				return false;
	}
	return true;
}

#ifdef KDLOCK_SELFTEST
#include "../../tests/kernel/mutex/owned_wait_selftest.c"
#endif
