# Standalone consumer of the KD provider; build and load only in the guest.
KDLOCK_ROOT ?= ../../../..
kdlock-module-dir := $(if $(KERNELRELEASE),$(src),$(CURDIR))
kdlock-root := $(if $(filter /%,$(KDLOCK_ROOT)),$(KDLOCK_ROOT),$(abspath $(kdlock-module-dir)/$(KDLOCK_ROOT)))
KBUILD_EXTRA_SYMBOLS ?= $(kdlock-root)/kernel_module/Module.symvers

ifneq ($(KERNELRELEASE),)
obj-m := kd_spin_irq_api_test.o
kd_spin_irq_api_test-y := irq_api.o
ccflags-y += -I$(kdlock-root)/include
else
KDIR ?= /lib/modules/$(shell uname -r)/build

.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 KDLOCK_ROOT=$(kdlock-root) KBUILD_EXTRA_SYMBOLS="$(KBUILD_EXTRA_SYMBOLS)" modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
