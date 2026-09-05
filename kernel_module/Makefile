obj-m += kdlock_km.o

ccflags-y += -I$(src)/../include

kdlock_km-objs := \
	kd_main.o \
	kd_lock.o \
	kd_hotlock.o \
	sys.o \
	exe.o \
	kd_exec.o \
	kd_spinlock.o \
	kd_mutex.o \
	kd_mutex_tasks.o

OBJECT_FILES_NON_STANDARD_kd_spinlock.o := y

KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
