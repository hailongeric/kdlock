ifneq ($(KERNELRELEASE),)
obj-m := rwlock_bench.o
rwlock_bench-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -DRB_LINES=$(RB_LINES) -I$(RB_SHARED)
ifeq ($(RB_LOCK_KIND),spin)
ccflags-y += -DRB_SPIN
else ifeq ($(RB_LOCK_KIND),rwsem)
RB_RWSEM_CABI ?= 1
ccflags-y += -DRB_RWSEM -DKD_OWNED_MUTEX_CABI=$(RB_RWSEM_CABI)
ifeq ($(RB_BACKEND),tclock)
$(error TCLock backend has no sleeping rwsem port)
endif
endif
ifneq ($(filter taskname argbounds,$(RB_WORKLOAD)),)
ccflags-y += -DRB_SNAPSHOT_PAYLOAD
ifeq ($(RB_WORKLOAD),taskname)
ccflags-y += -DRB_TASKNAME
endif
endif
ifeq ($(RB_WORKLOAD),rcuht)
ccflags-y += -DRB_HASH
endif
ifeq ($(RB_BACKEND),kdlock)
ccflags-y += -DRB_KDLOCK -I$(KDLOCK_INCLUDE)
else ifeq ($(RB_BACKEND),tclock)
ccflags-y += -DRB_TCLOCK -I$(TCLOCK_INCLUDE)
else ifneq ($(RB_BACKEND),native)
$(error RB_BACKEND must be native, tclock or kdlock)
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
RB_BACKEND ?= native
RB_WORKLOAD ?= cacheline
RB_LINES ?= 1
RB_SHARED ?= $(abspath ../spin_cacheline)
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 RB_BACKEND=$(RB_BACKEND) RB_LINES=$(RB_LINES) RB_SHARED=$(RB_SHARED) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
