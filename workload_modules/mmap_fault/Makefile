# Build only in the recovery VM. Both providers are explicit module dependencies.
ifneq ($(KERNELRELEASE),)
obj-m := kd_mmap_fault.o
kd_mmap_fault-objs := mapping.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE) -I$(TCLOCK_INCLUDE)
else
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
endif
