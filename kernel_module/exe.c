/*
 * Critical-section registry and high-level JIT dispatcher (derived from BCD).
 * This file owns the high-level wrapper exit loop. execution/ components own
 * services, timing, registry and known CALL handling. Read with sys.c for
 * uploads and kd_exec.c for frame/owner lifetimes; see README.md for the map.
 *
 * Registration consumes one bounded code block; it does not compile text.
 * The daemon fills that block, then this file interprets wrapper exit packets:
 *   CALL_MISS: known lock control, or original-waiter native continuation;
 *   HOSTCALL: exact allowlisted service, then another wrapper invocation;
 *   ENTRY_REFUSED: native fallback only after validating an unstarted root;
 *   NATIVE_ESCAPE: checked instruction boundary, finish this native suffix;
 *   INDIRECT_CALL: exact source CALL miss, validate then finish native suffix;
 *   IJ_MISS / ERROR / INST_LIMIT: error, not generic native continuation.
 * The budget counts instrumented blocks, not retired instructions. NORMAL
 * remains a legacy syscall exit, unsupported for kernel critical sections.
 *
 * Only validated outer-unlock handling completes a delegated request. A miss
 * after stores never rolls them back or grants permission to replay the entry.
 * Mutex and guarded spin frames bind immutable code images. Ordinary spin
 * blocks retain in-place publication until their first guarded generation.
 * Original-source residency pins are separate from executable image identity.
 */
#include "exe.h"
#include "kd_exec.h"
#include "kd_source.h"
#include "kd_jit_batch.h"

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
#include <linux/unaligned.h>
#include <linux/vmalloc.h>

#include "utils.h"
#include "kd_lock.h"
#include "kd_mutex.h"
#include "kd_mutex_direct.h"
#include "kd_spinlock.h"
#include "kd_rwlock.h"
#include "kd_hostcall.h"
#include "kd_api_provider.h"

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

/* Exact observations only; admission and ownership never depend on this total. */
static atomic64_t kd_native_escape_count = ATOMIC64_INIT(0);
static int kd_native_escape_count_get(char *buffer, const struct kernel_param *kp)
{
	(void)kp;
	return scnprintf(buffer, PAGE_SIZE, "%lld\n",
			 (long long)atomic64_read(&kd_native_escape_count));
}
static const struct kernel_param_ops kd_native_escape_count_ops = {
	.get = kd_native_escape_count_get,
};
module_param_cb(native_escape_count, &kd_native_escape_count_ops, NULL, 0444);
MODULE_PARM_DESC(native_escape_count, "Validated instruction-marker native continuations");

static atomic64_t kd_address_guard_count = ATOMIC64_INIT(0);
static int kd_address_guard_count_get(char *buffer, const struct kernel_param *kp)
{
	(void)kp;
	return scnprintf(buffer, PAGE_SIZE, "%lld\n",
			 (long long)atomic64_read(&kd_address_guard_count));
}
static const struct kernel_param_ops kd_address_guard_count_ops = {
	.get = kd_address_guard_count_get,
};
module_param_cb(address_guard_count, &kd_address_guard_count_ops, NULL, 0444);
MODULE_PARM_DESC(address_guard_count, "Validated spin address-guard native continuations");

static void *kd_code_block_pool[KD_CODE_BLOCK_POOL];
static void *kd_code_block_allocations[KD_CODE_BLOCK_POOL];
/* Direct E8 calls need addresses in the kernel/module rel32 region. This cold
 * pool has separate storage, but shares the same 64 image descriptors. */
static void *kd_near_block_pool[KD_CODE_BLOCK_POOL];
static void *kd_near_block_allocations[KD_CODE_BLOCK_POOL];
static int kd_near_block_free;
static void (*kd_near_memfree)(void *);
static struct kd_jit_image kd_images[KD_CODE_BLOCK_POOL];
static const struct kd_jit_image *kd_published_images[KD_MAX_EXE];
static int kd_code_block_free;
static atomic_t kd_code_block_gate = ATOMIC_INIT(0);

static unsigned long kd_code_block_gate_lock(void)
{
	unsigned long flags;

	/* A process-side publisher must not be preempted by a lock hook which
	 * takes the same existing registry gate on this CPU. */
	local_irq_save(flags);
	while (atomic_cmpxchg_acquire(&kd_code_block_gate, 0, 1))
		cpu_relax();
	return flags;
}

static void kd_code_block_gate_unlock(unsigned long flags)
{
	atomic_set_release(&kd_code_block_gate, 0);
	local_irq_restore(flags);
}

static unsigned long end_points[6];
static int end_point_count;
static unsigned long raw_spin_lock_addr;
static unsigned long raw_spin_unlock_addr;
static unsigned long clobber_spin_lock_addr;
static unsigned long clobber_spin_unlock_addr;
static unsigned long pinned_spin_lock_addr;
static unsigned long cold_spin_unlock_addr;
static unsigned long rwlock_fast_unlock_addr;
static unsigned long mutex_lock_addr;
static unsigned long mutex_unlock_addr;
static unsigned long clobber_mutex_lock_addr;
static unsigned long clobber_mutex_unlock_addr;
static unsigned long direct_mutex_lock_addr;
static unsigned long contended_mutex_lock_addr;
static unsigned long outer_mutex_lock_addr;
static unsigned long direct_mutex_unlock_addr;

#include "execution/native_terminals.inc"
#include "execution/hostcalls.inc"

#include "execution/timing.inc"

#include "execution/registry_lifecycle.inc"
#include "execution/images.inc"

#include "execution/control_calls.inc"

#include "execution/registry_publish.inc"

#include "execution/wrapper_entry.inc"

/* A bridge is per-object. Only a sole, exact root acquisition can complete
 * through its alias here; early/nested aliases retain their Native CALL. */
static bool kd_jit_outer_unlock(struct kd_exec_frame *frame,
				struct kd_regs *regs, unsigned long outer)
{
	return is_outer_lock_unlock(regs, outer) ||
		(frame && kd_exec_frame_can_borrow_locks(frame) &&
		 !kd_exec_frame_has_unreleased_nested(frame) &&
		 kd_api_outer_unlock(regs->ip, regs->di, outer, frame->mutex_backend));
}

static int kd_exe_dispatch(struct kd_exe_info *exe, struct kd_regs *regs,
			  unsigned long entry_ip, unsigned long outer_lock_addr,
			  const struct kd_jit_batch_call *pending)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();
	void (*translated)(struct kd_regs *regs, unsigned long *args);
	unsigned long args[2];
	int continuation_count = 0;
	int hostcall_count = 0;
	unsigned int string_count = 0;
	unsigned long direct_strcmp = 0, direct_pad = 0;
	bool direct_image;
	bool direct_returned = false;
	bool root_escape_image;
	bool root_escape_returned = false;
	const struct kd_jit_image *previous_image;
	bool resume_after_hostcall = false;
	bool body_reported = false;
	bool pristine_root;
	u64 dispatch_start;
	int ret_flag;

	/* Both a pending batch return and a refused fast preparation arrive here.
	 * Materialize before generic validation, scope checks, logging or service
	 * reads; preserve a MINIMAL/refused borrowed packet and consume FULL once. */
	if (frame && frame->mutex_backend && !frame->complex_ready &&
	    kd_exec_frame_prepare_mutex_complex(frame))
		return KD_EXE_RUN_ERROR;
	if (!regs || !frame || !kd_exec_frame_validate(frame) ||
	    !frame->gsbase || !frame->logical_task)
		return KD_EXE_RUN_ERROR;

	/* Reuse the caller's slot, not its earlier readiness result. A successful
	 * frame push admitted a source lease; closure before that push refuses,
	 * closure observed here refuses, and closure racing after this check must
	 * retain pins while this frame drains. Slot storage/keys are never reused
	 * in-session. Mutex frames separately bind one immutable code generation. */
	if (!pending && !kd_exe_entry_is_ready(exe, 0, entry_ip)) {
		if (!exe)
			return KD_EXE_NO_RUN;
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
	if (!pending && !kd_jit_entry_has_scope(frame, regs, entry_ip)) {
		kd_jit_log_hl_error("ENTRY_SCOPE_MISMATCH", frame, regs, 0,
				    -EINVAL, 0, 0);
		return KD_EXE_NO_RUN;
	}
	previous_image = frame->image;
	if (!kd_jit_image_matches(exe, frame))
		return frame->executed ? KD_EXE_RUN_ERROR : KD_EXE_NO_RUN;
	direct_image = kd_jit_direct_image(frame);
	root_escape_image = kd_jit_root_escape_image(frame);
	if (!pending && (!kd_jit_direct_entry(frame) ||
			 !kd_jit_root_escape_entry(frame))) {
		frame->image = previous_image;
		return frame->executed ? KD_EXE_RUN_ERROR : KD_EXE_NO_RUN;
	}

	/* Exclude pre-entry rejections and the caller's frame setup/teardown. */
	dispatch_start = pending ? pending->dispatch_start : kd_jit_timing_start();
	pristine_root = pending || (!frame->resume_target && regs->ip == entry_ip);
	translated = kd_jit_bound_code(exe, frame);
	for (;;) {
		int call_ret;
		int fault_kind;
		unsigned long entry_sp = regs->sp;
		u64 boundary_start;

		if ((direct_image && direct_returned) ||
		    (root_escape_image && root_escape_returned)) {
			ret_flag = KD_EXE_RUN_ERROR;
			break;
		}

		/* The batch wrapper already ran. Consume that exit exactly once; an
		 * extra invocation here would repeat stores before handling the miss. */
		if (pending) {
			if (direct_image && !kd_jit_note_direct_calls(pending, frame))
				return KD_EXE_RUN_ERROR;
			if (direct_image) {
				direct_strcmp = pending->direct_strcmp;
				direct_pad = pending->direct_pad;
			}
			kd_jit_timing_end(KD_JIT_TIME_WRAPPER, pending->wrapper_start);
			args[0] = pending->args[0];
			args[1] = pending->args[1];
			entry_sp = pending->entry_sp;
			pending = NULL;
			fault_kind = 0;
			goto returned_wrapper;
		}
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
			if (kd_entry_abi_clobber(frame->entry_abi) &&
			    frame->packet_state == KD_PACKET_MINIMAL) {
				struct kd_jit_batch_call call;

				kd_jit_prepare_clobber(&call, frame, (void *)translated);
				kd_jit_clobber_call_v1(&call);
				if (direct_image && !kd_jit_note_direct_calls(&call, frame))
					return KD_EXE_RUN_ERROR;
				if (direct_image) {
					direct_strcmp = call.direct_strcmp;
					direct_pad = call.direct_pad;
				}
				args[0] = call.args[0];
				args[1] = call.args[1];
			} else {
				translated(regs, args);
			}
			kd_jit_timing_end(KD_JIT_TIME_WRAPPER, boundary_start);
returned_wrapper:
			direct_returned = direct_image;
			root_escape_returned = root_escape_image;
			if (args[0] == KD_EXE_ENTRY_REFUSED) {
				/* Only this explicit pre-body exit can undo our conservative
				 * executed mark. A zero witness by itself never permits replay.
				 * Root packet preservation is part of the generated guard ABI.
				 */
				if (pristine_root && !continuation_count &&
				    !hostcall_count && !string_count && !direct_strcmp && !direct_pad &&
				    regs->ip == entry_ip &&
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
				kd_exe_note_body(entry_ip, outer_lock_addr, args[1]);
				body_reported = true;
			}
			if (resume_after_hostcall)
				atomic64_inc(&kd_hostcall_resumed);
		}
		resume_after_hostcall = false;

		/* A fresh physical single-lock root needs no control transaction or
		 * combiner checkpoint for its final unlock. Match the backend's exact
		 * CALL target as well as L; mixed mutex/spin exits stay rejected below.
		 * Every other exit materializes complex state BEFORE its side effects. */
		if (args[0] == KD_EXE_CLOBBER_COMPLETE) {
			/* A minimal result never enters the general register dispatcher. */
			if (frame->packet_state != KD_PACKET_COMPLETE ||
			    !kd_jit_minimal_complete_allowed(frame)) {
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}
			ret_flag = KD_EXE_RUN_TO_UNLOCK;
			break;
		}
		if (frame->packet_state != KD_PACKET_FULL) {
			ret_flag = KD_EXE_RUN_ERROR;
			break;
		}
		/* A native mutex waiter releases its node before the owner ACK/pop.
		 * Detach only after a real FULL exit, before any C control service or
		 * publication can outlive that node. Normal COMPLETE never copies it. */
		if (frame->mutex_backend && frame->regs_borrowed) {
			kd_exec_frame_own_regs(frame);
			regs = kd_exec_frame_regs(frame);
		}
		if (frame->spin_simple) {
			if (!direct_image && !root_escape_image &&
			    args[0] == KD_EXE_CALL_MISS &&
			    regs->ip == raw_spin_unlock_addr &&
			    regs->di == outer_lock_addr) {
				ret_flag = KD_EXE_RUN_TO_UNLOCK;
				break;
			}
			kd_spin_jit_prepare_complex(frame);
			regs = kd_exec_frame_regs(frame);
		}
		/* A root-marker image has no dispatcher control or hostcall path.
		 * Refuse malformed exits before servicing a control operation.
		 * Missing ordinary CALLs can still finish natively on the waiter. */
		if (root_escape_image &&
		    (!kd_jit_root_escape_owner(frame) ||
		     args[0] == KD_EXE_HOSTCALL ||
		     (args[0] == KD_EXE_CALL_MISS &&
		      (regs->ip == raw_spin_lock_addr ||
		       regs->ip == clobber_spin_lock_addr ||
		       regs->ip == pinned_spin_lock_addr ||
		       regs->ip == raw_spin_unlock_addr ||
		       (regs->ip == clobber_spin_unlock_addr &&
			regs->di != outer_lock_addr) ||
		       regs->ip == cold_spin_unlock_addr ||
		       regs->ip == rwlock_fast_unlock_addr ||
		       regs->ip == mutex_lock_addr || regs->ip == mutex_unlock_addr ||
		       regs->ip == direct_mutex_lock_addr ||
		       regs->ip == contended_mutex_lock_addr ||
		       regs->ip == outer_mutex_lock_addr ||
		       regs->ip == direct_mutex_unlock_addr)))) {
			ret_flag = KD_EXE_RUN_ERROR;
			break;
		}
		if (direct_image &&
		    (!frame->image->immutable || !frame->image->near_text ||
		     frame->entry_abi != KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
		     frame->mutex_backend || frame->parent || frame->depth ||
		     frame->resume_target || !frame->executed ||
		     frame->logical_task == current || frame->outer_unlock_seen ||
		     frame->jit_lock_depth != 1 || frame->outer_lock_index ||
		     !kd_exec_frame_can_borrow_locks(frame) ||
		     kd_exec_frame_remote_pending(frame) || frame->remote_request ||
		     frame->native_request || frame->control_call.phase != KD_CALL_NONE)) {
			ret_flag = KD_EXE_RUN_ERROR;
			break;
		}

		if (args[0] == KD_EXE_DIRECT_CALL_LIMIT) {
			const struct kd_hostcall_desc *service = kd_hostcall_lookup(regs->ip);

			/* Only a negotiated direct image can report this boundary. Its
			 * exhausted per-invocation quota has not executed the pending CALL. */
			call_ret = !direct_image || !service ||
				!((service->id == KD_HOSTCALL_STRCMP && direct_strcmp == KD_STRCMP_MAX_CALLS) ||
				  (service->id == KD_HOSTCALL_STRSCPY_PAD && direct_pad == KD_EXE_HL_MAX_HOSTCALLS)) ?
				-EINVAL : kd_jit_call_limit_native(frame, regs, true);
			if (!call_ret)
				atomic64_inc(&kd_hostcall_limit);
			else
				kd_jit_log_hl_error("INVALID_DIRECT_CALL_LIMIT", frame, regs,
					args[0], call_ret, continuation_count, hostcall_count);
			ret_flag = call_ret ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE;
		} else if (direct_image && args[0] == KD_EXE_HOSTCALL) {
			/* Direct images never reset quotas by entering the old service
			 * dispatcher or by invoking the wrapper again from FULL. */
			kd_jit_log_hl_error("DIRECT_IMAGE_HOSTCALL", frame, regs, args[0],
				-EINVAL, continuation_count, hostcall_count);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (args[0] == KD_EXE_NORMAL) {
			kd_jit_log_hl_error("UNSUPPORTED_SYSCALL", frame, regs,
					    args[0], regs->ax,
					    continuation_count, hostcall_count);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (args[0] == KD_EXE_HOSTCALL) {
			const struct kd_hostcall_desc *service = kd_hostcall_lookup(regs->ip);
			bool strcmp_budget = service && service->id == KD_HOSTCALL_STRCMP;
			bool string_service = strcmp_budget ||
				(service && service->id == KD_HOSTCALL_STRSCPY_PAD);
			unsigned long string_return = 0;

			atomic64_inc(&kd_hostcall_exits);
			/* Only strcmp has a separate allowance for an xattr traversal.
			 * Writing helpers share the existing control/scalar budget: at
			 * most 128 comparisons and 16 other continuations can complete. */
			if (string_service) {
				call_ret = fault_kind ? -EINVAL :
					kd_jit_string_prepare(exe, frame, regs, &string_return);
				if (call_ret) {
					atomic64_inc(&kd_hostcall_failed);
					kd_jit_log_hl_error("STRING_CONTINUATION_INVALID", frame,
						regs, args[0], call_ret, continuation_count,
						hostcall_count);
					ret_flag = KD_EXE_RUN_ERROR;
					break;
				}
			}
			if ((strcmp_budget && string_count >= KD_STRCMP_MAX_CALLS) ||
			    (!strcmp_budget &&
			     (hostcall_count >= KD_EXE_HL_MAX_HOSTCALLS ||
			      continuation_count >= KD_EXE_HL_MAX_CONTINUATIONS))) {
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
			call_ret = string_service ? service->invoke(regs) :
				kd_hostcall_dispatch(regs);
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

			if (string_service) {
				regs->sp += sizeof(unsigned long);
				regs->ip = string_return;
				frame->control_call.phase = KD_CALL_NONE;
				kd_exec_frame_save_continuation(frame, regs);
				call_ret = 1;
			} else {
				call_ret = advance_and_save_continuation(
					kd_exec_current_frame(), regs);
			}
			if (call_ret <= 0) {
				atomic64_inc(&kd_hostcall_failed);
				kd_jit_log_hl_error(
					"HOSTCALL_CONTINUATION_FAILED", frame,
					regs, args[0], call_ret,
					continuation_count, hostcall_count);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}

			if (strcmp_budget)
				string_count++;
			else {
				hostcall_count++;
				continuation_count++;
			}
			resume_after_hostcall = true;
			continue;
		} else if (args[0] == KD_EXE_INDIRECT_CALL) {
			call_ret = fault_kind ? -EINVAL :
				kd_jit_indirect_call_native(exe, frame, regs);
			if (call_ret)
				kd_jit_log_hl_error("INVALID_INDIRECT_CALL", frame, regs,
					args[0], call_ret, continuation_count, hostcall_count);
			ret_flag = call_ret ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE;
		} else if (args[0] == KD_EXE_CALL_MISS) {
			if (direct_image && !kd_jit_outer_unlock(frame, regs, outer_lock_addr)) {
				/* Preserve the actual source CALL word and physical owner for
				 * the original waiter. Learning affects a future generation;
				 * this invocation cannot return to generated direct code. */
				call_ret = kd_jit_call_limit_native(frame, regs, false);
				if (!call_ret && !is_end_point(regs->ip) &&
				    !kd_native_terminal_target(regs->ip))
					kd_image_report(exe, frame->image, KD_EXE_CALL_MISS, regs->ip, 0);
				ret_flag = call_ret ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE;
				break;
			}
			if (outer_lock_addr &&
			    kd_jit_outer_unlock(frame, regs, outer_lock_addr)) {
				call_ret = kd_api_outer_unlock(regs->ip, regs->di,
					outer_lock_addr, frame->mutex_backend) ?
					KD_EXE_KNOWN_OUTER_UNLOCK : kd_jit_timed_control(regs, outer_lock_addr);
				if (call_ret == KD_EXE_KNOWN_OUTER_UNLOCK) {
					ret_flag = KD_EXE_RUN_TO_UNLOCK;
					break;
				}
				if (call_ret == KD_EXE_KNOWN_NATIVE) {
					ret_flag = KD_EXE_RUN_NATIVE;
					break;
				}
				if (call_ret > 0) {
					if (direct_image) {
						ret_flag = KD_EXE_RUN_ERROR;
						break;
					}
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

				if (kd_native_terminal_target(regs->ip)) {
					call_ret = fault_kind ? -EINVAL :
						kd_jit_pending_call_native(frame, regs, false, 0,
							"NATIVE_CALL_TERMINAL");
					if (call_ret)
						kd_jit_log_hl_error("NATIVE_CALL_TERMINAL_REFUSED", frame,
							regs, args[0], call_ret, continuation_count, hostcall_count);
					ret_flag = call_ret ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE;
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
				call_ret = fault_kind ? 0 : kd_source_pin_target(regs->ip);
				if (call_ret) {
					kd_jit_log_hl_error(
						"SOURCE_TARGET_REFUSED", frame,
						regs, args[0], call_ret,
						continuation_count,
						hostcall_count);
					ret_flag = KD_EXE_RUN_ERROR;
					break;
				}
				if (!is_end_point(regs->ip) && !kd_native_terminal_target(regs->ip))
					kd_image_report(exe, frame->image, KD_EXE_CALL_MISS,
							regs->ip, 0);
				/* Synthetic faults have no CALL frame and are not resumable. */
				ret_flag = fault_kind ? KD_EXE_RUN_ERROR :
							KD_EXE_RUN_NATIVE;
			}
		} else if (args[0] == KD_EXE_NATIVE_ESCAPE) {
			call_ret = kd_jit_native_escape(exe, frame, regs);
			if (call_ret)
				kd_jit_log_hl_error("INVALID_NATIVE_ESCAPE", frame,
						    regs, args[0], call_ret,
						    continuation_count, hostcall_count);
			ret_flag = call_ret ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE;
		} else if (args[0] == KD_EXE_ADDRESS_GUARD) {
			call_ret = fault_kind ? -EINVAL :
				kd_jit_address_guard(exe, frame, regs);
			if (call_ret)
				kd_jit_log_hl_error("INVALID_ADDRESS_GUARD", frame,
						    regs, args[0], call_ret,
						    continuation_count, hostcall_count);
			ret_flag = call_ret ? KD_EXE_RUN_ERROR : KD_EXE_RUN_NATIVE;
		} else if (args[0] == KD_EXE_ERROR_INST) {
			kd_jit_log_hl_error("UNSUPPORTED_INSTRUCTION", frame,
					    regs, args[0], -EILSEQ,
					    continuation_count, hostcall_count);
			kd_image_report(exe, frame->image, KD_EXE_ERROR_INST, regs->ip, 0);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (args[0] == KD_EXE_INST_LIMIT) {
			kd_jit_log_hl_error("BUDGET_LIMIT", frame, regs,
					    args[0], 0, continuation_count,
					    hostcall_count);
			ret_flag = KD_EXE_RUN_ERROR;
		} else {
			kd_jit_log_hl_error("IJ_MISS", frame, regs, args[0], 0,
					    continuation_count, hostcall_count);
			if (!is_end_point(regs->ip) && !is_end_point(args[0]))
				kd_image_report(exe, frame->image, KD_EXE_IJ_MISS,
						regs->ip, args[0]);
			ret_flag = KD_EXE_RUN_ERROR;
		}
		break;
	}

	/* Only a validated marker may request flags-aware waiter restoration.
	 * CALL packets can carry old/uninitialized orig_ax bytes; never interpret
	 * them as an instruction-continuation tag when publishing a native suffix. */
	if ((frame->mutex_backend || root_escape_image) &&
	    ret_flag == KD_EXE_RUN_NATIVE &&
	    args[0] != KD_EXE_NATIVE_ESCAPE)
		regs->orig_ax = 0;

	/* Completion/native/ACK releases and registry status CAS publish their
	 * own state; returning this local result needs no additional full fence. */
	kd_jit_timing_end(KD_JIT_TIME_DISPATCH, dispatch_start);
	return ret_flag;
}

int kd_exe_on_call_hl_entry(struct kd_exe_info *exe, struct kd_regs *regs,
			    unsigned long entry_ip, unsigned long outer_lock_addr)
{
	return kd_exe_dispatch(exe, regs, entry_ip, outer_lock_addr, NULL);
}

int kd_exe_spin_batch_resume(struct kd_exe_info *exe,
			     const struct kd_jit_batch_call *call)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();

	/* A non-final exit needs the explicit ledger before generic validation,
	 * logging or any service side effect. The packet itself stays shared. */
	kd_spin_jit_prepare_complex(frame);
	return kd_exe_dispatch(exe, call->regs, frame->entry_ip,
			       frame->outer_lock_addr, call);
}

int kd_exe_mutex_batch_resume(struct kd_exe_info *exe,
	const struct kd_jit_batch_call *call)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();

	if (!frame || !frame->mutex_backend || !frame->batch_lease ||
	    frame->entry_abi != KD_ENTRY_ABI_MUTEX_CLOBBER_V1)
		return KD_EXE_RUN_ERROR;
	/* The exact ledger already exists. Dispatch first materializes lazy
	 * routing, then consumes the pending exit once and detaches only FULL
	 * packets before any service or native owner-ACK wait. */
	return kd_exe_dispatch(exe, call->regs, frame->entry_ip,
			       frame->outer_lock_addr, call);
}
