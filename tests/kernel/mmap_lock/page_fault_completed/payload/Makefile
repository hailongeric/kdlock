obj-m += kd_mmap_completed.o
kd_mmap_completed-y := module.o
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
