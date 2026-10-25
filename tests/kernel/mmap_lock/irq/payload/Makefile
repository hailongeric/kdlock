obj-m += kd_mmap_irq_probe.o
kd_mmap_irq_probe-y := probe.o adapter_probe.o pool.o kd_mmap_mutex_local.o kd_mmap_mutex_osq.o rwsem_probe.o
ccflags-y += -I$(KD_IRQ_INCLUDE)
UBSAN_SANITIZE := n
