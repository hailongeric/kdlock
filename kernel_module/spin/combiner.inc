// SPDX-License-Identifier: GPL-2.0
// Derived from TCLocks; Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi.
/*
 * Delegated body execution, outer release and bounded combiner batches.
 * Private implementation included only by kd_spinlock.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

struct kd_spin_batch {
	struct kd_exec_outer_unlock outer;
	struct kd_spin_node *next;
	struct kd_spin_request *request;
	struct kd_exe_info *exe;
	/* Slots are append-only until drained module shutdown. */
	struct kd_spin_diag_slot *diag;
	unsigned long entry_ip;
	struct qspinlock *lock;
	struct kd_spin_node *cursor;
	struct kd_jit_batch_call call;
	bool pending;
	bool fast_previous;
	int counter;
	u64 queue_end;
#ifdef KDLOCK_SELFTEST
	int frame_event;
#endif
#ifdef NUMA_AWARE
	struct kd_spin_node *saved_tail;
#endif
};

/* The batch's source lease keeps registry slots alive until the last unbind.
 * Cache identity, never publication/readiness or the mutable code pointer.
 * Spin is the fixed backend of this batch; a foreign registration still goes
 * through the ordinary dispatcher rejection, without becoming a cache hit. */
static struct kd_exe_info *
kd_spin_batch_lookup(struct kd_spin_batch *batch, unsigned long entry_ip)
{
	struct kd_exe_info *exe = batch->exe;

	if (exe && batch->entry_ip == entry_ip &&
	    READ_ONCE(exe->lock_kind) == KD_EXE_LOCK_SPIN)
		return exe;

	exe = kd_get_exe(0, entry_ip);
	if (exe && READ_ONCE(exe->lock_kind) == KD_EXE_LOCK_SPIN) {
		batch->exe = exe;
		batch->entry_ip = entry_ip;
	}
	return exe;
}

/* Resolution is not admission. Ordinary roots validate publication once in
 * kd_exe_spin_batch_prepare; the generic path needs its own readiness check. */
static struct kd_exe_info *
kd_spin_batch_find_ready(struct kd_spin_batch *batch, unsigned long entry_ip)
{
	struct kd_exe_info *exe = kd_spin_batch_lookup(batch, entry_ip);

	return kd_exe_entry_is_ready(exe, 0, entry_ip) ? exe : NULL;
}

/* A's executor keeps its ticket pin and local frame stack, not ownership of
 * A. No published successor can be inspected again by this detached batch. */
static int kd_spin_release_outer(struct kd_exec_frame *frame,
				 struct kd_exec_outer_unlock *hook)
{
	struct kd_spin_batch *batch =
		container_of(hook, struct kd_spin_batch, outer);
	struct qspinlock *lock = (struct qspinlock *)frame->outer_lock_addr;
	struct qspinlock *word = batch->request->word;
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	struct kd_spin_node *next = batch->next;
	unsigned int i, remaining = 0;
	int ret;

	if (frame->mutex_backend || !next ||
	    (!check_irq_node(next) && !next->execution->frame.logical_task) ||
	    frame->jit_lock_kind[frame->outer_lock_index] !=
		    KD_EXEC_LOCK_QUEUE_OWNER ||
	    READ_ONCE(word->locked) != _Q_LOCKED_COMBINER_VAL)
		return -EINVAL;
#ifdef NUMA_AWARE
	if (ptr->local_queue_head) {
		if (!ptr->local_queue_tail)
			return -EINVAL;
		ptr->local_queue_tail->next = next;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_splice(lock, next, true);
#endif
		next = ptr->local_queue_head;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
		frame->saved_combiner.local_queue_head = NULL;
		frame->saved_combiner.local_queue_tail = NULL;
	}
#endif
	for (i = frame->outer_lock_index; i < frame->jit_lock_depth; i++)
		remaining += !frame->jit_lock_released[i];
	/* Log before L opens: a native successor may run immediately afterward. */
	pr_info("kd_spin outer release: task=%d owner=%d owner_task=%lx cpu=%u outer=%lx next_task=%d next_cpu=%d remaining=%u remote=%u\n",
		frame->logical_task->pid, current->pid, (unsigned long)current,
		raw_smp_processor_id(), frame->outer_lock_addr,
		next->execution ? next->execution->frame.logical_task->pid : 0,
		next->cpuid, remaining,
		kd_exec_frame_remote_pending(frame));
	ret = kd_spin_entry_release_origin(&batch->request->ref);
	if (ret)
		return ret;
	kd_spin_debug_ooo_unlock(lock, kd_spin_lock_stack_depth(ptr));
	smp_store_release(&word->locked, 0);
	smp_store_release(&next->locked, 0);
	return 0;
}

/* Reclaim the original waiter's outer lock on return from a native/remote
 * delegation run. The holder must reacquire origin scheduling only, never
 * open a new queue fast path through this packet.
 */
static void kd_spin_reclaim_outer(struct kd_spin_request *request)
{
	/* Rejoin as a non-combinable MCS waiter on the existing C stack.
	 * The original ticket remains live; do not allocate another frame. */
	kd_hotlock_spin_entry_pinned();
	kd_spin_acquire_nondelegated(request->word);
	BUG_ON(kd_spin_entry_reclaim(&request->ref));
}

#include "execute.inc"

/* Single-root admission and binding touch only hot state. Complex/virtual,
 * legacy wrapper and refused candidates stay on execute_cs's existing path. */
static bool kd_spin_batch_prepare_simple(struct kd_spin_batch *batch,
					 struct kd_spin_node *node)
{
	struct kd_spin_continuation *execution = node->execution;
	struct kd_exec_frame *frame = &execution->frame;
	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	struct kd_exe_info *exe;

	if (execution->kind == KD_SPIN_CONT_VIRTUAL ||
	    !execution->native_regs_decoded || kd_exec_current_frame() ||
	    kd_spin_lock_stack_depth(ptr) != 1 || kd_spin_jit_is_disabled(batch->diag))
		return false;
	exe = kd_spin_batch_lookup(batch, frame->entry_ip);
	if (!exe)
		return false;
	/* Eligibility precedes binding so a legacy upload needs no undo/pop. */
	frame->spin_simple = true;
	if (!kd_exe_spin_batch_prepare(exe, frame, &batch->call)) {
		frame->spin_simple = false;
		return false;
	}
	if (kd_exec_frame_bind(frame, 1, true)) {
		frame->spin_simple = false;
		return false;
	}
	ptr->curr_cs_cpu = node->cpuid;
#ifdef KDLOCK_SELFTEST
	/* Observers inspect ledgers; production roots leave this storage cold. */
	kd_exec_frame_prepare_complex(frame);
	batch->frame_event = kd_spin_selftest_frame_begin(frame);
#endif
	batch->queue_end = kd_exe_queue_timing_start();
	frame->executed = true;
	batch->pending = true;
	this_cpu_inc(kd_spin_diag_cpu->batch_entries);
	if (batch->fast_previous)
		this_cpu_inc(kd_spin_diag_cpu->ww_jumps);
	return true;
}

/* Like TCLock's WWJUMP, keep one combiner continuation for the entire batch.
 * Finish and unbind before publishing completion, then admit the successor.
 * Both wrapper ABIs clobber compiler-owned registers inside this same C frame;
 * neither a mixed boundary nor a new waiter returns through an outer runner.
 * Physical RSP stays on this stack; only the JIT's logical stack is switched. */
static void kd_spin_batch_run(void *opaque)
{
	struct kd_spin_batch *batch = opaque;
	struct qspinlock *lock = batch->lock;
	struct kd_spin_cpu_state *ptr __maybe_unused = this_cpu_ptr(&kd_spin_cpu);
	struct kd_spin_node *curr_node, *next_node;
	int exe_flag;
	for (;;) {
		curr_node = batch->cursor;
		if (batch->pending) {
			next_node = batch->next;
			if (kd_exe_spin_batch_completed(&batch->call)) {
				struct kd_exec_frame *frame = &curr_node->execution->frame;

#ifdef KDLOCK_SELFTEST
				/* Observers require the completed ledger before its pop. */
				BUG_ON(kd_exec_frame_complete_single_spin(frame));
				kd_spin_selftest_frame_end(batch->frame_event, frame,
							   KD_EXE_RUN_TO_UNLOCK);
				BUG_ON(kd_exec_frame_pop(frame, NULL));
#else
				BUG_ON(kd_exec_frame_retire_single_spin(frame));
#endif
				kd_exe_queue_timing_end(false,
					&curr_node->execution->queued_at_ns, batch->queue_end);
				kd_spin_debug_jit_success(batch->diag, 1);
				batch->pending = false;
				batch->fast_previous = true;
				exe_flag = 0;
			} else {
				/* Promote before the generic dispatcher consumes this exit.
				 * Install the lock hook before a service can release L. */
				kd_spin_jit_prepare_complex(&curr_node->execution->frame);
				curr_node->execution->frame.outer_unlock_hook = &batch->outer;
				batch->fast_previous = false;
				exe_flag = execute_cs(lock, curr_node, batch);
			}
		} else {
#ifdef NUMA_AWARE
			batch->saved_tail = ptr->local_queue_tail;
#endif
			batch->counter++;

			next_node = get_next_node(curr_node);
			batch->next = next_node;
			batch->outer.released = false;
			kd_spin_prefetch_request(next_node);

			if (kd_spin_batch_prepare_simple(batch, curr_node)) {
				if (batch->call.entry_abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1)
					kd_jit_clobber_call_v1(&batch->call);
				else
					kd_jit_legacy_batch_call(&batch->call);
				continue;
			}
			batch->fast_previous = false;
			exe_flag = execute_cs(lock, curr_node, batch);
		}

#ifdef NUMA_AWARE
		if (exe_flag == KD_EXE_NO_RUN || exe_flag == KD_EXE_RUN_ERROR) {
#ifdef KDLOCK_SELFTEST
			struct kd_spin_node *discarded_tail =
				ptr->local_queue_tail;
#endif
			/* The rejected waiter's next still owns this scan's followers.
			 * Discard only speculative deferrals; the final splice attaches
			 * any previously committed prefix to the rejected waiter. */
			if (!batch->saved_tail)
				ptr->local_queue_head = NULL;
			ptr->local_queue_tail = batch->saved_tail;
#ifdef KDLOCK_SELFTEST
			if (discarded_tail != batch->saved_tail)
				kd_spin_selftest_restore(lock, curr_node,
							 discarded_tail,
							 exe_flag);
#endif
		}
#endif
		if (exe_flag == KD_EXE_NO_RUN) {
			print_debug("can't assembly\n");
			next_node = curr_node;
			batch->next = next_node;
			return;
		}
		if (exe_flag == KD_EXE_RUN_ERROR) {
			print_debug("run error\n");
			/* No JIT body ran. Keep the packet queued and uncompleted until
			 * it acquires the lock. Native packets may need ret4; virtual
			 * packets use the ordinary acquired return to their parent. */
			next_node = curr_node;
			batch->next = next_node;
			return;
		}

		if (exe_flag != KD_EXE_NATIVE_DONE)
			clear_locked_set_completed(curr_node);

		if (batch->outer.released) {
			/* B and this logical frame have finished. A's queue was already
			 * published; only reacquire for our own original request. */
			return;
		}

		if (next_node == NULL || next_node->next == NULL ||
		    check_irq_node(next_node) || check_irq_node(next_node->next) ||
		    batch->counter >= kd_combiner_batch_size) {
			batch->next = next_node;
			return;
		}

		batch->cursor = next_node;
	}

}

#pragma GCC push_options
#pragma GCC optimize("O3")
/*
 * Combiner loop over the currently-formed queue segment.
 * Stops at batch boundary, native handoff, OOO release, or JIT failure and
 * leaves the lock in a state expected by the successor waiter.
 */
__attribute__((noipa)) noinline notrace static void
run_combiner(struct qspinlock *lock, struct kd_spin_node *curr_node,
	     struct kd_spin_request *request, struct kd_spin_diag_slot *diag)
{
#ifdef DEBUG_KD_SPIN
	BUG_ON(curr_node == NULL);
#endif
	struct kd_spin_node *next_node =
		kd_spin_linked_successor(request->word, curr_node);
	struct kd_spin_batch batch = {
		.outer.release = kd_spin_release_outer,
		.request = request,
	};

	if (next_node == NULL || check_irq_node(curr_node) ||
	    check_irq_node(next_node) || !kd_source_frame_get()) {
		set_locked(request->word);
		/*
		 * Make this node spin on the locked variable and then it will
		 * become the combiner.
		 */
		smp_store_release(&curr_node->locked, false);
		smp_mb();
		return;
	}

	struct kd_spin_cpu_state *ptr = this_cpu_ptr(&kd_spin_cpu);
	batch.diag = diag;
	kd_spin_debug_combiner(batch.diag, kd_spin_lock_stack_depth(ptr));

	batch.lock = lock;
	batch.cursor = curr_node;
	kd_spin_batch_run(&batch);
	if (batch.outer.released) {
		kd_spin_reclaim_outer(request);
		kd_source_frame_put();
		return;
	}
	next_node = batch.next;

#ifdef NUMA_AWARE
	if (ptr->local_queue_head != NULL) {
		ptr->local_queue_tail->next = next_node;
#ifdef KDLOCK_SELFTEST
		kd_spin_selftest_splice(lock, next_node, false);
#endif
		next_node = ptr->local_queue_head;
		ptr->local_queue_head = NULL;
		ptr->local_queue_tail = NULL;
	}
#endif

	print_debug("After combiner %d, next node: %d\n", smp_processor_id(),
		    next_node->cpuid);

#ifdef DEBUG_KD_SPIN
	BUG_ON(next_node == NULL);
#endif

	set_locked(request->word);

	/* Publish the finished queue splice before successor acquisition. This
	 * is the last node access: its waiter can immediately reuse the slot. */
	smp_store_release(&next_node->locked, false);
	/* One lease covers the complete synchronous batch, including native ACK
	 * waits and every child unbind. New requests still check admission. */
	kd_source_frame_put();
}
#pragma GCC pop_options
