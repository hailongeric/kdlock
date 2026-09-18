# Guest-only module. Preserve the experiment kernel's frame pointer/mitigations.
obj-m := tclock_backend_km.o
tclock_backend_km-objs := provider.o komb.o context.o
ccflags-y += -I$(src)/include -DKD_SPIN_LEGACY_CALLER
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
