#ifndef KD_EXEC_H
#define KD_EXEC_H

/*
 * Explicit execution state for delegated critical sections.
 *
 * Native TCLock-style handoff uses a real stack switch. The JIT backend uses
 * pt_regs and a software continuation instead, so nested execution must have
 * an explicit frame rather than relying on the C call stack for logical state.
 * Suspended physical C/shadow stacks must still stay alive until return/ACK.
 */

#include <linux/errno.h>
#include <linux/types.h>
#include <linux/list.h>
#include <asm/ptrace.h>
#include "kd_call.h"
#include "exe_info.h"
#include "kd_spin_entry.h"

struct task_struct;
struct kd_native_request;
struct kd_remote_request;

#define KD_EXEC_MAX_NESTING 8
#define KD_EXEC_MAX_LOCK_DEPTH 8

enum kd_exec_event {
	KD_EXEC_EVENT_CONTINUE = 0,
	KD_EXEC_EVENT_NESTED_LOCK,
	KD_EXEC_EVENT_NESTED_UNLOCK,
	KD_EXEC_EVENT_OUTER_UNLOCK,
	KD_EXEC_EVENT_COMPLETE,
	KD_EXEC_EVENT_ERROR,
};

enum kd_exec_frame_state {
	KD_EXEC_FRAME_UNUSED = 0,
	KD_EXEC_FRAME_RUNNING,
	KD_EXEC_FRAME_WAITING_LOCK,
	KD_EXEC_FRAME_RESUME,
	KD_EXEC_FRAME_COMPLETE,
	KD_EXEC_FRAME_ERROR,
};

enum kd_exec_lock_kind {
	KD_EXEC_LOCK_NONE = 0,
	KD_EXEC_LOCK_FAST,
	KD_EXEC_LOCK_QUEUE_OWNER,
	KD_EXEC_LOCK_NATIVE,
};

enum kd_exec_remote_state {
	KD_EXEC_REMOTE_IDLE,
	KD_EXEC_REMOTE_WAITING,
	KD_EXEC_REMOTE_NATIVE,
	KD_EXEC_REMOTE_DONE,
};

/*
 * State that TCLock saves before entering a nested combiner. Pointers are
 * intentionally opaque here; the spinlock backend owns their concrete types.
 */
struct kd_combiner_state {
	unsigned long lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	unsigned int lock_depth;
	int curr_cs_cpu;
	int prev_cs_cpu;
	void *local_queue_head;
	void *local_queue_tail;
	unsigned long local_shadow_stack_ptr;
	int irqs_disabled;
};

struct kd_exec_frame;

/* Backend-owned batch state remains live until this frame is retired. */
struct kd_exec_outer_unlock {
	int (*release)(struct kd_exec_frame *frame,
		       struct kd_exec_outer_unlock *hook);
	bool released;
};

struct kd_exec_frame {
	/* Ordinary single-lock execution touches this 64-byte header and the
	 * referenced packet. The cold ledger below is activated only on promotion;
	 * no allocation, zero-fill or packet copy is needed at that boundary. */
	struct pt_regs *regs_ref;
	unsigned long entry_ip;
	unsigned long outer_lock_addr;
	unsigned long gsbase;
	struct task_struct *logical_task;
	struct kd_exec_frame *parent;
	int state;
	unsigned int depth;
	bool executed;
	bool mutex_backend;
	bool spin_simple;
	bool request_frame;
	bool batch_lease;
	bool complex_ready;
	bool regs_borrowed;
	bool completion_seen;
	struct pt_regs regs;
	unsigned int entry_abi;
	unsigned int packet_state;

	/* Cold storage: unread until complex_ready, including all eight locks,
	 * control/native routing and the combiner checkpoint. */
	unsigned long continuation_ip;
	union {
		unsigned long continuation_sp;
		struct pt_regs *borrowed_regs;
	};
	unsigned long delegated_lock_addr;
	struct kd_exec_frame *resume_target;
	struct kd_remote_request *remote_request;
	struct kd_combiner_state saved_combiner;
	unsigned long jit_lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	enum kd_exec_lock_kind jit_lock_kind[KD_EXEC_MAX_LOCK_DEPTH];
	void *jit_lock_node[KD_EXEC_MAX_LOCK_DEPTH];
	bool jit_lock_released[KD_EXEC_MAX_LOCK_DEPTH];
	unsigned int held_lock_depth;
	unsigned int outer_lock_depth;
	unsigned int outer_lock_index;
	unsigned int jit_lock_depth;
	int logical_pid;
	bool outer_unlock_seen;
	int remote_result;
	struct kd_exec_outer_unlock *outer_unlock_hook;
	struct kd_call_state control_call;
	struct list_head native_link;
	struct kd_native_request *native_request;
	struct kd_spin_ref spin_origin;
};

struct kd_exec_context {
	/* One physical owner while depth != 0; frames cannot migrate independently. */
	struct kd_exec_frame frames[KD_EXEC_MAX_NESTING];
	struct kd_exec_frame *top;
	struct task_struct *owner;
	unsigned int depth;
};

static inline struct pt_regs *kd_exec_frame_regs(const struct kd_exec_frame *frame)
{
	if (frame->regs_ref)
		return frame->regs_ref;
	return frame->regs_borrowed ? frame->borrowed_regs :
		(struct pt_regs *)&frame->regs;
}

static inline void kd_exec_frame_own_regs(struct kd_exec_frame *frame)
{
	if (frame->regs_borrowed) {
		frame->regs = *frame->borrowed_regs;
		frame->continuation_sp = 0;
		frame->regs_borrowed = false;
	}
}

/* Module lifetime and CPU-local frame stack. Push/pop also balance the source
 * lease; a completed event alone neither pops the frame nor releases its pin. */
void kd_exec_context_init(void);
void kd_exec_context_exit(void);

struct kd_exec_frame *kd_exec_current_frame(void);
bool kd_exec_context_busy(void);

/* Prepare once on the producer; bind only changes physical execution state.
 * batch_lease requires an enclosing source lease through the final unbind. */
void kd_exec_frame_prepare_complex(struct kd_exec_frame *frame);
void kd_exec_frame_prepare(struct kd_exec_frame *frame, unsigned long entry_ip,
			   unsigned long lock, unsigned long gsbase,
			   struct task_struct *task);
int kd_exec_frame_bind(struct kd_exec_frame *frame, unsigned int lock_depth,
		       bool batch_lease);

struct kd_exec_frame *
kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,
		   unsigned long outer_lock_addr, void *waiter,
		   void *outgoing_rsp_ptr, unsigned int held_lock_depth,
		   unsigned long gsbase, struct task_struct *logical_task);
/* Bind a physical spin packet; nested physical contexts retain a private copy. */
struct kd_exec_frame *
kd_exec_frame_push_spin(struct pt_regs *regs, unsigned long entry_ip,
		       unsigned long outer_lock_addr, void *waiter,
		       void *outgoing_rsp_ptr, unsigned int held_lock_depth,
		       unsigned long gsbase, struct task_struct *logical_task);
int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs);
int kd_exec_frame_complete_single_spin(struct kd_exec_frame *frame);
bool kd_exec_frame_validate(const struct kd_exec_frame *frame);
void kd_exec_frame_save_continuation(struct kd_exec_frame *frame,
				     const struct pt_regs *regs);
unsigned int kd_exec_frame_lock_depth(const struct kd_exec_frame *frame);

/* Logical lock ledger only. Backends perform physical acquisition/release;
 * these mutations must describe that outcome, never grant ownership by fiat. */
int kd_exec_frame_set_lock_stack(struct kd_exec_frame *frame,
				 const unsigned long *lock_addr,
				 unsigned int depth);
int kd_exec_frame_set_lock_entries(struct kd_exec_frame *frame,
				   const unsigned long *lock_addr,
				   const enum kd_exec_lock_kind *lock_kind,
				   void *const *lock_node,
				   const bool *lock_released,
				   unsigned int depth);
int kd_exec_frame_lock_push(struct kd_exec_frame *frame,
			    unsigned long lock_addr,
			    enum kd_exec_lock_kind kind, void *lock_node);
int kd_exec_frame_lock_pop(struct kd_exec_frame *frame,
			   unsigned long lock_addr);
int kd_exec_frame_lock_mark_released(struct kd_exec_frame *frame,
				     unsigned long lock_addr);
enum kd_exec_lock_kind
kd_exec_frame_lock_kind(const struct kd_exec_frame *frame,
			unsigned long lock_addr);
void *kd_exec_frame_lock_node(const struct kd_exec_frame *frame,
			      unsigned long lock_addr);
bool kd_exec_frame_lock_contains(const struct kd_exec_frame *frame,
				 unsigned long lock_addr);
bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *frame);
bool kd_exec_frame_can_complete(const struct kd_exec_frame *frame);
bool kd_exec_frame_locks_released(const struct kd_exec_frame *frame);
bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame);
/* Ledger admission only; physical locks and origin references stay backend-owned. */
bool kd_exec_frame_can_borrow_locks(const struct kd_exec_frame *frame);
/* Completion requires every retained lock released and remote requests done.
 * Aborting changes frame state; backend cleanup/owner ACKs still must finish. */
int kd_exec_frame_record_event(struct kd_exec_frame *frame,
			       enum kd_exec_event event,
			       const struct pt_regs *regs);
int kd_exec_frame_complete(struct kd_exec_frame *frame);
int kd_exec_frame_abort(struct kd_exec_frame *frame);
int kd_exec_frame_state(const struct kd_exec_frame *frame);

/* Native continuation borrows the combiner's locks until the waiter unlocks.
 * Unlock requests are serviced on the executor that acquired each lock. */
int kd_exec_native_begin(struct kd_exec_frame *frame, bool mutex);
int kd_exec_native_wait(struct kd_exec_frame *frame);
bool kd_exec_native_unlock(unsigned long lock_addr, bool mutex);

/* Only a waiting virtual request owns these logical-parent links/mailboxes. */
int kd_exec_remote_unlock(struct kd_exec_frame *frame, unsigned long lock_addr);
void kd_exec_remote_poll(struct kd_exec_frame *frame);
int kd_exec_remote_native(struct kd_exec_frame *frame);
int kd_exec_remote_complete(struct kd_exec_frame *frame);
/* Detach an unexecuted child without cancelling the queued parent request. */
void kd_exec_remote_cancel(struct kd_exec_frame *frame);

#ifdef KDLOCK_SELFTEST
void kd_exec_selftest_capacity_probe(const struct kd_exec_frame *frame);
void kd_exec_selftest_capacity_report(void);
#endif

#endif /* KD_EXEC_H */
