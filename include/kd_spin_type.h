/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_SPIN_TYPE_H
#define KD_SPIN_TYPE_H
#include "kd_config.h"
#include <linux/atomic.h>
#include <linux/types.h>

/* Explicit KD object: never pass to Linux spin APIs. The low byte arbitrates
 * ownership/combining; pending and tail share this same 32-bit word. Object
 * storage must survive every caller, queued request and retained frame. */
typedef struct kd_spinlock {
 union {
  atomic_t val;
  struct { u8 locked, pending; };
  struct { u16 locked_pending, tail; };
 };
} kd_spinlock_t;
/* Paired native ownership, distinct from normal (1), combiner (3), OOO (7)
 * and IRQ (15). Only the low byte changes; pending/tail keep their protocol.
 * CPU heat may change while waiting/holding, so heat is never unlock proof. */
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
#define KD_SPINLOCK_INITIALIZER { .val = ATOMIC_INIT(0) }
#define DEFINE_KD_SPINLOCK(name) kd_spinlock_t name = KD_SPINLOCK_INITIALIZER
static inline void kd_spin_init(kd_spinlock_t *lock)
{
 atomic_set(&lock->val, 0);
}
#endif
