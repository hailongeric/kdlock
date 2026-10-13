/* Worker threads have joined and the ioctl holds the snapshot gate. Test the
 * production drain decision against residual owner/flag/list/OSQ state. */
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %d: %s\n", __LINE__, #c); exit(1); } } while (0)
static struct {
	unsigned long owner;
	struct { bool empty; } wait_list;
	struct { bool locked; } osq;
} sc_lock;
#define atomic_long_read(p) (*(p))
#define list_empty(p) ((p)->empty)
#define osq_is_locked(p) ((p)->locked)
#include "drain_code.h"

int main(void)
{
	sc_lock.wait_list.empty = true;
	CHECK(!sc_workers_drain());
	for (unsigned long flags = 0; flags < 8; flags++) {
		sc_lock.owner = 0x1000 | flags;
		CHECK(sc_workers_drain() == -EBUSY);
		sc_lock.owner = flags;
		CHECK(sc_workers_drain() == (flags ? -EBUSY : 0));
	}
	sc_lock.owner = 0;
	sc_lock.wait_list.empty = false;
	CHECK(sc_workers_drain() == -EBUSY);
	sc_lock.wait_list.empty = true;
	sc_lock.osq.locked = true;
#ifdef CONFIG_MUTEX_SPIN_ON_OWNER
	CHECK(sc_workers_drain() == -EBUSY);
#else
	CHECK(!sc_workers_drain());
#endif
	sc_lock.osq.locked = false;
	CHECK(!sc_workers_drain());
	puts("PASS: original mutex owner flags, wait list and configured OSQ must drain");
	return 0;
}
