#ifndef KD_HOTLOCK_H
#define KD_HOTLOCK_H

/* Append-only sampling state consumed by hooks before entry registration.
 * Promotion authorizes considering JIT; it does not mean code is ready or ran. */
#include <linux/atomic.h>
#include <linux/types.h>

enum kd_hotlock_status {
	KD_HOTLOCK_INIT = 0,
	KD_HOTLOCK_CHECKING,
	KD_HOTLOCK_DELEGATE,
	KD_HOTLOCK_IGNORE,
};

/* Entries never move after release-publication of lock_addr. Promotion readers
 * acquire the address and READ_ONCE(status); other fields require the writer
 * lock. Pointers remain valid only until callers drain before module teardown. */
struct kd_hotlock_state {
	unsigned long lock_addr;
	unsigned long begin_cycles;
	unsigned long end_cycles;
	unsigned long sample_window;
	unsigned int samples;
	enum kd_hotlock_status status;
} ____cacheline_aligned;

int kd_hotlock_init(void);
void kd_hotlock_exit(void);

struct kd_hotlock_state *kd_hotlock_state_get(unsigned long lock_addr);
int kd_hotlock_record(unsigned long lock_addr);
bool kd_hotlock_is_promoted(unsigned long lock_addr);

#endif /* KD_HOTLOCK_H */
