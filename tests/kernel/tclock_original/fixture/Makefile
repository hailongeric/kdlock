TEST_KIND ?= 4
obj-m := tc_original_test.o
ifeq ($(TEST_KIND),4)
obj-m += tc_original_reap.o
endif
tc_original_reap-objs := reap.o
tc_original_test-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(TCLOCK_INCLUDE) -DTEST_KIND=$(TEST_KIND)
KDIR ?= /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
