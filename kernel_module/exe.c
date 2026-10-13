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
#include "kd_jit_batch.h"

#include <asm/current.h>
#include <asm/unaligned.h>
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
#include "kd_mutex_legacy.h"
#include "kd_mutex.h"
#include "kd_mutex_direct.h"
#include "kd_owned_mutex_direct.h"
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

/* Exercise a real, validated post-mutex-control continuation. Unlike the
 * synthetic fault above, this never fabricates a CALL or instruction exit. */
static int kd_owned_mutex_native_after_control;
module_param_named(owned_mutex_native_after_control,
		   kd_owned_mutex_native_after_control, int, 0644);
MODULE_PARM_DESC(owned_mutex_native_after_control,
	"One-shot owned mutex diagnostic: resume natively after a checked control CALL");

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

static unsigned long end_points[16];
static int end_point_count;
static unsigned long raw_spin_lock_addr;
static unsigned long raw_spin_unlock_addr;
static unsigned long clobber_spin_lock_addr;
static unsigned long clobber_spin_unlock_addr;
static unsigned long pinned_spin_lock_addr;
static unsigned long cold_spin_unlock_addr;
static unsigned long mutex_lock_addr;
static unsigned long mutex_unlock_addr;
static unsigned long clobber_mutex_lock_addr;
static unsigned long clobber_mutex_unlock_addr;
static unsigned long direct_mutex_lock_addr;
static unsigned long contended_mutex_lock_addr;
static unsigned long outer_mutex_lock_addr;
static unsigned long direct_mutex_unlock_addr;
static unsigned long owned_mutex_lock_addr;
static unsigned long owned_mutex_unlock_addr;
static unsigned long owned_outer_unlock_addr;
static unsigned long owned_direct_lock_addr;
static unsigned long owned_contended_lock_addr;
static unsigned long owned_outer_lock_addr;
static unsigned long owned_direct_unlock_addr;

#include "execution/hostcalls.inc"

#include "execution/timing.inc"

#include "execution/registry_lifecycle.inc"

#include "execution/control_calls.inc"

#include "execution/registry_publish.inc"

#include "execution/wrapper_entry.inc"

static int kd_exe_dispatch(struct kd_exe_info *exe, struct kd_regs *regs,
			  unsigned long entry_ip, unsigned long outer_lock_addr,
			  const struct kd_jit_batch_call *pending)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();
	void (*translated)(struct kd_regs *regs, unsigned long *args);
	unsigned long args[2];
	int continuation_count = 0;
	int hostcall_count = 0;
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
	 * in-session. This does not make in-place code uploads immutable. */
	if (!pending && !kd_exe_entry_is_ready(exe, 0, entry_ip)) {
		if (!exe)
			return KD_EXE_NO_RUN;
		KD_PR_INFO(
			"translation not ready: exe=%px status=%d entry=%lx ip=%lx pid=%d\n",
			exe, exe->status_code, exe->RIP, regs->ip, exe->pid);
		return KD_EXE_NO_RUN;
	}

	if (!kd_jit_image_matches(exe, frame))
		return frame->executed ? KD_EXE_RUN_ERROR : KD_EXE_NO_RUN;

	if (READ_ONCE(exe->lock_kind) !=
	    (frame->owned_mutex ? KD_EXE_LOCK_OWNED_MUTEX :
	     frame->mutex_backend ? KD_EXE_LOCK_MUTEX : KD_EXE_LOCK_SPIN)) {
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
	/* Exclude pre-entry rejections and the caller's frame setup/teardown. */
	dispatch_start = pending ? pending->dispatch_start : kd_jit_timing_start();
	pristine_root = pending || (!frame->resume_target && regs->ip == entry_ip);
	translated = exe->code_block;
	for (;;) {
		int call_ret;
		int fault_kind;
		unsigned long entry_sp = regs->sp;
		u64 boundary_start;

		/* The batch wrapper already ran. Consume that exit exactly once; an
		 * extra invocation here would repeat stores before handling the miss. */
		if (pending) {
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
				args[0] = call.args[0];
				args[1] = call.args[1];
			} else {
				translated(regs, args);
			}
			kd_jit_timing_end(KD_JIT_TIME_WRAPPER, boundary_start);
returned_wrapper:
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
			if (args[0] == KD_EXE_CALL_MISS &&
			    regs->ip == raw_spin_unlock_addr &&
			    regs->di == outer_lock_addr) {
				ret_flag = KD_EXE_RUN_TO_UNLOCK;
				break;
			}
			kd_spin_jit_prepare_complex(frame);
			regs = kd_exec_frame_regs(frame);
		}

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
