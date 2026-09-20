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
#define SC_EXTRA_LOCK(n) KD_SPIN_DIRECT_CALL(kd_spin_lock_clobber_v1, &sc_inner, "")
#if SC_SCENARIO == 1
#define SC_EXIT() do { \
 KD_SPIN_DIRECT_CALL(kd_spin_unlock_clobber_v1, &sc_inner, ""); \
 SC_UNLOCK(); \
} while (0)
#elif SC_SCENARIO == 2
/* Releasing the outer object while B remains held exercises early release
 * and the out-of-order continuation without changing data protection. */
#define SC_EXIT() do { \
 SC_UNLOCK(); \
 KD_SPIN_DIRECT_CALL(kd_spin_unlock_clobber_v1, &sc_inner, ""); \
} while (0)
#else
#error "Unknown KD scenario"
#endif
#else
#define SC_EXTRA_LOCK(n) do { } while (0)
#define SC_EXIT() SC_UNLOCK()
#endif
#endif
