# Build only in the recovery VM. One provider per artifact; Native is common.
MF_TC_BUILD ?= 0
ifneq ($(KERNELRELEASE),)
obj-m := kd_mmap_fault.o
kd_mmap_fault-objs := mapping.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE) -I$(TCLOCK_INCLUDE) -DMF_TC_BUILD=$(MF_TC_BUILD)
else
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
endif
