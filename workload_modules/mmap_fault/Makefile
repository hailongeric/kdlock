# Build only in the recovery VM. One provider per artifact; Native is common.
MF_TC_BUILD ?= 0
# Actual mmap-lock comparisons keep identical Native backing work in both modes.
MF_NATIVE_ONLY ?= 0
ifneq ($(filter $(MF_NATIVE_ONLY),0 1),$(MF_NATIVE_ONLY))
$(error MF_NATIVE_ONLY must be 0 or 1)
endif
ifeq ($(MF_NATIVE_ONLY)$(MF_TC_BUILD),11)
$(error Native-only and TCLock profiles are mutually exclusive)
endif
ifneq ($(KERNELRELEASE),)
obj-m := kd_mmap_fault.o
kd_mmap_fault-objs := mapping.o
UBSAN_SANITIZE := n
ccflags-y += -DMF_TC_BUILD=$(MF_TC_BUILD) -DMF_NATIVE_ONLY=$(MF_NATIVE_ONLY)
ifeq ($(MF_NATIVE_ONLY),0)
ccflags-y += -I$(KDLOCK_INCLUDE) -I$(TCLOCK_INCLUDE)
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
endif
