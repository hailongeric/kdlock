# Current explicit API workload; the obsolete hook workload was removed.
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all spin_cacheline clean
all: spin_cacheline
spin_cacheline:
	$(MAKE) -C $(CURDIR)/spin_cacheline KDIR=$(KDIR) SC_BACKEND=native
clean:
	$(MAKE) -C $(CURDIR)/spin_cacheline KDIR=$(KDIR) clean
