# Wiring kdlock into a Linux 7 tree

Nothing here has been applied or built. This is the list of changes the
kernel patch has to make, with [kd_linux_map.h](kd_linux_map.h) as the
symbol-level reference.

## Files

| From this directory tree | To the kernel tree |
| --- | --- |
| `include/kdlock/*.h` | `include/kdlock/` |
| `kernel/*` | `kernel/locking/kdlock/` |

`apply_to_tree.sh <kernel-source>` does this copy and adds the three hooks
the build needs: `source "kernel/locking/kdlock/Kconfig"` in
`kernel/Kconfig.locks`, `obj-$(CONFIG_KDLOCK) += kdlock/` in
`kernel/locking/Makefile`, and `#include <kdlock/kd_api.h>` in
`arch/x86/include/asm/asm-prototypes.h` (symbols exported from assembly need
C prototypes under MODVERSIONS/gendwarfksyms). It does not switch any lock
API over.

## Type replacement

| Native type | Replacement | Size |
| --- | --- | --- |
| `arch_spinlock_t` | `struct kd_spinlock` | 4 |
| `arch_rwlock_t` | `struct kd_rwlock` | 8 |
| `struct mutex` | wrapper around `struct kd_mutex` | 32 |
| `struct rw_semaphore` | wrapper around `struct kd_rwsem` | 40 |

Sizes equal the native ones, so `struct page`, `struct lockref` and other
size-sensitive containers keep their layout. Static initialisers
(`__MUTEX_INITIALIZER`, `__RWSEM_INITIALIZER`, `__ARCH_SPIN_LOCK_UNLOCKED`)
map to the `__KD_*` initialisers in `kd_types.h`.

## API replacement

1. With `CONFIG_KDLOCK`, `kernel/locking/spinlock.c`, `qspinlock.c`,
   `qrwlock.c`, `mutex.c`, `rwsem.c` and `osq_lock.c` are not built. The
   `_raw_*` layer and the mutex/rwsem entry points become the macros in
   `kd_linux_map.h`.
2. Disable every inline lock variant (`CONFIG_INLINE_*`,
   `CONFIG_UNINLINE_SPIN_UNLOCK=y`). A release that is inlined is invisible
   to generated code, and a delegated section would run past its end.
3. `spin_lock*()` on `spinlock_t` maps to the delegable `kd_spin_lock*()`;
   `raw_spin_lock*()` maps to `kd_raw_spin_lock*()`. Both share the release
   functions.
4. Callers of the `arch_spin_*` level (a handful in tracing, printk and
   architecture code) manage preemption themselves. Give them
   `kd_q_trylock_fifo()`/`kd_q_lock_plain()`/`kd_q_unlock()` on
   `&lock->q` (from `kd_internal.h`), which leave the preempt count alone.
5. Not provided and left to follow-up work: `ww_mutex`, `rt_mutex`,
   `percpu_rwsem` internals that reach into `rw_semaphore`, mutex/rwsem
   owner inspection helpers (`mutex_get_owner`, `rwsem_is_contended`,
   optimistic-spin tunables), and `lockref`'s cmpxchg fast path check
   (`arch_spin_value_unlocked` is provided).

## Required configuration

`CONFIG_KDLOCK` depends on: `X86_64`, `SMP`, `!PREEMPT_RT`, no lock
debugging or lockdep, `!TRACE_IRQFLAGS`, `!PARAVIRT_XXL`, `VMAP_STACK`,
`EXECMEM`. `CONFIG_KALLSYMS_ALL` is selected (the translator reads the
exception table bounds from kallsyms).

Call-depth tracking (`retbleed=stuff`) must stay off: the entry stubs and
`kd_resume` leave functions through paths the accounting thunks do not see.

## Per-CPU symbol names

`kd_entry.S` and `kd_image.c` use `__preempt_count`, `current_task`,
`cpu_current_top_of_stack` and `__stack_chk_guard` as separate per-CPU
variables, which is their form since the `pcpu_hot` structure was split up.
On an older tree these are `pcpu_hot` members and the references need the
matching offsets.

## Executable memory

`kd_image.c` reserves image space with `execmem_alloc(EXECMEM_BPF, ...)`,
writes it once and switches it to ROX with `set_memory_rox()`. Check both
against the target tree; if the tree's BPF range is not within rel32 of
kernel text, use the module text type and its write-then-protect helpers.

## Running

```
python3 jit/kd_daemon.py -v        # as root, in the guest
cat /sys/kernel/debug/kdlock_stats
```

The daemon enables delegation on start and disables it on exit. Without
it, all locks behave as plain FIFO queued locks.
