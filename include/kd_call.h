#ifndef KD_CALL_H
#define KD_CALL_H

#include <linux/errno.h>

enum kd_call_phase {
	KD_CALL_NONE,
	KD_CALL_PENDING,
	KD_CALL_ENTERED,
	KD_CALL_ACQUIRED,
	KD_CALL_COMPLETE,
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

#endif
