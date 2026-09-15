# Guest-only workload module, built after kdlock for its exported interfaces.
# fragments/ sources are included, not separately loaded modules.
# common/ and modes/ .inc files also share the original translation unit.
obj-m += klock_module.o
# Build the second source only for the learned-depth dependency experiment.
# Default workloads must not acquire a new mandatory module dependency.
KDLOCK_SOURCE_HELPER ?= 0
ifeq ($(KDLOCK_SOURCE_HELPER),1)
obj-m += kd_depth_source.o
ccflags-y += -DKDLOCK_SOURCE_HELPER
endif
# The contention oracle reads the actual non-RT mutex waiter type.
ccflags-y += -I$(srctree)

KDIR ?= /lib/modules/$(shell uname -r)/build
KDLOCK_SYMVERS ?= $(abspath $(CURDIR)/../../kernel_module/Module.symvers)

.PHONY: all clean

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) \
		KBUILD_EXTRA_SYMBOLS=$(KDLOCK_SYMVERS) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
