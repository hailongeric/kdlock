// SPDX-License-Identifier: GPL-2.0
/* Metadata only: no lock state, flags, registers or wake decisions are changed. */
#include <linux/fs.h>
#include <linux/kallsyms.h>
#include <linux/kprobes.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmap_lock.h>
#include <linux/module.h>
#include <linux/percpu.h>
#include <linux/pid.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/tracepoint.h>
#include <linux/threads.h>
#include <linux/uaccess.h>
#include "api.h"

#ifndef CONFIG_KDLOCK_MMAP
#error "Linux 7 CONFIG_KDLOCK_MMAP integration kernel required"
#endif

#define SLOTS 64
enum stage { ENTRY, PHASE, GATE, DRAIN };
struct record {
	/* Published only after the retained identities and zeroed counters exist.
	 * Thereafter only this exact task updates its record, including switch-out.
	 * No incoming scheduler callback writes another CPU's record. */
	struct task_struct *task;
	struct mm_struct *mm;
	struct phase_row row;
	enum stage stage;
	bool queued, schedule, switched, blocked, after_block, reserved;
};
static struct record records[SLOTS];
static DEFINE_PER_CPU(struct record *, cache);
static atomic_t used = ATOMIC_INIT(0), errors = ATOMIC_INIT(0);
static DEFINE_MUTEX(control);
static struct pid *tgid;
static struct mm_struct *fixture_mm[2];
static struct task_struct *fixture_owner;
static struct tracepoint *switch_point;
static bool armed, finished, registered;

/* Bind the exact unchanged kdmm1 emitted instructions, not source line guesses.
 * +9 is after the optional fentry patch and before the argument is changed.
 * Validate every site before registration can patch any of them. */
struct site { unsigned int offset, size; unsigned char bytes[5]; struct kprobe probe; };
static struct site sites[] = {
	{ .offset=0x009, .size=1, .bytes={0x55} },
	{ .offset=0x055, .size=4, .bytes={0x4c,0x8d,0x65,0xb0} },
	{ .offset=0x073, .size=5, .bytes={0xe8,0xa8,0x64,0xd9,0x00} },
	{ .offset=0x078, .size=5, .bytes={0xba,0x02,0x01,0x00,0x00} },
	{ .offset=0x088, .size=3, .bytes={0x48,0x89,0xc2} },
	{ .offset=0x0a9, .size=3, .bytes={0x48,0x85,0xd2} },
	{ .offset=0x0b6, .size=3, .bytes={0x48,0x89,0xdf} },
	{ .offset=0x0be, .size=3, .bytes={0x41,0x89,0xc6} },
	{ .offset=0x0d7, .size=4, .bytes={0x48,0x8b,0x45,0xd8} },
	{ .offset=0x11a, .size=5, .bytes={0xe8,0x01,0x64,0xd9,0x00} },
	{ .offset=0x11f, .size=5, .bytes={0xba,0x02,0x01,0x00,0x00} },
	{ .offset=0x12f, .size=4, .bytes={0x48,0x8b,0x53,0x40} },
	{ .offset=0x143, .size=2, .bytes={0xeb,0x92} },
	{ .offset=0x150, .size=5, .bytes={0xe9,0x61,0xff,0xff,0xff} },
};

static struct record *lookup(struct task_struct *task)
{
	struct record *r = this_cpu_read(cache);
	unsigned int i;
	if (r && r->task == task)
		return r;
	for (i = 0; i < SLOTS; i++)
		if (smp_load_acquire(&records[i].task) == task) {
			this_cpu_write(cache, &records[i]);
			return &records[i];
		}
	return NULL;
}

static struct mm_struct *selected(unsigned long sem)
{
	unsigned int i;
	if (tgid) {
		if (task_tgid(current) != tgid || strcmp(current->comm, "mw_time_worker") ||
		    !current->mm || sem != (unsigned long)&current->mm->mmap_lock.kd)
			return NULL;
		return current->mm;
	}
	for (i = 0; i < ARRAY_SIZE(fixture_mm); i++)
		if (fixture_mm[i] && sem == (unsigned long)&fixture_mm[i]->mmap_lock.kd)
			return fixture_mm[i];
	return NULL;
}

static void schedule_start(struct record *r, bool drain)
{
	if (r->schedule)
		r->row.count[PH_errors]++;
	r->schedule = true;
	r->switched = r->blocked = false;
	r->row.count[drain ? PH_drain_schedule : PH_phase_schedule]++;
}

static void schedule_end(struct record *r, bool drain)
{
	/* Both return addresses are also reached by initial-loop jumps. */
	if (!r->schedule)
		return;
	r->row.count[drain ? PH_drain_schedule_return : PH_phase_schedule_return]++;
	if (!r->switched)
		r->row.count[drain ? PH_drain_no_switch : PH_phase_no_switch]++;
	else if (!r->blocked)
		r->row.count[drain ? PH_drain_runnable_return : PH_phase_runnable_return]++;
	if (r->blocked) {
		r->row.count[drain ? PH_drain_blocked_return : PH_phase_blocked_return]++;
		if (!drain)
			r->after_block = true;
	}
	r->schedule = false;
}

static int observe(struct kprobe *kp, struct pt_regs *regs)
{
	struct site *s = container_of(kp, struct site, probe);
	struct record *r;
	struct mm_struct *mm;
	int slot;
	if (!smp_load_acquire(&armed))
		return 0;
	r = lookup(current);
	if (s->offset == 9) {
		mm = selected(regs->di);
		if (!mm)
			return 0;
		if (!r) {
			slot = atomic_fetch_inc(&used);
			if (slot >= SLOTS) {
				atomic_inc(&errors);
				return 0;
			}
			r = &records[slot];
			get_task_struct(current);
			/* Fixture refs retain both objects; a selected user task owns its
			 * mm during this handler, allowing this explicit allocation ref. */
			if (tgid) {
				mmgrab(mm);
				r->mm = mm;
			}
			r->row.index = slot;
			r->row.task = (unsigned long)current;
			r->row.tid = task_pid_nr(current);
			r->row.mm = (unsigned long)mm;
			smp_store_release(&r->task, current);
			this_cpu_write(cache, r);
		}
		if (r->row.active || (tgid && r->mm != mm)) {
			/* Never replace an outstanding identity on recursion/mismatch. */
			r->row.count[PH_errors]++;
			return 0;
		}
		r->row.active = 1;
		r->row.sequence++;
		if (!r->row.first_entry_ns) r->row.first_entry_ns = ktime_get_ns();
		r->row.last_sem = regs->di;
		r->row.count[PH_entries]++;
		r->stage = ENTRY;
		r->queued = r->schedule = r->after_block = r->reserved = false;
		return 0;
	}
	if (!r || !r->row.active)
		return 0;
	switch (s->offset) {
	case 0x55:
		r->row.count[PH_initial_fail]++; r->queued = true; r->stage = PHASE; break;
	case 0x73: schedule_start(r, false); break;
	case 0x78: schedule_end(r, false); break;
	case 0x88: r->row.count[PH_phase_prepare]++; break;
	case 0xa9:
		r->row.count[PH_queued_fail]++;
		if ((s32)regs->dx) {
			r->row.count[PH_phase_fail_cancel]++;
			if (r->after_block) r->row.count[PH_phase_after_block_cancel]++;
		} else if (r->after_block) r->row.count[PH_phase_after_block_fail]++;
		r->after_block = false; break;
	case 0xb6:
		if (r->reserved) r->row.count[PH_errors]++;
		r->reserved = true;
		r->row.count[PH_reserved]++;
		r->row.count[r->queued ? PH_reserved_queued : PH_reserved_initial]++;
		if (r->after_block) r->row.count[PH_phase_after_block_reserve]++;
		r->after_block = false; r->stage = GATE; break;
	case 0xbe:
		r->row.count[PH_gate_return]++;
		if ((s32)regs->ax) r->row.count[PH_gate_error]++;
		r->stage = DRAIN; break;
	case 0xd7:
		/* RBX can point inside the semaphore after cancellation rollback.
		 * The saved identity remains authoritative for this observation. */
		r->row.count[PH_epilogues]++;
		r->row.last_epilogue_ns = ktime_get_ns();
		if (!(s32)regs->r14) r->row.count[PH_success]++;
		else if ((s32)regs->r14 == -EINTR) r->row.count[PH_eintr]++;
		else r->row.count[PH_errors]++;
		if (r->schedule || r->after_block) r->row.count[PH_errors]++;
		r->row.active = 0; break;
	case 0x11a: schedule_start(r, true); break;
	case 0x11f: schedule_end(r, true); break;
	case 0x12f: r->row.count[PH_drain_prepare]++; break;
	case 0x143: r->row.count[PH_drain_finish]++; break;
	case 0x150: r->row.count[PH_phase_finish]++; break;
	}
	return 0;
}

/* A post handler disables jump optimization; retain normal breakpoint probe
 * semantics at branches and flag-sensitive instruction boundaries. */
static void observed(struct kprobe *kp, struct pt_regs *regs, unsigned long flags) { }

static void switch_out(void *ignored, bool preempt, struct task_struct *prev,
		       struct task_struct *next, unsigned int prev_state)
{
	struct record *r;
	unsigned int counter;
	/* __schedule can restore TASK_RUNNING for a pending signal while still
	 * passing its earlier prev_state to this tracepoint. Under its rq lock,
	 * on_rq==0 distinguishes an actual dequeue from that runnable departure. */
	bool blocked = !preempt && prev_state != TASK_RUNNING && !READ_ONCE(prev->on_rq);
	if (!smp_load_acquire(&armed))
		return;
	/* The outgoing task is current. No next-task or cross-CPU writes. */
	if (WARN_ON_ONCE(prev != current)) {
		atomic_inc(&errors);
		return;
	}
	r = lookup(prev);
	if (!r || !r->row.active)
		return;
	counter = PH_entry_blocked_out + 2 * r->stage + !blocked;
	r->row.count[counter]++;
	if (r->schedule) {
		r->switched = true;
		r->blocked |= blocked;
	}
}

static void find_switch(struct tracepoint *tp, void *ignored)
{
	if (!strcmp(tp->name, "sched_switch")) switch_point = tp;
}

static void collect(struct phase_result *out)
{
	unsigned int i, j;
	memset(out, 0, sizeof(*out));
	out->abi = 1;
	out->records = min(atomic_read(&used), SLOTS);
	out->errors = atomic_read(&errors);
	for (i = 0; i < ARRAY_SIZE(sites); i++) out->missed += sites[i].probe.nmissed;
	for (i = 0; i < out->records; i++) {
		out->active += records[i].row.active;
		for (j = 0; j < PH_COUNT; j++) out->count[j] += records[i].row.count[j];
	}
}

static void unregister_all(void)
{
	unsigned int i;
	if (!registered) return;
	for (i = 0; i < ARRAY_SIZE(sites); i++) unregister_kprobe(&sites[i].probe);
	tracepoint_probe_unregister(switch_point, switch_out, NULL);
	tracepoint_synchronize_unregister();
	registered = false;
}

static int begin(void)
{
	if (armed || finished || !registered) return -EBUSY;
	__module_get(THIS_MODULE);
	smp_store_release(&armed, true);
	return 0;
}

int kd_phase_begin(struct mm_struct *first, struct mm_struct *second)
{
	int ret;
	mutex_lock(&control);
	if (armed || finished || !first || !second || first == second ||
	    !first->mmap_lock.use_kd || !second->mmap_lock.use_kd) {
		ret = -EINVAL;
		goto out;
	}
	fixture_mm[0] = first; fixture_mm[1] = second;
	mmgrab(first); mmgrab(second);
	fixture_owner = current;
	get_task_struct(fixture_owner);
	ret = begin();
	if (ret) {
		mmdrop(first); mmdrop(second);
		fixture_mm[0] = fixture_mm[1] = NULL;
		put_task_struct(fixture_owner); fixture_owner = NULL;
	}
out:
	(mutex_unlock)(&control);
	return ret;
}
EXPORT_SYMBOL_GPL(kd_phase_begin);

int kd_phase_snapshot(struct phase_result *out)
{
	/* Caller contract: same fixture controller, every worker joined, and no
	 * further target call until this snapshot returns. Not a drain oracle. */
	if (current != fixture_owner || !armed) return -EPERM;
	collect(out);
	return out->active ? -EBUSY : 0;
}
EXPORT_SYMBOL_GPL(kd_phase_snapshot);

static int stop(struct phase_result *out)
{
	unsigned int i;
	if (finished) { collect(out); return 0; }
	if (!armed) return -EINVAL;
	if (fixture_owner) {
		if (current != fixture_owner) return -EPERM;
	} else {
		/* Require actual task exit, not zero observation counters. Retained
		 * struct pid/task references prevent identity reuse across the endpoint. */
		rcu_read_lock();
		if (pid_task(tgid, PIDTYPE_TGID)) {
			rcu_read_unlock();
			return -EBUSY;
		}
		rcu_read_unlock();
		for (i = 0; i < min(atomic_read(&used), SLOTS); i++)
			if (pid_alive(records[i].task)) return -EBUSY;
	}
	smp_store_release(&armed, false);
	unregister_all();
	collect(out);
	/* Independent drain above permits retirement even when missed events
	 * invalidate the accounting. No counter substitutes for that drain. */
	for (i = 0; i < SLOTS; i++)
		if (records[i].mm) { mmdrop(records[i].mm); records[i].mm = NULL; }
	for (i = 0; i < ARRAY_SIZE(fixture_mm); i++)
		if (fixture_mm[i]) { mmdrop(fixture_mm[i]); fixture_mm[i] = NULL; }
	if (fixture_owner) { put_task_struct(fixture_owner); fixture_owner = NULL; }
	finished = true;
	module_put(THIS_MODULE);
	return 0;
}

int kd_phase_end(struct phase_result *out)
{
	int ret;
	mutex_lock(&control);
	ret = stop(out);
	(mutex_unlock)(&control);
	return ret;
}
EXPORT_SYMBOL_GPL(kd_phase_end);

static long phase_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	void __user *user = (void __user *)arg;
	struct phase_result result;
	struct phase_row row;
	u64 number;
	int ret = 0;
	mutex_lock(&control);
	if (cmd == PHASE_ARM) {
		if (armed || finished || copy_from_user(&number, user, sizeof(number)) ||
		    !number || number > PID_MAX_LIMIT) { ret = -EINVAL; goto out; }
		tgid = find_get_pid(number);
		if (!tgid) { ret = -ESRCH; goto out; }
		ret = begin();
		if (ret) { put_pid(tgid); tgid = NULL; }
	} else if (cmd == PHASE_STOP) {
		if (fixture_owner) { ret = -EPERM; goto out; }
		ret = stop(&result);
	} else if (cmd == PHASE_RESULT && finished) {
		collect(&result);
		if (copy_to_user(user, &result, sizeof(result))) ret = -EFAULT;
	} else if (cmd == PHASE_ROW && finished) {
		if (copy_from_user(&row, user, sizeof(row)) || row.index >= SLOTS ||
		    row.index >= atomic_read(&used)) { ret = -EINVAL; goto out; }
		row = records[row.index].row;
		if (copy_to_user(user, &row, sizeof(row))) ret = -EFAULT;
	} else ret = -EINVAL;
out:
	(mutex_unlock)(&control);
	return ret;
}
static const struct file_operations ops = {
	.owner = THIS_MODULE, .unlocked_ioctl = phase_ioctl,
};
static struct miscdevice device = {
	.minor = MISC_DYNAMIC_MINOR, .name = "kd_mmap_phase", .fops = &ops, .mode = 0600,
};

static int __init observer_init(void)
{
	unsigned long address;
	unsigned int i;
	int ret;
	/* The retained table binds the retired kdmm1 image. Compilation does
	 * not qualify those instruction sites on Linux 7; never register them. */
	if (IS_ENABLED(CONFIG_KDLOCK_MMAP)) {
		pr_err("kd_mmap_phase: Linux 7 instruction-site profile is unvalidated\n");
		return -EOPNOTSUPP;
	}
	address = kallsyms_lookup_name("kd_mmap_down_write_killable");
	if (address != 0xffffffff81150880UL) return -ESTALE;
	for (i = 0; i < ARRAY_SIZE(sites); i++)
		if (memcmp((void *)(address + sites[i].offset), sites[i].bytes, sites[i].size))
			return -ESTALE;
	for_each_kernel_tracepoint(find_switch, NULL);
	if (!switch_point) return -ENOENT;
	ret = tracepoint_probe_register(switch_point, switch_out, NULL);
	if (ret) return ret;
	for (i = 0; i < ARRAY_SIZE(sites); i++) {
		sites[i].probe.addr = (void *)(address + sites[i].offset);
		sites[i].probe.pre_handler = observe;
		sites[i].probe.post_handler = observed;
		ret = register_kprobe(&sites[i].probe);
		if (ret) goto fail;
	}
	registered = true;
	ret = misc_register(&device);
	if (!ret) return 0;
fail:
	while (i--) unregister_kprobe(&sites[i].probe);
	tracepoint_probe_unregister(switch_point, switch_out, NULL);
	tracepoint_synchronize_unregister();
	registered = false;
	return ret;
}

static void __exit observer_exit(void)
{
	unsigned int i;
	misc_deregister(&device);
	unregister_all();
	/* All callbacks are retired before exact retained references are dropped. */
	for (i = 0; i < min(atomic_read(&used), SLOTS); i++) {
		if (records[i].mm) mmdrop(records[i].mm);
		if (records[i].task) put_task_struct(records[i].task);
	}
	for (i = 0; i < ARRAY_SIZE(fixture_mm); i++)
		if (fixture_mm[i]) mmdrop(fixture_mm[i]);
	if (tgid) put_pid(tgid);
	if (fixture_owner) put_task_struct(fixture_owner);
}
module_init(observer_init);
module_exit(observer_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Exact kdmm1 killable mmap writer phase metadata observer");
