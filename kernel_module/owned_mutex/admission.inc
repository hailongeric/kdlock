// SPDX-License-Identifier: GPL-2.0
/*
 * Included by kd_hotlock.c. Owned objects have an independent exact-key heat
 * history; these observations never grant ownership or retire queued work.
 */
struct kd_owned_hotlock_cpu {
	struct kd_hotlock_table table;
	unsigned int hot;
};
static struct kd_owned_hotlock_cpu __percpu *kd_owned_heat;
DEFINE_PER_CPU(unsigned long, kd_hotlock_owned_mutex_entries);
EXPORT_PER_CPU_SYMBOL_GPL(kd_hotlock_owned_mutex_entries);
static DEFINE_PER_CPU(unsigned long, kd_owned_contentions);
static unsigned int owned_mutex_entry_ratio_limit = 256;
module_param(owned_mutex_entry_ratio_limit, uint, 0444);
MODULE_PARM_DESC(owned_mutex_entry_ratio_limit,
		 "Owned mutex exclusive entry ratio; power of two from 2 through 256");

bool kd_hotlock_record_owned_mutex_pinned(unsigned long address)
{
	struct kd_owned_hotlock_cpu *cpu = this_cpu_ptr(kd_owned_heat);
	struct kd_hotlock_table *t = &cpu->table;
	struct kd_hotlock_entry *slot;
	unsigned long now = 0;
	bool admitted = false;

	this_cpu_inc(kd_owned_contentions);
	if (!cpu->hot && this_cpu_read(kd_owned_contentions) < KD_HOTLOCK_CHECK_INTERVAL)
		return false;
	if (!kd_hotlock_try_enter(t))
		return false;
	t->rate_samples = this_cpu_read(kd_owned_contentions);
	if (t->rate_samples >= KD_HOTLOCK_CHECK_INTERVAL) {
		bool was_hot = cpu->hot;
		bool ratio = (this_cpu_read(kd_hotlock_owned_mutex_entries) >>
			      10) <
			owned_mutex_entry_ratio_limit;
		unsigned int i;

		this_cpu_write(kd_hotlock_owned_mutex_entries, 0);
		this_cpu_write(kd_owned_contentions, 0);
		now = rdtsc_ordered();
		cpu->hot = ratio && now >= t->rate_begin &&
			   now - t->rate_begin < KD_HOTLOCK_CPU_WINDOW;
		t->rate_begin = now;
		t->rate_samples = 0;
		if (!was_hot || !cpu->hot)
			for (i = 0; i < t->used; i++) {
				t->entries[i].begin = now;
				t->entries[i].count = 0;
				t->entries[i].hot = false;
			}
	}
	if (!cpu->hot)
		goto out;
	slot = kd_hotlock_find(t, address);
	if (!slot)
		slot = kd_hotlock_insert(t, address);
	if (!slot)
		goto out;
	if (++slot->count >= KD_HOTLOCK_SAMPLE_TARGET + 1U) {
		if (t->rate_samples)
			now = rdtsc_ordered();
		slot->hot = now >= slot->begin &&
			    now - slot->begin < KD_HOTLOCK_INITIAL_WINDOW;
		slot->begin = now;
		slot->count = 0;
	}
	admitted = slot->hot;
out:
	barrier();
	WRITE_ONCE(t->busy, 0);
	return admitted;
}

static int kd_owned_hotlock_init(void)
{
	unsigned long now;
	int cpu;

	if (owned_mutex_entry_ratio_limit < 2 ||
	    owned_mutex_entry_ratio_limit > 256 ||
	    (owned_mutex_entry_ratio_limit &
	     (owned_mutex_entry_ratio_limit - 1)))
		return -EINVAL;
	kd_owned_heat = alloc_percpu(struct kd_owned_hotlock_cpu);
	if (!kd_owned_heat)
		return -ENOMEM;
	now = rdtsc_ordered();
	for_each_possible_cpu(cpu) {
		struct kd_owned_hotlock_cpu *local =
			per_cpu_ptr(kd_owned_heat, cpu);

		memset(local, 0, sizeof(*local));
		local->table.rate_begin = now;
		per_cpu(kd_hotlock_owned_mutex_entries, cpu) = 0;
		per_cpu(kd_owned_contentions, cpu) = 0;
	}
	return 0;
}

static void kd_owned_hotlock_exit(void)
{
	int cpu;
	unsigned int i;

	if (hotlock_stats && kd_owned_heat)
		for_each_possible_cpu(cpu) {
			struct kd_owned_hotlock_cpu *local =
				per_cpu_ptr(kd_owned_heat, cpu);

			for (i = 0; i < local->table.used; i++) {
				struct kd_hotlock_entry *slot =
					&local->table.entries[i];

				pr_info("kd_hotlock owned: cpu=%d address=%lx count=%u cpu_hot=%u lock_hot=%u entry_ratio_limit=%u role=DONE\n",
					cpu, slot->address, slot->count,
					local->hot, slot->hot,
					owned_mutex_entry_ratio_limit);
			}
		}
	free_percpu(kd_owned_heat);
	kd_owned_heat = NULL;
}
