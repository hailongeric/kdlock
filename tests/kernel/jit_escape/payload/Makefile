JIT_ESCAPE_MUTEX_API ?= outer
JIT_ESCAPE_FAMILY ?= mutex
JIT_ESCAPE_MIXED_SPIN ?= 0
JIT_ESCAPE_ORIGIN_INSTRUCTIONS ?= 0
ifneq ($(KERNELRELEASE),)
obj-m := jit_escape_test.o
jit_escape_test-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE)
ifeq ($(JIT_ESCAPE_ORIGIN_INSTRUCTIONS),1)
ifneq ($(JIT_ESCAPE_FAMILY):$(JIT_ESCAPE_MIXED_SPIN),mutex:0)
$(error origin instruction probe requires a mutex with no nested spin)
endif
ccflags-y += -DJIT_ESCAPE_ORIGIN_INSTRUCTIONS
endif
ifeq ($(JIT_ESCAPE_MIXED_SPIN),1)
ccflags-y += -DJIT_ESCAPE_MIXED_SPIN
endif
ifeq ($(JIT_ESCAPE_FAMILY),spin)
ccflags-y += -DJIT_ESCAPE_SPIN
else ifeq ($(JIT_ESCAPE_FAMILY),rwlock)
ccflags-y += -DJIT_ESCAPE_RWLOCK
else ifeq ($(JIT_ESCAPE_FAMILY),rwsem)
ccflags-y += -DJIT_ESCAPE_RWSEM
else ifneq ($(JIT_ESCAPE_FAMILY),mutex)
$(error JIT_ESCAPE_FAMILY must be mutex, spin, rwlock or rwsem)
endif
ifeq ($(JIT_ESCAPE_MUTEX_API),public)
ifneq ($(JIT_ESCAPE_FAMILY),mutex)
$(error public mutex API requires JIT_ESCAPE_FAMILY=mutex)
endif
ccflags-y += -DJIT_ESCAPE_PUBLIC_API
else ifneq ($(JIT_ESCAPE_MUTEX_API),outer)
$(error JIT_ESCAPE_MUTEX_API must be outer or public)
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
