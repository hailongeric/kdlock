#ifndef KD_HOSTCALL_H
#define KD_HOSTCALL_H

/* IDs and required safety properties shared with the typed native dispatcher.
 * The manifest is an allowlist, not permission to invoke arbitrary callees. */
#define KD_HOSTCALL_F_ATOMIC_SAFE (1U << 0)
#define KD_HOSTCALL_F_NO_TASK_CONTEXT (1U << 1)
#define KD_HOSTCALL_F_RETRY_SAFE (1U << 2)

enum kd_hostcall_id {
	KD_HOSTCALL_NONE = 0,
#define KD_HOSTCALL(name, id, symbol, flags) KD_HOSTCALL_##name = id,
#include "kd_hostcalls.def"
#undef KD_HOSTCALL
};

#endif
