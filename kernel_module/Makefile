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
	kd_mutex_tasks.o

OBJECT_FILES_NON_STANDARD_kd_spin_runtime.o := y

KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
