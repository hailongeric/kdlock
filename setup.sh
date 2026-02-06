#!/bin/bash

insmod ./klock_module/klock_module.ko
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
# sudo touch /tmp/nf_iva
