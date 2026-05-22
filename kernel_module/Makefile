obj-m += kdlock_km.o

# ccflags-y += -O2
ccflags-y += -I$(src)/../include

kdlock_km-objs := kd_main.o kd_lock.o sys.o exe.o kd_spinlock.o combiner.o

OBJECT_FILES_NON_STANDARD_kd_spinlock.o := y

KDIR ?= /lib/modules/$(shell uname -r)/build

all:
	make -C $(KDIR) M=$(CURDIR) modules
# EXTRA_CFLAGS="-O1"

clean:
	make -C $(KDIR) M=$(CURDIR) clean
