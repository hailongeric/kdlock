# Guest-only module. Preserve the experiment kernel's frame pointer/mitigations.
obj-m := tclock_backend_km.o
tclock_backend_km-objs := provider.o komb.o combiner.o
# Match upstream RCUHT's unsanitized build for this benchmark module only.
# Keep the running kernel, frame pointers and return mitigations unchanged.
UBSAN_SANITIZE := n
ccflags-y += -I$(src)/include -DKD_SPIN_LEGACY_CALLER
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
