obj-m += kd_mutex_proxy_pin_probe.o
ccflags-y += -I$(src)/../../../../../include
KBUILD_EXTRA_SYMBOLS := $(src)/../../../../../kernel_module/Module.symvers
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
