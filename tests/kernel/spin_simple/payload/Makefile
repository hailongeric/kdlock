obj-m := kd_spin_simple.o
ifndef KD_SOURCE_ROOT
$(error KD_SOURCE_ROOT must name the pinned 7338197a KD source)
endif
ccflags-y += -I$(KD_SOURCE_ROOT)
# Keep the declared fixture source free of function tracing instrumentation.
CFLAGS_REMOVE_kd_spin_simple.o += $(CC_FLAGS_FTRACE)
