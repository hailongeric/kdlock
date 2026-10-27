# Build in the recovery guest; each binary selects one real kernel API and lock.
ifneq ($(KERNELRELEASE),)
obj-m := real_api.o
real_api-objs := module.o
ifneq ($(filter $(RB_KIND),PIPEBYTES PIPECAP SEEK),)
real_api-objs := mutex.o
endif
ifeq ($(RB_KIND),UTSNAME)
real_api-objs := uts.o
endif
ifeq ($(RB_KIND),XATTR)
real_api-objs := xattr.o
endif
UBSAN_SANITIZE := n
ccflags-y += -DRB_$(RB_KIND) -I$(KDLOCK_INCLUDE)
ccflags-y += -I$(TCLOCK_INCLUDE)
ifeq ($(RB_BACKEND),kdlock)
ccflags-y += -DRB_KDLOCK
ifeq ($(RB_MUTEX_API),public)
ccflags-y += -DRB_MUTEX_PUBLIC_API
else ifneq ($(filter-out outer,$(RB_MUTEX_API)),)
$(error RB_MUTEX_API must be outer or public)
endif
ifneq ($(RB_MUTEX_LOCK_OFFSET),)
ccflags-y += -DRB_MUTEX_LOCK_OFFSET=$(RB_MUTEX_LOCK_OFFSET)
endif
else ifeq ($(RB_BACKEND),tclock)
ccflags-y += -DRB_TCLOCK
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
endif
