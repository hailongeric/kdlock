# Independent guest workload: no kdlock symbol dependency for the native arm.
SC_LIST_NODES ?= 16
ifneq ($(KERNELRELEASE),)
obj-m := spin_cacheline.o
spin_cacheline-objs := module.o
# All direct comparison arms use the same unsanitized payload. Ordinary test
# builds without SC_BACKEND continue inheriting the kernel's UBSAN setting.
ifneq ($(filter native tclock kdlock,$(SC_BACKEND)),)
UBSAN_SANITIZE := n
endif
ifeq ($(SC_WORKLOAD),rcuht)
ccflags-y += -DSC_HASH_PAYLOAD
endif
ifneq ($(filter list list-prefetch,$(SC_WORKLOAD)),)
ccflags-y += -DSC_LIST_PAYLOAD -DSC_LIST_NODES=$(SC_LIST_NODES)
ccflags-y += -DSC_LIST_PREFETCH=$(if $(filter list-prefetch,$(SC_WORKLOAD)),1,0)
endif
ifeq ($(SC_BACKEND),kdlock)
ccflags-y += -DSC_DIRECT_KDLOCK -I$(KDLOCK_INCLUDE)
ifneq ($(SC_SCENARIO),)
ccflags-y += -DSC_SCENARIO=$(SC_SCENARIO)
endif
else ifeq ($(SC_BACKEND),tclock)
ccflags-y += -DSC_DIRECT_TCLOCK
else ifeq ($(SC_BACKEND),native)
ccflags-y += -DSC_DIRECT_NATIVE
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
SC_BACKEND ?= native

.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 SC_BACKEND=$(SC_BACKEND) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
