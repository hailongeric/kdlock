# Independent guest workload: no kdlock symbol dependency for the native arm.
SC_WORKLOAD ?= cacheline
SC_SPIN_API ?= direct
ifneq ($(words $(SC_SPIN_API)),1)
$(error SC_SPIN_API requires one caller name)
endif
ifneq ($(filter $(SC_SPIN_API),direct public),$(SC_SPIN_API))
$(error SC_SPIN_API must be direct or public)
endif
ifneq ($(words $(SC_WORKLOAD)),1)
$(error SC_WORKLOAD requires one payload name)
endif
ifneq ($(filter $(SC_WORKLOAD),cacheline rcuht),$(SC_WORKLOAD))
$(error SC_WORKLOAD must be cacheline or rcuht)
endif
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
ifeq ($(SC_SPIN_API),public)
ccflags-y += -DSC_SPIN_PUBLIC_API
endif
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
