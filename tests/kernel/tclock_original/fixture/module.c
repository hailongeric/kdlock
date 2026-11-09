// SPDX-License-Identifier: GPL-2.0
/* Correctness-only exercise of the original rwsem; no alternate lock protocol. */
#include <linux/module.h>
#include <linux/kthread.h>
#include <linux/completion.h>
#include <linux/delay.h>
#include <linux/slab.h>
#include <linux/sched.h>
#include <linux/preempt.h>
#include <linux/spinlock.h>
#if TEST_KIND == 1
#include "spinlock/komb.h"
static struct qspinlock lock = __ARCH_SPIN_LOCK_UNLOCKED;
#define register_worker() 0
#define drain_workers() 0
#define read_lock_test() do { preempt_disable(); komb_spin_lock(&lock); } while (0)
#define read_unlock_test() do { komb_spin_unlock(&lock); preempt_enable(); } while (0)
#define write_lock_test() read_lock_test()
#define write_unlock_test() read_unlock_test()
#define lock_busy() atomic_read(&lock.val)
#elif TEST_KIND == 2
#include "mutex/komb_mutex.h"
extern int tc_mutex_worker_register(void), tc_mutex_workers_drain(void);
static struct komb_mutex lock = __KOMBMUTEX_INITIALIZER(lock);
#define register_worker() tc_mutex_worker_register()
#define drain_workers() tc_mutex_workers_drain()
#define read_lock_test() komb_mutex_lock(&lock)
#define read_unlock_test() komb_mutex_unlock(&lock)
#define write_lock_test() read_lock_test()
#define write_unlock_test() read_unlock_test()
#define lock_busy() (lock.tail || lock.locked || lock.combiner_task)
#elif TEST_KIND == 3
#include "rwlock/komb_rwlock.h"
static struct komb_rwlock lock = __KOMB_RWLOCK_UNLOCKED;
#define register_worker() 0
#define drain_workers() 0
#define read_lock_test() do { preempt_disable(); komb_read_lock(&lock); } while (0)
#define read_unlock_test() do { komb_read_unlock(&lock); local_irq_enable(); preempt_enable(); } while (0)
#define write_lock_test() do { preempt_disable(); komb_write_lock(&lock); } while (0)
#define write_unlock_test() do { komb_write_unlock(&lock); local_irq_enable(); preempt_enable(); } while (0)
#define lock_busy() (atomic_read(&lock.cnts) || atomic_read(&lock.lock.val))
#else
#include "rwsem/komb_rwsem.h"
extern int tc_rwsem_worker_register(void), tc_rwsem_workers_drain(void);
static DECLARE_KOMB_RWSEM(lock);
#define register_worker() tc_rwsem_worker_register()
#define drain_workers() tc_rwsem_workers_drain()
#define read_lock_test() komb_rwsem_down_read(&lock)
#define read_unlock_test() komb_rwsem_up_read(&lock)
#define write_lock_test() komb_rwsem_down_write(&lock)
#define write_unlock_test() komb_rwsem_up_write(&lock)
#define lock_busy() (atomic_long_read(&lock.cnts) || lock.writer_tail || atomic_read(&lock.reader_wait_lock.val))
#endif
static unsigned int workers = 8, iterations = 10000, write_percent = 20;
module_param(workers, uint, 0444);
module_param(iterations, uint, 0444);
module_param(write_percent, uint, 0444);
static int result = -EINPROGRESS;
module_param(result, int, 0444);
static unsigned long remote_writes, writes, reads;
module_param(remote_writes, ulong, 0444);
module_param(writes, ulong, 0444);
module_param(reads, ulong, 0444);
static DECLARE_COMPLETION(start);
static u64 first, second;
static atomic_t errors = ATOMIC_INIT(0), active_readers = ATOMIC_INIT(0);
static atomic_t peak_readers = ATOMIC_INIT(0);
static int peak;
module_param(peak, int, 0444);
struct worker {
	struct task_struct *task;
	struct completion ready, finished;
	unsigned long writes, reads, remote;
	unsigned int id;
};
static struct worker cohort[16];
static __attribute__((noipa)) noinline struct task_struct *observed_current(void)
{
	return current;
}
static int body(void *arg)
{
	struct worker *w = arg;
	struct task_struct *caller = current;
	unsigned int i;
	int ret = register_worker();
	if (ret)
		atomic_inc(&errors);
	complete(&w->ready);
	wait_for_completion(&start);
	if (ret)
		goto done;
	for (i = 0; i < iterations; i++) {
		int pc = preempt_count();
		if ((i + w->id * 17) % 100 < write_percent) {
			write_lock_test();
			barrier();
			if (observed_current() != caller)
				w->remote++;
			if (first != second || atomic_read(&active_readers))
				atomic_inc(&errors);
			first++;
			cpu_relax();
			second++;
			w->writes++;
			write_unlock_test();
		} else {
			int n, old;
			read_lock_test();
			n = atomic_inc_return(&active_readers);
			old = atomic_read(&peak_readers);
			while (n > old && !atomic_try_cmpxchg(&peak_readers, &old, n))
				cpu_relax();
			if (observed_current() != caller || first != second)
				atomic_inc(&errors);
			udelay(1);
			if (first != second)
				atomic_inc(&errors);
			atomic_dec(&active_readers);
			w->reads++;
			read_unlock_test();
		}
		if (observed_current() != caller || preempt_count() != pc || irqs_disabled())
			atomic_inc(&errors);
	}
done:
	complete(&w->finished);
	while (!kthread_should_stop()) {
		set_current_state(TASK_INTERRUPTIBLE);
		if (!kthread_should_stop())
			schedule();
	}
	__set_current_state(TASK_RUNNING);
	return 0;
}
static int __init test_init(void)
{
	unsigned int i, created = 0;
	if (!workers || workers > 16 || !iterations || iterations > 100000 || write_percent > 100)
		return -EINVAL;
	for (i = 0; i < workers; i++) {
		struct worker *w = &cohort[i];
		if (!cpu_online(i))
			break;
		w->id = i;
		init_completion(&w->ready);
		init_completion(&w->finished);
		w->task = kthread_create(body, w, "tc-original/%u", i);
		if (IS_ERR(w->task))
			break;
		kthread_bind(w->task, i);
		wake_up_process(w->task);
		created++;
	}
	for (i = 0; i < created; i++)
		wait_for_completion(&cohort[i].ready);
	complete_all(&start);
	for (i = 0; i < created; i++) {
		wait_for_completion(&cohort[i].finished);
		kthread_stop(cohort[i].task);
		writes += cohort[i].writes;
		reads += cohort[i].reads;
		remote_writes += cohort[i].remote;
	}
	/* kthread_stop joins the function; task PID retirement can follow it. */
	for (i = 0; i < 100; i++) {
		result = drain_workers();
		if (result != -EBUSY)
			break;
		msleep(10);
	}
	if (created != workers || atomic_read(&errors) || first != writes || second != writes ||
	    writes + reads != (unsigned long)workers * iterations ||
	    lock_busy())
		result = -EINVAL;
	peak = atomic_read(&peak_readers);
	pr_info("tc-original: result=%d workers=%u writes=%lu reads=%lu remote=%lu peak_readers=%d errors=%d\n",
		result, workers, writes, reads, remote_writes, peak, atomic_read(&errors));
	return 0;
}
static void __exit test_exit(void) {}
module_init(test_init);
module_exit(test_exit);
MODULE_LICENSE("GPL");
