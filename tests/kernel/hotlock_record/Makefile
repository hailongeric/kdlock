# Build in an evidence directory populated by bench/hotlock_record/run.py.
obj-m += hotlock_record_bench.o
hotlock_record_bench-y := record_bench.o
ccflags-y += -I$(src)
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
