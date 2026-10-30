obj-m += kd_rwsem_poll_probe.o
kd_rwsem_poll_probe-y := module.o
ccflags-y += -I$(KDLOCK_INCLUDE)
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
