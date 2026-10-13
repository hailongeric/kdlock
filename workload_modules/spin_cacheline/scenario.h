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
#ifdef SC_MUTEX_OWNED
/* The mutex translation unit owns and initializes both objects. Inner calls
 * cover ordinary controls in nested and clobber controls in early. */
#if SC_SCENARIO == 1
#define SC_EXTRA_LOCK(n) kd_mutex_lock(&sc_inner)
#define SC_INNER_UNLOCK() kd_mutex_unlock(&sc_inner)
#else
#define SC_EXTRA_LOCK(n) KD_OWNED_MUTEX_DIRECT_LOCK(&sc_inner, "")
#define SC_INNER_UNLOCK() KD_OWNED_MUTEX_DIRECT_UNLOCK(&sc_inner)
#endif
#else
static kd_spinlock_t sc_inner = KD_SPINLOCK_INITIALIZER;
/* Both outer interfaces now expose the original broad-clobber contract. */
#define SC_INNER_CALL(symbol) KD_SPIN_DIRECT_CALL(symbol, &sc_inner, "")
#define SC_EXTRA_LOCK(n) SC_INNER_CALL(kd_spin_lock_clobber_v1)
#define SC_INNER_UNLOCK() SC_INNER_CALL(kd_spin_unlock_clobber_v1)
#endif
#if SC_SCENARIO == 1
#define SC_EXIT()                                 \
    do                                            \
    {                                             \
        SC_INNER_UNLOCK();                        \
        SC_UNLOCK();                              \
    } while (0)
#elif SC_SCENARIO == 2
/* Releasing the outer object while B remains held exercises early release
 * and the out-of-order continuation without changing data protection. */
#ifdef SC_MUTEX_OWNED
/* Alternate release orders using protected data. Native early A unlocks
 * cannot combine while their own B is held; LIFO releases supply executors
 * that can run queued early-release bodies. Both paths use the same oracle. */
#define SC_EXIT()                                 \
    do                                            \
    {                                             \
        if (READ_ONCE(sc_data[0].value) & 1) {      \
            SC_UNLOCK();                          \
            SC_INNER_UNLOCK();                    \
        } else {                                  \
            SC_INNER_UNLOCK();                    \
            SC_UNLOCK();                          \
        }                                         \
    } while (0)
#else
#define SC_EXIT()                                 \
    do                                            \
    {                                             \
        SC_UNLOCK();                              \
        SC_INNER_UNLOCK();                        \
    } while (0)
#endif
#else
#error "Unknown KD scenario"
#endif
#else
#define SC_EXTRA_LOCK(n) \
    do                   \
    {                    \
    } while (0)
#define SC_EXIT() SC_UNLOCK()
#endif
#endif
