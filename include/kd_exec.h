#ifndef KD_EXEC_H
#define KD_EXEC_H

/*
 * Explicit execution state for delegated critical sections.
 *
 * Native TCLock-style handoff uses a real stack switch. The JIT backend uses
 * pt_regs and a software continuation instead, so nested execution must have
 * an explicit frame rather than relying on the C call stack.
 */

#include <linux/errno.h>
#include <linux/types.h>
#include <linux/list.h>
#include <asm/ptrace.h>

struct task_struct;
struct kd_native_request;

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

struct kd_exec_frame {
	struct pt_regs regs;
	unsigned long entry_ip;
	unsigned long outer_lock_addr;
	unsigned long continuation_ip;
	unsigned long continuation_sp;
	unsigned long gsbase;
	struct task_struct *logical_task;
	void *waiter;
	void *outgoing_rsp_ptr;
	struct kd_exec_frame *parent;
	struct kd_exec_frame *resume_target;
	void *lock_node;
	struct kd_combiner_state saved_combiner;
	unsigned long jit_lock_addr[KD_EXEC_MAX_LOCK_DEPTH];
	enum kd_exec_lock_kind jit_lock_kind[KD_EXEC_MAX_LOCK_DEPTH];
	void *jit_lock_node[KD_EXEC_MAX_LOCK_DEPTH];
	bool jit_lock_released[KD_EXEC_MAX_LOCK_DEPTH];
	unsigned int depth;
	unsigned int held_lock_depth;
	unsigned int outer_lock_depth;
	unsigned int outer_lock_index;
	unsigned int jit_lock_depth;
	enum kd_exec_lock_kind lock_kind;
	bool nested;
	bool outer_unlock_seen;
	bool completion_seen;
	int state;
	int remote_result;
	bool executed;
	bool mutex_backend;
	struct list_head native_link;
	struct kd_native_request *native_request;
};

struct kd_exec_context {
	struct kd_exec_frame frames[KD_EXEC_MAX_NESTING];
	struct task_struct *owner;
	unsigned int depth;
};

void kd_exec_context_init(void);
void kd_exec_context_exit(void);

struct kd_exec_frame *kd_exec_current_frame(void);
bool kd_exec_context_busy(void);

struct kd_exec_frame *
kd_exec_frame_push(const struct pt_regs *regs, unsigned long entry_ip,
		   unsigned long outer_lock_addr, void *waiter,
		   void *outgoing_rsp_ptr, unsigned int held_lock_depth,
		   unsigned long gsbase, struct task_struct *logical_task);
int kd_exec_frame_pop(struct kd_exec_frame *frame, struct pt_regs *regs);
bool kd_exec_frame_validate(const struct kd_exec_frame *frame);
void kd_exec_frame_save_continuation(struct kd_exec_frame *frame,
				     const struct pt_regs *regs);
unsigned int kd_exec_frame_lock_depth(const struct kd_exec_frame *frame);

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

#endif /* KD_EXEC_H */
