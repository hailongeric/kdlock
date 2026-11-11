/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef KDLOCK_LINUX_RWSEM_QUERY_H
#define KDLOCK_LINUX_RWSEM_QUERY_H

#include "kd_linux_rwsem.h"
#include "kd_mutex_api.h"

/* These distinct targets carry only an exact physical-state boolean. The
 * immutable binding retains the actual KD object through the complete query.
 * Neither predicate acquires a grant nor proves logical-task ownership.
 */
int kd_linux_rwsem_is_locked_entry_asm(struct kd_rwsem *lock,
		unsigned long source_sp, unsigned long continuation_ip,
		unsigned long source_bp);
int kd_linux_rwsem_is_write_locked_entry_asm(struct kd_rwsem *lock,
		unsigned long source_sp, unsigned long continuation_ip,
		unsigned long source_bp);

/* Keep the typed CALL at the original inline assertion/query site. This early
 * header defines no ordinary Linux lock macros. Real callable definitions use
 * only the normal C predicates, including when their object is source-enabled.
 */
static __always_inline bool kd_linux_rwsem_source_is_locked(
		const struct kd_linux_rwsem_binding *binding)
{
#ifndef KDLOCK_RWSEM_CALLABLE
	if (binding->source_calls)
		return KD_SOURCE_CALL_INT(binding->lock, struct kd_rwsem,
			kd_linux_rwsem_is_locked_entry_asm);
#endif
	return kd_linux_rwsem_is_locked(binding);
}

static __always_inline bool kd_linux_rwsem_source_is_write_locked(
		const struct kd_linux_rwsem_binding *binding)
{
#ifndef KDLOCK_RWSEM_CALLABLE
	if (binding->source_calls)
		return KD_SOURCE_CALL_INT(binding->lock, struct kd_rwsem,
			kd_linux_rwsem_is_write_locked_entry_asm);
#endif
	/* A retained logical read still has the physical writer. Native/real
	 * downgrade instead holds a reader credit and this predicate is false.
	 */
	return kd_linux_rwsem_is_write_locked(binding);
}

#endif
