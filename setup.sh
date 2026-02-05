#!/bin/bash

insmod ./kernel_lock_module/lock_module.ko
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
# sudo touch /tmp/nf_iva
