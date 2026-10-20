# Separate mutex translation unit; payload/timing helpers are shared sources.
SC_LIST_NODES ?= 16
ifneq ($(KERNELRELEASE),)
obj-m := mutex_cacheline.o
mutex_cacheline-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(SC_SHARED) -I$(TCLOCK_INCLUDE)
ifeq ($(SC_WORKLOAD),rcuht)
ccflags-y += -DSC_HASH_PAYLOAD
endif
ifneq ($(filter list list-prefetch,$(SC_WORKLOAD)),)
ccflags-y += -DSC_LIST_PAYLOAD -DSC_LIST_NODES=$(SC_LIST_NODES)
ccflags-y += -DSC_LIST_PREFETCH=$(if $(filter list-prefetch,$(SC_WORKLOAD)),1,0)
endif
ifeq ($(SC_BACKEND),kdlock)
ccflags-y += -DSC_DIRECT_KDLOCK -I$(KDLOCK_INCLUDE)
ifeq ($(SC_MUTEX_API),public)
ccflags-y += -DSC_MUTEX_PUBLIC_API
else ifneq ($(filter-out outer,$(SC_MUTEX_API)),)
$(error SC_MUTEX_API must be outer or public)
endif
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
