ifneq ($(KERNELRELEASE),)
obj-m := kd_origin_gs.o
kd_origin_gs-y := module.o
ccflags-y += -I$(KDLOCK_INCLUDE) -DKD_OWNED_MUTEX_CABI=1
UBSAN_SANITIZE := n
else
KDIR ?= /root/linux-6.1.159-kdclobber2
KDLOCK_INCLUDE ?= $(abspath ../../../../include)
KBUILD_EXTRA_SYMBOLS ?= $(abspath ../../../../kernel_module/Module.symvers)
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) KDLOCK_INCLUDE=$(KDLOCK_INCLUDE) KBUILD_EXTRA_SYMBOLS=$(KBUILD_EXTRA_SYMBOLS) W=1 modules
endif
