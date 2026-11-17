# Build locktorture, torture and test-ww_mutex from the 7.0 source as external modules for kdclaude1.
set -e
D=/root/kdc_torture; rm -rf $D; mkdir -p $D
S=/mnt/kdlock-builds/kdc/src
cp $S/kernel/locking/locktorture.c $S/kernel/locking/test-ww_mutex.c $S/kernel/torture.c $D/
grep -n '#include "' $D/*.c || true
cat > $D/setaff.c <<'C'
// Stand-in for torture_sched_setaffinity(), which kdclaude1's configuration does not build.
#include <linux/sched.h>
#include <linux/pid.h>
#include <linux/cpumask.h>
#include <linux/sched/task.h>
long ext_torture_sched_setaffinity(pid_t pid, const struct cpumask *in_mask, bool dowarn);
long ext_torture_sched_setaffinity(pid_t pid, const struct cpumask *in_mask, bool dowarn)
{
	/* locktorture binds only the calling kthread (pid 0). */
	if (pid)
		return -EINVAL;
	return set_cpus_allowed_ptr(current, in_mask);
}
C
cat > $D/Kbuild <<'K'
obj-m := torture.o locktorture_ext.o test-ww_mutex.o
locktorture_ext-y := locktorture.o setaff.o
ccflags-y += -I$(srctree)/kernel -Dtorture_sched_setaffinity=ext_torture_sched_setaffinity
K
make -C /mnt/kdlock-builds/kdc/out M=$D modules 2>&1 | grep -E "error|warning|undefined|WARNING" | head -20
ls $D/*.ko
