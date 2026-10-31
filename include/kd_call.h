#ifndef KD_CALL_H
#define KD_CALL_H

/* Control-CALL transaction boundary, not a memory transaction. The saved
 * target/stack/return token distinguishes pending acquisition from a completed
 * operation whose suffix can resume; none of these helpers undoes stores. */
#include <linux/errno.h>

enum kd_call_phase {
	KD_CALL_NONE,
	KD_CALL_PENDING,
	KD_CALL_ENTERED,
	KD_CALL_ACQUIRED,
	KD_CALL_COMPLETE,
	/* A completed mutex control was checked before handing off its suffix. */
	KD_CALL_STACK_CHANGED,
	/* A local spin acquisition and its post-CALL packet were validated. */
	KD_CALL_SPIN_NATIVE,
	/* Cold original-task instruction owns the frame until its returned ACK. */
	KD_CALL_ORIGIN_INSTRUCTION,
};

/* A post-CALL RIP may be staged before B's queue publication. Keep the
 * original CALL frame until its acquisition phase makes replay unsafe. */
struct kd_call_state {
	unsigned long target;
	unsigned long stack;
	unsigned long return_ip;
	enum kd_call_phase phase;
};

static inline int kd_call_begin(struct kd_call_state *call,
				unsigned long target, unsigned long stack,
				unsigned long return_ip)
{
	*call = (struct kd_call_state){};
	if (!target || !stack || !return_ip)
		return -EINVAL;
	call->target = target;
	call->stack = stack;
	call->return_ip = return_ip;
	call->phase = KD_CALL_PENDING;
	return 0;
}

static inline int kd_call_resume_pending(const struct kd_call_state *call,
					 int error, unsigned long *ip,
					 unsigned long *sp)
{
	if (call->phase != KD_CALL_PENDING || !call->target || !call->stack ||
	    !call->return_ip || (error != -ENOMEM && error != -E2BIG))
		return 0;
	*ip = call->target;
	*sp = call->stack;
	return 1;
}

static inline int kd_call_after_matches(const struct kd_call_state *call,
					unsigned long ip, unsigned long sp)
{
	/* Never turn an arbitrary COMPLETE phase into permission to replay a lock
	 * acquisition. A checked post-control exit consumes exactly one CALL word. */
	return call->target && call->return_ip && call->stack &&
	       call->stack <= ~0UL - sizeof(unsigned long) &&
	       ip == call->return_ip &&
	       sp == call->stack + sizeof(unsigned long);
}

#endif
