# Guest-only build entry for the demo critical-section modules.
# Build kernel_module first for the interfaces used by lock_scenarios.
KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all lock_scenarios spin_cacheline clean
all: lock_scenarios spin_cacheline

lock_scenarios:
	$(MAKE) -C $(CURDIR)/lock_scenarios KDIR=$(KDIR)

spin_cacheline:
	$(MAKE) -C $(CURDIR)/spin_cacheline KDIR=$(KDIR)

clean:
	$(MAKE) -C $(CURDIR)/lock_scenarios KDIR=$(KDIR) clean
	$(MAKE) -C $(CURDIR)/spin_cacheline KDIR=$(KDIR) clean
