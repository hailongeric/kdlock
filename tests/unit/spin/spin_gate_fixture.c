/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise the actual fixed gate map and physical-hold checks in userspace.
 * Lock words/tasks below are substitutes; stale holds must still be rejected. */
#include "spin_gate_mock.h"
#include "gate_production.h"

int main(void)
{
	static raw_spinlock_t locks[KD_SPIN_GATE_SLOTS + 1];
	struct kd_spin_hold hold = { 0 }, second = { 0 }, stale;
	struct kd_spin_gate *gate = kd_spin_gate_get(&locks[0]);
	const unsigned int marker = 0x7abc0003;

	CHECK(gate && gate->origin == &locks[0]);
	CHECK((void *)&gate->word != (void *)gate->origin);
	CHECK(kd_spin_gate_get(NULL) == NULL);
	CHECK(kd_spin_gate_find(NULL) == NULL);
	CHECK(kd_spin_gate_find(&locks[1]) == NULL);
	CHECK(kd_spin_gate_find(&locks[0]) == gate);
	CHECK(kd_spin_gate_get(&locks[0]) == gate);
	CHECK(kd_spin_gates_check_idle() == 0);
	CHECK(kd_spin_gate_claim(NULL, &hold) == -EINVAL);
	CHECK(kd_spin_gate_claim(gate, NULL) == -EINVAL);
	gate->word.val.counter = marker;
	CHECK(kd_spin_gate_claim(gate, &hold) == -EINVAL);
	mock_preempt = 1;
	mock_in_task = false;
	CHECK(kd_spin_gate_claim(gate, &hold) == -EINVAL);
	mock_in_task = true;
	mock_irq = true;
	CHECK(kd_spin_gate_claim(gate, &hold) == -EINVAL);
	mock_irq = false;
	gate->word.val.counter = 0;
	CHECK(kd_spin_gate_claim(gate, &hold) == -EINVAL);
	gate->word.val.counter = marker;
	CHECK(kd_spin_gate_claim(gate, &hold) == 0);
	CHECK(hold.gate == gate && hold.owner == current &&
	      hold.cpu == mock_cpu);
	CHECK(gate->held && locks[0].held && mock_preempt == 1);
	CHECK((unsigned int)gate->word.val.counter == marker);
	CHECK(kd_spin_gate_claim(gate, &hold) == -EBUSY);
	CHECK(kd_spin_gate_claim(gate, &second) == -EBUSY);
	CHECK(kd_spin_gates_check_idle() == -EBUSY);
	stale = hold;
	current = &tasks[1];
	CHECK(kd_spin_gate_release(&hold) == -EPERM);
	current = &tasks[0];
	mock_cpu++;
	mock_preempt = 1;
	CHECK(kd_spin_gate_release(&hold) == -EPERM);
	mock_preempt = 0;
	mock_cpu--;
	mock_preempt = 0;
	CHECK(kd_spin_gate_release(&hold) == -EPERM);
	mock_preempt = 1;
	CHECK(locks[0].held && gate->held && native_releases == 0);
	CHECK(kd_spin_gate_release(&hold) == 0);
	CHECK(!hold.gate && !locks[0].held && !gate->held && !gate->owner);
	CHECK(mock_preempt == 1 &&
	      (unsigned int)gate->word.val.counter == marker);
	CHECK(kd_spin_gate_release(&hold) == -EINVAL);
	CHECK(kd_spin_gate_release(&stale) == -ESTALE);
	CHECK(kd_spin_gates_check_idle() == -EBUSY);
	gate->word.val.counter = 0;
	CHECK(kd_spin_gates_check_idle() == 0);
	/* Same storage can be reused only after the original and gate have drained. */
	locks[0] = (raw_spinlock_t){ 0 };
	CHECK(kd_spin_gate_get(&locks[0]) == gate);
	gate->word.val.counter = marker;
	CHECK(kd_spin_gate_claim(gate, &hold) == 0);
	CHECK(hold.generation == stale.generation + 1);
	CHECK(kd_spin_gate_release(&stale) == -ESTALE && locks[0].held);
	CHECK(kd_spin_gate_release(&hold) == 0);
	gate->generation = ULONG_MAX;
	CHECK(kd_spin_gate_claim(gate, &hold) == -EOVERFLOW);
	CHECK(!gate->owner && !gate->held && !hold.gate && !locks[0].held);
	gate->word.val.counter = 0;
	mock_preempt = 0;
	for (unsigned int i = 1; i < KD_SPIN_GATE_SLOTS; i++) {
		struct kd_spin_gate *other = kd_spin_gate_get(&locks[i]);

		CHECK(other && other != gate && other->origin == &locks[i]);
	}
	CHECK(kd_spin_gate_get(&locks[KD_SPIN_GATE_SLOTS]) == NULL);
	CHECK(kd_spin_gate_get(&locks[0]) == gate);
	CHECK(kd_spin_gates_check_idle() == 0);
	CHECK(mock_preempt == 0 && !mock_irq);
	CHECK(native_claims == 2 && native_releases == 2);
	printf("[PASS] test_spin_gate (%u checks, production map/owner helpers)\n",
	       checks);
	return 0;
}
