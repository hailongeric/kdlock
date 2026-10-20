JIT_ESCAPE_MUTEX_API ?= outer
ifneq ($(KERNELRELEASE),)
obj-m := jit_escape_test.o
jit_escape_test-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE)
ifeq ($(JIT_ESCAPE_MUTEX_API),public)
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
