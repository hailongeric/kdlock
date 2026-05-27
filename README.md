# kdlock

kdlock is an experimental kernel-space lock delegation system.  The goal is
to apply the transparent critical-section delegation idea from
[TCLocks](https://github.com/rs3lab/TCLocks) to Linux kernel locks, while using
the dynamic binary translation path from
[BCD](https://github.com/zjyiu/BCD) as the runtime mechanism for packaging and
executing delegated code.

TCLocks delegates a critical section from a waiter to a combiner so the
lock-protected data stays local to the combiner core.  BCD shows how to discover
and translate critical sections dynamically, without rewriting the application
binary.  kdlock moves this direction into kernel space: a patched kernel
spinlock path calls into a loadable module, the module records the kernel
instruction address that should be delegated, a userspace daemon translates that
instruction stream into a sandboxed JIT block, and the kernel module later
executes that block on behalf of waiters.

This repository is a research prototype.  It assumes a kernel that already
contains the kdlock hook points and exports the hook function pointers consumed
by `kernel_module/kd_main.c`.

## Repository Layout

1. `kernel_module/`: main kdlock module.  It registers `/dev/kd_dev`, installs
   the kernel hook callbacks, tracks translated entries, and executes delegated
   code.
1. `klock_module/`: small test module exposing `/dev/lock_dev`.  It creates
   kernel-side `spin_lock` workloads that can be driven from userspace.
1. `daemon/`: userspace daemon that polls `/dev/kd_dev`, runs the dynamic
   translator, and writes generated JIT code back to the kernel module.
1. `disassem/`: Python/miasm-based translator.  It reads kernel text through
   `/proc/kcore`, emits `asm/jit.S`, and produces `asm/jit.bin`.
1. `include/`: shared headers and the assembly wrapper used by translated
   blocks.
1. `bench/`: small userspace driver for `/dev/lock_dev`.
1. `setup.sh`: convenience setup for the test module and a few sysctls.

The local reference trees are expected at `/tmp/TCLocks` and `/tmp/BCD`.

## Architecture

```
                    Patched Kernel
                   ┌──────────────┐
  spin_lock ───────┤ kd_raw_spin_*│──────────────┐
  mutex_lock ──────┤ kd_mutex_*   │              │
                   └──────────────┘              ▼
                                         ┌─────────────┐
                    Userspace            │ kdlock_km.ko│
                  ┌──────────┐           │             │
  /dev/kd_dev ◄───┤ daemon.c │──write──►│ kd_exe_info │
       │          │          │           │ code_block  │
       ▼          │ disassem │           │             │
  /proc/kcore ───►│  .py     │──JIT──┐   │ kd_spinlock │──delegation──►
       │          │ miasm    │       │   │ kd_mutex    │
       │          └──────────┘       │   │ kd_exe_on_* │──JIT sandbox──►
       │                             │   └─────────────┘
       ▼                             │
  disassem + asm/ ───────────────────┘
  wrapper.S → jit.bin
```

### Delegation Paths

| Lock type | Protocol file | Delegation style |
|-----------|-------------|-------------------|
| Raw spinlock | kd_spinlock.c | JIT sandbox via kd_exe_on_call_hl() |
| Mutex | kd_mutex.c | Stack-switch via kd_context_switch() |

### Key Modules

| Component | File(s) | Role |
|-----------|---------|------|
| Hook layer | kd_lock.c | Intercepts kernel lock calls, routes to delegation |
| Spinlock protocol | kd_spinlock.c | TCLocks MCS queue + combiner/waiter + JIT execution |
| Mutex protocol | kd_mutex.c | TCLocks linked-list queue + combiner/waiter |
| JIT engine | exe.c | Manages translated code blocks, executes sandboxes |
| Char device | sys.c | /dev/kd_dev for daemon ↔ kernel communication |
| Daemon | daemon/daemon.c | Polls /dev/kd_dev, invokes translator, writes JIT back |
| Translator | disassem/disassem.py | miasm-based kernel text → JIT assembly translation |
| Sandbox wrapper | include/wrapper.S | Assembly prologue/epilogue for JIT context save/restore |

### Current Status

- **Spinlock delegation**: fully functional.  The combiner executes JIT-translated
  sandbox code for queued waiters.  Tested with modes 0–2.
- **Mutex delegation**: protocol implemented (kd_mutex.c), shadow table wired.
  Basic lock/unlock works; combiner stack-switch delegation functional.
  JIT sandbox integration for mutex is pending (currently does raw stack-switch,
  not translated execution).
- **Futex delegation**: engine present in kd_lock.c; intercepts futex syscalls
  inside translated CS and executes them on behalf of waiters.
- **Dynamic translation**: miasm pipeline functional; supports call-miss and
  indirect-jump-miss recompilation via daemon polling.

## Runtime Model

1. The patched kernel lock path checks whether the current task matches
   `target_process`.
1. On a target raw spinlock or mutex path, the hook in `kdlock_km` observes the
   lock address and return address.
1. Hot lock addresses are promoted to delegation candidates.
1. For a new candidate return address, `exe_add()` allocates executable module
   memory and marks the entry `F_UN_INIT`.
1. `daemon/daemon --mode 2` reads `/dev/kd_dev`, creates a per-entry workspace under
   `daemon/0x.../<tgid>/`, and invokes `disassem/disassem.py`.
1. The translator disassembles kernel text from `/proc/kcore`, wraps the
   translated block with `include/wrapper.S`, and emits `asm/jit.bin`.
1. The daemon writes the binary back through `/dev/kd_dev`; the module copies it
   into the entry's executable code buffer and marks it runnable.
1. The combiner path can call the translated block with a saved `pt_regs`
   context and use the result to continue delegation or fall back.

## VM Workflow

All builds and tests must run inside the VM.  Do not build the modules directly
from the host copy of this directory.

If the VM is not running, start it from the host with the local QEMU script:

```sh
../qemu-scripts/run_vm.sh
```

Then connect to the VM:

```sh
ssh -p 2222 root@127.0.0.1
cd /root/host_fs/kdlock
```

`/root/host_fs/kdlock` in the VM is the same shared directory as this repository
on the host.  Source edits can be made on the host, but compilation, module
loading, daemon execution, and benchmarks should be run from this VM path.

## Prerequisites

Install the normal kernel module build tools and Python dependencies inside the
VM:

```sh
apt-get update
apt-get install -y build-essential gcc make python3 python3-pip binutils \
    linux-headers-$(uname -r)
pip3 install pyelftools future pyparsing==2.4.7 miasm==0.1.5
```

If `miasm==0.1.5` is not available from pip in the VM, install the same miasm
version used by the BCD artifact.

The VM kernel and the kernel build tree used by `make` must include the kdlock
hook patch.  In particular, the kernel lock code must call and export the raw
spinlock and mutex hook pointers used by this module and declared in
`include/kd_lock.h`.

For the mutex path, the patched kernel must export `is_kd`, `kd_mutex_lock`,
`kd_mutex_unlock`, `__mutex_lock_slowpath`, and
`__mutex_unlock_slowpath`.  Both mutex hooks pass
`(lock, ret_rsp, ret_addr)`: `ret_rsp` supplies the saved execution context and
`ret_addr` supplies the translated critical-section entry or the original
unlock caller address.  `kdlock_km` installs callbacks for the hook symbols
during module init and clears them during module exit.

## Build

Build the main module:

```sh
cd /root/host_fs/kdlock/kernel_module
make
```

If the patched kernel build tree is not the VM's
`/lib/modules/$(uname -r)/build`, pass it explicitly:

```sh
make KDIR=/path/to/patched/linux/build
```

Build the test lock device module:

```sh
cd /root/host_fs/kdlock/klock_module
make
```

Build the daemon:

```sh
cd /root/host_fs/kdlock/daemon
make
```

Build the userspace benchmark driver:

```sh
cd /root/host_fs/kdlock
gcc -Iinclude bench/klock_test.c -o bench/klock_test -lpthread
```

## Run A Minimal Test

Use two VM terminals.

Terminal 1 loads the modules:

```sh
cd /root/host_fs/kdlock
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
insmod kernel_module/kdlock_km.ko target_process="klock_test"
insmod klock_module/klock_module.ko
```

`target_process` is matched against `current->comm`, so it should be the process
name that enters the hooked lock path.  For the benchmark built above, use
`klock_test`.

Terminal 2 starts the dynamic translation daemon:

```sh
cd /root/host_fs/kdlock/daemon
./daemon --mode 2
```

The daemon must run from `daemon/`, because it expects the `asm/` template
directory in its current working directory.  It will create transient
directories named like `0xffffffff...`.

Use `./daemon --mode 1` only when you need the old `daemon1.c` workspace layout
under `daemon/0x.../` without the `tgid` subdirectory.

Terminal 1 starts the test workload:

```sh
cd /root/host_fs/kdlock
./bench/klock_test 4 100000 1000 10 0
```

Benchmark modes:

1. `0`: contended single spinlock.
1. `1`: nested spinlocks.
1. `2`: spinlock with a kernel API call inside the critical section.
1. `3`: contended single mutex.
1. `4`: nested mutexes.
1. `5`: mutex with a kernel API call inside the critical section.

Inspect kernel logs after a run:

```sh
dmesg -T | tail -n 100
```

## Module Options

`kernel_module/km.sh` is a helper for reloading `kdlock_km`:

```sh
cd /root/host_fs/kdlock/kernel_module
./km.sh "klock_test"
./km.sh "klock_test" UB
./km.sh "klock_test" DE
./km.sh "klock_test" VW
```

The second argument toggles prototype optimizations:

1. `UB`: disable both `velvet_wait_queue` and `delegate_election`.
1. `DE`: disable `velvet_wait_queue`.
1. `VW`: disable `delegate_election`.

## Stop And Clean

Stop the daemon with `Ctrl-C`, then unload modules:

```sh
rmmod klock_module
rmmod kdlock_km
```

Clean build outputs:

```sh
cd /root/host_fs/kdlock/kernel_module && make clean
cd /root/host_fs/kdlock/klock_module && make clean
cd /root/host_fs/kdlock/daemon && make clean
rm -f /root/host_fs/kdlock/bench/klock_test
```

## Current Limitations

1. The prototype is tied to x86-64 and a patched Linux kernel.
1. Raw spinlock delegation is the primary tested path. The mutex path is wired
   through the same dynamic translation machinery by mapping hot mutex
   addresses to internal shadow qspinlocks.
1. The mutex proxy assumes all participants in a delegated mutex critical
   section enter through the kdlock-patched mutex hooks. Mixing delegated mutex
   users with code paths that bypass the hooks can break mutual exclusion.
1. Dynamic translation currently depends on miasm and `/proc/kcore` access.
1. Unsupported calls or indirect jumps are reported back to the daemon as
   `F_CALL_MISS` or `F_IJ_MISS`; the daemon extends the translation tables and
   recompiles the block.
1. If a lock address is not promoted to delegation, the hook falls back to the
   original kernel lock path.
