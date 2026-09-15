// SPDX-License-Identifier: GPL-2.0
/* Non-target peers use only Linux B. They must remain excluded while two
 * delegated native frames retain their physical owners, then make progress
 * as each owner releases B. No queue words, frames or task refs are fabricated.
 */
static struct kd_parallel_peer {
	struct task_struct *task;
	unsigned long before_owner, value;
	pid_t pid;
	unsigned int acquired, released, cancelled, ready;
	atomic_t claimed;
} parallel_peers[2];

static bool kd_parallel_peer_queued(unsigned int index, unsigned int attempt)
{
	struct kd_parallel_peer *peer = &parallel_peers[index];
	struct kd_parallel_lane *lane = &parallel_lanes[index];
	struct mutex_waiter *waiter;
	unsigned long flags, owner;
	unsigned int count = 0, matched = 0;
	bool valid;

	if (smp_load_acquire(&peer->ready) != attempt)
		return false;
	raw_spin_lock_irqsave(&lane->b.wait_lock, flags);
	owner = kd_test_mutex_owner(&lane->b);
	list_for_each_entry(waiter, &lane->b.wait_list, list) {
		count++;
		matched += waiter->task == peer->task;
	}
	raw_spin_unlock_irqrestore(&lane->b.wait_lock, flags);
	if (!matched)
		return false;
	valid = count == 1 && matched == 1 && !READ_ONCE(peer->acquired) &&
		READ_ONCE(peer->cancelled) == attempt - 1 && owner &&
		owner == peer->before_owner &&
		owner == lane->records[KD_PAR_WAITER].owner &&
		!lane->records[KD_PAR_WAITER].called &&
		!lane->records[KD_PAR_WAITER].after;
	kd_parallel_check(valid, index, "native-peer-queue");
	pr_info("kd_parallel peer queued: lane=%u attempt=%u task=%d waiter=%lx lock=%lx owner=%lx queued=%u matched=%u valid=%u\n",
		index, attempt, peer->pid, (unsigned long)peer->task,
		(unsigned long)&lane->b, owner, count, matched, valid);
	return true;
}

static int kd_parallel_peer_run(unsigned long loops, unsigned int index)
{
	struct kd_parallel_peer *peer;
	struct kd_parallel_lane *lane, *other;
	unsigned long owner, other_owner;
	unsigned int cross_try = 2, attempt = 1;
	int ret;
	bool first, valid;

	if (!mutex_parallel_peers || !mutex_parallel_armed ||
	    !READ_ONCE(mutex_parallel_source_hold) ||
	    (index == 2 ? (loops < 1 || loops > 2) : loops != 1) ||
	    atomic_read_acquire(&parallel_arrived) != 3 ||
	    strcmp(current->comm, "kd_native"))
		return -EINVAL;
	if (index == 2) {
		unsigned long deadline = jiffies + 10 * HZ;
		unsigned int observed = 0, i;

		/* For the observer only, loops selects the initial/retry snapshot.
		 * Each must see a real Linux wait_list before either frame resumes;
		 * a pre-CALL flag or an old first-attempt observation is insufficient. */
		while (observed != 3) {
			for (i = 0; i < 2; i++)
				if (!(observed & BIT(i)) &&
				    kd_parallel_peer_queued(i, loops))
					observed |= BIT(i);
			if (time_after_eq(jiffies, deadline)) {
				kd_parallel_check(false, 0,
						  "native-peer-timeout");
				break;
			}
			usleep_range(100, 200);
		}
		return atomic_read(&parallel_failures) ? -EINVAL : 0;
	}
	if (index >= ARRAY_SIZE(parallel_peers))
		return -EINVAL;
	peer = &parallel_peers[index];
	lane = &parallel_lanes[index];
	other = &parallel_lanes[1 - index];
	if (atomic_cmpxchg(&peer->claimed, 0, 1)) {
		/* Retry is a new userspace ioctl from this exact surviving caller,
		 * not an automatic retry that hides EINTR or a replacement task. */
		if (peer->task != current || peer->pid != current->pid ||
		    READ_ONCE(peer->cancelled) != 1 ||
		    atomic_cmpxchg(&peer->claimed, 1, 2) != 1)
			return -EALREADY;
		attempt = 2;
	} else {
		peer->task = current;
		peer->pid = current->pid;
		peer->before_owner = kd_test_mutex_owner(&lane->b);
	}
	valid = peer->before_owner &&
		peer->before_owner == kd_test_mutex_owner(&lane->b) &&
		peer->before_owner == lane->records[KD_PAR_WAITER].owner &&
		peer->before_owner != (unsigned long)current;
	if (mutex_trylock(&lane->b)) {
		mutex_unlock(&lane->b);
		valid = false;
	}
	if (!kd_parallel_check(valid, index, "native-peer-try"))
		return -EINVAL;
	pr_info("kd_parallel peer try: lane=%u attempt=%u task=%d waiter=%lx lock=%lx owner=%lx result=0 comm=%s valid=1\n",
		index, attempt, peer->pid, (unsigned long)current,
		(unsigned long)&lane->b, peer->before_owner, current->comm);
	smp_store_release(&peer->ready, attempt);
	if (attempt == 1) {
		struct mutex_waiter *waiter;
		unsigned long flags;
		unsigned int queued = 0, matched = 0;

		/* Only a native B wait is cancellable. Never cancel either retained
		 * kdlock frame or flush the signal to fake a userspace return. */
		ret = mutex_lock_interruptible(&lane->b);
		if (!ret)
			mutex_unlock(&lane->b);
		raw_spin_lock_irqsave(&lane->b.wait_lock, flags);
		owner = kd_test_mutex_owner(&lane->b);
		list_for_each_entry(waiter, &lane->b.wait_list, list) {
			queued++;
			matched += waiter->task == current;
		}
		raw_spin_unlock_irqrestore(&lane->b.wait_lock, flags);
		other_owner = kd_test_mutex_owner(&other->b);
		valid = ret == -EINTR && signal_pending(current) &&
			!fatal_signal_pending(current) && !queued && !matched &&
			!preempt_count() && !irqs_disabled() &&
			owner == peer->before_owner &&
			kd_test_mutex_owner(&lane->a) == owner && other_owner &&
			other_owner == other->records[KD_PAR_WAITER].owner &&
			kd_test_mutex_owner(&other->a) == other_owner &&
			!lane->records[KD_PAR_WAITER].called &&
			!other->records[KD_PAR_WAITER].called &&
			!peer->cancelled && !peer->acquired && !peer->released;
		kd_parallel_check(valid, index, "native-peer-cancel");
		peer->cancelled++;
		smp_store_release(&peer->ready, 0);
		pr_info("kd_parallel peer cancelled: lane=%u task=%d waiter=%lx lock=%lx owner=%lx other_owner=%lx error=%d pending=%u fatal=%u queued=%u matched=%u cancelled=%u acquired=%u released=%u valid=%u\n",
			index, peer->pid, (unsigned long)current,
			(unsigned long)&lane->b, owner, other_owner, -ret,
			signal_pending(current), fatal_signal_pending(current),
			queued, matched, peer->cancelled, peer->acquired,
			peer->released, valid);
		return valid ? ret : -EINVAL;
	}
	mutex_lock(&lane->b);
	owner = kd_test_mutex_owner(&lane->b);
	first = index == mutex_parallel_first;
	other_owner = kd_test_mutex_owner(&other->b);
	valid = owner == (unsigned long)current && !preempt_count() &&
		!irqs_disabled() && !peer->acquired && !peer->released;
	if (first) {
		/* B0 being available must not make retained B1 available. This
		 * second native trylock executes while the peer really holds B0. */
		cross_try = mutex_trylock(&other->b);
		if (cross_try)
			mutex_unlock(&other->b);
		valid &= !cross_try && other_owner &&
			 other_owner == other->records[KD_PAR_WAITER].owner &&
			 !other->records[KD_PAR_WAITER].called &&
			 !other->records[KD_PAR_WAITER].after;
	} else {
		valid &= (atomic_read_acquire(&parallel_peer_done) &
			  BIT(mutex_parallel_first)) &&
			 (atomic_read_acquire(&parallel_done) &
			  BIT(mutex_parallel_first));
	}
	peer->acquired++;
	peer->value = ((0x700UL + index) * 33 + 17) ^ 0x5a5a;
	kd_parallel_check(valid, index, "native-peer-acquire");
	pr_info("kd_parallel peer acquired: lane=%u task=%d waiter=%lx lock=%lx owner=%lx other=%lx other_owner=%lx cross_try=%u value=%lx valid=%u\n",
		index, peer->pid, (unsigned long)current,
		(unsigned long)&lane->b, owner, (unsigned long)&other->b,
		other_owner, cross_try, peer->value, valid);
	mutex_unlock(&lane->b);
	peer->released++;
	pr_info("kd_parallel peer released: lane=%u task=%d acquired=%u released=%u value=%lx valid=%u\n",
		index, peer->pid, peer->acquired, peer->released, peer->value,
		valid);
	/* The second original waiter may now recheck its retained owners. No
	 * dereference of peer->task is permitted after this caller exits. */
	atomic_fetch_or(BIT(index), &parallel_peer_done);
	return atomic_read(&parallel_failures) ? -EINVAL : 0;
}

static void kd_parallel_peer_report(void)
{
	unsigned int i;
	bool valid = atomic_read(&parallel_peer_done) == 3;

	if (!mutex_parallel_peers)
		return;
	for (i = 0; i < 2; i++)
		valid &= parallel_peers[i].ready == 2 &&
			 parallel_peers[i].cancelled == 1 &&
			 parallel_peers[i].acquired == 1 &&
			 parallel_peers[i].released == 1;
	kd_parallel_check(valid, 0, "native-peer-final");
	pr_info("kd_parallel peer stats: completed=%u acquired=%u released=%u cancelled=%u valid=%u\n",
		atomic_read(&parallel_peer_done),
		parallel_peers[0].acquired + parallel_peers[1].acquired,
		parallel_peers[0].released + parallel_peers[1].released,
		parallel_peers[0].cancelled + parallel_peers[1].cancelled,
		valid);
}
