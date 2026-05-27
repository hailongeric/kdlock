#ifndef SYS_H
#define SYS_H

#include <linux/cdev.h>

void kd_sys_init(void);
void kd_sys_exit(void);

struct kd_dev {
	struct cdev cdev;
};

#endif