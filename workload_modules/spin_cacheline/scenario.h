/* SPDX-License-Identifier: GPL-2.0 */
#ifndef SC_SCENARIO_H
#define SC_SCENARIO_H
/* Opt-in protocol regression with the same payload oracle. The default
 * comparison has exactly the original single lock and body instructions. */
#ifndef SC_SCENARIO
#define SC_SCENARIO 0
#endif
#if SC_SCENARIO
#ifndef SC_DIRECT_KDLOCK
#error "Nested regression requires explicit KD objects"
#endif
static kd_spinlock_t sc_inner = KD_SPINLOCK_INITIALIZER;
/* Both outer interfaces now expose the original broad-clobber contract. */
#define SC_INNER_CALL(symbol) KD_SPIN_DIRECT_CALL(symbol, &sc_inner, "")
#define SC_EXTRA_LOCK(n) SC_INNER_CALL(kd_spin_lock_clobber_v1)
#if SC_SCENARIO == 1
#define SC_EXIT() do { \
 SC_INNER_CALL(kd_spin_unlock_clobber_v1); \
 SC_UNLOCK(); \
} while (0)
#elif SC_SCENARIO == 2
/* Releasing the outer object while B remains held exercises early release
 * and the out-of-order continuation without changing data protection. */
#define SC_EXIT() do { \
 SC_UNLOCK(); \
 SC_INNER_CALL(kd_spin_unlock_clobber_v1); \
} while (0)
#else
#error "Unknown KD scenario"
#endif
#else
#define SC_EXTRA_LOCK(n) do { } while (0)
#define SC_EXIT() SC_UNLOCK()
#endif
#endif
