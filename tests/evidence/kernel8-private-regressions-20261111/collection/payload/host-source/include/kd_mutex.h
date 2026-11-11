/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_PREPARED_MUTEX_ENTRY_H
#define KDLOCK_PREPARED_MUTEX_ENTRY_H

/* Private source-rebuilt entry metadata, with no old binary ABI promise. */
#define KD_MUTEX_ENTRY_CONTROL_TOP 0
#define KD_MUTEX_ENTRY_RUN 8
#define KD_MUTEX_ENTRY_PHASE 64
#define KD_MUTEX_ENTRY_PRIVATE 0
#define KD_MUTEX_ENTRY_PREPARED 1
#define KD_MUTEX_ENTRY_ENTERED 2
#define KD_MUTEX_ENTRY_COMPLETE 3

#ifndef __ASSEMBLY__
#include <linux/compiler.h>
#include <linux/stddef.h>
#include <asm/asm.h>

struct kd_mutex;
struct kd_mutex_entry;
struct task_struct;

typedef void (*kd_mutex_entry_run_fn)(struct kd_mutex_entry *entry,
		struct kd_mutex *lock, unsigned long source_sp,
		unsigned long continuation_ip, unsigned long source_bp);

/*
 * One referring entry, not another source packet or a saved invocation image.
 * control_top/run are immutable assembly inputs. phase belongs to this exact
 * entry: preparation sets PREPARED, assembly sets ENTERED before switching,
 * and final native resume sets COMPLETE before releasing auxiliary occupancy.
 * Cancel is valid only while PREPARED. task owns the auxiliary
 * wait stack; context refers to the root/node/driver resources reserved before
 * entry. Root admission validates current task, exact own-root/node identities,
 * task context, source/auxiliary/code/object lifetimes and exclusive use.
 *
 * Ranges are [low, high). control_top is 16-byte aligned, lies above control_low
 * and at or below control_high, and leaves space for the complete admitted
 * callback/wait/recursive path. No stack size, depth, allocator or guard-page
 * default is selected here. The auxiliary range is disjoint from the retained
 * original source range; source SP-8 and subsequent source accesses are valid.
 * Entry/context storage must survive its last user and may not be overwritten
 * by either stack. Reuse waits for abandoned control frames AND all escaped
 * request, grant, binding, return and notifier users to finish.
 *
 * The caller supplies the task-owned auxiliary stack route, following the
 * TCLock wait-stack separation. Numerical ranges alone do not prove Linux IRQ,
 * scheduler, stack-overflow or unwinder compatibility on that route. Those
 * context/guard obligations remain admission inputs; this unrun source does
 * not enable or validate an arbitrary alternate stack.
 *
 * run never returns: capture the declared inputs into the one canonical S_W,
 * perform the selected ordinary mutex bridge on this auxiliary stack, close
 * control users as required, then resume the current canonical regs.ip/sp on W.
 * Local/proxy completion never restores an entry snapshot or returns through
 * abandoned C frames. No source publication may precede the stack switch.
 */
struct kd_mutex_entry {
	unsigned long control_top;
	kd_mutex_entry_run_fn run;
	struct task_struct *task;
	unsigned long control_low;
	unsigned long control_high;
	unsigned long source_low;
	unsigned long source_high;
	void *context;
	unsigned long phase;
};

_Static_assert(offsetof(struct kd_mutex_entry, control_top) ==
	KD_MUTEX_ENTRY_CONTROL_TOP, "private mutex entry stack offset");
_Static_assert(offsetof(struct kd_mutex_entry, run) == KD_MUTEX_ENTRY_RUN,
	"private mutex entry callback offset");
_Static_assert(offsetof(struct kd_mutex_entry, phase) == KD_MUTEX_ENTRY_PHASE,
	"private mutex entry phase offset");
_Static_assert(sizeof(unsigned long) == 8, "private mutex entry needs x86_64");

/* Raw assembly endpoint; use only the prepared compiler-clobber prefix below.
 * Admission must already have reserved a nonfailing route and a nonnull run.
 */
void __noreturn kd_mutex_entry_asm(struct kd_mutex *lock,
		unsigned long source_sp, unsigned long continuation_ip,
		unsigned long source_bp, struct kd_mutex_entry *entry);

/*
 * This private prefix requires successful root admission before invocation.
 * One __auto_type initializer captures both arguments before any capture local
 * enters scope, so an operand name cannot be shadowed by the other capture.
 * Ordinary lock acquisition cannot report an allocation/admission error here.
 * The compiler spills all values it needs across the boundary. Only object DI,
 * pre-CALL SP, the explicit post-CALL label and BP are source capture inputs;
 * R8 is referring entry metadata, not an additional source register packet.
 * General flags/SIMD remain AS01 assumptions. Native resume imports the
 * current canonical SP/BP rather than restoring these entry values blindly.
 *
 * The CALL's transient source word is abandoned after the assembly switch.
 * CAPTURED_CONTINUATION uses the pre-CALL SP and label directly: no source pop
 * and no second source CALL word is fabricated on successful completion.
 * The assembly never returns conventionally; canonical native resume reaches
 * label 1 (or a later exact source continuation after delegated work).
 */
#define KD_MUTEX_LOCK_PREPARED(lock, entry) \
	do { \
		__auto_type kd_entry_inputs = ((struct { \
			struct kd_mutex *source_object; \
			struct kd_mutex_entry *prepared_control; \
		}) { (lock), (entry) }); \
		struct kd_mutex *kd_lock_arg = kd_entry_inputs.source_object; \
		register struct kd_mutex_entry *kd_entry_arg asm("r8") = \
			kd_entry_inputs.prepared_control; \
		unsigned long kd_source_sp, kd_continuation_ip, kd_source_bp; \
		asm volatile("movq %%rsp, %%rsi\n\t" \
			     "leaq 1f(%%rip), %%rdx\n\t" \
			     "movq %%rbp, %%rcx\n\t" \
			     "call kd_mutex_entry_asm\n\t1:\n\t" \
			     : "+D"(kd_lock_arg), "=S"(kd_source_sp), \
			       "=d"(kd_continuation_ip), "=c"(kd_source_bp), \
			       "+r"(kd_entry_arg), ASM_CALL_CONSTRAINT \
			     : \
			     : "rax", "rbx", "r9", "r10", "r11", \
			       "r12", "r13", "r14", "r15", "cc", "memory"); \
	} while (0)

#endif /* !__ASSEMBLY__ */
#endif /* KDLOCK_PREPARED_MUTEX_ENTRY_H */
