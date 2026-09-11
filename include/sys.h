#ifndef SYS_H
#define SYS_H

/* Character-device setup/teardown; source leases and upload checks live in
 * sys.c. Call only at provider lifecycle boundaries, not from a lock hook. */
int kd_sys_init(void);
void kd_sys_exit(void);

#endif
