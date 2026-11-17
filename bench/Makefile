# SPDX-License-Identifier: GPL-2.0
# Out-of-tree module against a kernel built with CONFIG_KDLOCK=y.
#   make -C <kernel build dir> M=$PWD modules
# With the original TCLock locks as a third backend (the four tclock_backend
# modules, built against the same kernel, must be loaded first):
#   make -C <kernel build dir> M=$PWD KDB_TCLOCK=1 TCLOCK_DIR=<tclock_backend> \
#        KBUILD_EXTRA_SYMBOLS="<each TCLock module's Module.symvers>" modules
ccflags-y += -I$(src)/../include
ifeq ($(KDB_TCLOCK),1)
ccflags-y += -DKDB_WITH_TCLOCK -I$(TCLOCK_DIR)/include
endif
obj-m += kd_bench.o
