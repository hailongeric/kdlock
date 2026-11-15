# SPDX-License-Identifier: GPL-2.0
#
# kdlock core. Built into the kernel (never a module): the locks are used
# from early boot, and generated code addresses kd_cpu with a 32-bit
# %gs-relative displacement, which only built-in per-CPU data permits.
#
# Place this directory at kernel/locking/kdlock/ and the public headers at
# include/kdlock/; see ../integration/README.md.

ccflags-y += -I$(src)

obj-$(CONFIG_KDLOCK) += kd_entry.o kd_core.o kd_spinlock.o kd_rwlock.o \
			kd_mutex.o kd_ww_mutex.o kd_rwsem.o kd_image.o kd_dev.o
obj-$(CONFIG_KDLOCK_MM) += kd_mm.o
obj-$(CONFIG_KDLOCK_API) += kd_sw.o

# The wait and session paths run on a per-CPU stack and on other tasks'
# stacks; keep instrumentation that assumes the task stack out of them.
KASAN_SANITIZE := n
KCSAN_SANITIZE := n
UBSAN_SANITIZE := n
KCOV_INSTRUMENT := n
CFLAGS_REMOVE_kd_core.o = $(CC_FLAGS_FTRACE)
CFLAGS_REMOVE_kd_spinlock.o = $(CC_FLAGS_FTRACE)
CFLAGS_REMOVE_kd_rwlock.o = $(CC_FLAGS_FTRACE)
CFLAGS_REMOVE_kd_mutex.o = $(CC_FLAGS_FTRACE)
CFLAGS_REMOVE_kd_rwsem.o = $(CC_FLAGS_FTRACE)
CFLAGS_REMOVE_kd_ww_mutex.o = $(CC_FLAGS_FTRACE)
