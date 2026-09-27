# Separate mutex translation unit; payload/timing helpers are shared sources.
ifneq ($(KERNELRELEASE),)
obj-m := mutex_cacheline.o
mutex_cacheline-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(SC_SHARED) -I$(TCLOCK_INCLUDE)
ifeq ($(SC_WORKLOAD),rcuht)
ccflags-y += -DSC_HASH_PAYLOAD
endif
ifeq ($(SC_BACKEND),kdlock)
ccflags-y += -DSC_DIRECT_KDLOCK -I$(KDLOCK_INCLUDE)
else ifeq ($(SC_BACKEND),tclock)
ccflags-y += -DSC_DIRECT_TCLOCK
else ifeq ($(SC_BACKEND),native)
ccflags-y += -DSC_DIRECT_NATIVE
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
SC_SHARED ?= $(abspath ../spin_cacheline)
TCLOCK_INCLUDE ?= $(abspath ../../tclock_backend/include)
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 SC_SHARED=$(SC_SHARED) TCLOCK_INCLUDE=$(TCLOCK_INCLUDE) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
