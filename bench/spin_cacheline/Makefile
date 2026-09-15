# Build and run tests only in the recovery guest; no kernel rebuild.
KDIR ?= /lib/modules/$(shell uname -r)/build
CC ?= cc
PYTHON ?= python3
CFLAGS ?= -O2 -g
CFLAGS += -Wall -Wextra -Werror -std=gnu11
PROVIDER_DIR := $(CURDIR)/.build/provider
WORKLOAD_DIR := $(abspath $(CURDIR)/../../workload_modules/spin_cacheline)

.PHONY: all provider module test clean
all: provider module client
# The source copy and observation overlay live entirely below this benchmark.
# Each explicit provider build starts fresh; ordinary project objects stay intact.
provider:
	$(PYTHON) provider/prepare.py
	$(MAKE) -C $(PROVIDER_DIR)/kernel_module KDIR=$(KDIR) W=1 KDLOCK_SELFTEST=0 KDLOCK_NUMA=0
module:
	$(MAKE) -C $(WORKLOAD_DIR) KDIR=$(KDIR)
client: client.c $(WORKLOAD_DIR)/api.h
	$(CC) $(CFLAGS) -pthread $< -o $@
test: client
	$(PYTHON) test_spin_cacheline.py
	$(PYTHON) test_assembly.py
clean:
	$(MAKE) -C $(WORKLOAD_DIR) KDIR=$(KDIR) clean
	rm -f client
	rm -rf $(CURDIR)/.build
