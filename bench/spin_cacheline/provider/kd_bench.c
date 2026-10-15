/* SPDX-License-Identifier: GPL-2.0 */
/* Opt-in benchmark accounting, independent of routing and admission policy. */
#include <linux/cpu.h>
#include <linux/moduleparam.h>
#include "kd_bench.h"

bool kd_bench_quiet;
module_param_named(bench_quiet, kd_bench_quiet, bool, 0444);
MODULE_PARM_DESC(bench_quiet, "Suppress routine per-invocation diagnostics");

unsigned long kd_bench_lock_addr;
/* Bind after the dependent workload module loads, before preparation/workers.
 * The runner freezes it throughout measurement and retirement. */
module_param_named(bench_lock_addr, kd_bench_lock_addr, ulong, 0644);
MODULE_PARM_DESC(bench_lock_addr, "Count returned JIT bodies for this lock; 0 disables");

DEFINE_PER_CPU(u64, kd_bench_bodies);
DEFINE_PER_CPU(u64, kd_bench_completions);
bool kd_bench_complete_probe;
module_param_named(bench_complete_probe, kd_bench_complete_probe, bool, 0444);
MODULE_PARM_DESC(bench_complete_probe, "Observe pristine batch completion as well as entry witnesses");

static int kd_bench_bodies_get(char *buffer, const struct kernel_param *param)
{
	u64 total = 0;
	int cpu;

	/* Include offline CPUs too: their previous contributions still belong
	 * to this loaded session. Reads during execution are only approximate. */
	for_each_possible_cpu(cpu)
		total += param->arg ? READ_ONCE(per_cpu(kd_bench_completions, cpu)) :
			READ_ONCE(per_cpu(kd_bench_bodies, cpu));
	return scnprintf(buffer, PAGE_SIZE, "%llu\n", (unsigned long long)total);
}

static const struct kernel_param_ops kd_bench_bodies_ops = {
	.get = kd_bench_bodies_get,
};
module_param_cb(bench_jit_bodies, &kd_bench_bodies_ops, NULL, 0444);
MODULE_PARM_DESC(bench_jit_bodies, "Returned bodies for bench_lock_addr; read after drain");
module_param_cb(bench_jit_completions, &kd_bench_bodies_ops, &kd_bench_complete_probe, 0444);
MODULE_PARM_DESC(bench_jit_completions, "Pristine wrappers reaching matching outer unlock; read after drain");
