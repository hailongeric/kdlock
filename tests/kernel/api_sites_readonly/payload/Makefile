obj-m += kd_api_sites_readonly.o
kd_api_sites_readonly-y := module.o
KDIR ?= /mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
