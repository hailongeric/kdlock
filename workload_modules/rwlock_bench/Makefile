ifneq ($(KERNELRELEASE),)
obj-m := rwlock_bench.o
rwlock_bench-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -DRB_LINES=$(RB_LINES) -DRB_POST_WORK_ROUNDS=$(RB_POST_WORK_ROUNDS) -I$(RB_SHARED)
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
RB_POST_WORK_ROUNDS ?= 4
RB_SHARED ?= $(abspath ../spin_cacheline)
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 RB_BACKEND=$(RB_BACKEND) RB_LINES=$(RB_LINES) RB_POST_WORK_ROUNDS=$(RB_POST_WORK_ROUNDS) RB_SHARED=$(RB_SHARED) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
