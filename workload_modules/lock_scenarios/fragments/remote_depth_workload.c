// SPDX-License-Identifier: GPL-2.0
/* Mode 8 opt-in: one logical waiter, independent physical executors per lock. */
#define KD_DEEP_MAX 8
#define KD_DEEP_DEFER_MAX 8
static unsigned int remote_chain_depth, remote_chain_stage;
static bool remote_chain_reverse;
static unsigned int remote_chain_defer;
static unsigned int remote_chain_defer_count = 1;
static bool remote_chain_defer_ready;
static bool remote_chain_readmit, remote_chain_readmit_ready;
static unsigned int remote_chain_readmit_layer = 3;
module_param(remote_chain_depth, uint, 0444);
module_param(remote_chain_stage, uint, 0644);
module_param(remote_chain_reverse, bool, 0644);
module_param(remote_chain_defer, uint, 0444);
module_param(remote_chain_defer_count, uint, 0444);
module_param(remote_chain_defer_ready, bool, 0644);
module_param(remote_chain_readmit, bool, 0444);
module_param(remote_chain_readmit_ready, bool, 0644);
module_param(remote_chain_readmit_layer, uint, 0444);
MODULE_PARM_DESC(
	remote_chain_readmit_layer,
	"Readmission virtual layer: 1=B, 2=C, 3=D in the four-lock workload");
MODULE_PARM_DESC(
	remote_chain_readmit,
	"Four-lock JIT test: real local lead and remote prefix before virtual request");
MODULE_PARM_DESC(
	remote_chain_defer,
	"Extra successor at logical layer + 1, 0=off; requires selftest link tracing");
MODULE_PARM_DESC(
	remote_chain_defer_count,
	"Remote followers at the selected layer: 1..8, followed by one local successor");
MODULE_PARM_DESC(remote_chain_depth,
		 "Mode 8 logical remote depth: 0=off, 4..8");
MODULE_PARM_DESC(
	remote_chain_stage,
	"Arm after publication: 1=JIT, 2=before, 3=after, 4=between, 5=capacity at depth 8");

static spinlock_t deep_locks[KD_DEEP_MAX + 1];
static struct kd_cs_state deep_states[KD_DEEP_MAX];
static unsigned long deep_completed[KD_DEEP_MAX];
static atomic_t deep_inside[KD_DEEP_MAX + 1];
static atomic_t deep_direct[KD_DEEP_MAX];
static bool deep_holder[KD_DEEP_MAX], deep_published[KD_DEEP_MAX];
static bool deep_dependency_ready, deep_abort;
static atomic_t deep_failures = ATOMIC_INIT(0);
static unsigned int deep_prefix, deep_suffix, deep_observed, deep_origin_cpu;
static unsigned int deep_requests, deep_checked;
static struct task_struct *deep_waiter;
static unsigned int deep_follower_acquired[KD_DEEP_DEFER_MAX + 1];
static unsigned int deep_follower_returned[KD_DEEP_DEFER_MAX + 1];

struct kd_deep_record {
	struct task_struct *task;
	unsigned int id, before, called, after;
	unsigned long value;
};

#include "remote_depth/callee.inc"

#include "remote_depth/participants.inc"

static int kd_deep_run(unsigned long loops, unsigned int role)
{
	unsigned long i;
	unsigned int id = role >= 2 ? (role - 2) / 4 : 0;
	unsigned int kind = role >= 2 ? (role - 2) % 4 : 0;
	unsigned int base = 2 + 4 * remote_chain_depth;
	bool extra = remote_chain_defer && role >= base;
	bool readmit = remote_chain_readmit && role >= base;

	if (remote_chain_stage > 5 ||
	    role >= base + (remote_chain_readmit ? 2 :
			    remote_chain_defer	 ? remote_chain_defer_count :
						   0) ||
	    (remote_chain_readmit && remote_chain_stage > 1) ||
	    (remote_chain_stage == 5 && remote_chain_depth != 8) ||
	    (remote_chain_stage == 1 && remote_chain_depth == 8) ||
	    (!remote_chain_stage && role &&
	     (extra || readmit || role == 1 || kind == 0 || kind == 3)) ||
	    (remote_chain_stage && loops != 1))
		return -EINVAL;
	for (i = 0; i < loops; i++) {
		if (!role) {
			switch (remote_chain_depth) {
			case 4:
				kd_deep_request_4();
				break;
			case 5:
				kd_deep_request_5();
				break;
			case 6:
				kd_deep_request_6();
				break;
			case 7:
				kd_deep_request_7();
				break;
			case 8:
				kd_deep_request_8();
				break;
			}
		} else if (role == 1)
			kd_deep_observer();
		else if (readmit) {
			if (kd_deep_readmit_wait(role - base + 1))
				kd_deep_direct(remote_chain_readmit_layer);
		} else if (extra)
			kd_deep_trailing(remote_chain_defer - 1,
					 role - base + 1);
		else if (kind == 0)
			kd_deep_holder(id);
		else if (kind == 3)
			kd_deep_trailing(id, 0);
		else
			kd_deep_direct(id);
	}
	return READ_ONCE(deep_abort) ? -ETIMEDOUT : 0;
}

static int kd_deep_init(void)
{
	unsigned int i;

	if (!remote_chain_defer_count ||
	    remote_chain_defer_count > KD_DEEP_DEFER_MAX ||
	    (!remote_chain_defer && remote_chain_defer_count != 1))
		return -EINVAL;
	if (remote_chain_readmit_layer < 1 || remote_chain_readmit_layer > 3 ||
	    (!remote_chain_readmit && remote_chain_readmit_layer != 3) ||
	    remote_chain_readmit_ready ||
	    (remote_chain_readmit &&
	     (remote_chain_depth != 4 || remote_chain_defer)))
		return -EINVAL;
	if (!remote_chain_depth)
		return remote_chain_stage || remote_chain_reverse ||
				       remote_chain_defer ||
				       remote_chain_defer_ready ?
			       -EINVAL :
			       0;
	if (remote_chain_depth < 4 || remote_chain_depth > KD_DEEP_MAX ||
	    remote_chain_stage || remote_chain_reverse || native_resume_stage ||
	    spin_chain_depth || mixed_lock_probe || remote_spin_ooo ||
	    remote_chain_defer > remote_chain_depth || remote_chain_defer_ready)
		return -EINVAL;
	for (i = 0; i <= remote_chain_depth; i++) {
		spin_lock_init(&deep_locks[i]);
		atomic_set(&deep_inside[i], 0);
		pr_info("kd_deep lock: index=%u addr=%lx\n", i,
			(unsigned long)&deep_locks[i]);
	}
	return 0;
}

static void kd_deep_report(void)
{
	unsigned int i, n = remote_chain_depth;

	if (!n)
		return;
	for (i = 0; i < n; i++) {
		struct kd_cs_state expected = {};
		unsigned long j, count = deep_completed[i];
		bool valid = count <= KD_CS_VERIFY_LIMIT &&
			     deep_states[i].sequence == count;

		if (valid)
			for (j = 0; j < count; j++)
				kd_cs_transition(&expected);
		valid &= !memcmp(&deep_states[i], &expected, sizeof(expected));
		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep state: index=%u operations=%lu valid=%u\n", i,
			count, valid);
	}
	for (i = 0; i <= n; i++) {
		int queued = kd_spin_debug_waiter_count(&deep_locks[i].rlock);
		unsigned int inside = atomic_read(&deep_inside[i]);
		u32 word = atomic_read(&deep_locks[i].rlock.raw_lock.val);
		unsigned long owner = kd_spin_debug_owner(&deep_locks[i].rlock);
		bool valid = !inside && !word && !owner &&
			     (!queued || (i == n && queued == -ENOSPC));

		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep drain: index=%u inside=%u word=%x owner=%lx queued=%d valid=%u\n",
			i, inside, word, owner, queued, valid);
	}
	if (deep_prefix != 1 || deep_suffix != 1 || deep_observed != 1 ||
	    deep_requests != 2 || deep_checked != deep_requests)
		atomic_inc(&deep_failures);
	if (remote_chain_readmit) {
		bool valid = remote_chain_readmit_ready;
		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep readmit: ready=%u valid=%u\n",
			remote_chain_readmit_ready, valid);
	}
	if (remote_chain_defer) {
		unsigned int acquired = 0, returned = 0;
		bool valid = remote_chain_defer_ready;

		for (i = 0; i <= remote_chain_defer_count; i++) {
			valid &= deep_follower_acquired[i] == 1 &&
				 deep_follower_returned[i] == 1;
			acquired += deep_follower_acquired[i];
			returned += deep_follower_returned[i];
		}
		if (!valid)
			atomic_inc(&deep_failures);
		pr_info("kd_deep deferred: layer=%u ready=%u followers=%u acquired=%u returned=%u valid=%u\n",
			remote_chain_defer - 1, remote_chain_defer_ready,
			remote_chain_defer_count + 1, acquired, returned,
			valid);
	}
	pr_info("kd_deep summary: depth=%u stage=%u reverse=%u requests=%u checked=%u prefix=%u suffix=%u observed=%u failures=%d abort=%u\n",
		n, remote_chain_stage, remote_chain_reverse, deep_requests,
		deep_checked, deep_prefix, deep_suffix, deep_observed,
		atomic_read(&deep_failures), deep_abort);
}
