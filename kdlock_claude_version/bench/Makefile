# SPDX-License-Identifier: GPL-2.0
# Out-of-tree module against a kernel built with CONFIG_KDLOCK=y.
#   make -C <kernel build dir> M=$PWD modules
ccflags-y += -I$(src)/../include
obj-m += kd_bench.o
