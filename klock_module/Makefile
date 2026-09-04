obj-m += klock_module.o

KDIR ?= /lib/modules/$(shell uname -r)/build
KDLOCK_SYMVERS ?= $(abspath ../kernel_module/Module.symvers)

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) \
		KBUILD_EXTRA_SYMBOLS=$(KDLOCK_SYMVERS) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
