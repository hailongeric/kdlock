// SPDX-License-Identifier: GPL-2.0
/* Contended entry checks, without a translator or timing claims. */
#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/completion.h>
#include <linux/cpu.h>
#include <linux/irqflags.h>
#include <linux/preempt.h>
#include <kdlock/kd_api.h>

#define CHECK_LOOPS 30000

enum entry_kind { PLAIN, IRQ, IRQSAVE, IRQSAVE_OFF, BH, CLOBBER, ENTRY_NR };
static const char * const names[] = {
	"plain", "irq", "irqsave", "irqsave-disabled", "bh", "clobber"
};
static struct kd_spinlock lock;
static struct completion start;
static atomic_t inside, errors, contended;
static unsigned long value;
static enum entry_kind kind;
struct worker {
	struct completion ready, done;
	unsigned int operations;
};
static struct worker workers[2];

static int check_worker(void *arg)
{
	struct worker *w = arg;
	unsigned int i, j;

	complete(&w->ready);
	wait_for_completion(&start);
	for (i = 0; i < CHECK_LOOPS; i++) {
		unsigned long flags = 0, outer = 0;
		int pc = preempt_count();

		if (irqs_disabled())
			atomic_inc(&errors);
		if (kind == IRQSAVE_OFF)
			local_irq_save(outer);
		switch (kind) {
		case PLAIN: kd_spin_lock(&lock); break;
		case IRQ: kd_spin_lock_irq(&lock); break;
		case IRQSAVE:
		case IRQSAVE_OFF: flags = kd_spin_lock_irqsave(&lock); break;
		case BH: kd_spin_lock_bh(&lock); break;
		case CLOBBER: kd_spin_lock_cl(&lock); break;
		default: break;
		}
		if (atomic_inc_return(&inside) != 1)
			atomic_inc(&errors);
		if (kind == BH) {
			if (!softirq_count() || preempt_count() <= pc)
				atomic_inc(&errors);
		} else if (preempt_count() != pc + 1) {
			atomic_inc(&errors);
		}
		if (irqs_disabled() !=
		    (kind == IRQ || kind == IRQSAVE || kind == IRQSAVE_OFF))
			atomic_inc(&errors);
		if ((kind == IRQSAVE || kind == IRQSAVE_OFF) &&
		    !!raw_irqs_disabled_flags(flags) != (kind == IRQSAVE_OFF))
			atomic_inc(&errors);
		if (kd_spin_is_contended(&lock))
			atomic_inc(&contended);
		WRITE_ONCE(value, READ_ONCE(value) + 1);
		for (j = 0; j < 64; j++)
			cpu_relax();
		if (atomic_dec_return(&inside) != 0)
			atomic_inc(&errors);
		switch (kind) {
		case PLAIN: kd_spin_unlock(&lock); break;
		case IRQ: kd_spin_unlock_irq(&lock); break;
		case IRQSAVE:
		case IRQSAVE_OFF: kd_spin_unlock_irqrestore(&lock, flags); break;
		case BH: kd_spin_unlock_bh(&lock); break;
		case CLOBBER: kd_spin_unlock_cl(&lock); break;
		default: break;
		}
		if (kind == IRQSAVE_OFF) {
			if (!irqs_disabled())
				atomic_inc(&errors);
			local_irq_restore(outer);
		}
		if (irqs_disabled() || preempt_count() != pc)
			atomic_inc(&errors);
		w->operations++;
		cond_resched();
	}
	/* Completion cannot release module text while this worker returns to it. */
	kthread_complete_and_exit(&w->done, 0);
}

static int __init check_init(void)
{
	int ret = 0;

	cpus_read_lock();
	if (!cpu_online(0) || !cpu_online(1)) {
		ret = -ENODEV;
		goto out;
	}
	for (kind = PLAIN; kind < ENTRY_NR; kind++) {
		struct task_struct *a, *b;
		int i;

		kd_spin_lock_init(&lock);
		init_completion(&start);
		atomic_set(&inside, 0);
		atomic_set(&errors, 0);
		atomic_set(&contended, 0);
		value = 0;
		for (i = 0; i < 2; i++) {
			init_completion(&workers[i].ready);
			init_completion(&workers[i].done);
			workers[i].operations = 0;
		}
		a = kthread_create(check_worker, &workers[0], "kd_entry_0");
		if (IS_ERR(a)) { ret = PTR_ERR(a); goto out; }
		b = kthread_create(check_worker, &workers[1], "kd_entry_1");
		if (IS_ERR(b)) {
			/* The first task was never woken into module code. */
			kthread_stop(a);
			ret = PTR_ERR(b);
			goto out;
		}
		kthread_bind(a, 0);
		kthread_bind(b, 1);
		wake_up_process(a);
		wake_up_process(b);
		wait_for_completion(&workers[0].ready);
		wait_for_completion(&workers[1].ready);
		complete_all(&start);
		wait_for_completion(&workers[0].done);
		wait_for_completion(&workers[1].done);
		pr_info("kd_spin_entry_check: %s count=%lu workers=%u,%u errors=%d contended=%d inside=%d\n",
			names[kind], value, workers[0].operations, workers[1].operations,
			atomic_read(&errors), atomic_read(&contended), atomic_read(&inside));
		if (value != 2 * CHECK_LOOPS || atomic_read(&errors) ||
		    atomic_read(&inside) || !atomic_read(&contended) ||
		    workers[0].operations != CHECK_LOOPS ||
		    workers[1].operations != CHECK_LOOPS || kd_spin_is_locked(&lock)) {
			ret = -EINVAL;
			goto out;
		}
	}
 out:
	cpus_read_unlock();
	return ret;
}

static void __exit check_exit(void) { }
module_init(check_init);
module_exit(check_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Contended KD spin entry state and exclusion checks");
