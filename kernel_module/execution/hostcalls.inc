/*
 * Allowlisted native services and bounded mutex CALL stack observations.
 * Private implementation included only by exe.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

struct kd_hostcall_desc {
	enum kd_hostcall_id id;
	const char *symbol;
	unsigned long addr;
	unsigned int flags;
	int (*invoke)(struct kd_regs *regs);
};

static atomic64_t kd_hostcall_exits;
static atomic64_t kd_hostcall_executed;
static atomic64_t kd_hostcall_resumed;
static atomic64_t kd_hostcall_rejected;
static atomic64_t kd_hostcall_failed;
static atomic64_t kd_hostcall_limit;

/* The same-device capability authorizes only bounded mutex stack facts, not
 * arbitrary callee memory preservation. Exclude the consumed CALL word, whose
 * identity is checked separately before JIT may resume. */
#define KD_MUTEX_CALL_STACK_BYTES KD_JIT_MUTEX_STACK_BYTES
struct kd_mutex_call_stack {
	struct kd_call_state call;
	unsigned char bytes[KD_MUTEX_CALL_STACK_BYTES];
};
static atomic64_t kd_mutex_stack_equal;
static atomic64_t kd_mutex_stack_changed;
static atomic64_t kd_mutex_stack_unavailable;

static int kd_hostcall_invoke_ktime_get(struct kd_regs *regs)
{
	regs->ax = (unsigned long)ktime_to_ns(ktime_get());
	return 0;
}

static int kd_hostcall_invoke_ktime_get_ns(struct kd_regs *regs)
{
	regs->ax = (unsigned long)ktime_get_ns();
	return 0;
}

/* x86-64 unsigned long: consume the full saved RDI and replace only RAX.
 * The native helper has at most 32 scalar iterations and no external memory,
 * sleeping or task/CPU-context dependency; it does not run on the waiter stack.
 * This CALL boundary requires no new flags or memory-access recovery contract.
 */
static int kd_hostcall_invoke_int_sqrt(struct kd_regs *regs)
{
	regs->ax = int_sqrt(regs->di);
	return 0;
}

static struct kd_hostcall_desc kd_hostcalls[] = {
#define KD_HOSTCALL(name, service_id, service_symbol, service_flags) \
	{ KD_HOSTCALL_##name, #service_symbol, 0, service_flags,     \
	  kd_hostcall_invoke_##service_symbol },
#include "kd_hostcalls.def"
#undef KD_HOSTCALL
};

static const struct kd_hostcall_desc *kd_hostcall_lookup(unsigned long addr)
{
	int i;

	for (i = 0; i < ARRAY_SIZE(kd_hostcalls); i++)
		if (kd_hostcalls[i].addr && kd_hostcalls[i].addr == addr)
			return &kd_hostcalls[i];
	return NULL;
}

/* Quota exits must validate the same service contract without invoking it. */
static int kd_hostcall_validate(const struct kd_hostcall_desc *service)
{
	const unsigned int required_flags = KD_HOSTCALL_F_ATOMIC_SAFE |
					    KD_HOSTCALL_F_NO_TASK_CONTEXT |
					    KD_HOSTCALL_F_RETRY_SAFE;

	if (!service)
		return -ENOENT;
	if ((service->flags & required_flags) != required_flags)
		return -EPERM;
	return 0;
}

static int kd_hostcall_dispatch(struct kd_regs *regs)
{
	const struct kd_hostcall_desc *service = kd_hostcall_lookup(regs->ip);
	int ret = kd_hostcall_validate(service);

	if (ret)
		return ret;
	return service->invoke(regs);
}
