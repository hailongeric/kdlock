obj-m := kd_rwlock_irq_api_test.o
kd_rwlock_irq_api_test-y := module.o
KDLOCK_INCLUDE ?= $(abspath ../../../../../include)
KBUILD_EXTRA_SYMBOLS ?= $(abspath ../../../../../kernel_module/Module.symvers)
ccflags-y += -I$(KDLOCK_INCLUDE)
UBSAN_SANITIZE := n
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
