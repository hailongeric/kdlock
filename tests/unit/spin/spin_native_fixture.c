/* Isolated witnesses, not a replacement qspinlock or a kernel stress test. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {
	int counter;
} atomic_t;

#define qspinlock orig_qspinlock
#define __pure
#define WRITE_ONCE(p, value) ((p) = (value))
#define smp_store_release(p, value) (*(p) = (value))
#include "audit_types.h"

enum { CPUS = 4, NODES = 4 };
static struct kd_spin_node kd_storage[CPUS][NODES];
static struct qnode native_storage[CPUS][NODES];
#define kd_spin_nodes kd_storage[0]
#define qnodes native_storage[0]

static struct kd_spin_node *kd_per_cpu(struct kd_spin_node *p, int cpu)
{
	ptrdiff_t idx = p - kd_storage[0];

	assert(cpu >= 0 && cpu < CPUS && idx >= 0 && idx < NODES);
	return &kd_storage[cpu][idx];
}

static struct mcs_spinlock *native_per_cpu(struct mcs_spinlock *p, int cpu)
{
	size_t offset = (unsigned char *)p - (unsigned char *)native_storage[0];
	size_t idx = offset / sizeof(struct qnode);

	assert(cpu >= 0 && cpu < CPUS && idx < NODES);
	assert(offset % sizeof(struct qnode) == 0);
	return &native_storage[cpu][idx].mcs;
}

#define per_cpu_ptr(p, cpu)                        \
	_Generic((p),                              \
		struct kd_spin_node *: kd_per_cpu, \
		struct mcs_spinlock *: native_per_cpu)((p), (cpu))
#include "audit_queue.h"

/* Scheduler and lock primitives are deterministic counters/word operations.
 * The real inline API and hook bodies are compiled, but only their ordinary
 * uncontended paths are exercised. No native-continuation route is modeled.
 */
typedef struct orig_qspinlock raw_spinlock_t;
static int preempt_count;
static bool promoted;
struct shadow_stack {
	int curr_cs_cpu;
};
static struct shadow_stack local_shadow_stack;
#define this_cpu_ptr(p) (p)
#define preempt_disable() (++preempt_count)
#define preempt_enable() (--preempt_count)
#define spin_acquire(...) ((void)0)
#define spin_release(...) ((void)0)
#define LOCK_CONTENDED(lock, trylock, acquire) acquire(lock)
#define KD_EXE_LOCK_SPIN 1

static void do_raw_spin_lock(raw_spinlock_t *lock)
{
	assert(lock->val.counter == 0);
	lock->locked = 1;
}

static void do_raw_spin_unlock(raw_spinlock_t *lock)
{
	assert(lock->locked == 1);
	lock->locked = 0;
}

static u32 atomic_cmpxchg_acquire(atomic_t *word, int old, int value)
{
	int before = word->counter;

	if (before == old)
		word->counter = value;
	return before;
}

static bool kd_hotlock_is_promoted(unsigned long lock)
{
	(void)lock;
	return promoted;
}

static void kd_hotlock_record(unsigned long lock)
{
	(void)lock;
}
static void kd_exe_add(int pid, unsigned long ip, int kind)
{
	(void)pid;
	(void)ip;
	(void)kind;
}

static bool kd_exec_native_unlock(unsigned long lock, bool mutex)
{
	(void)lock;
	(void)mutex;
	return false;
}

#include "audit_fastpath.h"

static int preemption_case(const char *name, bool at_lock, bool at_unlock,
			   bool renamed)
{
	raw_spinlock_t lock = { 0 };
	int inside, after;

	preempt_count = 0;
	promoted = at_lock;
	__kd_raw_spin_lock(&lock, 0, 0);
	inside = preempt_count;
	promoted = at_unlock;
	if (renamed)
		__raw_spin_unlock(&lock);
	else
		__kd_raw_spin_unlock(&lock, 0, 0);
	after = preempt_count;
	assert(lock.val.counter == 0);
	printf("{\"case\":\"%s\",\"inside_delta\":%d,\"after_delta\":%d}", name,
	       inside, after);
	return inside != 1 || after != 0;
}

int main(void)
{
	unsigned int wrong_native_links = 0, wrong_kd_links = 0, controls = 0;
	struct kd_spin_node kd = { .tail = 0x12345678, .locked = 1 };
	struct mcs_spinlock native = { 0 };
	unsigned char bytes[sizeof(kd)];
	int one = 1, preempt_defects = 0;
	bool wake_misses, wake_outside;

	_Static_assert(sizeof(void *) == 8, "x86-64 required");
	_Static_assert(sizeof(struct orig_qspinlock) == 4,
		       "unexpected lock word");
	for (int cpu = 0; cpu < CPUS; cpu++) {
		for (int idx = 0; idx < NODES; idx++) {
			u32 kt = kd_encode_tail(cpu, idx);
			u32 nt = native_encode_tail(cpu, idx);
			struct kd_spin_node *kp = &kd_storage[cpu][idx];
			struct mcs_spinlock *np = &native_storage[cpu][idx].mcs;
			struct kd_spin_node *kn =
				&kd_storage[(cpu + 1) % CPUS][idx];
			struct mcs_spinlock *nn =
				&native_storage[(cpu + 1) % CPUS][idx].mcs;

			assert(kt == nt);
			assert(kd_decode_tail(kt) == kp);
			assert(native_decode_tail(nt) == np);
			assert((void *)kp != (void *)np);
			kp->next = NULL;
			np->next = NULL;
			/* Native enqueuer behind a kdlock tail: wrong array. */
			native_decode_tail(kt)->next = nn;
			wrong_native_links += kp->next == NULL &&
					      np->next == nn;
			kp->next = NULL;
			np->next = NULL;
			/* kdlock enqueuer behind a native tail: same defect. */
			kd_decode_tail(nt)->next = kn;
			wrong_kd_links += np->next == NULL && kp->next == kn;
			kd_decode_tail(kt)->next = kn;
			native_decode_tail(nt)->next = nn;
			assert(kp->next == kn && np->next == nn);
			controls += 2;
		}
	}

	/* Show the native wake store against kdlock bytes without invalid casts
	 * or out-of-bounds writes. Conversely, only measure the KD wake offset.
	 */
	memcpy(bytes, &kd, sizeof(kd));
	memcpy(bytes + offsetof(struct mcs_spinlock, locked), &one,
	       sizeof(one));
	wake_misses = bytes[offsetof(struct kd_spin_node, locked)] == 1;
	wake_outside = offsetof(struct kd_spin_node, locked) >=
		       sizeof(struct qnode);
	arch_mcs_spin_unlock_contended(&native.locked);
	clear_locked_set_completed(&kd);
	assert(native.locked == 1 && kd.locked == 0 && kd.completed == 1);
	printf("{\"slots\":%d,\"same_protocol_links\":%u,"
	       "\"native_after_kd_wrong_links\":%u,\"kd_after_native_wrong_links\":%u,"
	       "\"kd_node_bytes\":%zu,\"native_qnode_bytes\":%zu,\"native_mcs_bytes\":%zu,"
	       "\"kd_locked_offset\":%zu,\"native_locked_offset\":%zu,"
	       "\"kd_locked_bytes\":%zu,\"native_locked_bytes\":%zu,"
	       "\"native_wake_misses_kd_locked\":%s,\"kd_locked_outside_qnode\":%s,"
	       "\"preemption\":[",
	       CPUS * NODES, controls, wrong_native_links, wrong_kd_links,
	       sizeof(kd), sizeof(struct qnode), sizeof(native),
	       offsetof(struct kd_spin_node, locked),
	       offsetof(struct mcs_spinlock, locked), sizeof(kd.locked),
	       sizeof(native.locked), wake_misses ? "true" : "false",
	       wake_outside ? "true" : "false");
	preempt_defects +=
		preemption_case("native_control", false, false, false);
	printf(",");
	preempt_defects += preemption_case("promoted", true, true, false);
	printf(",");
	preempt_defects +=
		preemption_case("promotion_before_unlock", false, true, false);
	printf(",");
	preempt_defects +=
		preemption_case("renamed_before_unlock", true, true, true);
	printf("],\"preemption_defects\":%d,\"incompatible\":%s}\n",
	       preempt_defects,
	       wrong_native_links || wrong_kd_links || wake_misses ||
			       wake_outside || preempt_defects ?
		       "true" :
		       "false");
	return 0;
}
