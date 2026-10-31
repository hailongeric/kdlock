/* SPDX-License-Identifier: GPL-2.0 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t u8;
#ifndef __always_inline
#define __always_inline inline __attribute__((always_inline))
#endif
struct task_state { int migration_disabled, rcu_read_lock_nesting; } task;
static struct task_state *current = &task;
static unsigned int preempt, bh;
static bool task_context, irq_off;
#define in_task() (task_context)
#define preempt_count() (preempt)
#define softirq_count() (bh)
#define irqs_disabled() (irq_off)
#define READ_ONCE(value) (value)
#include "proxy_context_production.h"

int main(void)
{
	unsigned int cases = 0;
	/* Independent expected state, including stale invalid capture and both IF
	 * directions. Admission must have no side effect on any context component. */
	for (unsigned int context = 0; context < 2; context++)
	for (unsigned int pin = 0; pin < 4; pin++)
	for (unsigned int soft = 0; soft < 2; soft++)
	for (unsigned int migration = 0; migration < 2; migration++)
	for (int nesting = -1; nesting < 3; nesting++)
	for (unsigned int disabled = 0; disabled < 2; disabled++) {
		struct task_state before;
		bool eligible = context && pin == 1 && !soft && !migration;
		u8 captured;
		task_context = context;
		preempt = pin;
		bh = soft ? 0x200 : 0;
		task.migration_disabled = migration;
		task.rcu_read_lock_nesting = nesting;
		irq_off = disabled;
		before = task;
#ifdef CONFIG_PREEMPT_RCU
		eligible = eligible && !nesting;
#endif
		captured = kd_spin_proxy_context();
		assert(captured == (eligible ? (disabled ? 3 : 1) : 0));
		assert(!memcmp(&before, &task, sizeof(task)) && preempt == pin &&
		       bh == (soft ? 0x200U : 0) && task_context == context &&
		       irq_off == disabled);
		for (unsigned int executor = 0; executor < 4; executor++) {
			bool allowed = eligible && executor == (disabled ? 3U : 1U);
			assert(kd_spin_proxy_context_matches(captured, executor) == allowed);
		}
		cases++;
	}
	printf("spin proxy context: %u capture states, IF matches and preserved physical state\n", cases);
	return 0;
}
