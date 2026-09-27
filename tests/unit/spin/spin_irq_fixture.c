/* SPDX-License-Identifier: GPL-2.0 */
/* Execute the actual IRQ/BH header wrappers. Primitive events expose ordering,
 * not just final balance; hardware IRQ delivery and MCS peers are not modeled. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "irq_typecheck.h"

typedef uint32_t u32;
typedef union { u32 val; unsigned char locked; } kd_spinlock_t;
#define KD_SPIN_DIRECT_NATIVE_HELD 5U
#define PREEMPT_MASK 255U
#define SOFTIRQ_DISABLE_OFFSET 512U
#define SOFTIRQ_LOCK_OFFSET (SOFTIRQ_DISABLE_OFFSET + 1U)
#define _RET_IP_ 0x1234UL
#define IRQ_IF 0x200UL
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))

enum kind { SAVE, IRQ, BH };
static enum kind active_kind;
static unsigned int preempt_state, before_preempt, before_native;
static unsigned long irq_flags, before_flags, final_flags;
static struct { unsigned int nondelegated; } kd_spin_fast_cpu;
static kd_spinlock_t *active_lock;
static unsigned int cas_calls, samples, waits, gate_reads;
static unsigned int pin_adds, pin_drops, bh_adds, bh_drops;
static unsigned int lock_evaluations, flags_evaluations;
unsigned int kd_hotlock_spin_gate;
static char events[256];
static unsigned int event_count;

static void event(char code)
{
	assert(event_count < sizeof(events));
	events[event_count++] = code;
}

static void expected_events(unsigned int start, const char *expected)
{
	assert(event_count - start == strlen(expected));
	assert(!memcmp(events + start, expected, strlen(expected)));
}

static void assert_held_context(void)
{
	assert(preempt_state == before_preempt +
	       (active_kind == BH ? SOFTIRQ_LOCK_OFFSET : 1));
	assert((preempt_state & PREEMPT_MASK) != 0);
	assert(active_kind == BH ? irq_flags == before_flags : !(irq_flags & IRQ_IF));
}

static void mock_preempt_disable(void)
{
	assert(active_kind != BH && !(irq_flags & IRQ_IF));
	preempt_state++;
	pin_adds++;
	event('P');
}

static void mock_preempt_enable(void)
{
	assert(active_kind != BH && active_lock->locked == 0);
	assert(preempt_state == before_preempt + 1 && irq_flags == final_flags);
	assert(kd_spin_fast_cpu.nondelegated == before_native);
	preempt_state--;
	pin_drops++;
	event('E');
}

static unsigned long mock_irq_save(void)
{
	unsigned long saved = irq_flags;
	irq_flags &= ~IRQ_IF;
	event('S');
	return saved;
}

static void mock_irq_disable(void)
{
	irq_flags &= ~IRQ_IF;
	event('D');
}

static void mock_irq_restore(unsigned long flags)
{
	assert(active_lock->locked == 0 && preempt_state == before_preempt + 1);
	assert(kd_spin_fast_cpu.nondelegated == before_native);
	assert(flags == final_flags);
	irq_flags = flags;
	event('R');
}

static void mock_irq_enable(void)
{
	assert(active_lock->locked == 0 && preempt_state == before_preempt + 1);
	assert(kd_spin_fast_cpu.nondelegated == before_native);
	irq_flags |= IRQ_IF;
	event('I');
}

static void __local_bh_disable_ip(unsigned long ip, unsigned int count)
{
	assert(active_kind == BH && ip == _RET_IP_ && count == SOFTIRQ_LOCK_OFFSET);
	assert(irq_flags & IRQ_IF);
	preempt_state += count;
	bh_adds++;
	event('B');
}

static void __local_bh_enable_ip(unsigned long ip, unsigned int count)
{
	assert(active_kind == BH && ip == _RET_IP_ && count == SOFTIRQ_LOCK_OFFSET);
	assert_held_context();
	assert(active_lock->locked == 0 && kd_spin_fast_cpu.nondelegated == before_native);
	preempt_state -= count;
	bh_drops++;
	event('b');
}

#define preempt_disable() mock_preempt_disable()
#define preempt_enable() mock_preempt_enable()
#define local_irq_save(flags) do { (flags) = mock_irq_save(); } while (0)
#define local_irq_restore(flags) mock_irq_restore(flags)
#define local_irq_disable() mock_irq_disable()
#define local_irq_enable() mock_irq_enable()
#define READ_ONCE(x) (x)
#define this_cpu_read(x) (++gate_reads, (x))
#define this_cpu_inc(x) do { ++(x); event('+'); } while (0)
#define this_cpu_dec(x) do { \
	assert(active_lock->locked == 0 && (x) > 0); --(x); event('-'); \
} while (0)
#define smp_store_release(p, value) do { \
	assert((void *)(p) == (void *)&active_lock->locked); \
	assert_held_context(); *(p) = (value); event('U'); \
} while (0)

static u32 atomic_cmpxchg_acquire(u32 *word, u32 old, u32 value)
{
	u32 found = *word;
	assert(word == &active_lock->val && old == 0 && value == KD_SPIN_DIRECT_NATIVE_HELD);
	assert_held_context();
	assert(kd_spin_fast_cpu.nondelegated == before_native + 1);
	if (found == old)
		*word = value;
	cas_calls++;
	event('C');
	return found;
}

static void kd_hotlock_spin_entry_pinned(void)
{
	assert_held_context();
	samples++;
	event('H');
}

#include "irq_production.h"

/* Only the hardware contention finisher is substituted. Any attempt to call
 * the ordinary hot/JIT entry remains undefined and fails this fixture's link. */
void kd_spin_direct_native_contended(kd_spinlock_t *lock, u32 failed)
{
	assert_held_context();
	assert(lock == active_lock && failed == lock->val && failed);
	assert(cas_calls == samples && kd_spin_fast_cpu.nondelegated == before_native + 1);
	kd_hotlock_spin_gate ^= 1;
	lock->locked = KD_SPIN_DIRECT_NATIVE_HELD;
	waits++;
	event('Q');
}

static kd_spinlock_t *lock_expression(kd_spinlock_t *lock)
{
	lock_evaluations++;
	return lock;
}

static void prepare(enum kind kind, kd_spinlock_t *lock)
{
	active_kind = kind;
	active_lock = lock;
	before_preempt = preempt_state;
	before_native = kd_spin_fast_cpu.nondelegated;
	before_flags = irq_flags;
	final_flags = kind == IRQ ? irq_flags | IRQ_IF : irq_flags;
}

static void one_pair(enum kind kind, bool disabled, unsigned int nesting,
		     bool contended)
{
	kd_spinlock_t lock = { .val = contended ? 0x12340101U : 0 };
#ifdef KD_IRQ_WRONG_FLAGS
	unsigned int saved[1] = { 0xdeadbeefU };
#else
	unsigned long saved[1] = { 0xdeadbeefUL };
#endif
	unsigned int start, old_cas = cas_calls, old_samples = samples, old_waits = waits;
	unsigned int old_pins = pin_adds, old_unpins = pin_drops;
	unsigned int old_bh = bh_adds, old_unbh = bh_drops;

	irq_flags = 0x4002UL | (disabled ? 0 : IRQ_IF);
	preempt_state = nesting;
	/* Model unrelated native holds without letting this release consume them. */
	kd_spin_fast_cpu.nondelegated = 2;
	lock_evaluations = flags_evaluations = 0;
	kd_hotlock_spin_gate = 1;
	prepare(kind, &lock);
	start = event_count = 0;
	if (kind == SAVE)
		kd_spin_lock_irqsave(lock_expression(&lock), saved[(flags_evaluations++, 0)]);
	else if (kind == IRQ)
		kd_spin_lock_irq(lock_expression(&lock));
	else
		kd_spin_lock_bh(lock_expression(&lock));
	expected_events(start, kind == SAVE ? (contended ? "SP+CHQ" : "SP+CH") :
		kind == IRQ ? (contended ? "DP+CHQ" : "DP+CH") :
		(contended ? "B+CHQ" : "B+CH"));
	assert_held_context();
	assert(lock.locked == KD_SPIN_DIRECT_NATIVE_HELD);
	assert(lock_evaluations == 1 && flags_evaluations == (kind == SAVE));
	assert(cas_calls == old_cas + 1 && samples == old_samples + 1);
	assert(waits == old_waits + contended && !gate_reads);
	if (kind == SAVE)
		assert(saved[0] == before_flags);
	/* A successor may publish pending/tail after acquisition. Only release the
	 * owned byte, even when the CPU's profiling gate changes meanwhile. */
	lock.val |= 0x56780100U;
	u32 queued = lock.val & ~255U;
	kd_hotlock_spin_gate ^= 1;
	start = event_count;
	if (kind == SAVE)
		kd_spin_unlock_irqrestore(lock_expression(&lock), saved[(flags_evaluations++, 0)]);
	else if (kind == IRQ)
		kd_spin_unlock_irq(lock_expression(&lock));
	else
		kd_spin_unlock_bh(lock_expression(&lock));
	expected_events(start, kind == SAVE ? "U-RE" : kind == IRQ ? "U-IE" : "U-b");
	assert(lock.val == queued && preempt_state == nesting && irq_flags == final_flags);
	assert(kd_spin_fast_cpu.nondelegated == 2 && !gate_reads);
	assert(lock_evaluations == 2 && flags_evaluations == (kind == SAVE ? 2U : 0U));
	assert(pin_adds == old_pins + (kind != BH) && pin_drops == old_unpins + (kind != BH));
	assert(bh_adds == old_bh + (kind == BH) && bh_drops == old_unbh + (kind == BH));
	assert(cas_calls == old_cas + 1 && samples == old_samples + 1);
}

static void nested_pairs(enum kind kind)
{
	kd_spinlock_t outer = { 0 }, inner = { 0 };
	unsigned long outer_flags = 0, inner_flags = 0;
	unsigned int increment = kind == BH ? SOFTIRQ_LOCK_OFFSET : 1;

	irq_flags = 0x4202;
	preempt_state = 2;
	kd_spin_fast_cpu.nondelegated = 0;
	event_count = 0;
	prepare(kind, &outer);
	if (kind == SAVE)
		kd_spin_lock_irqsave(&outer, outer_flags);
	else
		kd_spin_lock_bh(&outer);
	prepare(kind, &inner);
	if (kind == SAVE)
		kd_spin_lock_irqsave(&inner, inner_flags);
	else
		kd_spin_lock_bh(&inner);
	assert(preempt_state == 2 + 2 * increment && kd_spin_fast_cpu.nondelegated == 2);
	if (kind == SAVE) {
		assert((outer_flags & IRQ_IF) && !(inner_flags & IRQ_IF));
		kd_spin_unlock_irqrestore(&inner, inner_flags);
		assert(!(irq_flags & IRQ_IF));
	} else {
		kd_spin_unlock_bh(&inner);
	}
	assert(outer.locked == KD_SPIN_DIRECT_NATIVE_HELD && !inner.locked);
	assert(preempt_state == 2 + increment && kd_spin_fast_cpu.nondelegated == 1);
	/* Reinstall the outer call's recorded baseline; the real wrapper has no
	 * such model state and must consume only its own pin/BH/flags pair. */
	active_lock = &outer;
	before_preempt = 2;
	before_native = 0;
	before_flags = final_flags = 0x4202;
	if (kind == SAVE)
		kd_spin_unlock_irqrestore(&outer, outer_flags);
	else
		kd_spin_unlock_bh(&outer);
	assert(!outer.locked && preempt_state == 2 && irq_flags == 0x4202);
	assert(!kd_spin_fast_cpu.nondelegated && !gate_reads);
}

int main(void)
{
	for (unsigned int disabled = 0; disabled < 2; disabled++)
		for (unsigned int nesting = 0; nesting <= 2; nesting += 2)
			for (unsigned int contended = 0; contended < 2; contended++) {
				one_pair(SAVE, disabled, nesting, contended);
				one_pair(IRQ, disabled, nesting, contended);
			}
	for (unsigned int nesting = 0; nesting < 2; nesting++)
		for (unsigned int pins = 0; pins <= 2; pins += 2)
			for (unsigned int contended = 0; contended < 2; contended++)
				one_pair(BH, false, nesting * SOFTIRQ_DISABLE_OFFSET + pins,
					 contended);
	nested_pairs(SAVE);
	nested_pairs(BH);
	puts("PASS IRQ/BH header: saved flags, nested pins/BH, ordered release, single evaluation and native-only hot/contended routing");
	return 0;
}
