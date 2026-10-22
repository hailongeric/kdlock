obj-m += kd_mm_body_test.o
kd_mm_body_test-y := module.o
KDIR ?= /root/linux-6.1.159-kdclobber2
ccflags-y += -Werror
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
