JIT_CONTINUATION_MUTEX_API ?= outer
JIT_CONTINUATION_FAMILY ?= mutex
JIT_CONTINUATION_MIXED_SPIN ?= 0
JIT_CONTINUATION_ORIGIN_INSTRUCTIONS ?= 0
JIT_CONTINUATION_MODE ?= continuation
ifneq ($(KERNELRELEASE),)
obj-m := jit_continuation_test.o
jit_continuation_test-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE)
ifeq ($(JIT_CONTINUATION_MODE),killable)
ifneq ($(JIT_CONTINUATION_FAMILY),rwsem)
$(error killable continuation mode requires JIT_CONTINUATION_FAMILY=rwsem)
endif
ccflags-y += -DJIT_CONTINUATION_KILLABLE
else ifneq ($(JIT_CONTINUATION_MODE),continuation)
$(error JIT_CONTINUATION_MODE must be continuation or killable)
endif
ifeq ($(JIT_CONTINUATION_ORIGIN_INSTRUCTIONS),1)
ifneq ($(JIT_CONTINUATION_FAMILY):$(JIT_CONTINUATION_MIXED_SPIN),mutex:0)
$(error origin instruction probe requires a mutex with no nested spin)
endif
ccflags-y += -DJIT_CONTINUATION_ORIGIN_INSTRUCTIONS
endif
ifeq ($(JIT_CONTINUATION_MIXED_SPIN),1)
ccflags-y += -DJIT_CONTINUATION_MIXED_SPIN
endif
ifeq ($(JIT_CONTINUATION_FAMILY),spin)
ccflags-y += -DJIT_CONTINUATION_SPIN
else ifeq ($(JIT_CONTINUATION_FAMILY),rwlock)
ccflags-y += -DJIT_CONTINUATION_RWLOCK
else ifeq ($(JIT_CONTINUATION_FAMILY),rwsem)
ccflags-y += -DJIT_CONTINUATION_RWSEM
else ifneq ($(JIT_CONTINUATION_FAMILY),mutex)
$(error JIT_CONTINUATION_FAMILY must be mutex, spin, rwlock or rwsem)
endif
ifeq ($(JIT_CONTINUATION_MUTEX_API),public)
ifneq ($(JIT_CONTINUATION_FAMILY),mutex)
$(error public mutex API requires JIT_CONTINUATION_FAMILY=mutex)
endif
ccflags-y += -DJIT_CONTINUATION_PUBLIC_API
else ifneq ($(JIT_CONTINUATION_MUTEX_API),outer)
$(error JIT_CONTINUATION_MUTEX_API must be outer or public)
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
