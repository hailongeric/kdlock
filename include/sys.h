#ifndef SYS_H
#define SYS_H

#include <linux/cdev.h>

void sys_init(void);
void sys_exit(void);

struct nf_dev {
    struct cdev cdev;
    // struct semaphore sem;
};

#endif