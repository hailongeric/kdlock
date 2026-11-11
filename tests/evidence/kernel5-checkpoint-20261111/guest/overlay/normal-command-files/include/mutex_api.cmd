savedcmd_kernel/kdlock/include/mutex_api.o := gcc -Wp,-MMD,kernel/kdlock/include/.mutex_api.o.d -nostdinc -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include -I./arch/x86/include/generated -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include -I./include -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi -I./arch/x86/include/generated/uapi -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi -I./include/generated/uapi -include /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler-version.h -include /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kconfig.h -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/ubuntu/include -D__KERNEL__ -fmacro-prefix-map=/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/= -D__ASSEMBLY__ -fno-PIE -m64 -DCC_USING_FENTRY -g -gdwarf-5 -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/include -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock -Ikernel/kdlock    -DKBUILD_MODFILE='"kernel/kdlock/kdlock_rebuild"' -DKBUILD_MODNAME='"kdlock_rebuild"' -D__KBUILD_MODNAME=kdlock_rebuild -c -o kernel/kdlock/include/mutex_api.o /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/include/mutex_api.S 

source_kernel/kdlock/include/mutex_api.o := /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/include/mutex_api.S

deps_kernel/kdlock/include/mutex_api.o := \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler-version.h \
    $(wildcard include/config/CC_VERSION_TEXT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kconfig.h \
    $(wildcard include/config/CPU_BIG_ENDIAN) \
    $(wildcard include/config/BOOGER) \
    $(wildcard include/config/FOO) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/include/kd_mutex_api.h \

kernel/kdlock/include/mutex_api.o: $(deps_kernel/kdlock/include/mutex_api.o)

$(deps_kernel/kdlock/include/mutex_api.o):
