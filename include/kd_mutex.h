#ifndef _LINUX_KD_MUTEX_H
#define _LINUX_KD_MUTEX_H

/*
 * kd_mutex — JIT-sandbox mutex delegation protocol.
 *
 * Follows the same JIT execution model as kd_spinlock: the combiner calls
 * kd_exe_on_call_hl_entry() with the waiter's saved kd_regs. The translated
 * sandbox runs the critical section and returns KD_EXE_RUN_TO_UNLOCK when it
 * reaches mutex_unlock. JIT replaces the body handoff, while queue execution
 * still uses physical shadow stacks with their own lifetime constraints.
 *
 * Each KD object owns physical exclusion and its embedded delegation root.
 * Every executor acquires the KD owner word; only that task releases it.
 * Linux mutex objects and waiters never participate in this protocol.
 */

/* Build-time policy bounds. Independent of spin batching; these values
 * change fairness/amortization policy, never physical exclusion or retirement.
 * The diagnostic histogram covers the full permitted total-cap range. */
#ifndef KDLOCK_MUTEX_BATCH
#define KDLOCK_MUTEX_BATCH 1024
#endif
#ifndef KDLOCK_MUTEX_NUMA_BOUNDARY
#define KDLOCK_MUTEX_NUMA_BOUNDARY 1024
#endif
#if KDLOCK_MUTEX_BATCH < 1 || KDLOCK_MUTEX_BATCH > 32767
#error "KDLOCK_MUTEX_BATCH must be 1..32767"
#endif
#if KDLOCK_MUTEX_NUMA_BOUNDARY < 1 || KDLOCK_MUTEX_NUMA_BOUNDARY > 32767
#error "KDLOCK_MUTEX_NUMA_BOUNDARY must be 1..32767"
#endif
#ifndef KDLOCK_MUTEX_SPIN_BUDGET
#define KDLOCK_MUTEX_SPIN_BUDGET 65536
#endif
#if KDLOCK_MUTEX_SPIN_BUDGET < 1 || KDLOCK_MUTEX_SPIN_BUDGET > 2147483647
#error "KDLOCK_MUTEX_SPIN_BUDGET must be 1..2147483647 PAUSE iterations"
#endif

#define KD_MUTEX_SHADOW_STACK_SIZE 8192L
#define KD_MUTEX_MAX_NODES 4 /* concurrent waiter slots per CPU */
#define KD_MUTEX_GATE_COMBINER 3 /* existing gate state while servicing a batch */
#define KD_MUTEX_GATE_FREE 0
#define KD_MUTEX_GATE_HELD 1
#define KD_MUTEX_GATE_ACQUIRING 2
#define KD_MUTEX_GATE_RELEASING 4
#define KD_MUTEX_GATE_PHASE_MASK 7U
#define KD_MUTEX_GATE_WITHDRAW 8U

#include <linux/atomic.h>
#include <linux/spinlock.h>
#include <linux/list.h>
#include <linux/osq_lock.h>
#include <linux/percpu.h>
#include "kd_mutex_types.h"
#include "kd_regs.h"

struct kd_exec_frame;
struct kd_mutex;
struct kd_local_waiter;
struct lock_class_key;
struct kd_mutex_node;

enum kd_mutex_custody_phase {
	KD_MUTEX_CUSTODY_WAIT_READY = 1,
	KD_MUTEX_CUSTODY_NATIVE,
	KD_MUTEX_CUSTODY_COMBINING,
	KD_MUTEX_CUSTODY_RETIRED,
};

/* Activated only after FULL has been copied to the owner's native stack.
 * The retained slot and task record name one exact ownership generation.
 * Overflow disables combining; it never rejects a valid native acquisition. */
#define KD_MUTEX_CUSTODY_LOCKS 8
struct kd_mutex_custody {
	struct kd_mutex_node *head;
	u64 generation;
	unsigned int phase;
	bool ready;
	bool source_lease;
	bool native_overflow;
	u8 native_count;
	struct kd_mutex *native_locks[KD_MUTEX_CUSTODY_LOCKS];
};

bool kd_mutex_check_idle(void);

/* Independent abortable-MCS membership inside an existing reserved slot.
 * Delegation can remain published while this native-spin membership comes
 * and goes; its links and notification must therefore never alias these. */
struct kd_mutex_osq_node {
	struct kd_mutex_osq_node *next;
	struct kd_mutex_osq_node *prev;
	int locked;
	u32 tail; /* immutable encoded CPU and slot, initialized with the pool */
};

/* READY is published only by a pinned, quiescent origin. The gate excludes
 * withdrawal during a proxy epoch; no REQUEST/ACK round trip exists.
 * CLAIMED is needed only when the exact current survives epoch closure.
 * INIT distinguishes never-ready publication from irrevocably withdrawn WAIT.
 * Zero remains the exact completion/native/head result publication. */
#define KD_MUTEX_WAIT 1
#define KD_MUTEX_PROXY_READY 2
#define KD_MUTEX_PROXY_CLAIMED 3
#define KD_MUTEX_QUEUE_INIT 4
#define KD_MUTEX_CLAIM_SLOTS 1

/*
 * kd_mutex_node — per-waiter queue node.
 *
 * Each CPU owns KD_MUTEX_MAX_NODES independently reserved slots. A slot also
 * owns its shadow stack, so an executor acquiring a sleeping KD mutex cannot
 * have its stack reused by another target task running on the same CPU.
 * A queued origin initially spins pinned, then checks scheduling after its
 * finite spin budget. The epoch protects every READY origin, while its owner
 * retains one exact current claim. A withdrawn origin stays preemptible until
 * its native head/result wake.
 * The combiner feeds node->regs
 * into kd_exe_on_call_hl_entry() to execute the waiter's critical section
 * inside the JIT sandbox.
 */
struct kd_mutex_node {
	struct kd_mutex_node *next;
	unsigned long gsbase; /* logical waiter's kernel GS base   */
	uint64_t rsp; /* saved real stack ptr (for restore) */
	void *shadow_stack_base;
	uint64_t shadow_stack_ptr;
	struct kd_mutex *lock;
	struct task_struct *task_struct_ptr;
	/* Explicit clobber continuation, or legacy hook return-slot validation. */
	unsigned long saved_ret_addr; /* CS entry point (ret_addr)         */

	/* Immutable identity and result tags are separate from the polled line.
	 * Reading the ABI must not first fetch the waiter's notification line. */
	u8 entry_abi __attribute__((aligned(64)));
	unsigned int packet_state; /* published with completed/native_resume */
	int tail; /* encoded tail (cpu+idx)            */
	int slot; /* reserved per-CPU slot index       */
	int numa_node; /* immutable slot locality, set before source publication */
	/* Origin-only exact waiter record. The version never resets on slot reuse;
	 * cold observations validate it without writing this CPU's cacheline. */
	u64 count_seq;
	struct kd_mutex *counted_lock;
	struct kd_mutex_osq_node osq;
	/* The combiner writes IP/SP and virtual registers while the producer
	 * polls locked. Sharing their cacheline makes every packet update fight
	 * the polling CPU for ownership, especially across NUMA nodes. */
	union {
		struct kd_regs regs;
		struct kd_mutex_custody custody;
	}; /* Header ends at byte 128; lifecycle asserts this offset and stride. */
	/* Optional queue residence clock, not critical-section execution time. */
	uint64_t queued_at_ns;
	/* The unused tail of the FULL packet's last line holds notification.
	 * MINIMAL/COMPLETE bodies write only the first packet line. Cold FULL
	 * handoff may share this line, but ordinary body writes never do. Keep
	 * the five-line stride and isolate the producer's next pointer too. */
	u8 completed;
	u8 locked;
	bool native_resume;
	/* Cold native suffix metadata, written only before a native release wake. */
	unsigned int native_spin_pins;
	struct kd_exec_frame *native_transfer;
};

void kd_mutex_init(struct kd_mutex *lock);
void __kd_mutex_init(struct kd_mutex *lock, const char *name,
		     struct lock_class_key *key);
void kd_mutex_destroy(struct kd_mutex *lock);
/* Conventional C ABI for indirect calls and cleanup helpers. Acquisition is
 * local; unlock still routes retained owners and borrowed continuation ACKs.
 * Include kd_mutex_api.h for the DIRECT-backed source call interface. */
/* The captured kernel already exports legacy bridge names kd_mutex_lock and
 * kd_mutex_unlock for Linux objects. Public C identifiers must link to the
 * KD-only provider even when used through a pointer or parenthesized call. */
void kd_mutex_lock(struct kd_mutex *lock) __asm__("kd_mutex_api_lock");
void kd_mutex_unlock(struct kd_mutex *lock) __asm__("kd_mutex_api_unlock");
void kd_mutex_api_lock(struct kd_mutex *lock);
void kd_mutex_api_unlock(struct kd_mutex *lock);
void kd_mutex_local_lock(struct kd_mutex *lock);
void kd_mutex_local_unlock(struct kd_mutex *lock);
int kd_mutex_lock_interruptible(struct kd_mutex *lock);
int kd_mutex_lock_killable(struct kd_mutex *lock);
void kd_mutex_lock_io(struct kd_mutex *lock);
int kd_atomic_dec_and_mutex_lock(atomic_t *count, struct kd_mutex *lock);
int kd_mutex_trylock(struct kd_mutex *lock);
bool kd_mutex_is_locked(struct kd_mutex *lock);
bool kd_mutex_is_idle(struct kd_mutex *lock);
/* Combiner state is only a hint. Ownership is authorized only for current. */
bool kd_mutex_combiner_active(struct kd_mutex *lock);
bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task);
int kd_mutex_init_percpu(void);
int kd_mutex_local_runtime_init(void);
void kd_mutex_local_runtime_exit(void);
void kd_mutex_exit(void);

void _kd_mutex_lock_abi(struct kd_mutex *lock, unsigned long rsp_value,
		       unsigned long ret_addr, unsigned long bp, unsigned int abi);
int _kd_mutex_unlock_checked(struct kd_mutex *lock);
void _kd_mutex_unlock(struct kd_mutex *lock);

int kd_mutex_debug_nested_waiters(void);
int kd_mutex_nested_lock(struct kd_mutex *lock);
int kd_mutex_nested_unlock(struct kd_mutex *lock);
/* A transfer preserves exclusion; PICKUP is acknowledged by the new owner. */
int kd_mutex_transfer_owner(struct kd_mutex *lock, struct task_struct *next);
int kd_mutex_transfer_pickup(struct kd_mutex *lock);
bool kd_mutex_custody_unlock(struct kd_mutex *lock);
void kd_mutex_custody_native_acquire(struct kd_mutex *lock);
void kd_mutex_custody_native_release(struct kd_mutex *lock);
/* Only a fast rejection hint. Every positive path validates the exact task,
 * retained node, lock and generation; this mask never grants ownership. */
DECLARE_PER_CPU(unsigned long, kd_mutex_custody_slots);
static __always_inline void kd_mutex_note_native_acquire(struct kd_mutex *lock)
{
	if (unlikely(raw_cpu_read(kd_mutex_custody_slots)))
		kd_mutex_custody_native_acquire(lock);
}
static __always_inline void kd_mutex_note_native_release(struct kd_mutex *lock)
{
	if (unlikely(raw_cpu_read(kd_mutex_custody_slots)))
		kd_mutex_custody_native_release(lock);
}
void kd_mutex_note_nested_jit(void);
/* Cold exact snapshot; -EAGAIN on repeated changes, -ENOMEM on scratch failure.
 * Neither a successful zero nor an error is an admission/lifetime barrier. */
int kd_mutex_waiter_count(struct kd_mutex *lock);
/* Stopped/joined object only: inspect exact node records without allocation. */
bool kd_mutex_waiters_idle(struct kd_mutex *lock);
void kd_mutex_note_nested_abort_release(void);

#endif /* _LINUX_KD_MUTEX_H */
