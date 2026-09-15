# Independent guest workload: no kdlock symbol dependency for the native arm.
ifneq ($(KERNELRELEASE),)
obj-m := spin_cacheline.o
spin_cacheline-objs := module.o
else
KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
