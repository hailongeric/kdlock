obj-m := rwsem_probe.o
rwsem_probe-objs := module.o
ccflags-y += -I$(KDLOCK_INCLUDE)
UBSAN_SANITIZE := n
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
