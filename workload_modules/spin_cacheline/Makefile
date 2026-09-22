# Independent guest workload: no kdlock symbol dependency for the native arm.
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
ifeq ($(SC_BACKEND),kdlock)
ccflags-y += -DSC_DIRECT_KDLOCK -I$(KDLOCK_INCLUDE)
SC_COLD_FASTPATH ?= 0
ccflags-y += -DSC_COLD_FASTPATH=$(SC_COLD_FASTPATH)
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
