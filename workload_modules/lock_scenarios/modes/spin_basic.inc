/*
 * Single, nested, deep and out-of-order spin critical sections (modes 0/1/6/7).
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* Exercise the same hook/JIT entry with both incoming IRQ states. The saved
 * flags live in the original caller frame and must survive delegated calls. */
static bool spin_irq_off;
module_param(spin_irq_off, bool, 0644);
MODULE_PARM_DESC(spin_irq_off, "mode 0: mask IRQs around the spin pair and verify restoration");

static void run_contention_test(unsigned long loop_count,
				unsigned long work_load)
{
	unsigned long i, j;
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		struct kd_resume_record *record = kd_resume_begin();
		unsigned long flags = 0;
		bool mask_irq = READ_ONCE(spin_irq_off);

		if (mask_irq)
			local_irq_save(flags);
		spin_lock(&global_lock);
		kd_spin_oracle_enter();
		kd_cs_step(KD_CS_SPIN_GLOBAL);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		kd_resume_probe(record, 1);
		atomic_dec(&spin_inside);
		spin_unlock(&global_lock);
		kd_spin_check_context(count, irq || mask_irq);
		if (mask_irq)
			local_irq_restore(flags);
		kd_spin_check_context(count, irq);
		if (native_resume_rename)
			kd_test_rename("klock_test");
	}
}

static void kd_acquired_spin_prepare(struct kd_resume_record *record,
				     unsigned int role);
static void kd_acquired_spin_observe(struct kd_resume_record *record);
static void kd_acquired_spin_finish(struct kd_resume_record *record);
static void kd_acquired_spin_role(unsigned int role);
static unsigned int acquired_prefix;

static void run_nested_spinlock_test(unsigned long loop_count,
				     unsigned long work_load, unsigned int role)
{
	unsigned long i, j;
	unsigned int count = preempt_count();
	bool irq = irqs_disabled();
	volatile int dummy_computation = 0;

	if (native_acquired_queue && (role & MODE_ROLE_SYNCHRONIZED) &&
	    (role & ~MODE_ROLE_SYNCHRONIZED)) {
		kd_acquired_spin_role(role & ~MODE_ROLE_SYNCHRONIZED);
		return;
	}
	if (READ_ONCE(spin_ooo_dependency) && (role & MODE_ROLE_SYNCHRONIZED) &&
	    (role & ~MODE_ROLE_SYNCHRONIZED)) {
		kd_ooo_spin_role(role & ~MODE_ROLE_SYNCHRONIZED);
		return;
	}

	for (i = 0; i < loop_count; i++) {
		struct kd_resume_record *record = kd_resume_begin();

		kd_ooo_spin_prepare(record);
		kd_acquired_spin_prepare(record, role);
		spin_lock(&nested_lock_a);
		/* A translated prefix detects replay across B without duplicating
		 * B's complex state machine and its bounded admission workload.
		 * Scheduling barriers stay outside this shared acquisition site. */
		if (native_acquired_queue && (role & MODE_ROLE_SYNCHRONIZED)) {
			WRITE_ONCE(acquired_prefix,
				   READ_ONCE(acquired_prefix) + 1);
		}
		kd_resume_before_pending_lock(record);
		spin_lock(&nested_lock_b);
		kd_resume_after_pending_lock(record);
		if (native_acquired_queue && (role & MODE_ROLE_SYNCHRONIZED))
			kd_acquired_spin_observe(record);

		kd_cs_step(KD_CS_SPIN_B);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		if (READ_ONCE(native_resume_ooo) == 3 && record) {
			kd_ooo_pending_spin_enter(record);
			kd_resume_probe(record, 3);
			kd_ooo_checkpoint(record, false, 1);
			kd_cs_step(KD_CS_SPIN_B);
			kd_ooo_pending_spin_leave();
			spin_unlock(&nested_lock_b);
			kd_ooo_checkpoint(record, false, 2);
			goto nested_spin_done;
		}
		if (READ_ONCE(native_resume_ooo) == 2 && record) {
			kd_ooo_jit_prefix(record);
			spin_unlock(&nested_lock_a);
			kd_resume_probe(record, 3);
			goto spin_ooo_after_a;
		}
		kd_resume_probe(record, 3);
		if (READ_ONCE(native_resume_ooo) == 1) {
			kd_ooo_checkpoint(record, false, 0);
			spin_unlock(&nested_lock_a);
spin_ooo_after_a:
			kd_ooo_checkpoint(record, false, 1);
			kd_cs_step(KD_CS_SPIN_B);
			spin_unlock(&nested_lock_b);
			kd_ooo_checkpoint(record, false, 2);
			goto nested_spin_done;
		}
		spin_unlock(&nested_lock_b);
		kd_resume_probe(record, 2);
		spin_unlock(&nested_lock_a);
nested_spin_done:
		kd_spin_check_context(count, irq);
		if (native_acquired_queue && (role & MODE_ROLE_SYNCHRONIZED))
			kd_acquired_spin_finish(record);
		if (native_resume_rename)
			kd_test_rename("klock_test");
	}
}

static void run_deep_nested_spinlock_test(unsigned long loop_count,
					  unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);
		spin_lock(&nested_lock_c);

		kd_cs_step(KD_CS_SPIN_C);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&nested_lock_c);
		spin_unlock(&nested_lock_b);
		spin_unlock(&nested_lock_a);
	}
}

static void run_ooo_nested_spinlock_test(unsigned long loop_count,
					 unsigned long work_load)
{
	unsigned long i, j;
	volatile int dummy_computation = 0;

	for (i = 0; i < loop_count; i++) {
		spin_lock(&nested_lock_a);
		spin_lock(&nested_lock_b);

		kd_cs_step(KD_CS_SPIN_B);
		for (j = 0; j < work_load; j++)
			dummy_computation++;

		spin_unlock(&nested_lock_a);
		spin_unlock(&nested_lock_b);
	}
}
