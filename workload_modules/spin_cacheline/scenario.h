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
#if SC_COLD_FASTPATH
/* The outer paired unlock saves all five C callee-saved values. An inner
 * broad-clobber CALL invalidates them in minimal-entry analysis, even when
 * this fixture's C body does not otherwise use them. Preserve/reload them
 * explicitly across each old inner call. Its target, metadata, compiler
 * clobber contract and nested/native continuation protocol remain unchanged.
 * This shell is only for the mixed-interface protocol workload, not plain. */
#define SC_INNER_CALL(symbol) do { \
 kd_spinlock_t *kd_arg = &sc_inner; \
 unsigned long kd_sp, kd_ip, kd_bp; \
 asm volatile(KD_SPIN_DIRECT_SAVE \
  "movq %%rsp, %%rsi\n\tleaq 1f(%%rip), %%rdx\n\t" \
  "movq %%rbp, %%rcx\n\tcall " #symbol "\n\t1:\n\t" \
  KD_SPIN_DIRECT_RESTORE \
  : "+D" (kd_arg), "=S" (kd_sp), "=d" (kd_ip), "=c" (kd_bp), \
    ASM_CALL_CONSTRAINT \
  : : "rax", "rbx", "r8", "r9", "r10", "r11", \
      "r12", "r13", "r14", "r15", "cc", "memory"); \
} while (0)
#else
#define SC_INNER_CALL(symbol) KD_SPIN_DIRECT_CALL(symbol, &sc_inner, "")
#endif
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
