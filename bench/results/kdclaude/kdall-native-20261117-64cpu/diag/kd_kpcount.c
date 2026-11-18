// SPDX-License-Identifier: GPL-2.0
/*
 * Diagnostic: count how often instructions are reached. probes= takes
 * "name:symbol+offset" entries; a kprobe at each one counts hits per CPU
 * (kd's files are built without ftrace, so tracefs kprobe events refuse
 * them). The totals are printed when the module is removed, so load and
 * remove it around the measurement window.
 */
#include <linux/module.h>
#include <linux/kprobes.h>
#include <linux/percpu.h>
#include <linux/string.h>
#include <linux/slab.h>

#define KP_MAX 16

static char *probes[KP_MAX];
static int nprobes;
module_param_array(probes, charp, &nprobes, 0);

static struct kprobe kps[KP_MAX];
static char names[KP_MAX][32];
static char syms[KP_MAX][64];
static DEFINE_PER_CPU(unsigned long [KP_MAX], kp_hits);
static int nreg;

static int kp_pre(struct kprobe *p, struct pt_regs *regs)
{
	__this_cpu_inc(kp_hits[p - kps]);
	return 0;
}

static int __init kp_init(void)
{
	int i, ret;

	for (i = 0; i < nprobes; i++) {
		char *s = probes[i], *c = strchr(s, ':'), *plus;
		unsigned long off = 0;

		if (!c)
			return -EINVAL;
		strscpy(names[i], s, min_t(size_t, c - s + 1, sizeof(names[i])));
		strscpy(syms[i], c + 1, sizeof(syms[i]));
		plus = strchr(syms[i], '+');
		if (plus) {
			*plus = 0;
			if (kstrtoul(plus + 1, 0, &off))
				return -EINVAL;
		}
		kps[i].symbol_name = syms[i];
		kps[i].offset = off;
		kps[i].pre_handler = kp_pre;
		ret = register_kprobe(&kps[i]);
		if (ret) {
			pr_info("kd_kpcount: %s at %s+%#lx: %d\n", names[i], syms[i], off, ret);
			while (--i >= 0)
				unregister_kprobe(&kps[i]);
			return ret;
		}
	}
	nreg = nprobes;
	pr_info("kd_kpcount: %d probes armed\n", nreg);
	return 0;
}

static void __exit kp_exit(void)
{
	int i, cpu;

	for (i = 0; i < nreg; i++)
		unregister_kprobe(&kps[i]);
	for (i = 0; i < nreg; i++) {
		unsigned long n = 0;

		for_each_possible_cpu(cpu)
			n += per_cpu(kp_hits, cpu)[i];
		pr_info("kd_kpcount: hits %s %lu missed %lu\n", names[i], n, kps[i].nmissed);
	}
}
module_init(kp_init);
module_exit(kp_exit);
MODULE_LICENSE("GPL");
