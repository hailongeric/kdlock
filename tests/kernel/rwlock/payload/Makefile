ifneq ($(KERNELRELEASE),)
obj-m := rwlock_test.o
rwlock_test-objs := module.o
UBSAN_SANITIZE := n
ifeq ($(RW_BACKEND),kdlock)
ccflags-y += -DRW_KDLOCK -I$(KDLOCK_INCLUDE)
else ifneq ($(RW_BACKEND),native)
$(error RW_BACKEND must be native or kdlock)
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
RW_BACKEND ?= native
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 RW_BACKEND=$(RW_BACKEND) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
