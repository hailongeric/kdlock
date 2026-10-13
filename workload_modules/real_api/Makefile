# Build in the recovery guest; each binary selects one real kernel API and lock.
ifneq ($(filter-out legacy,$(RB_MUTEX_IMPLEMENTATION)),)
$(error real kernel API mutexes support only RB_MUTEX_IMPLEMENTATION=legacy)
endif
ifneq ($(filter owned owned-v1 kdlock-owned,$(RB_BACKEND)),)
$(error a KD-owned object cannot replace a kernel-owned mutex)
endif
ifneq ($(KERNELRELEASE),)
obj-m := real_api.o
real_api-objs := module.o
ifneq ($(filter $(RB_KIND),PIPEBYTES PIPECAP SEEK),)
real_api-objs := mutex.o
endif
ifeq ($(RB_KIND),UTSNAME)
real_api-objs := uts.o
endif
UBSAN_SANITIZE := n
ccflags-y += -DRB_$(RB_KIND) -I$(KDLOCK_INCLUDE)
ccflags-y += -I$(TCLOCK_INCLUDE)
ifeq ($(RB_BACKEND),kdlock)
ccflags-y += -DRB_KDLOCK
else ifeq ($(RB_BACKEND),tclock)
ccflags-y += -DRB_TCLOCK
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
endif
