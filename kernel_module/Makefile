# Guest-only external-module build against the captured running kernel.
# This compiles kdlock, not the guest kernel; SELFTEST is an explicit opt-in.
# kd_spin_runtime.c combines spin, mutex and shared execution implementations;
# Kbuild tracks their C/.inc dependencies. Do not link them a second time.
obj-m += kdlock_km.o

ccflags-y += -I$(src)/../include

# Private-state kernel regressions are absent from normal builds.
ifeq ($(KDLOCK_SELFTEST),1)
ccflags-y += -DKDLOCK_SELFTEST
endif

# Bounded NUMA batching; explicit overrides support matched measurements.
KDLOCK_NUMA ?= 1
KDLOCK_SPIN_BATCH ?= 1024
ccflags-y += -DKDLOCK_SPIN_BATCH=$(KDLOCK_SPIN_BATCH)
# Independent mutex policy; explicit overrides support matched comparisons.
KDLOCK_MUTEX_BATCH ?= 1024
KDLOCK_MUTEX_NUMA_BOUNDARY ?= 1024
ccflags-y += -DKDLOCK_MUTEX_BATCH=$(KDLOCK_MUTEX_BATCH)
ccflags-y += -DKDLOCK_MUTEX_NUMA_BOUNDARY=$(KDLOCK_MUTEX_NUMA_BOUNDARY)
# Initial delegated-waiter pin budget; a small override forces expiry tests.
KDLOCK_MUTEX_SPIN_BUDGET ?= 65536
ccflags-y += -DKDLOCK_MUTEX_SPIN_BUDGET=$(KDLOCK_MUTEX_SPIN_BUDGET)
# Optional observations are compiled out of ordinary timing builds.
KDLOCK_MUTEX_DIAGNOSTICS ?= 0
ccflags-y += -DKDLOCK_MUTEX_DIAGNOSTICS=$(KDLOCK_MUTEX_DIAGNOSTICS)
KDLOCK_MUTEX_PIN_TSC_SHIFT ?= 0
ccflags-y += -DKDLOCK_MUTEX_PIN_TSC_SHIFT=$(KDLOCK_MUTEX_PIN_TSC_SHIFT)
ifeq ($(KDLOCK_NUMA),1)
ccflags-y += -DNUMA_AWARE
endif

kdlock_km-objs := \
	kd_main.o \
	kd_lock.o \
	kd_hotlock.o \
	sys.o \
	kd_spin_runtime.o \
	kd_source.o \
	kd_spin_entry.o \
	kd_mutex_tasks.o \
	kd_mutex_local.o \
	kd_mutex_osq.o \
	kd_rwsem.o \
	kd_rwsem_api.o

OBJECT_FILES_NON_STANDARD_kd_spin_runtime.o := y

KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
