# Separate mutex translation unit; payload/timing helpers are shared sources.
ifneq ($(KERNELRELEASE),)
obj-m := mutex_cacheline.o
mutex_cacheline-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(SC_SHARED) -I$(TCLOCK_INCLUDE)
ifneq ($(SC_SCENARIO),)
ccflags-y += -DSC_SCENARIO=$(SC_SCENARIO)
endif
ifeq ($(SC_WORKLOAD),rcuht)
ccflags-y += -DSC_HASH_PAYLOAD
endif
ifeq ($(SC_BACKEND),kdlock)
ccflags-y += -DSC_DIRECT_KDLOCK -I$(KDLOCK_INCLUDE)
ifeq ($(SC_MUTEX_OWNED),1)
ccflags-y += -DSC_MUTEX_OWNED
ifeq ($(SC_OWNED_MUTEX_CABI),1)
ccflags-y += -DKD_OWNED_MUTEX_CABI=1
endif
ifeq ($(SC_OWNED_MUTEX_PREFLIGHT),1)
ccflags-y += -DKD_OWNED_MUTEX_PREFLIGHT=1
endif
endif
else ifeq ($(SC_BACKEND),tclock)
ccflags-y += -DSC_DIRECT_TCLOCK
else ifeq ($(SC_BACKEND),native)
ccflags-y += -DSC_DIRECT_NATIVE
endif
ifeq ($(SC_MUTEX_OWNED),1)
ifneq ($(SC_BACKEND),kdlock)
$(error SC_MUTEX_OWNED requires SC_BACKEND=kdlock)
endif
ifeq ($(SC_WORKLOAD),rcuht)
$(error owned-v1 is limited to the c01 cacheline workload)
endif
endif
ifeq ($(SC_OWNED_MUTEX_PREFLIGHT),1)
ifneq ($(SC_MUTEX_OWNED),1)
$(error SC_OWNED_MUTEX_PREFLIGHT requires SC_MUTEX_OWNED=1)
endif
endif
ifeq ($(SC_OWNED_MUTEX_CABI),1)
ifneq ($(SC_MUTEX_OWNED),1)
$(error SC_OWNED_MUTEX_CABI requires SC_MUTEX_OWNED=1)
endif
ifeq ($(SC_OWNED_MUTEX_PREFLIGHT),1)
$(error SC_OWNED_MUTEX_CABI and SC_OWNED_MUTEX_PREFLIGHT are mutually exclusive)
endif
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
