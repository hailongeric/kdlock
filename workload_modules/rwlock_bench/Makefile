RB_WORKLOAD ?= cacheline
ifneq ($(words $(RB_WORKLOAD)),1)
$(error RB_WORKLOAD requires one payload name)
endif
ifneq ($(filter $(RB_WORKLOAD),cacheline rcuht taskname argbounds nano),$(RB_WORKLOAD))
$(error unsupported RB_WORKLOAD)
endif
ifneq ($(KERNELRELEASE),)
obj-m := rwlock_bench.o
rwlock_bench-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -DRB_LINES=$(RB_LINES) -DRB_POST_WORK_ROUNDS=$(RB_POST_WORK_ROUNDS) -I$(RB_SHARED)
ifeq ($(RB_LOCK_KIND),spin)
ccflags-y += -DRB_SPIN
ifneq ($(filter taskname argbounds,$(RB_WORKLOAD)),$(RB_WORKLOAD))
$(error spin requires a taskname or argbounds snapshot workload)
endif
else ifeq ($(RB_LOCK_KIND),rwsem)
ccflags-y += -DRB_RWSEM -DRB_RWSEM_DELEGATE=$(RB_RWSEM_DELEGATE)
else ifeq ($(RB_LOCK_KIND),mutex)
ccflags-y += -DRB_MUTEX -DRB_MUTEX_DELEGATE=$(RB_MUTEX_DELEGATE)
ifneq ($(filter nano cacheline,$(RB_WORKLOAD)),$(RB_WORKLOAD))
$(error mutex requires the nano pair or cacheline locality workload)
endif
ifeq ($(RB_WORKLOAD),cacheline)
ifneq ($(words $(RB_LINES)),1)
$(error mutex cacheline workload requires one RB_LINES value)
endif
ifeq ($(filter $(RB_LINES),1 2 4 8 16),)
$(error mutex cacheline workload requires RB_LINES=1,2,4,8,16)
endif
endif
else ifneq ($(RB_LOCK_KIND),rwlock)
$(error RB_LOCK_KIND must be rwlock, spin, rwsem or mutex)
endif
ifneq ($(filter taskname argbounds,$(RB_WORKLOAD)),)
ifneq ($(RB_LOCK_KIND),spin)
$(error taskname and argbounds require RB_LOCK_KIND=spin)
endif
ccflags-y += -DRB_SNAPSHOT_PAYLOAD
ifeq ($(RB_WORKLOAD),taskname)
ccflags-y += -DRB_TASKNAME
endif
endif
ifeq ($(RB_WORKLOAD),rcuht)
ccflags-y += -DRB_HASH
endif
ifeq ($(RB_WORKLOAD),nano)
ccflags-y += -DRB_NANO
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
RB_LOCK_KIND ?= rwlock
RB_RWSEM_DELEGATE ?= 0
RB_MUTEX_DELEGATE ?= 1
RB_LINES ?= 1
RB_POST_WORK_ROUNDS ?= 4
RB_SHARED ?= $(abspath ../spin_cacheline)
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 RB_BACKEND=$(RB_BACKEND) RB_LOCK_KIND=$(RB_LOCK_KIND) RB_RWSEM_DELEGATE=$(RB_RWSEM_DELEGATE) RB_MUTEX_DELEGATE=$(RB_MUTEX_DELEGATE) RB_LINES=$(RB_LINES) RB_POST_WORK_ROUNDS=$(RB_POST_WORK_ROUNDS) RB_SHARED=$(RB_SHARED) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
