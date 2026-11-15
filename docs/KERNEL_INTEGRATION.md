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
| `mm->mmap_lock` switched to kdlock (`CONFIG_KDLOCK_MM`, section 4a) | **done** (build #43): every mmap lock operation of the kernel goes through kdlock for mms created while `kd_mm=1`; will-it-scale mmap1 runs, writers are delegated, data-checked stress and the nano correctness pass are clean |
| Syscall-path lock objects switchable (`CONFIG_KDLOCK_API`, section 4b) | **done** (build #45): `file_lock`, `flc_lock`, pipe mutex, `f_pos_lock`, `simple_xattrs.lock`, `uts_sem`, for all their kernel users; data-checked syscall stress and a native/kd build comparison clean (`bench/results/kdclaude/api-20261113/`) |
| Whole kernel lock API switched to kdlock (`kd_linux_map.h` applied) | **no**. Only the objects above and the mmap lock are switchable; every other kernel lock is native |
| Per-subsystem lock objects converted | the mmap lock and the six objects of 4b |

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

## 4a. The mmap lock (`CONFIG_KDLOCK_MM`)

This is the scope TCLocks used for will-it-scale mmap1: the lock of
`mm_struct` is replaced, nothing else. TCLocks replaced `rw_semaphore`
throughout its 5.14 kernel; here only `mm->mmap_lock` changes, so every
other lock in an mmap critical section stays native.

**Source changes.** `integration/apply_to_tree.sh` runs
`integration/apply_mm.py`, which adds one `#elif defined(CONFIG_KDLOCK_MM)`
branch to two headers of the 7.0 tree, beside the earlier adapter's
`CONFIG_KDLOCK_MMAP` branch (which this tree already carries and which stays
off):

* `include/linux/mm_types.h`: `mmap_lock` becomes `struct kd_mm_lock`
  (`include/kdlock/kd_mm_types.h`): a union of the native `rw_semaphore` and
  a `struct kd_rwsem`, plus the choice.
* `include/linux/mmap_lock.h`: its `__mmap_sem_*` indirection maps to the
  inline functions of `include/kdlock/kd_mm.h`, and `mmap_destroy_lock()`
  checks that a kdlock mmap lock is idle when the mm is freed.

No MM function body changes. Every user of the mmap lock already goes
through `mmap_lock.h` (`mmap_write_lock*`, `mmap_read_*`, the per-VMA lock
fallbacks, BPF's deferred `mmap_read_unlock_non_owner`); the remaining
direct references are lockdep-only and compile to nothing here.

**Per-mm choice.** `kd_mm_init()` (`kernel/kd_mm.c`) picks the backend when
an mm is created, from the core parameter `kd_mm` (0 native, default; 1
kdlock), and it never changes for that mm. Static mms (`init_mm`, `efi_mm`)
stay native. A process started after the parameter changed gets the other
backend, so Native and kdlock runs alternate within one boot; the runner
does exactly that.

**Why inline.** A delegable acquisition is keyed by its call site, so
`kd_down_write*()` must be called from the code that holds the lock. With an
out-of-line wrapper every mmap writer would share one site, one image and one
usefulness account (munmap's planned handbacks would switch mmap off). The
release must likewise be a direct call to `kd_up_write()` there.

**What is delegated.** Contended writers: `mmap`, `munmap`, `mprotect`,
`mremap`, `brk`, `fork` (the parent's lock), and the rest. Readers stay
local. munmap downgrades to a read hold before it unmaps. The write part
is delegated; from build #67 the combiner keeps the write side at the
downgrade and executes the read part as well, until the release of the
read hold or the first frontier (`kd_vdown`, LOCKS 5). At a frontier the
downgrade is done for real and the remainder goes back to the caller,
which counts as useful for the site. With `kd_vdown=0` the downgrade itself
hands the remainder back (`hb_downgrade`). Inside a
section, the following are handed back to the caller rather than run on the
lock holder's CPU (TRANSLATOR frontier list): native sleeping-lock acquires
(`down_write` of `anon_vma` and `i_mmap_rwsem`, `mutex_lock`, ...), TLB
shootdowns and cross-CPU calls, `schedule`. Native spinlocks inside a
section are called directly. [MMAP_LOCKS.md](MMAP_LOCKS.md) goes through every
lock of the mmap write section, says which ones kdlock could own and which are
not locks at all, and attaches the will-it-scale counters to each case; the
short version is that `mapping->i_mmap_rwsem` is what stops `mmap2`
(0.78-0.86 of Native, every session handed back at the frontier) and
`anon_vma->root->rwsem` is what stops the ordinary merging anon case.

**Translator policy for this kernel.** Images for the mmap paths copy the
memory allocator, maple tree and VMA code: about 50 000 instructions per
site after learning. The daemon runs with `max_insns` 250 000
(`--config`, `{"max_insns": 250000}`).

**Kernel ABI.** `mm_struct` changes size, so every module must be rebuilt
and installed with the kernel (`modules_install`); a kernel booted with the
old modules cannot mount `/boot/efi` (`module_layout` mismatch).

## 4b. Switchable lock objects on syscall paths (`CONFIG_KDLOCK_API`)

The lock objects behind the micro/API syscall workloads (the earlier
project's BENCHMARK_WORKLOADS, tag `full-tree-before-cleanup-20261115`:
OFD, setfd, pipe, seek, UTS, xattr) are converted
the same way as the mmap lock, for every kernel user of each object:

| Field | Native type | Workload system calls |
| --- | --- | --- |
| `files_struct.file_lock` | `spinlock_t` | `fcntl(F_SETFD)`, open, close, dup, fork |
| `file_lock_context.flc_lock` | `spinlock_t` | `fcntl(F_OFD_GETLK/SETLK)`, flock, leases |
| `pipe_inode_info.mutex` | `struct mutex` | pipe read/write, `FIONREAD`, `F_GETPIPE_SZ`, splice |
| `file.f_pos_lock` | `struct mutex` | read/write/lseek on a shared file |
| `simple_xattrs.lock` | `rwlock_t` | tmpfs/kernfs `getxattr`/`setxattr` |
| `uts_sem` | `rw_semaphore` | `uname`, `sethostname`, UTS sysctls |

**Source changes** (`integration/apply_api.py`, run by `apply_to_tree.sh`):

* the six field declarations change type, each inside `#ifdef
  CONFIG_KDLOCK_API` with the native line in the `#else` branch, plus the two
  static initialisers (`init_files`, `uts_sem`);
* `linux/spinlock.h`, `linux/mutex.h` and `linux/rwsem.h` include
  `include/kdlock/kd_sw_{spin,mutex,rwsem}.h` at their end;
* `kernel/locking/mutex.c` and `rwsem.c`, which define the native functions,
  set `KD_SW_NO_DISPATCH`.

No call site changes. The headers make each lock API name (`spin_lock`,
`mutex_lock`, `down_write`, `read_lock`, the `_irq/_bh/_irqsave/_nested`
forms, trylocks, init, `is_locked`, asserts) a `_Generic` dispatch: a
pointer to a switchable object selects the `kd_sw_*` inline operation,
any other argument the native function exactly as before. Because the field
type changed, any native-only interface applied to a converted field (one
the dispatch does not cover, e.g. a lock guard class) fails to compile, so
the build itself checks that every user of an object follows one protocol.
The whole 7.0 tree with the Ubuntu configuration (all modules, including
nfsd, ceph, smb, fuse) built without a change, which also means none of
those users needed a guard class.

**Per-object choice.** A switchable object is a union of the native lock
and the kdlock one plus a `use_kd` flag, set by the object's init call from
the core parameter `kd_api` (bit mask: 1 spinlock_t, 2 rwlock_t, 4 mutex,
8 rw_semaphore; default 0) and never changed. Zero-filled objects are native
and unlocked. `uts_sem` is static and taken by system calls at any moment,
so it follows the boot parameter `kd_uts=1` instead, applied in an initcall
before any user task exists (`kernel/kd_sw.c`).

**What delegates.** spinlock_t and mutex sections and rwlock/rwsem write
sections, as for any kdlock object. Readers run locally. Sections that copy
to or from user memory hand back at the copy (the `f_pos_lock` section is a
whole `read()`), so those objects stay in the plain path.

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
