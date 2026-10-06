# Explicit workloads. Backend-specific comparison builds belong to the runner.
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all spin_cacheline mutex_cacheline clean
all: spin_cacheline mutex_cacheline
spin_cacheline:
	$(MAKE) -C $(CURDIR)/spin_cacheline KDIR=$(KDIR) SC_BACKEND=native
mutex_cacheline:
	$(MAKE) -C $(CURDIR)/mutex_cacheline KDIR=$(KDIR) SC_BACKEND=native
clean:
	$(MAKE) -C $(CURDIR)/spin_cacheline KDIR=$(KDIR) clean
	$(MAKE) -C $(CURDIR)/mutex_cacheline KDIR=$(KDIR) clean
