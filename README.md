# kdlock

Kernel-space lock delegation via dynamic binary translation.

kdlock combines [TCLocks](https://github.com/rs3lab/TCLocks) (lock delegation)
with [BCD](https://github.com/zjyiu/BCD) (runtime binary translation) to explore
transparent delegation of contended kernel locks. A combiner core executes
translated critical sections on behalf of queued waiters, aiming to reduce
movement of lock-protected data. Net speedup has not yet been established.

## Idea

```
Problem:  4 cores compete for spin_lock(L) → cache line of L bounces 4 ways

Approach: 1 core (combiner) holds L and batches queued critical sections
          → protected data may remain cache-local during that batch
```

How it works:
1. Kernel lock path calls into a loadable module (hook)
2. Module records the critical-section entry address
3. Userspace daemon translates that code into a JIT sandbox binary
4. Combiner executes the sandbox on behalf of queued waiters

The goal is to leave critical-section source unchanged, not to run on an
unmodified kernel. The current sandbox executes in kernel mode; it is neither
a security boundary nor a transaction with memory rollback.
Recoverable JIT exits should preserve completed effects and resume the original
code at the exit point, as in BCD's ordinary CALL-miss path. Current high-level
fallback still restarts at entry; the gap and target protocol are described in
[DESIGN section 9.6](docs/DESIGN.md#96-bcd-comparison-and-forward-continuation-target).

See [docs/DESIGN.md](docs/DESIGN.md) for the full technical design.

## Status

| Component | State |
|-----------|-------|
| Spinlock delegation | Synthetic modes 0-2 and 6-10 validated; latest mode 9 run did not inject faults |
| Mutex delegation | Native handoff plus opt-in JIT modes 3-5 and 11 validated on test locks |
| Translation pipeline | Daemon, miasm translation, JIT write-back, and execution validated |
| Hot-lock promotion | Functional; timing-sensitive nested promotion needs deterministic tests |
| Architecture scope | x86-64 only; NUMA-aware combining is not enabled |

This is a research prototype. Arbitrary kernel critical sections are not yet
supported safely: partial-execution retry, mixed native/shadow lock users,
concurrent JIT replacement, instruction/flags semantics, and per-CPU execution
context remain correctness gaps. See [docs/TODO.md](docs/TODO.md) for the
ordered implementation and acceptance plan.

## Repository Layout

```
kdlock/
├── kernel_module/     Main kdlock kernel module (kdlock_km.ko)
│   ├── kd_main.c     Module init/exit, hook installation
│   ├── kd_lock.c     Hook implementations (spinlock + mutex)
│   ├── kd_spinlock.c Spinlock delegation protocol
│   ├── kd_mutex.c    Mutex delegation protocol
│   ├── kd_exec.c     Nested execution frames and lock ownership
│   ├── kd_hotlock.c  Bounded hot-lock promotion table
│   ├── exe.c         JIT lookup, execution, and hostcall engine
│   ├── sys.c         /dev/kd_dev char device
├── klock_module/      Test workload module (/dev/lock_dev)
├── daemon/            Userspace translation daemon
├── disassem/          miasm-based kernel text translator
├── include/           Shared headers + wrapper.S
├── docs/              Design, JIT ABI, operations, validation, TODOs
├── bench/             Userspace benchmark driver
└── tests/             Test suite
    ├── unit/          User-space unit tests (no kernel needed)
    └── *.sh           Integration test scripts
```

## Quick Start

Git operations (`git status`, `git diff`, `git diff --check`, commits) run on
the host checkout at `/home/eric/vm/vm-shared/kdlock`. Build and runtime
validation run inside the VM (`ssh -p 2222 root@127.0.0.1`) at
`/root/host_fs/kdlock`.

In normal mode that guest path is the 9p view of the host tree. In recovery
mode it is a guest-local ext4 directory at the same pathname. Do not move or
recursively copy the repository: compare file hashes and use `scp` only for
individual changed files.

### Build

```bash
cd /root/host_fs/kdlock
make -C kernel_module W=1
make -C klock_module W=1
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
cc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c \
  -o bench/klock_test -lpthread
```

### Run

Terminal 1 — load modules:
```bash
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
insmod kernel_module/kdlock_km.ko target_process="klock_test"
insmod klock_module/klock_module.ko
```

Kernel KASLR must already be disabled at boot (`nokaslr`);
`kernel.randomize_va_space=0` only disables userspace ASLR.

Terminal 2 — start daemon:
```bash
cd daemon && ./daemon --mode 2
```

Terminal 1 — run benchmark:
```bash
timeout 120 ./bench/klock_test 4 100000 1000 10 0
```

### Benchmark Modes

| Mode | Lock type | Scenario |
|------|-----------|----------|
| 0 | Spinlock | Contended single lock |
| 1 | Spinlock | Nested locks (A → B) |
| 2 | Spinlock | JIT CS exits to an allowlisted native API and resumes after CALL |
| 3 | Mutex | Contended single lock |
| 4 | Mutex | Nested locks (A → B) |
| 5 | Mutex | API call inside CS |
| 6 | Spinlock | Deep nesting (A -> B -> C) |
| 7 | Spinlock | Out-of-order unlock (unlock A before B) |
| 8 | Spinlock | Independent contention and queues on A and B |
| 9 | Spinlock | Nested recovery topology; fault injection requires the environment flags below |
| 10 | Spinlock | Nested A/B proxy with translated per-CPU GS and logical `current` validation |
| 11 | Mutex | Nested A/B proxy with translated per-CPU GS and logical `current` validation (`mutex_jit=1`) |

### Inspect Results

```bash
dmesg | grep -i "delegation ok\|kd_cs integrity\|begin delegate"
```

## Testing

### Unit And Build Checks

Run inside the VM from `/root/host_fs/kdlock`:

```bash
make -C tests/unit clean >/dev/null && make -C tests/unit run
python3 -m compileall -q disassem tests/unit
make -C kernel_module -j"$(nproc)"
make -C klock_module -j"$(nproc)"
make -C daemon
```

Nine C model binaries plus two Python tests against the actual code generator
cover tail encoding, bounded translation lookup/publication, hot-lock state, spin/mutex node
capacity, explicit nested execution frames, hostcall/call-miss policy, generated
hostcall stubs, GS/current lowering, mutex shadow lookup, and safe draining
during promotion among intercepted users. The C models are not a substitute
for kernel implementation tests. Missing miasm currently makes the Python tests
print `SKIP` and exit successfully; 11/11 is valid only with no skipped tests.

### Default Integration Suite

```bash
bash tests/run_all.sh
```

This runs six scripts covering module load, JIT installation, hot-lock promotion,
spinlock delegation, mutex delegation, and daemon pipeline.

The default suite does not prove translated execution for mutex modes 3/4/5:
`test_05_mutex.sh` deliberately uses `mutex_jit=0` to validate the queue and
handoff protocol without entering the experimental mutex sandbox.

### Modes 0/1/2/3/4/5/10/11 JIT Acceptance

After confirming a recovery snapshot, run:

```bash
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4 5 10 11
```

Selectors may be supplied individually. The workload inside every tested lock is
a multi-field state transition: sequence and sum updates, an odd/even branch, a
rolling rotate/mix, indexed writes to four lanes, multiplication, and a final
commit value. A pass requires the executable part of `jit.S` to retain the
distinctive branch, rotate, multiply, and indexed-memory operations. After the
module unloads, native code replays every per-lock state and requires
`kd_cs integrity: operations=<exact> active_states=<expected> failures=0` in
addition to the exact legacy counter.

A pass also requires complete translation artifacts, kernel write-back, actual
translated completion (`jit_success`), drained queues/frames, and clean kernel
diagnostics. Modes 3/4/5/11 additionally verify that `mutex_jit=1` is active.
The final `install JIT chunk: ... status=0` log records a write attempt, before
the kernel copies its payload. Require checked daemon writes plus runtime
execution evidence; that line alone does not prove completed publication.
The daemon sends `KD_EXE_NORMAL` only on its final chunk, but the kernel has no
complete-image or concurrent-replacement protocol yet.
Modes 2 and 5 also require a named `ktime_get` hostcall stub, no service callee
translation or runtime recompilation, and matching nonzero
exit/execute/resume counters. Mode 5 additionally requires hostcall counts to
equal mutex JIT completion and waiter resume counts under repeated contention.
Modes 10 and 11 require generated code to load both `Stack_RGS` and
`Stack_RCT`, contain no live hardware segment operand, execute that artifact,
and report zero GS/current mismatches.

The latest strengthened regression passed the complete mode set in one run.
Every mode matched its exact transition count and reported zero complex-state
mismatch. Current artifact sizes, commands, counters, and retained logs are in
[docs/VALIDATION.md](docs/VALIDATION.md).

| Mode | `tests/run_all.sh` | Real JIT acceptance |
| --- | --- | --- |
| 0 | Yes, translated spin CS executes | `test_04_spinlock.sh 0` |
| 1 | Yes, translated nested spin CS executes | `test_04_spinlock.sh 1` |
| 2 | Yes, translated spin CS executes around a native hostcall | `test_04_spinlock.sh 2` |
| 3 | No, default uses `mutex_jit=0` | `test_07_mutex_jit.sh` |
| 4 | No, default uses `mutex_jit=0` | `test_08_mutex_jit_modes.sh 4` |
| 5 | No, default uses `mutex_jit=0` | `test_08_mutex_jit_modes.sh 5` |
| 10 | No, recovery-only GS/current contract | `test_04_spinlock.sh 10` |
| 11 | No, default uses `mutex_jit=0` | `test_08_mutex_jit_modes.sh 11` |

Mode 1 executes one translated outer A stream through the nested B lock/unlock
known-call path; B's nested counters prove those boundaries were crossed without
native fallback. Mode 2 exits that stream at an allowlisted time API, executes a
typed native handler while retaining outer-lock ownership, and resumes the same
artifact at the instruction after CALL. Mode 4 forms independent A and B queues
and requires both entry RIPs to execute, including remote B proxy evidence. Mode
5 applies the mode 2 hostcall protocol to a mutex waiter and proves repeated
sandbox exit/resume plus final waiter resume under contention. See
[docs/VALIDATION.md](docs/VALIDATION.md) for the exact latest results and this
distinction.

Modes 10 and 11 validate the x86 kernel segment-context ABI. The two wrapper
inputs remain exactly two machine words: `args[0]` is the original waiter's
kernel GS base and `args[1]` is the logical waiter task. Generic `%gs:` memory
operands are lowered to ordinary addressing through that captured base;
`%gs:current_task` reads the logical task argument. Hardware GS is never
switched to the waiter while the combiner runs, and `%fs:` operands fail closed.
These probes validate addressing and identity for the synthetic workload, not
arbitrary remote per-CPU atomicity or scheduler/IRQ context equivalence.

### Specialized Recovery Tests

```bash
KD_MODE8_NOT_READY=1 bash tests/test_04_spinlock.sh 8
KD_MODE8_NOT_READY=1 KD_SPIN_ABORT_INJECT=1 \
  bash tests/test_04_spinlock.sh 8
KD_SPIN_ABORT_INJECT=1 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=1 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=2 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=3 bash tests/test_04_spinlock.sh 9
bash tests/test_07a_mutex_jit_smoke.sh
bash tests/test_07_mutex_jit.sh
bash tests/test_08_mutex_jit_modes.sh 4
bash tests/test_08_mutex_jit_modes.sh 5
bash tests/test_04_spinlock.sh 10
bash tests/test_08_mutex_jit_modes.sh 11
```

These are intentionally excluded from `tests/run_all.sh`. The injected mode 9
variants exercise lock/frame cleanup and entry retry, not rollback of memory or
native service side effects. The mutex tests explicitly opt into `mutex_jit=1`.

### Recovery VM

The normal VM configuration includes VirtFS and VFIO, so QEMU `savevm` is not
available. For high-risk tests, first check that no other VM is running and
start the VM from the host in recovery mode:

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery
```

After SSH becomes available, use the existing guest-local repository at
`/root/host_fs/kdlock`; compare hashes and sync only changed files before
building and testing. This pathname is not a live host share in recovery mode.

Recovery mode omits VirtFS and VFIO, writes serial output to
`/tmp/qemu-serial.log`, and exposes `/tmp/qemu-monitor.sock`. Connect with
`./run_vm.sh monitor` in a separate host terminal, issue `savevm pre_mutex_jit`,
verify it with `info snapshots`, and use `Ctrl-C` to detach.
Do not issue HMP `quit`, which exits QEMU.

## Module Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_process` | `"kd_test"` | One exact `current->comm` name routed through kdlock hooks |
| `mutex_jit` | 0 | Opt-in translated mutex path for modes 3-5 and 11; keep disabled outside recovery tests |
| `spin_jit_fail_after_nested_lock` | 0 | Inject one failure after nested spin acquisition |
| `jit_hl_fault_after_known_call` | 0 | Inject CALL miss (1), IJ miss (2), or instruction limit (3) |

## Prerequisites

- Patched Linux kernel (6.1.x) with kdlock hook exports
- x86-64 architecture, KASLR disabled
- Python 3 + miasm 0.1.5 (for translator)
- `/proc/kcore` access from daemon

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) - architecture, delegation protocols, and
  sandbox model
- [docs/JIT_REGISTER_ABI.md](docs/JIT_REGISTER_ABI.md) - x86-64 JIT register,
  stack, exit, and continuation ABI
- [docs/AGENTS.md](docs/AGENTS.md) - VM operating procedure and safety rules
- [docs/VALIDATION.md](docs/VALIDATION.md) - latest reproducible execution
  evidence and acceptance contract
- [docs/TODO.md](docs/TODO.md) - unfinished work and known gaps
- [daemon/README.md](daemon/README.md) - daemon options and workspace behavior
