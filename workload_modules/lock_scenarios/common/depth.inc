/*
 * Learned deep-mutex callee used by the bounded lock-depth workload.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

/* A normal missing CALL is learned first. With its caller's A still held,
 * seven acquisitions fill the frame; the eighth must fail before acquisition
 * and continue natively with the prior seven children still owned by A's owner.
 * Keep the calls explicit so the fixture does not depend on loop inference.
 * Keep this a real CALL in both builds. The optional source needs two learned
 * levels, including saved-register reloads across checked mutex controls and
 * the external helper's translated RET; inlining would bypass that contract. */
static __attribute__((noipa)) noinline void
kd_resume_depth_mutex(struct kd_resume_record *record)
{
	if (!record)
		return;
#ifdef KDLOCK_SOURCE_HELPER
	/* Learn the cross-module CALL before the capacity wave. Moving only this
	 * prefix keeps the native owner/record oracle in the original module. */
	kd_depth_source_enter(resume_depth_locks);
#else
	mutex_lock(&resume_depth_locks[0]);
	mutex_lock(&resume_depth_locks[1]);
	mutex_lock(&resume_depth_locks[2]);
	mutex_lock(&resume_depth_locks[3]);
	mutex_lock(&resume_depth_locks[4]);
	mutex_lock(&resume_depth_locks[5]);
	mutex_lock(&resume_depth_locks[6]);
#endif
	record->before++;
	record->value *= 3;
	mutex_lock(&resume_depth_locks[7]);
	kd_resume_native_probe(record);
	record->after++;
	record->value ^= 0x5a5a;
	kd_cs_step(KD_CS_MUTEX_B);
	mutex_unlock(&resume_depth_locks[7]);
	mutex_unlock(&resume_depth_locks[6]);
	mutex_unlock(&resume_depth_locks[5]);
	mutex_unlock(&resume_depth_locks[4]);
	mutex_unlock(&resume_depth_locks[3]);
	mutex_unlock(&resume_depth_locks[2]);
	mutex_unlock(&resume_depth_locks[1]);
	mutex_unlock(&resume_depth_locks[0]);
}
