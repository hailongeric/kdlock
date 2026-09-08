obj-m += kdlock_km.o

ccflags-y += -I$(src)/../include

# Private-state kernel regressions are absent from normal builds.
ifeq ($(KDLOCK_SELFTEST),1)
ccflags-y += -DKDLOCK_SELFTEST
endif

# Opt-in existing NUMA queue selection; ordinary builds keep the prior protocol.
ifeq ($(KDLOCK_NUMA),1)
ccflags-y += -DNUMA_AWARE
endif

kdlock_km-objs := \
	kd_main.o \
	kd_lock.o \
	kd_hotlock.o \
	sys.o \
	exe.o \
	kd_exec.o \
	kd_spinlock.o \
	kd_spin_gate.o \
	kd_spin_entry.o \
	kd_mutex.o \
	kd_mutex_tasks.o

OBJECT_FILES_NON_STANDARD_kd_spinlock.o := y

KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
