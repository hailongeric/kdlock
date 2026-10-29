// SPDX-License-Identifier: GPL-2.0
/* Mechanism test, not a real-world API workload. Five original tasks keep
 * every pointer/stack live through the forced C -> W owner exchange and ACK. */
#include <linux/fs.h>
#include <linux/bitops.h>
#include <linux/jiffies.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/objtool.h>
#include <linux/sched.h>
#include <linux/timekeeping.h>
#include <linux/uaccess.h>
#include <linux/wait.h>
#include "kd_lock.h"
#include "kd_hotlock.h"
#include "kd_mutex_api.h"
#include "kd_spin_api.h"
#include "api.h"

static DEFINE_KD_MUTEX(a);
static DEFINE_KD_SPINLOCK(b);
static DEFINE_KD_MUTEX(m);
static unsigned int protocol, test_case;
module_param(protocol, uint, 0444);
module_param(test_case, uint, 0444);
static DECLARE_WAIT_QUEUE_HEAD(gate_wait);
static atomic_t active = ATOMIC_INIT(0), failures = ATOMIC_INIT(0);
static unsigned long started, ready, done;
/* Address tokens only: never dereference a task after its ioctl returns. */
static unsigned long task[MIXED_ROLES];
static bool release_gate, prefix_observed, thief_stop, thief_done, armed;
static bool preholder_release, preholder_done;
static unsigned long warm_eligible, entry_checked, entry_eligible;
static u64 warm_ops;
static u64 prefix, suffix, combiner_bodies, owner_before, owner_after;
static u64 combiner_owner, samples, steal_attempts, steals;
static u64 c_native_task, c_native_owner, c_native_flags, c_native_visits;
static u64 early_unlocked, early_inner_held;
extern char mixed_transfer_entry[], mixed_transfer_native_marker[];

static unsigned long owner(void)
{
	return atomic_long_read(&a.owner) & ~KD_MUTEX_OWNER_FLAGS;
}

/* Both queued tasks use one prepared public API call site. The prefix waits
 * for independent observation while C really owns A. W must resume after the
 * still-pending B CALL, without replaying this prefix or opening A. */
static __attribute__((noipa)) void protected_body(unsigned int role)
{
	unsigned int polls;

	kd_mutex_lock(&a);
	asm volatile(".globl mixed_transfer_entry\n.set mixed_transfer_entry, 1b\n\t"
		     ".pushsection .discard.noendbr\n\t"
		     _ASM_PTR " mixed_transfer_entry\n\t.popsection\n\t"
		     : : : "memory");
	if (!READ_ONCE(armed)) {
		/* Real contention on the same CPUs prepares the production admission
		 * state. No provider gate or eligibility counter is written by a probe. */
		WRITE_ONCE(warm_ops, READ_ONCE(warm_ops) + 1);
		for (polls = 0; polls < 128; polls++)
			cpu_relax();
	} else if (role == MIXED_GATE) {
		/* G acquired through the free delegation gate while T held A.
		 * Hold the resulting HELD gate until both later producers publish.
		 * This same entry stays translatable without another prepared image. */
		for (polls = 0; polls < 500000000 && !READ_ONCE(release_gate); polls++)
			cpu_relax();
		if (!READ_ONCE(release_gate))
			atomic_inc(&failures);
	} else if (role == MIXED_WAITER) {
		if (READ_ONCE(prefix) || READ_ONCE(suffix) || READ_ONCE(combiner_bodies))
			atomic_inc(&failures);
		WRITE_ONCE(prefix, READ_ONCE(prefix) + 1);
		for (polls = 0; polls < 100000000 && !READ_ONCE(prefix_observed); polls++)
			cpu_relax();
		if (!READ_ONCE(prefix_observed))
			atomic_inc(&failures);
		/* Actual public pair: the runtime must encounter the unpinned
		 * recognized CALL, make one failed CAS and resume this task there. */
		kd_spin_lock(&b);
		if ((atomic_long_read(&a.owner) & ~KD_MUTEX_OWNER_FLAGS) !=
		    READ_ONCE(task[MIXED_WAITER]) || !READ_ONCE(owner_after) ||
		    READ_ONCE(prefix) != 1 || READ_ONCE(suffix) ||
		    !(preempt_count() & PREEMPT_MASK))
			atomic_inc(&failures);
		WRITE_ONCE(suffix, READ_ONCE(suffix) + 1);
		if (READ_ONCE(test_case) != MIXED_W_EARLY_SPIN)
			kd_spin_unlock(&b);
		if (READ_ONCE(test_case) == MIXED_W_EARLY_MUTEX)
			kd_mutex_lock(&m);
		/* Stop and acknowledge the thief before A's legitimate final unlock,
		 * so an acquisition after the protected suffix cannot be misclassified. */
		WRITE_ONCE(thief_stop, true);
		for (polls = 0; polls < 100000000 && !READ_ONCE(thief_done); polls++)
			cpu_relax();
		if (!READ_ONCE(thief_done))
			atomic_inc(&failures);
		if (READ_ONCE(test_case) == MIXED_W_EARLY_SPIN ||
		    READ_ONCE(test_case) == MIXED_W_EARLY_MUTEX) {
			/* Native W must release A and wake C without running C under its
			 * still-held inner lock. C's body independently observes that lock. */
			kd_mutex_unlock(&a);
			WRITE_ONCE(early_unlocked, 1);
			for (polls = 0; polls < 100000000 && !READ_ONCE(combiner_bodies); polls++)
				cpu_relax();
			if (!READ_ONCE(combiner_bodies))
				atomic_inc(&failures);
			if (READ_ONCE(test_case) == MIXED_W_EARLY_SPIN)
				kd_spin_unlock(&b);
			else
				kd_mutex_unlock(&m);
			return;
		}
	} else {
		unsigned long wanted_owner = READ_ONCE(task[MIXED_COMBINER]);

		if (READ_ONCE(protocol) == MIXED_ROLE_SWAP &&
		    READ_ONCE(test_case) != MIXED_W_EARLY_SPIN &&
		    READ_ONCE(test_case) != MIXED_W_EARLY_MUTEX)
			wanted_owner = READ_ONCE(task[MIXED_WAITER]);
		WRITE_ONCE(combiner_owner, atomic_long_read(&a.owner) & ~KD_MUTEX_OWNER_FLAGS);
		if (role != MIXED_COMBINER || READ_ONCE(combiner_owner) !=
		    wanted_owner || READ_ONCE(prefix) != 1 ||
		    READ_ONCE(suffix) != 1 || !READ_ONCE(thief_done) ||
		    READ_ONCE(combiner_bodies))
			atomic_inc(&failures);
		if (READ_ONCE(test_case) == MIXED_W_EARLY_SPIN ||
		    READ_ONCE(test_case) == MIXED_W_EARLY_MUTEX) {
			bool held = READ_ONCE(test_case) == MIXED_W_EARLY_SPIN ?
				atomic_read(&b.val) != 0 :
				(atomic_long_read(&m.owner) & ~KD_MUTEX_OWNER_FLAGS) ==
				READ_ONCE(task[MIXED_WAITER]);

			WRITE_ONCE(early_inner_held, held);
			if (!held)
				atomic_inc(&failures);
		}
		WRITE_ONCE(combiner_bodies, READ_ONCE(combiner_bodies) + 1);
		if (READ_ONCE(test_case) == MIXED_C_NATIVE) {
			unsigned long actual_task;
			unsigned int flags;

			/* The existing safe instruction escape restores original C and
			 * arithmetic flags. A stays physically owned by W until C's ACK. */
			asm volatile("movl $1, %%eax\n\tcmpl $2, %%eax\n\t"
				     "jmp mixed_transfer_native_marker\n\t"
				     ".globl mixed_transfer_native_marker\n"
				     "mixed_transfer_native_marker:\n\trdtsc\n\t"
				     "lahf\n\tmovzbl %%ah, %%eax\n\tmovl %%eax, %0\n\t"
				     "movq %%gs:current_task, %%rax\n\tmovq %%rax, %1\n\t"
				     : "=m"(flags), "=m"(actual_task)
				     : : "rax", "rdx", "cc", "memory");
			WRITE_ONCE(c_native_task, actual_task);
			WRITE_ONCE(c_native_owner, atomic_long_read(&a.owner) & ~KD_MUTEX_OWNER_FLAGS);
			WRITE_ONCE(c_native_flags, flags & 0xd5);
			WRITE_ONCE(c_native_visits, READ_ONCE(c_native_visits) + 1);
			if (actual_task != READ_ONCE(task[MIXED_COMBINER]) ||
			    READ_ONCE(c_native_owner) != READ_ONCE(task[MIXED_WAITER]) ||
			    (flags & 0xd5) != 0x95 || READ_ONCE(c_native_visits) != 1)
				atomic_inc(&failures);
		} else if (READ_ONCE(test_case) == MIXED_C_EARLY_SPIN) {
			/* W's new frame owns C's inner B ticket. Releasing A early must
			 * retain B, then finish without reacquiring A for another W body. */
			kd_spin_lock(&b);
			kd_mutex_unlock(&a);
			WRITE_ONCE(early_inner_held, atomic_read(&b.val) != 0);
			WRITE_ONCE(early_unlocked, !atomic_long_read(&a.owner) &&
				   !atomic_read(&a.delegation_state));
			if (!READ_ONCE(early_inner_held) || !READ_ONCE(early_unlocked))
				atomic_inc(&failures);
			kd_spin_unlock(&b);
			return;
		}
	}
	kd_mutex_unlock(&a);
}

static void hold_predecessor(void)
{
	/* A local holder alone leaves the delegation gate FREE. Let G claim
	 * ACQUIRING before releasing A, so G subsequently owns a HELD gate. */
	(kd_mutex_lock)(&a);
	set_bit(MIXED_THIEF, &ready);
	if (!wait_event_timeout(gate_wait, READ_ONCE(preholder_release), 10 * HZ))
		atomic_inc(&failures);
	(kd_mutex_unlock)(&a);
	smp_store_release(&preholder_done, true);
}

static void hold_spin(void)
{
	u64 deadline = ktime_get_ns() + 8000000000ULL;
	bool observed = false;

	kd_spin_lock(&b);
	set_bit(MIXED_SPIN, &ready);
	while (ktime_get_ns() < deadline) {
		unsigned long actual;

		if (!READ_ONCE(prefix)) {
			cpu_relax();
			continue;
		}
		actual = owner();
		WRITE_ONCE(samples, READ_ONCE(samples) + 1);
		if (actual != READ_ONCE(task[MIXED_COMBINER]) &&
		    actual != READ_ONCE(task[MIXED_WAITER]))
			atomic_inc(&failures);
		if (!READ_ONCE(prefix_observed)) {
			/* C cannot leave its prefix barrier yet. Wait for the thief
			 * to begin actual trylocks before releasing that barrier. */
			if (actual != READ_ONCE(task[MIXED_COMBINER]))
				atomic_inc(&failures);
			if (!READ_ONCE(steal_attempts))
				continue;
			WRITE_ONCE(owner_before, actual);
			WRITE_ONCE(prefix_observed, true);
		}
		if (actual == READ_ONCE(task[MIXED_WAITER])) {
			WRITE_ONCE(owner_after, actual);
			if (READ_ONCE(prefix) != 1 || READ_ONCE(suffix) ||
			    atomic_read(&a.delegation_state) != KD_MUTEX_GATE_COMBINER)
				atomic_inc(&failures);
			if (READ_ONCE(steal_attempts) >= 10000) {
				observed = true;
				break;
			}
		}
		cpu_relax();
	}
	if (!observed)
		atomic_inc(&failures);
	/* This is the holder's normal paired unlock, including on a bounded
	 * observation failure. It never unlocks a lock owned by another task. */
	kd_spin_unlock(&b);
}

static void try_to_steal(void)
{
	u64 deadline;

	hold_predecessor();
	deadline = ktime_get_ns() + 10000000000ULL;
	while (!READ_ONCE(thief_stop) && ktime_get_ns() < deadline) {
		if (READ_ONCE(prefix)) {
			if (kd_mutex_trylock(&a)) {
				WRITE_ONCE(steals, READ_ONCE(steals) + 1);
				atomic_inc(&failures);
				kd_mutex_local_unlock(&a);
			}
			WRITE_ONCE(steal_attempts, READ_ONCE(steal_attempts) + 1);
		}
		cond_resched();
	}
	if (!READ_ONCE(thief_stop))
		atomic_inc(&failures);
	smp_store_release(&thief_done, true);
}

static long mixed_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct mixed_run run;
	unsigned int before_preempt, before_migration, after_preempt, after_migration;
	int ret = 0;
	bool before_irqs, after_irqs;

	(void)file;
	if (cmd == MIXED_RUN || cmd == MIXED_WARMUP) {
		if (copy_from_user(&run, user, sizeof(run)))
			return -EFAULT;
		if (run.role >= MIXED_ROLES || !run.iterations || run.iterations > 200000 || preempt_count() ||
		    irqs_disabled() || cpumask_weight(current->cpus_ptr) != 1 ||
		    (cmd == MIXED_RUN && (!READ_ONCE(armed) || run.iterations != 1 ||
					 test_and_set_bit(run.role, &started))) ||
		    (cmd == MIXED_WARMUP && (READ_ONCE(armed) || READ_ONCE(started))))
			return -EINVAL;
		atomic_inc(&active);
		if (cmd == MIXED_RUN)
			WRITE_ONCE(task[run.role], (unsigned long)current);
		before_preempt = preempt_count();
		before_migration = READ_ONCE(current->migration_disabled);
		before_irqs = irqs_disabled();
		run.returned = run.errors = 0;
		if (cmd == MIXED_WARMUP) {
			unsigned int i;

			for (i = 0; i < run.iterations; i++)
				protected_body(run.role);
			/* Read cached eligibility on this worker's actual affine CPU.
			 * The diagnostic export does not record an acquisition or heat. */
			if (kd_hotlock_query_mutex((unsigned long)&a))
				set_bit(run.role, &warm_eligible);
			else
				clear_bit(run.role, &warm_eligible);
		} else if (run.role == MIXED_SPIN)
			hold_spin();
		else if (run.role == MIXED_THIEF)
			try_to_steal();
		else {
			bool eligible = kd_hotlock_query_mutex((unsigned long)&a);

			set_bit(run.role, &ready);
			if (eligible)
				set_bit(run.role, &entry_eligible);
			set_bit(run.role, &entry_checked);
			if (!eligible) {
				run.errors = 1;
				goto finished;
			}
			protected_body(run.role);
		}
		run.returned = run.iterations;
finished:
		after_preempt = preempt_count();
		after_migration = READ_ONCE(current->migration_disabled);
		after_irqs = irqs_disabled();
		/* CPU affinity is not a migration pin. The reservation's one pin must
		 * retire after COMPLETE, native relay or final queue-custody release. */
		run.errors += after_preempt != before_preempt || after_irqs != before_irqs ||
			before_migration || after_migration != before_migration;
		pr_info("KD_MIXED_CONTEXT phase=%s role=%u pid=%d preempt_before=%u preempt_after=%u migration_before=%u migration_after=%u irqs_before=%u irqs_after=%u errors=%llu\n",
			cmd == MIXED_WARMUP ? "warmup" : "run", run.role, current->pid,
			before_preempt, after_preempt, before_migration, after_migration,
			(unsigned int)before_irqs, (unsigned int)after_irqs, run.errors);
		if (run.errors)
			atomic_inc(&failures);
		if (cmd == MIXED_RUN) {
			pr_info("KD_MIXED_RETURN role=%u pid=%d task=%lx prefix=%llu suffix=%llu cbody=%llu errors=%llu\n",
			run.role, current->pid, (unsigned long)current,
			READ_ONCE(prefix), READ_ONCE(suffix), READ_ONCE(combiner_bodies), run.errors);
			set_bit(run.role, &done);
		}
		atomic_dec(&active);
		return copy_to_user(user, &run, sizeof(run)) ? -EFAULT : 0;
	}
	if (cmd == MIXED_PREPARE) {
		if (READ_ONCE(started))
			return -EBUSY;
		return kd_mutex_prepare(&a, (unsigned long)mixed_transfer_entry,
					KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	}
	if (cmd == MIXED_RELEASE) {
		if (READ_ONCE(ready) != (1UL << MIXED_ROLES) - 1 ||
		    owner() != READ_ONCE(task[MIXED_GATE]) ||
		    atomic_read(&a.delegation_state) != KD_MUTEX_GATE_HELD ||
		    kd_mutex_debug_waiter_count(&a) != 2)
			return -EAGAIN;
		WRITE_ONCE(release_gate, true);
		return 0;
	}
	if (cmd == MIXED_PREHOLDER_RELEASE) {
		if (!test_bit(MIXED_THIEF, &ready) || !test_bit(MIXED_GATE, &ready) ||
		    owner() != READ_ONCE(task[MIXED_THIEF]) ||
		    atomic_read(&a.delegation_state) != KD_MUTEX_GATE_ACQUIRING)
			return -EAGAIN;
		WRITE_ONCE(preholder_release, true);
		wake_up_all(&gate_wait);
		return 0;
	}
	if (cmd == MIXED_ARM) {
		if (atomic_read(&active) || READ_ONCE(started) || !READ_ONCE(warm_ops) ||
		    !kd_mutex_is_idle(&a) || !kd_mutex_is_idle(&m) || atomic_read(&b.val))
			return -EBUSY;
		WRITE_ONCE(armed, true);
		return 0;
	}
	if (cmd == MIXED_DRAIN) {
		/* The runner calls only after all five process joins. Active==0 is
		 * an additional observation, never the authority to infer a join. */
		return atomic_read(&active) || READ_ONCE(done) != (1UL << MIXED_ROLES) - 1 ||
		       !kd_mutex_is_idle(&a) || !kd_mutex_is_idle(&m) || atomic_read(&b.val) ? -EBUSY : 0;
	}
	if (cmd == MIXED_SNAPSHOT) {
		struct mixed_snapshot s = {
			.a = (unsigned long)&a, .b = (unsigned long)&b,
			.entry = (unsigned long)mixed_transfer_entry,
			.spin_call = (unsigned long)kd_spin_lock_clobber_v1,
			.active = atomic_read(&active), .failures = atomic_read(&failures),
			.started = READ_ONCE(started), .ready = READ_ONCE(ready),
			.done = READ_ONCE(done), .release_gate = READ_ONCE(release_gate),
			.owner = owner(), .gate = atomic_read(&a.delegation_state),
			.tail = READ_ONCE(a.delegation_tail), .b_word = atomic_read(&b.val),
			.prefix = READ_ONCE(prefix), .suffix = READ_ONCE(suffix),
			.combiner_bodies = READ_ONCE(combiner_bodies),
			.owner_before = READ_ONCE(owner_before), .owner_after = READ_ONCE(owner_after),
			.combiner_owner = READ_ONCE(combiner_owner), .samples = READ_ONCE(samples),
			.steal_attempts = READ_ONCE(steal_attempts), .steals = READ_ONCE(steals),
			.prefix_observed = READ_ONCE(prefix_observed), .thief_done = READ_ONCE(thief_done),
			.c_task = READ_ONCE(task[MIXED_COMBINER]), .w_task = READ_ONCE(task[MIXED_WAITER]),
			.warm_ops = READ_ONCE(warm_ops), .armed = READ_ONCE(armed),
			.warm_eligible = READ_ONCE(warm_eligible),
			.entry_checked = READ_ONCE(entry_checked), .entry_eligible = READ_ONCE(entry_eligible),
			.preholder_release = READ_ONCE(preholder_release),
			.preholder_done = READ_ONCE(preholder_done),
			.g_task = READ_ONCE(task[MIXED_GATE]), .t_task = READ_ONCE(task[MIXED_THIEF]),
			.protocol = protocol, .test_case = test_case,
			.native_marker = (unsigned long)mixed_transfer_native_marker,
			.m = (unsigned long)&m, .m_owner = atomic_long_read(&m.owner),
			.c_native_task = READ_ONCE(c_native_task), .c_native_owner = READ_ONCE(c_native_owner),
			.c_native_flags = READ_ONCE(c_native_flags), .c_native_visits = READ_ONCE(c_native_visits),
			.early_unlocked = READ_ONCE(early_unlocked), .early_inner_held = READ_ONCE(early_inner_held),
			.waiters = kd_mutex_debug_waiter_count(&a),
		};
		ret = copy_to_user(user, &s, sizeof(s)) ? -EFAULT : 0;
	} else {
		ret = -ENOTTY;
	}
	return ret;
}

static const struct file_operations mixed_fops = {
	.owner = THIS_MODULE, .unlocked_ioctl = mixed_ioctl,
};
static struct miscdevice mixed_device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mutex_mixed_transfer",
	.fops = &mixed_fops, .mode = 0600,
};
static int __init mixed_init(void)
{
	BUILD_BUG_ON(sizeof(struct mixed_run) != 24);
	BUILD_BUG_ON(sizeof(struct mixed_snapshot) != 384);
	if (protocol > MIXED_ROLE_SWAP || test_case >= MIXED_CASES ||
	    (protocol == MIXED_OWNER_HANDOFF && test_case != MIXED_SIMPLE))
		return -EINVAL;
	return misc_register(&mixed_device);
}
static void __exit mixed_exit(void)
{
	WARN_ON(atomic_read(&active) || !kd_mutex_is_idle(&a) || !kd_mutex_is_idle(&m) || atomic_read(&b.val));
	misc_deregister(&mixed_device);
}
module_init(mixed_init);
module_exit(mixed_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Deterministic public mutex to spin failed-CAS owner transfer probe");
