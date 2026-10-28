ifneq ($(KERNELRELEASE),)
obj-m := kd_mutex_mixed_transfer.o
kd_mutex_mixed_transfer-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE)
else
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
