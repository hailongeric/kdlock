# Guest-only module. Preserve the experiment kernel's frame pointer/mitigations.
ifeq ($(TCLOCK_MUTEX),1)
obj-m := tclock_mutex_backend_km.o
tclock_mutex_backend_km-objs := mutex_provider.o komb_mutex.o combiner.o
else
obj-m := tclock_backend_km.o
tclock_backend_km-objs := provider.o komb.o combiner.o
endif
# Match upstream RCUHT's unsanitized build for this benchmark module only.
# Keep the running kernel, frame pointers and return mitigations unchanged.
UBSAN_SANITIZE := n
ccflags-y += -I$(src)/include -DKD_SPIN_LEGACY_CALLER
TCLOCK_NUMA ?= 0
ifeq ($(TCLOCK_NUMA),1)
ccflags-y += -DNUMA_AWARE
endif
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
