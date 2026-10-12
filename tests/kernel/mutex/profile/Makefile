ifneq ($(KERNELRELEASE),)
obj-m := kd_mutex_profile.o
UBSAN_SANITIZE := n
else
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
endif
