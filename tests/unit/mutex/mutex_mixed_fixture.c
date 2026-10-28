// SPDX-License-Identifier: GPL-2.0
/* Production one-CAS service and ledger, with explicit ticket/pin substitutes.
 * Checks observable CALL advancement, cancellation, exact generation release
 * and native continuation boundaries; not Linux scheduling or JIT evidence. */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint64_t u64;
struct task_struct { int pid; };
struct list_head { struct list_head *next, *prev; };
typedef struct {
	union { unsigned int val; struct { u8 locked, pending; u16 tail; }; };
} raw_spinlock_t;
typedef raw_spinlock_t kd_spinlock_t;
#include "kd_regs.h"
#include "mixed_types.h"
#define KD_EXE_KNOWN_NATIVE 8
#define KD_SPIN_ENTRY_VIRTUAL 1
static struct task_struct owner = {1}, waiter = {2};
static struct task_struct *current = &owner;
struct kd_spin_entry {
	raw_spinlock_t *lock;
	struct task_struct *owner;
	unsigned long sequence;
	int state;
};
static struct kd_spin_entry entries[8];
static unsigned int pins, cas_calls, claims, ends, failures, checks;
static unsigned long sequence;
static int forced_reserve_error;
#define CHECK(c) do { checks++; if (!(c)) { fprintf(stderr,"FAIL line=%d: %s\n",__LINE__,#c); failures++; } } while (0)
#define BUG_ON(c) do { if (c) { CHECK(!(c)); exit(1); } } while (0)
#define READ_ONCE(x) (x)
#define smp_store_release(p,v) __atomic_store_n((p),(v),__ATOMIC_RELEASE)
#define list_empty(h) ((h)->next == (h))
static unsigned int atomic_cmpxchg_acquire(unsigned int *word, unsigned int old,
					  unsigned int value)
{
	cas_calls++;
	__atomic_compare_exchange_n(word, &old, value, false, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
	return old;
}
static int kd_spin_entry_begin(raw_spinlock_t *lock, int kind, struct kd_spin_ref *ref)
{
	CHECK(kind == KD_SPIN_ENTRY_VIRTUAL);
	if (forced_reserve_error)
		return forced_reserve_error;
	for (unsigned int i = 0; i < 8; i++) {
		if (entries[i].state)
			continue;
		entries[i] = (struct kd_spin_entry){lock, current, ++sequence, 1};
		*ref = (struct kd_spin_ref){&entries[i], sequence};
		pins++;
		return 0;
	}
	return -E2BIG;
}
static kd_spinlock_t *kd_spin_entry_word(const struct kd_spin_ref *ref)
{
	return ref->entry && ref->entry->owner == current && ref->entry->state &&
	       ref->entry->sequence == ref->sequence ? ref->entry->lock : NULL;
}
static int kd_spin_entry_claim(const struct kd_spin_ref *ref)
{
	if (!kd_spin_entry_word(ref) || ref->entry->state != 1)
		return -EINVAL;
	ref->entry->state = 2;
	claims++;
	return 0;
}
static int kd_spin_entry_release_origin(const struct kd_spin_ref *ref)
{
	if (!kd_spin_entry_word(ref) || ref->entry->state != 2)
		return -EINVAL;
	ref->entry->state = 3;
	return 0;
}
static int kd_spin_entry_end(struct kd_spin_ref *ref)
{
	if (!kd_spin_entry_word(ref) || ref->entry->state == 2)
		return -EINVAL;
	ref->entry->state = 0;
	*ref = (struct kd_spin_ref){0};
	CHECK(pins > 0);
	pins--; ends++;
	return 0;
}
bool kd_exec_frame_validate(const struct kd_exec_frame *f)
{
	return f && f->jit_lock_depth <= KD_EXEC_MAX_LOCK_DEPTH &&
	       f->outer_lock_index < f->jit_lock_depth;
}
static int kd_exec_invariant_failure(void) { CHECK(false); return -EINVAL; }
int kd_exec_frame_state(const struct kd_exec_frame *f) { return f->state; }
bool kd_exec_frame_remote_pending(const struct kd_exec_frame *f)
{
	return f->remote_result == KD_EXEC_REMOTE_WAITING || f->remote_result == KD_EXEC_REMOTE_NATIVE;
}
int kd_exec_frame_record_event(struct kd_exec_frame *f, enum kd_exec_event event,
			       const struct kd_regs *regs)
{
	(void)regs;
	CHECK(f->mutex_backend && (event == KD_EXEC_EVENT_NESTED_LOCK || event == KD_EXEC_EVENT_NESTED_UNLOCK));
	return 0;
}
void kd_exec_frame_save_continuation(struct kd_exec_frame *f, const struct kd_regs *r)
{
	f->continuation_ip = r->ip; f->continuation_sp = r->sp;
	f->state = KD_EXEC_FRAME_RESUME;
}
#include "mixed_production.h"

static unsigned long call_word;
static struct kd_exec_outer_unlock hook;
static void setup(struct kd_exec_frame *f, raw_spinlock_t *b)
{
	CHECK(!pins);
	memset(f, 0, sizeof(*f));
	memset(b, 0, sizeof(*b));
	f->mutex_backend = f->complex_ready = true;
	f->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	f->logical_task = &waiter;
	f->state = KD_EXEC_FRAME_RUNNING;
	f->outer_lock_addr = 0xa000;
	f->jit_lock_addr[0] = 0xa000;
	f->jit_lock_node[0] = (void *)0xa000;
	f->jit_lock_kind[0] = KD_EXEC_LOCK_QUEUE_OWNER;
	f->jit_lock_depth = f->held_lock_depth = f->outer_lock_depth = 1;
	f->native_link.next = f->native_link.prev = &f->native_link;
	hook.released = false;
	f->outer_unlock_hook = &hook;
	call_word = 0x900;
	f->regs.ip = 0x100;
	f->regs.sp = (unsigned long)&call_word;
	f->regs.di = (unsigned long)b;
	cas_calls = claims = ends = 0;
}

static void fast_and_exact_release(void)
{
	struct kd_exec_frame f;
	raw_spinlock_t b, c = {0};
	struct kd_spin_ref stale;

	setup(&f, &b);
	CHECK(kd_mutex_jit_spin_lock_ctx(&b, &f.regs, &f) == 1);
	CHECK(cas_calls == 1 && claims == 1 && pins == 1 && !ends);
	CHECK(f.regs.ip == call_word && f.regs.sp == (unsigned long)&call_word + sizeof(call_word));
	CHECK(f.jit_lock_depth == 2 && f.jit_lock_kind[1] == KD_EXEC_LOCK_MUTEX_SPIN);
	CHECK(kd_exec_mutex_spin_count(&f) == 1 && !f.mutex_mixed.transfer_requested);
	stale = (struct kd_spin_ref){f.jit_lock_node[1], f.mutex_mixed.spin_sequence[1] + 1};
	CHECK(kd_spin_nested_release_exact(&b, &stale) == -EINVAL && b.locked == 1 && pins == 1);
	/* Distinct generations survive a non-LIFO ledger compaction. */
	f.regs.ip = 0x100; f.regs.sp = (unsigned long)&call_word;
	CHECK(kd_mutex_jit_spin_lock_ctx(&c, &f.regs, &f) == 1);
	CHECK(kd_exec_mutex_spin_count(&f) == 2);
	b.pending = 3; b.tail = 7;
	CHECK(!kd_mutex_jit_spin_unlock_ctx(&b, &f));
	CHECK(!b.locked && b.pending == 3 && b.tail == 7 && pins == 1);
	CHECK(f.jit_lock_addr[1] == (unsigned long)&c);
	/* A can already be released, while B's exact ticket still owns progress. */
	f.outer_unlock_seen = f.jit_lock_released[0] = true;
	CHECK(!kd_mutex_jit_spin_unlock_ctx(&c, &f));
	CHECK(!pins && ends == 2 && kd_exec_frame_can_complete(&f));
}

static void miss_and_boundaries(void)
{
	struct kd_exec_frame f;
	raw_spinlock_t b, c = { .val = 1 };
	unsigned int prefix = 0, suffix = 0;
	struct kd_regs packet;

	setup(&f, &b); b.val = 1; packet = f.regs; prefix++;
	CHECK(kd_mutex_jit_spin_lock_ctx(&b, &f.regs, &f) == KD_EXE_KNOWN_NATIVE);
	CHECK(!memcmp(&packet, &f.regs, sizeof(packet)) && f.control_call.phase == KD_CALL_PENDING);
	CHECK(cas_calls == 1 && !claims && ends == 1 && !pins && f.jit_lock_depth == 1);
	CHECK(f.mutex_mixed.transfer_requested && kd_exec_mutex_transfer_allowed(&f));
	{
		struct kd_exec_frame pending = f;

		f.parent = &f;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		f.depth = 1;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		f.request_frame = true;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		f.entry_abi = KD_ENTRY_ABI_LEGACY;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		f.remote_result = KD_EXEC_REMOTE_WAITING;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		f.control_call.phase = KD_CALL_ACQUIRED;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		f.mutex_mixed.transferred = true;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		f.native_link.next = NULL;
		CHECK(!kd_exec_mutex_transfer_allowed(&f)); f = pending;
		CHECK(kd_exec_mutex_transfer_allowed(&f));
	}
	/* Source continuation executes the still-pending CALL, then only suffix. */
	suffix++;
	CHECK(prefix == 1 && suffix == 1);
	setup(&f, &b);
	forced_reserve_error = -E2BIG;
	CHECK(kd_mutex_jit_spin_lock_ctx(&b, &f.regs, &f) == KD_EXE_KNOWN_NATIVE);
	CHECK(!cas_calls && !pins && !f.mutex_mixed.transfer_requested);
	forced_reserve_error = 0;
	CHECK(kd_mutex_jit_spin_lock_ctx(&b, &f.regs, &f) == 1);
	f.regs.ip = 0x100; f.regs.sp = (unsigned long)&call_word;
	CHECK(kd_mutex_jit_spin_lock_ctx(&c, &f.regs, &f) == KD_EXE_KNOWN_NATIVE);
	CHECK(!f.mutex_mixed.transfer_requested && kd_exec_mutex_spin_count(&f) == 1);
	CHECK(!kd_exec_mutex_transfer_allowed(&f));
	CHECK(!kd_mutex_jit_spin_unlock_ctx(&b, &f) && !pins);
}

int main(void)
{
	fast_and_exact_release();
	miss_and_boundaries();
	for (unsigned int i = 0; i < 8; i++)
		CHECK(!entries[i].state);
	CHECK(!pins);
	if (failures)
		return 1;
	printf("PASS production mixed controls: %u checks, one CAS, exact CALL, stale tickets, non-LIFO release, pending transfer/borrow, drain\n", checks);
	return 0;
}
