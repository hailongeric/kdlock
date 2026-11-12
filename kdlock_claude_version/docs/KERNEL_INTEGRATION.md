# Kernel integration

What it takes to put kdlock into a Linux 7 (x86_64, non-RT) kernel, what has
been done, and what has not. The symbol-level mapping of the Linux lock API is
in `integration/kd_linux_map.h`; this page is the procedure and the status.

## 1. Status

| Step | State |
| --- | --- |
| kdlock directory builds in (`CONFIG_KDLOCK=y`) | **done**: compiled and objtool-checked in the VM, all undefined symbols resolve |
| Whole kernel with kdlock built in links | **done**: `7.0.0-38-kdclaude1` (vmlinux, bzImage, modules) built in the VM; 138 `kd_` symbols in vmlinux |
| Booted | **yes**, in the `kdclaude` VM next to `kdlock1` (one-shot `grub-reboot`); see BUILD_AND_TEST.md |
| Kernel lock API switched to kdlock (`kd_linux_map.h` applied) | **no**. Today only the directory is built in; no kernel code calls `kd_*`. Benchmarks and tests call `kd_*` directly |
| Per-subsystem lock objects converted | no |

## 2. Placing the code

`integration/apply_to_tree.sh <kernel-source>` copies `include/kdlock/*.h` to
`include/kdlock/` and `kernel/*` to `kernel/locking/kdlock/`, and adds three
hooks (idempotent):

* `source "kernel/locking/kdlock/Kconfig"` in `kernel/Kconfig.locks`;
* `obj-$(CONFIG_KDLOCK) += kdlock/` in `kernel/locking/Makefile`;
* `#include <kdlock/kd_api.h>` in `arch/x86/include/asm/asm-prototypes.h`
  (symbols exported from assembly need C prototypes under
  MODVERSIONS/gendwarfksyms).

## 3. Configuration

`CONFIG_KDLOCK` (bool, built in only) depends on: `X86_64`, `SMP`,
`!PREEMPT_RT`, `!DEBUG_SPINLOCK`, `!DEBUG_MUTEXES`, `!DEBUG_RWSEMS`,
`!DEBUG_LOCK_ALLOC`, `!LOCKDEP`, `!TRACE_IRQFLAGS`, `!PARAVIRT_XXL`,
`VMAP_STACK`, `EXECMEM`; it selects `KALLSYMS_ALL`. `NR_CPUS` must stay below
16384 (queue tail encoding).

Notes found while building:

* Ubuntu's configuration enables `PARAVIRT_XXL` through `XEN_PV`. The check
  configuration disables `XEN_PV`, `XEN_PVHVM_GUEST` and `PARAVIRT_XXL`.
* Call-depth tracking (`retbleed=stuff`) must stay off: the entry stubs and
  `kd_resume` leave functions through paths the accounting thunks do not see.
* Boot with `nopvspin` (as the project's VM policy already does).
* `CONFIG_INLINE_*` lock variants off and `CONFIG_UNINLINE_SPIN_UNLOCK=y`, so
  every release is an out-of-line call.

## 4. Replacing the lock API (not done)

Rules (from `kd_linux_map.h`):

1. Every lock operation is an out-of-line call to a `kd_` symbol, releases
   included.
2. `spinlock_t`, `rwlock_t`, `struct mutex` and `struct rw_semaphore` users get
   the delegable entries. `raw_spinlock_t` users get `kd_raw_*`, which never
   publish a continuation (scheduler, timers, interrupt paths).
3. With `CONFIG_KDLOCK`, `kernel/locking/{spinlock,qspinlock,qrwlock,mutex,
   rwsem,osq_lock}.c` are not built; the `_raw_*` layer and the
   mutex/rwsem entry points become the macros in `kd_linux_map.h`.

Type replacement (sizes equal native, so size-sensitive containers keep their
layout):

| Native | Replacement | Size |
| --- | --- | ---: |
| `arch_spinlock_t` | `struct kd_spinlock` | 4 |
| `arch_rwlock_t` | `struct kd_rwlock` | 8 |
| `struct mutex` | wrapper around `struct kd_mutex` | 32 |
| `struct rw_semaphore` | wrapper around `struct kd_rwsem` | 40 |

Static initialisers (`__MUTEX_INITIALIZER`, `__RWSEM_INITIALIZER`,
`__ARCH_SPIN_LOCK_UNLOCKED`) map to the `__KD_*` initialisers.

`arch_spin_*` and `arch_read/write_*` callers (tracing, printk, architecture
code) manage preemption themselves; they map to `kd_arch_*`, which leave the
preempt count alone and never publish.

### API coverage

`kd_linux_map.h` has a counterpart for every operation the Linux 7.0 headers
declare for `spinlock_t`, `raw_spinlock_t`, `rwlock_t`, `struct mutex`,
`struct ww_mutex` and `struct rw_semaphore`, including the `arch_` level, the
trylock/interrupt combinations, `mutex_lock_io`, the lockdep aliases, the
reader `_non_owner` forms and the state helpers (see LOCKS.md 1). The list
was taken from the 7.0 headers in the VM, and each kd variant is exercised by
the bench module's API test. It has not been compiled into a switched kernel.

### Not provided

`rwsem_owner` and the optimistic-spin tunables (no counterpart: readers and
write holders record no owner), `lockref`'s cmpxchg fast path check beyond
`arch_spin_value_unlocked`, lockdep and debug lock checks. `rt_mutex`,
`percpu_rwsem`, `semaphore`, `local_lock`, `bit_spin_lock` and seqlocks need
nothing: they are built on raw spinlocks or on the operations above.

## 5. Symbols and memory the code depends on

* Per-CPU variables `__preempt_count`, `current_task`,
  `cpu_current_top_of_stack`, `__stack_chk_guard` (separate variables in
  Linux 7; `pcpu_hot` members in older trees need matching offsets). The
  build and link resolved them; their runtime values are unchecked.
* `execmem_alloc(EXECMEM_BPF, ...)` + `set_memory_rox()` for image memory.
  The range must be within rel32 of kernel text; otherwise use the module
  text type.
* `wake_q_add`, `owner_on_cpu` and scheduler helpers for the mutex.

## 6. Scope of kernel use for the project goal

* **Stage 1 (nano/micro):** needs only the built-in directory and callers of
  `kd_*`: `bench/kd_bench.ko` is enough.
* **Stage 2/3 (mmap1, real syscalls):** needs the lock API switch above for at
  least `mm->mmap_lock` (rwsem writers delegable, readers local), plus the
  other objects the workload contends on. Native MM bodies and the real
  syscall path stay unchanged; only lock calls and lock objects are replaced.
