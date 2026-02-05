obj-m += kdlock_km.o

# ccflags-y += -O2
ccflags-y += -I$(PWD)/../include

kdlock_km-objs := kd_main.o  kd_lock.o sys.o exe.o komb.o combiner.o

all:
	make -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules 
# EXTRA_CFLAGS="-O1"

clean:
	make -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean