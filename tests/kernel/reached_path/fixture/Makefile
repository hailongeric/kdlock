ifneq ($(KERNELRELEASE),)
obj-m := kd_reached_test.o
kd_reached_test-objs := module.o engine.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE)
ccflags-y += -DKDLOCK_REACHED_SOURCE='"$(KDLOCK_REACHED_SOURCE)"'
else
KDIR ?= /lib/modules/$(shell uname -r)/build
KDLOCK_ROOT ?= $(abspath ../../../..)
KDLOCK_INCLUDE ?= $(KDLOCK_ROOT)/include
KDLOCK_REACHED_SOURCE ?= $(KDLOCK_ROOT)/tests/kernel/reached_path/fixture/reference.inc
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) KDLOCK_INCLUDE=$(KDLOCK_INCLUDE) KDLOCK_REACHED_SOURCE=$(KDLOCK_REACHED_SOURCE) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
