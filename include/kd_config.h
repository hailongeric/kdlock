/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_CONFIG_H
#define KD_CONFIG_H

/* All KD families share the same configuration contract. Keep it on the
 * public object-header path so a consumer cannot silently use a different
 * layout or scheduling/lockdep contract from the provider. These modes are
 * unsupported; dropping their annotations would not preserve native semantics.
 */
#ifdef CONFIG_PREEMPT_RT
#error "kdlock does not support CONFIG_PREEMPT_RT"
#endif
#ifdef CONFIG_DEBUG_MUTEXES
#error "kdlock does not support CONFIG_DEBUG_MUTEXES"
#endif
#ifdef CONFIG_DEBUG_LOCK_ALLOC
#error "kdlock does not support CONFIG_DEBUG_LOCK_ALLOC"
#endif
#ifdef CONFIG_LOCKDEP
#error "kdlock does not support CONFIG_LOCKDEP"
#endif

#endif /* KD_CONFIG_H */
