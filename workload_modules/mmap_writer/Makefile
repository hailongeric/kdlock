obj-m += kd_mmap_writer_native.o
kd_mmap_writer_native-y := mapping.o
KDIR ?= /lib/modules/$(shell uname -r)/build
ccflags-y += -Wall -Wextra -Wno-unused-parameter
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
