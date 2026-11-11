savedcmd_kernel/kdlock/kernel/source_epoch.o := gcc -Wp,-MMD,kernel/kdlock/kernel/.source_epoch.o.d -nostdinc -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include -I./arch/x86/include/generated -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include -I./include -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi -I./arch/x86/include/generated/uapi -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi -I./include/generated/uapi -include /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler-version.h -include /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kconfig.h -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/ubuntu/include -include /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler_types.h -D__KERNEL__ -fmacro-prefix-map=/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/= -std=gnu11 -fshort-wchar -funsigned-char -fno-common -fno-PIE -fno-strict-aliasing -mno-sse -mno-mmx -mno-sse2 -mno-3dnow -mno-avx -mno-sse4a -fcf-protection=none -m64 -falign-jumps=1 -falign-loops=1 -mno-80387 -mno-fp-ret-in-387 -mpreferred-stack-boundary=3 -mskip-rax-setup -march=x86-64 -mtune=generic -mno-red-zone -mcmodel=kernel -mstack-protector-guard-reg=gs -mstack-protector-guard-symbol=__ref_stack_chk_guard -Wno-sign-compare -fno-asynchronous-unwind-tables -mindirect-branch=thunk-extern -mindirect-branch-register -mindirect-branch-cs-prefix -mfunction-return=thunk-extern -fno-jump-tables -mharden-sls=all -fpatchable-function-entry=16,16 -fno-delete-null-pointer-checks -O2 -fno-allow-store-data-races -fstack-protector-strong -fno-omit-frame-pointer -fno-optimize-sibling-calls -ftrivial-auto-var-init=zero -fzero-init-padding-bits=all -fno-stack-clash-protection -fzero-call-used-regs=used-gpr -pg -mrecord-mcount -mfentry -DCC_USING_FENTRY -fmin-function-alignment=16 -fstrict-flex-arrays=3 -fms-extensions -fno-strict-overflow -fno-stack-check -fconserve-stack -fno-builtin-wcslen -Wall -Wextra -Wundef -Werror=implicit-function-declaration -Werror=implicit-int -Werror=return-type -Werror=strict-prototypes -Wno-format-security -Wno-trigraphs -Wno-frame-address -Wno-address-of-packed-member -Wmissing-declarations -Wmissing-prototypes -Wframe-larger-than=1024 -Wno-main -Wno-type-limits -Wno-dangling-pointer -Wvla-larger-than=1 -Wno-pointer-sign -Wcast-function-type -Wno-unterminated-string-initialization -Wno-array-bounds -Wno-stringop-overflow -Wno-alloc-size-larger-than -Wimplicit-fallthrough=5 -Werror=date-time -Werror=incompatible-pointer-types -Werror=designated-init -Wenum-conversion -Wunused -Wno-unused-but-set-variable -Wno-unused-const-variable -Wno-packed-not-aligned -Wno-format-overflow -Wno-format-truncation -Wno-stringop-truncation -Wno-override-init -Wno-missing-field-initializers -Wno-shift-negative-value -Wno-maybe-uninitialized -Wno-sign-compare -Wno-unused-parameter -g -gdwarf-5 -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/include -include /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/kernel/target.h  -fsanitize=bounds-strict -fsanitize=shift -fsanitize=bool -fsanitize=enum   -I/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock -Ikernel/kdlock    -DKBUILD_MODFILE='"kernel/kdlock/kdlock_rebuild"' -DKBUILD_BASENAME='"source_epoch"' -DKBUILD_MODNAME='"kdlock_rebuild"' -D__KBUILD_MODNAME=kdlock_rebuild -c -o kernel/kdlock/kernel/source_epoch.o /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/kernel/source_epoch.c  

source_kernel/kdlock/kernel/source_epoch.o := /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/kernel/source_epoch.c

deps_kernel/kdlock/kernel/source_epoch.o := \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler-version.h \
    $(wildcard include/config/CC_VERSION_TEXT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kconfig.h \
    $(wildcard include/config/CPU_BIG_ENDIAN) \
    $(wildcard include/config/BOOGER) \
    $(wildcard include/config/FOO) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler_types.h \
    $(wildcard include/config/DEBUG_INFO_BTF) \
    $(wildcard include/config/PAHOLE_HAS_BTF_TAG) \
    $(wildcard include/config/FUNCTION_ALIGNMENT) \
    $(wildcard include/config/CC_HAS_SANE_FUNCTION_ALIGNMENT) \
    $(wildcard include/config/X86_64) \
    $(wildcard include/config/ARM64) \
    $(wildcard include/config/LD_DEAD_CODE_DATA_ELIMINATION) \
    $(wildcard include/config/LTO_CLANG) \
    $(wildcard include/config/HAVE_ARCH_COMPILER_H) \
    $(wildcard include/config/KCSAN) \
    $(wildcard include/config/CC_HAS_ASSUME) \
    $(wildcard include/config/CC_HAS_COUNTED_BY) \
    $(wildcard include/config/FORTIFY_SOURCE) \
    $(wildcard include/config/UBSAN_BOUNDS) \
    $(wildcard include/config/CC_HAS_COUNTED_BY_PTR) \
    $(wildcard include/config/CC_HAS_MULTIDIMENSIONAL_NONSTRING) \
    $(wildcard include/config/UBSAN_INTEGER_WRAP) \
    $(wildcard include/config/CFI) \
    $(wildcard include/config/ARCH_USES_CFI_GENERIC_LLVM_PASS) \
    $(wildcard include/config/CC_HAS_BROKEN_COUNTED_BY_REF) \
    $(wildcard include/config/CC_HAS_ASM_INLINE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler-context-analysis.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler_attributes.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler-gcc.h \
    $(wildcard include/config/ARCH_USE_BUILTIN_BSWAP) \
    $(wildcard include/config/SHADOW_CALL_STACK) \
    $(wildcard include/config/KCOV) \
    $(wildcard include/config/CC_HAS_TYPEOF_UNQUAL) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/kernel/target.h \
    $(wildcard include/config/PREEMPT_RT) \
  include/generated/uapi/linux/version.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/compiler.h \
    $(wildcard include/config/TRACE_BRANCH_PROFILING) \
    $(wildcard include/config/PROFILE_ALL_BRANCHES) \
    $(wildcard include/config/OBJTOOL) \
  arch/x86/include/generated/asm/rwonce.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/rwonce.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kasan-checks.h \
    $(wildcard include/config/KASAN_GENERIC) \
    $(wildcard include/config/KASAN_SW_TAGS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/types.h \
    $(wildcard include/config/HAVE_UID16) \
    $(wildcard include/config/UID16) \
    $(wildcard include/config/ARCH_DMA_ADDR_T_64BIT) \
    $(wildcard include/config/PHYS_ADDR_T_64BIT) \
    $(wildcard include/config/64BIT) \
    $(wildcard include/config/ARCH_32BIT_USTAT_F_TINODE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/types.h \
  arch/x86/include/generated/uapi/asm/types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/int-ll64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/int-ll64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/bitsperlong.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitsperlong.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/bitsperlong.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/posix_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/stddef.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/stddef.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/posix_types.h \
    $(wildcard include/config/X86_32) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/posix_types_64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/posix_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kcsan-checks.h \
    $(wildcard include/config/KCSAN_WEAK_MEMORY) \
    $(wildcard include/config/KCSAN_IGNORE_ATOMICS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/errno.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/errno.h \
  arch/x86/include/generated/uapi/asm/errno.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/errno.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/errno-base.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/string.h \
    $(wildcard include/config/BINARY_PRINTF) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/args.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/array_size.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/cleanup.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/err.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/overflow.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/limits.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/limits.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/limits.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/const.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/const.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/const.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/stdarg.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/string.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/string.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/string_64.h \
    $(wildcard include/config/KMSAN) \
    $(wildcard include/config/ARCH_HAS_UACCESS_FLUSHCACHE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/jump_label.h \
    $(wildcard include/config/JUMP_LABEL) \
    $(wildcard include/config/HAVE_ARCH_JUMP_LABEL_RELATIVE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/jump_label.h \
    $(wildcard include/config/HAVE_JUMP_LABEL_HACK) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/asm.h \
    $(wildcard include/config/KPROBES) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/annotate.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/objtool_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/stringify.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/asm-offsets.h \
  include/generated/asm-offsets.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/extable_fixup_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/nops.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/fortify-string.h \
    $(wildcard include/config/CC_HAS_KASAN_MEMINTRINSIC_PREFIX) \
    $(wildcard include/config/GENERIC_ENTRY) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/bug.h \
    $(wildcard include/config/GENERIC_BUG) \
    $(wildcard include/config/PRINTK) \
    $(wildcard include/config/BUG_ON_DATA_CORRUPTION) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/bug.h \
    $(wildcard include/config/DEBUG_BUGVERBOSE) \
    $(wildcard include/config/DEBUG_BUGVERBOSE_DETAILED) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/instrumentation.h \
    $(wildcard include/config/NOINSTR_VALIDATION) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/objtool.h \
    $(wildcard include/config/FRAME_POINTER) \
    $(wildcard include/config/MITIGATION_UNRET_ENTRY) \
    $(wildcard include/config/MITIGATION_SRSO) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/static_call_types.h \
    $(wildcard include/config/HAVE_STATIC_CALL) \
    $(wildcard include/config/HAVE_STATIC_CALL_INLINE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bug.h \
    $(wildcard include/config/BUG) \
    $(wildcard include/config/GENERIC_BUG_RELATIVE_POINTERS) \
    $(wildcard include/config/SMP) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/once_lite.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/panic.h \
    $(wildcard include/config/PANIC_TIMEOUT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/printk.h \
    $(wildcard include/config/MESSAGE_LOGLEVEL_DEFAULT) \
    $(wildcard include/config/CONSOLE_LOGLEVEL_DEFAULT) \
    $(wildcard include/config/CONSOLE_LOGLEVEL_QUIET) \
    $(wildcard include/config/EARLY_PRINTK) \
    $(wildcard include/config/PRINTK_INDEX) \
    $(wildcard include/config/DYNAMIC_DEBUG) \
    $(wildcard include/config/DYNAMIC_DEBUG_CORE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/init.h \
    $(wildcard include/config/MEMORY_HOTPLUG) \
    $(wildcard include/config/HAVE_ARCH_PREL32_RELOCATIONS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/build_bug.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kern_levels.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/linkage.h \
    $(wildcard include/config/ARCH_USE_SYM_ANNOTATIONS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/export.h \
    $(wildcard include/config/MODVERSIONS) \
    $(wildcard include/config/GENDWARFKSYMS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/linkage.h \
    $(wildcard include/config/CALL_PADDING) \
    $(wildcard include/config/MITIGATION_RETHUNK) \
    $(wildcard include/config/MITIGATION_RETPOLINE) \
    $(wildcard include/config/MITIGATION_SLS) \
    $(wildcard include/config/FUNCTION_PADDING_BYTES) \
    $(wildcard include/config/UML) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/ibt.h \
    $(wildcard include/config/X86_KERNEL_IBT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/ratelimit_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/bits.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/bits.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/bits.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/param.h \
  arch/x86/include/generated/uapi/asm/param.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/param.h \
    $(wildcard include/config/HZ) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/param.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/spinlock_types_raw.h \
    $(wildcard include/config/DEBUG_SPINLOCK) \
    $(wildcard include/config/DEBUG_LOCK_ALLOC) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/spinlock_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/qspinlock_types.h \
    $(wildcard include/config/NR_CPUS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/qrwlock_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/byteorder.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/byteorder/little_endian.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/byteorder/little_endian.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/swab.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/swab.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/swab.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/byteorder/generic.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/lockdep_types.h \
    $(wildcard include/config/PROVE_RAW_LOCK_NESTING) \
    $(wildcard include/config/LOCKDEP) \
    $(wildcard include/config/LOCK_STAT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/dynamic_debug.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/kernel/kdlock/kernel/source_epoch.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/list.h \
    $(wildcard include/config/LIST_HARDENED) \
    $(wildcard include/config/DEBUG_LIST) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/container_of.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/poison.h \
    $(wildcard include/config/ILLEGAL_POINTER_VALUE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/barrier.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/alternative.h \
    $(wildcard include/config/CALL_THUNKS) \
    $(wildcard include/config/MITIGATION_ITS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/barrier.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/spinlock.h \
    $(wildcard include/config/PREEMPTION) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/typecheck.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/preempt.h \
    $(wildcard include/config/PREEMPT_COUNT) \
    $(wildcard include/config/DEBUG_PREEMPT) \
    $(wildcard include/config/TRACE_PREEMPT_TOGGLE) \
    $(wildcard include/config/PREEMPT_NOTIFIERS) \
    $(wildcard include/config/PREEMPT_DYNAMIC) \
    $(wildcard include/config/PREEMPT_NONE) \
    $(wildcard include/config/PREEMPT_VOLUNTARY) \
    $(wildcard include/config/PREEMPT) \
    $(wildcard include/config/PREEMPT_LAZY) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/preempt.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/rmwcc.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/percpu.h \
    $(wildcard include/config/CC_HAS_NAMED_AS) \
    $(wildcard include/config/USE_X86_SEG_SUPPORT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/percpu.h \
    $(wildcard include/config/HAVE_SETUP_PER_CPU_AREA) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/threads.h \
    $(wildcard include/config/BASE_SMALL) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/percpu-defs.h \
    $(wildcard include/config/ARCH_MODULE_NEEDS_WEAK_PER_CPU) \
    $(wildcard include/config/DEBUG_FORCE_WEAK_PER_CPU) \
    $(wildcard include/config/AMD_MEM_ENCRYPT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/irqflags.h \
    $(wildcard include/config/PROVE_LOCKING) \
    $(wildcard include/config/TRACE_IRQFLAGS) \
    $(wildcard include/config/IRQSOFF_TRACER) \
    $(wildcard include/config/PREEMPT_TRACER) \
    $(wildcard include/config/DEBUG_IRQFLAGS) \
    $(wildcard include/config/TRACE_IRQFLAGS_SUPPORT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/irqflags_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/irqflags.h \
    $(wildcard include/config/PARAVIRT) \
    $(wildcard include/config/PARAVIRT_XXL) \
    $(wildcard include/config/DEBUG_ENTRY) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/processor-flags.h \
    $(wildcard include/config/VM86) \
    $(wildcard include/config/MITIGATION_PAGE_TABLE_ISOLATION) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/processor-flags.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/mem_encrypt.h \
    $(wildcard include/config/ARCH_HAS_MEM_ENCRYPT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/mem_encrypt.h \
    $(wildcard include/config/X86_MEM_ENCRYPT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/cc_platform.h \
    $(wildcard include/config/ARCH_HAS_CC_PLATFORM) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/nospec-branch.h \
    $(wildcard include/config/CALL_THUNKS_DEBUG) \
    $(wildcard include/config/MITIGATION_CALL_DEPTH_TRACKING) \
    $(wildcard include/config/MITIGATION_IBPB_ENTRY) \
    $(wildcard include/config/BPF_JIT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/static_key.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cpufeatures.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/msr-index.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/unwind_hints.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/orc_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/ptrace-abi.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/GEN-for-each-reg.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/segment.h \
    $(wildcard include/config/XEN_PV) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cache.h \
    $(wildcard include/config/X86_L1_CACHE_SHIFT) \
    $(wildcard include/config/X86_INTERNODE_CACHE_SHIFT) \
    $(wildcard include/config/X86_VSMP) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/paravirt.h \
    $(wildcard include/config/X86_IOPL_IOPERM) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/paravirt-base.h \
    $(wildcard include/config/PARAVIRT_SPINLOCKS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/paravirt_types.h \
    $(wildcard include/config/ZERO_CALL_USED_REGS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/desc_defs.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/pgtable_types.h \
    $(wildcard include/config/X86_INTEL_MEMORY_PROTECTION_KEYS) \
    $(wildcard include/config/X86_PAE) \
    $(wildcard include/config/MEM_SOFT_DIRTY) \
    $(wildcard include/config/HAVE_ARCH_USERFAULTFD_WP) \
    $(wildcard include/config/PGTABLE_LEVELS) \
    $(wildcard include/config/PROC_FS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/page_types.h \
    $(wildcard include/config/PHYSICAL_START) \
    $(wildcard include/config/PHYSICAL_ALIGN) \
    $(wildcard include/config/DYNAMIC_PHYSICAL_MASK) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/page.h \
    $(wildcard include/config/PAGE_SHIFT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/page_64_types.h \
    $(wildcard include/config/KASAN) \
    $(wildcard include/config/RANDOMIZE_BASE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/kaslr.h \
    $(wildcard include/config/RANDOMIZE_MEMORY) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/pgtable_64_types.h \
    $(wildcard include/config/DEBUG_KMAP_LOCAL_FORCE_MAP) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/sparsemem.h \
    $(wildcard include/config/SPARSEMEM) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/cpumask.h \
    $(wildcard include/config/FORCE_NR_CPUS) \
    $(wildcard include/config/HOTPLUG_CPU) \
    $(wildcard include/config/DEBUG_PER_CPU_MAPS) \
    $(wildcard include/config/CPUMASK_OFFSTACK) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/atomic.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/atomic.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cmpxchg.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cmpxchg_64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/atomic64_64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/atomic/atomic-arch-fallback.h \
    $(wildcard include/config/GENERIC_ATOMIC64) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/atomic/atomic-long.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/atomic/atomic-instrumented.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/instrumented.h \
    $(wildcard include/config/DEBUG_ATOMIC) \
    $(wildcard include/config/DEBUG_ATOMIC_LARGEST_ALIGN) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kmsan-checks.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/bitmap.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/align.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/align.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/bitops.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/kernel.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/sysinfo.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/generic-non-atomic.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/bitops.h \
    $(wildcard include/config/X86_CMOV) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/sched.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/arch_hweight.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/const_hweight.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/instrumented-atomic.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/instrumented-non-atomic.h \
    $(wildcard include/config/KCSAN_ASSUME_PLAIN_WRITES_ATOMIC) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/instrumented-lock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/le.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/bitops/ext2-atomic-setbit.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/find.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/bitmap-str.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/cpumask_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/gfp_types.h \
    $(wildcard include/config/KASAN_HW_TAGS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/numa.h \
    $(wildcard include/config/NUMA_KEEP_MEMINFO) \
    $(wildcard include/config/NUMA) \
    $(wildcard include/config/HAVE_ARCH_NODE_DEV_GROUP) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/nodemask.h \
    $(wildcard include/config/HIGHMEM) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/minmax.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/nodemask_types.h \
    $(wildcard include/config/NODES_SHIFT) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/random.h \
    $(wildcard include/config/VMGENID) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kernel.h \
    $(wildcard include/config/PREEMPT_VOLUNTARY_BUILD) \
    $(wildcard include/config/HAVE_PREEMPT_DYNAMIC_CALL) \
    $(wildcard include/config/HAVE_PREEMPT_DYNAMIC_KEY) \
    $(wildcard include/config/PREEMPT_) \
    $(wildcard include/config/DEBUG_ATOMIC_SLEEP) \
    $(wildcard include/config/MMU) \
    $(wildcard include/config/DYNAMIC_FTRACE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/kstrtox.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/log2.h \
    $(wildcard include/config/ARCH_HAS_ILOG2_U32) \
    $(wildcard include/config/ARCH_HAS_ILOG2_U64) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/math.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/div64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/div64.h \
    $(wildcard include/config/CC_OPTIMIZE_FOR_PERFORMANCE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/sprintf.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/trace_printk.h \
    $(wildcard include/config/TRACING) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/instruction_pointer.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/util_macros.h \
    $(wildcard include/config/FOO_SUSPEND) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/wordpart.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/random.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/ioctl.h \
  arch/x86/include/generated/uapi/asm/ioctl.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/ioctl.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/asm-generic/ioctl.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/irqnr.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/irqnr.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/frame.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/thread_info.h \
    $(wildcard include/config/THREAD_INFO_IN_TASK) \
    $(wildcard include/config/ARCH_HAS_PREEMPT_LAZY) \
    $(wildcard include/config/HAVE_ARCH_WITHIN_STACK_FRAMES) \
    $(wildcard include/config/SH) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/restart_block.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/time64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/math64.h \
    $(wildcard include/config/ARCH_SUPPORTS_INT128) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/math64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/time64.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/time.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/time_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/current.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/cache.h \
    $(wildcard include/config/ARCH_HAS_CACHE_LINE_SIZE) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/vdso/cache.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/thread_info.h \
    $(wildcard include/config/X86_FRED) \
    $(wildcard include/config/COMPAT) \
    $(wildcard include/config/IA32_EMULATION) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/page.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/page_64.h \
    $(wildcard include/config/DEBUG_VIRTUAL) \
    $(wildcard include/config/X86_VSYSCALL_EMULATION) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/mmdebug.h \
    $(wildcard include/config/DEBUG_VM) \
    $(wildcard include/config/DEBUG_VM_IRQSOFF) \
    $(wildcard include/config/DEBUG_VM_PGFLAGS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/range.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/memory_model.h \
    $(wildcard include/config/FLATMEM) \
    $(wildcard include/config/SPARSEMEM_VMEMMAP) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/pfn.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/getorder.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cpufeature.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/processor.h \
    $(wildcard include/config/X86_VMX_FEATURE_NAMES) \
    $(wildcard include/config/X86_USER_SHADOW_STACK) \
    $(wildcard include/config/X86_DEBUG_FPU) \
    $(wildcard include/config/CPU_SUP_AMD) \
    $(wildcard include/config/XEN) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/math_emu.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/ptrace.h \
    $(wildcard include/config/X86_DEBUGCTLMSR) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/ptrace.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/proto.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/ldt.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/uapi/asm/sigcontext.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cpuid/api.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cpuid/types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/special_insns.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/fpu/types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/vmxfeatures.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/vdso/processor.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/shstk.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/personality.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/uapi/linux/personality.h \
  arch/x86/include/generated/asm/cpufeaturemasks.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/thread_info_tif.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/bottom_half.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/lockdep.h \
    $(wildcard include/config/DEBUG_LOCKING_API_SELFTESTS) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/smp.h \
    $(wildcard include/config/UP_LATE_INIT) \
    $(wildcard include/config/CSD_LOCK_WAIT_DEBUG) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/smp_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/llist.h \
    $(wildcard include/config/ARCH_HAVE_NMI_SAFE_CMPXCHG) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/smp.h \
    $(wildcard include/config/DEBUG_NMI_SELFTEST) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/cpumask.h \
  arch/x86/include/generated/asm/mmiowb.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/mmiowb.h \
    $(wildcard include/config/MMIOWB) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/spinlock_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/rwlock_types.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/spinlock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/qspinlock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/paravirt-spinlock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/qspinlock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/arch/x86/include/asm/qrwlock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/asm-generic/qrwlock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/rwlock.h \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/spinlock_api_smp.h \
    $(wildcard include/config/INLINE_SPIN_LOCK) \
    $(wildcard include/config/INLINE_SPIN_LOCK_BH) \
    $(wildcard include/config/INLINE_SPIN_LOCK_IRQ) \
    $(wildcard include/config/INLINE_SPIN_LOCK_IRQSAVE) \
    $(wildcard include/config/INLINE_SPIN_TRYLOCK) \
    $(wildcard include/config/INLINE_SPIN_TRYLOCK_BH) \
    $(wildcard include/config/UNINLINE_SPIN_UNLOCK) \
    $(wildcard include/config/INLINE_SPIN_UNLOCK_BH) \
    $(wildcard include/config/INLINE_SPIN_UNLOCK_IRQ) \
    $(wildcard include/config/INLINE_SPIN_UNLOCK_IRQRESTORE) \
    $(wildcard include/config/GENERIC_LOCKBREAK) \
  /mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f/source/include/linux/rwlock_api_smp.h \
    $(wildcard include/config/INLINE_READ_LOCK) \
    $(wildcard include/config/INLINE_WRITE_LOCK) \
    $(wildcard include/config/INLINE_READ_LOCK_BH) \
    $(wildcard include/config/INLINE_WRITE_LOCK_BH) \
    $(wildcard include/config/INLINE_READ_LOCK_IRQ) \
    $(wildcard include/config/INLINE_WRITE_LOCK_IRQ) \
    $(wildcard include/config/INLINE_READ_LOCK_IRQSAVE) \
    $(wildcard include/config/INLINE_WRITE_LOCK_IRQSAVE) \
    $(wildcard include/config/INLINE_READ_TRYLOCK) \
    $(wildcard include/config/INLINE_WRITE_TRYLOCK) \
    $(wildcard include/config/INLINE_READ_UNLOCK) \
    $(wildcard include/config/INLINE_WRITE_UNLOCK) \
    $(wildcard include/config/INLINE_READ_UNLOCK_BH) \
    $(wildcard include/config/INLINE_WRITE_UNLOCK_BH) \
    $(wildcard include/config/INLINE_READ_UNLOCK_IRQ) \
    $(wildcard include/config/INLINE_WRITE_UNLOCK_IRQ) \
    $(wildcard include/config/INLINE_READ_UNLOCK_IRQRESTORE) \
    $(wildcard include/config/INLINE_WRITE_UNLOCK_IRQRESTORE) \

kernel/kdlock/kernel/source_epoch.o: $(deps_kernel/kdlock/kernel/source_epoch.o)

$(deps_kernel/kdlock/kernel/source_epoch.o):
