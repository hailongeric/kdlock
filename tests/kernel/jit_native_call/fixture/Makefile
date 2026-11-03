NATIVE_CALL_MODE ?= direct
ifneq ($(KERNELRELEASE),)
obj-m := jit_native_call_test.o
jit_native_call_test-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -I$(KDLOCK_INCLUDE)
ifeq ($(NATIVE_CALL_MODE),indirect)
ccflags-y += -DNATIVE_CALL_INDIRECT
else ifneq ($(NATIVE_CALL_MODE),direct)
$(error NATIVE_CALL_MODE must be direct or indirect)
endif
else
KDIR ?= /lib/modules/$(shell uname -r)/build
.PHONY: all clean
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) W=1 modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
endif
