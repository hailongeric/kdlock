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
| Whole kernel lock API switched to kdlock (`CONFIG_KDLOCK_ALL`, section 4d) | **built, booted and tested with delegation off, then with delegation for allow-listed lock users and against a native twin** (2026-11-17, `7.0.0-38-kdall1` to `kdall3`; end of section 4d): every spinlock, raw spinlock, rwlock, mutex, ww_mutex and rwsem is a kd lock; locktorture, syscall stress, will-it-scale and the bench correctness pass clean (`bench/results/kdclaude/kdall-20261117-64cpu/`). Delegation on for the whole kernel: not safe, section 4c |
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
the bench module's API test. Section 4d compiles it into a switched kernel
(by casts and macros of its own rather than this header).

### Not provided

`rwsem_owner` and the optimistic-spin tunables (no counterpart: readers and
write holders record no owner), `lockref`'s cmpxchg fast path check beyond
`arch_spin_value_unlocked`, lockdep and debug lock checks. `rt_mutex`,
`percpu_rwsem`, `semaphore`, `local_lock`, `bit_spin_lock` and seqlocks need
nothing: they are built on raw spinlocks or on the operations above.

## 4c. Would a kernel with every lock switched run?

The question the user asked on 2026-11-16, analysed from the Linux 7.0
source in the VM, this kernel's configuration and the limits the
implementation states itself (ARCHITECTURE 11, DIFFERENCES D3). Layer 2
was then built and run (section 4d). The answer
has three layers, and each depends on the one before it.

**1. Building it: work, no obstacle found.** The type sizes match (4, 8, 32,
40 bytes), static initialisers have counterparts, and every operation the 7.0
headers declare has a mapping. The search found these users of the native
lock internals outside `kernel/locking/` (x86 and generic code):

| Where | What it relies on | What it needs |
|---|---|---|
| `arch/x86/include/asm/qspinlock*.h`, `CONFIG_PARAVIRT_SPINLOCKS=y` | the paravirt slow path and unlock, `virt_spin_lock()` | configured out; the switch replaces `queued_spin_*` |
| `kernel/bpf/rqspinlock.c` (BPF's resilient lock) | its own copy of the qspinlock algorithm on `struct qspinlock` with its own per-CPU nodes; not `arch_spinlock_t` | keeps compiling against the qspinlock headers after rule 3 drops `qspinlock.c`; stays native |
| `kernel/trace/{ring_buffer,trace,trace_clock,...}.c`, `kernel/rcu/tree.c`, `arch/x86/kernel/{dumpstack,tsc_sync,hpet}.c`, `bpf_spin_lock` | `arch_spin_lock()` with interrupts off, the oops path also in NMI | `kd_arch_*` (no preempt count change, never publish); an NMI past four nested nodes spins on the lock word (`kd_core.c`, `idx >= KD_MAX_NODES`) as qspinlock does |
| `kernel/hung_task.c:153,160` (`CONFIG_DETECT_HUNG_TASK_BLOCKER=y`) | `mutex_get_owner()`, `rwsem_owner()` | `kd_mutex_get_owner()`; a kd rwsem has no owner, so the detector names no blocker for it (diagnostics only) |
| `kernel/sched/core.c:6634` | `__mutex_owner()` | only with `CONFIG_SCHED_PROXY_EXEC`, which is off |

**2. Running it with delegation off: the realistic first step.** Without
the translator, or with `KD_IOC_ENABLE` off, every lock is a plain queued
lock, which is the same algorithm as qspinlock with a different word layout.
Nothing in that mode depends on task identity or on running another task's
code. What is not tested even in this mode (ARCHITECTURE 11.1): interrupt
and NMI paths at scale, CPU hotplug, signals. Stack traces through the
entry stubs stop early (11.6), which also matters for livepatch's
reliable-stack check and BPF stack maps, not for booting. Every release
becomes an out-of-line call (`CONFIG_UNINLINE_SPIN_UNLOCK`). The kernel's
own `locktorture` module (`CONFIG_LOCK_TORTURE_TEST`) exercises spinlock,
rwlock, mutex and rwsem through the ordinary API and would be the
correctness check for this step.

**3. Running it with delegation on for every lock: not today.** Today
delegation is reached only by the mmap lock and the six objects of 4b, whose
sections were measured and checked one by one. For the whole kernel, three
stated limits change from "not observed" to "certain to happen":

* **Text patching is not followed** (ARCHITECTURE 11.4). An image is a
  copy of the text as it was when it was translated. In a whole kernel,
  jump labels and static calls change at run time: every tracepoint that is
  enabled or disabled, `static_branch` keys of cgroup, memcg, scheduler and
  networking features, `PREEMPT_DYNAMIC` (static calls, `CONFIG_PREEMPT_DYNAMIC=y`
  here), ftrace, kprobes and livepatch. An image translated before the change
  keeps running the old branch. A tracepoint missing from a delegated section
  is harmless. A feature key that changes what a section does is a
  correctness error. An `int3` that a kprobe or `text_poke_bp()` left in the
  text at translation time is a frontier, so that case only costs a
  handback. The fix is a kernel hook in the text-patching paths that drops
  images whose source range covers the patched address, the way a module
  unload drops images now.
* **Per-CPU data is the executor's** (DIFFERENCES D3, ARCHITECTURE 11.2).
  Only `current`, the stack canary and the stack top are redirected. Counters
  and caches kept consistent by the lock are correct on any CPU. A section
  that relies on running on the origin's CPU is wrong: one that records
  `smp_processor_id()`, uses a per-CPU pointer taken before the lock after a
  handback, or updates per-CPU state that the origin's code around the lock
  assumes only it touches. Across the whole kernel that cannot be audited by
  hand. The translator would have to report or stop at `%gs` accesses to
  per-CPU symbols it has no rule for.
* **Task fields written through `current`** (11.7): `pagefault_disable()`
  and `migrate_disable()` inside a section are the known candidates.

Two more limits become costs. Module load and unload drop every image
(11.5), and a booting system loads modules continuously. The translator
handles one site at a time with up to 250 000 copied instructions (4a); the
vmlinux of build #84 alone, without modules, has about 13 400 direct
acquire call sites (`objdump`): 6 933 spinlock calls, `raw_spinlock_t`
included, of which 3 229 are `_irq`/`_irqsave` forms that execute locally
anyway; 461 rwlock; 4 815 mutex; 1 204 rwsem.

**What replacement costs where it does not delegate.** Replacing a lock pays
only where its sections delegate. Where they hand back, the replacement
costs (MMAP_LOCKS 3: `mmap2` 0.78-0.86 of Native, every session handed back
at `i_mmap_rwsem`; `page_fault1` 0.84-0.91 from reader spinning). A
whole-kernel switch therefore also depends on the per-site usefulness account
turning delegation off where it does not pay.

**Order of work** if this is pursued:

1. The switched kernel with delegation off: build, boot, `locktorture`, and
   the nano correctness runs. This establishes the plain path for every
   kernel user.
2. Images follow text patching (drop on `text_poke`).
3. The translator classifies `%gs` accesses: the three redirected ones, a
   list of symbols known to be correct on any CPU (statistics counters), and
   a frontier for everything else.
4. Delegation enabled by an allow list of lock objects or sites, extended as
   their sections are checked, as for the mmap lock and the objects of 4b.

## 4d. The switched kernel, delegation off (`CONFIG_KDLOCK_ALL`)

Step 1 of 4c's order of work, done on 2026-11-17. `integration/apply_all.py`
(run by `apply_to_tree.sh`) makes every edit inside `#ifdef
CONFIG_KDLOCK_ALL`, so a tree with the option off is unchanged.

**How each lock type is switched.** No lock user changes; only lock
headers, three files that read native lock internals, and the locking
Makefile.

| Native | With `KDLOCK_ALL` | Where |
|---|---|---|
| `arch_spinlock_t` (qspinlock) | type kept: the kd queue word has the same layout; `queued_spin_lock()` is `kd_arch_spin_lock()`, so every `raw_spinlock_t` and every direct `arch_spin_lock()` user takes the kd queue algorithm; trylock and unlock are the same operations for both | `asm-generic/qspinlock.h` |
| `arch_rwlock_t` (qrwlock) | type kept (same count word, bias and writer bits); `arch_read_lock()`/`arch_write_lock()` are the kd ones | `asm-generic/qrwlock.h` |
| `spinlock_t`, `rwlock_t` operations | macros calling the kd entries from the caller's code (`kd_spin_lock*()`, `kd_write_lock*()` delegable; readers local), defined before the lock guard classes so guards use them too | `include/kdlock/kd_all_spin.h`, included by `linux/spinlock.h` |
| `struct mutex` | `{ struct kd_mutex kd; }`, 32 bytes; operations are macros to `kd_mutex_*()` | `linux/mutex_types.h`, `include/kdlock/kd_all_mutex.h` |
| `struct rw_semaphore` | `{ struct kd_rwsem kd; }`, 40 bytes; state tests and initialisers replaced, operations macros to `kd_*()` | `linux/rwsem.h`, `include/kdlock/kd_all_rwsem*.h` |
| `struct ww_mutex` | definition kept (layout of `kd_ww_mutex`); the native function names call `kd_ww_mutex_*()` (wait-die for every class) | `kernel/kd_all.c` |
| `kernel/locking/mutex.c`, `rwsem.c` | not built; `kernel/kd_all.c` defines their function names (for address-taken uses and the inline helpers), the `lock:contention_*` tracepoints they instantiated, and static asserts on every layout the casts rely on | `kernel/locking/Makefile` |

Because the mutex and rwsem types lose their native fields, the compiler
finds every reader of native lock internals. In the whole Ubuntu
configuration (vmlinux and 6 707 modules) it found three, all outside lock
users proper: the `task->blocked_on` helpers of `linux/sched.h` (they name
the mutex's `wait_lock`; with kd nothing sets `blocked_on`, so they become
plain accessors), `__mutex_owner()` in `kernel/locking/mutex.h` (included
by the scheduler for proxy execution; it returns the kd mutex's logical
owner), and the lock tracepoints above. No driver or filesystem needed a
change.

**Configuration.** `KDLOCK_ALL` depends on `!KDLOCK_MM`, `!KDLOCK_API`
(both switch single objects and are pointless here), `!PARAVIRT_SPINLOCKS`
(its slow path and unlock would bypass the redirected level),
`!DETECT_HUNG_TASK_BLOCKER` (reads native owner words) and
`!SCHED_PROXY_EXEC` (follows `blocked_on` to the native owner).

**Results** (`bench/results/kdclaude/kdall-20261117-64cpu/`):

* The vmlinux calls 29 318 kd entries directly; nothing calls a native
  mutex, rwsem, qspinlock or qrwlock slow path.
* It boots on the 64-vCPU VM, reaches `multi-user`, ran three boots and
  shut down cleanly each time, without a kernel complaint.
* locktorture: all 11 lock types `SUCCESS` (60 s each, 128 writer threads);
  the deliberately broken `lock_busted` fails, as on the native kernel.
* The data-checked syscall stress, will-it-scale with page checks (64
  workers, threads and processes), a defconfig kernel build and the bench
  module's correctness pass (442 points) are clean.
* test-ww_mutex's wound-wait stress fails here and on the native kernel
  alike: the test reports an `-EDEADLK` that arrives after its timeout.

**What this does not show.** Nothing was delegated (no translator), so
4c's layer 3 is untouched. No performance result: native and kd cannot run
in one boot of a switched kernel, and the cross-boot indicators compare two
different kernels. They do point at two losses worth a matched study:
ww_mutex (0.31 of the native kernel's locktorture writes, and 6-17 times
fewer test-ww_mutex rounds) and rwsem under locktorture (0.50, with one
writer thread at about a quarter of the native minimum). Interrupt and NMI
paths were exercised only by the ordinary load; CPU hotplug was not tested.

**Since then (2026-11-17).**

- **Delegation by allow list.** Delegation is switched on lock user by
  lock user (`jit/kd_daemon.py --allow`, `bench/allow/`): the syscall-path
  locks, locktorture, and the mmap lock writers of brk, mmap and munmap
  (`bench/results/kdclaude/kdall-deleg-20261117-64cpu/`).
- **A matched comparison with native.** The native side is the same tree
  and configuration built with `CONFIG_KDLOCK_ALL` off (`kdnat1`); every
  edit of this section is inside `#ifdef CONFIG_KDLOCK_ALL`. The two kernels
  alternate over 3 boots each
  (`bench/results/kdclaude/kdall-native-20261117-64cpu/`).
  - **Gains with delegation:** up to 9.3x on the syscall-path locks, and
    1.06-2.45x on will-it-scale mmap1, mmap2 and brk1.
  - **Page faults:** parity, including a new 10 GB random-order fault
    benchmark.
  - **ww_mutex:** from 0.23 to 0.66 of native (spin phase, LOCKS 1).
  - **Mutex queue in plain mode:** from 0.82-1.00 to 1.02-1.75 of native
    on seek and pipe (node order, ARCHITECTURE 7a).
  - **Still behind:** locktorture rwsem (0.53-0.61), ww_mutex (0.66),
    page_fault_shared3 at 32 threads (0.83), page_fault1 at 16 threads
    (0.81), and the rwsem writers in plain mode (xattr 0.92-0.97).

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
