# VM-only, source/output-separated external module build.
obj-m := kd_nano.o
kd_nano-objs := module.o
UBSAN_SANITIZE := n
ccflags-y += -DRB_LINES=1 -DRB_POST_WORK_ROUNDS=256
ifeq ($(RB_LOCK_KIND),mutex)
ccflags-y += -DRB_MUTEX
else ifeq ($(RB_LOCK_KIND),rwsem)
ccflags-y += -DRB_RWSEM
else ifeq ($(RB_LOCK_KIND),spin)
ccflags-y += -DRB_SPIN
ifeq ($(RB_BACKEND),tclock)
$(error spin supports only native or kdlock)
endif
else
$(error RB_LOCK_KIND must be mutex, rwsem or spin)
endif
ifeq ($(RB_BACKEND),kdlock)
ccflags-y += -DRB_KDLOCK -I$(KD_SOURCE_ROOT)
else ifeq ($(RB_BACKEND),tclock)
ccflags-y += -DRB_TCLOCK -I$(TCLOCK_INCLUDE)
else ifneq ($(RB_BACKEND),native)
$(error RB_BACKEND must be native, tclock or kdlock)
endif
