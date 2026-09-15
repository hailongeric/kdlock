# Guest-only diagnostic provider for the unchanged hook-patched kernel.
obj-m += kd_dispatch_floor.o
kd_dispatch_floor-y := module.o
ccflags-y += -I$(src)/../../../include
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
