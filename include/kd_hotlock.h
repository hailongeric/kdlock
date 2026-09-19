#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H

#include <linux/types.h>

/* Discovery counters/windows are private per-CPU implementation details.
 * The shared set contains promoted addresses only, never warming-up locks. */
#define KD_HOTLOCK_LOCAL_DISCOVERY_V1 1

int kd_hotlock_init(void);
void kd_hotlock_exit(void);

/* Fresh acquisition: local CPU frequency -> local lock frequency -> caller
 * may select task. A true result is a hint, never permission to execute JIT. */
int kd_hotlock_record(unsigned long lock_addr);
/* Read-only identity query for existing/nested protocols and diagnostics. */
bool kd_hotlock_is_promoted(unsigned long lock_addr);

#endif /* KD_HOTLOCK_H */
