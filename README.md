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
Ordinary CALL misses preserve completed effects and resume the original callee
on the waiter, as in BCD. Combiners retain physical locks until native unlock
requests complete the handoff. Other post-entry errors currently fail-stop;
flags and non-CALL continuation remain deferred. The protocol is described in
[DESIGN section 9.6](docs/DESIGN.md#96-bcd-comparison-and-continuation-scope).

See [docs/DESIGN.md](docs/DESIGN.md) for the full technical design.

## Status

| Component | State |
|-----------|-------|
| Spinlock delegation | Synthetic JIT and ordinary CALL-miss continuation; legacy synthetic abort options are disabled |
| Mutex delegation | Original Linux mutex ownership, opt-in JIT, same-combiner nested B, and native-unlock rendezvous |
| Translation pipeline | Daemon, miasm translation, JIT write-back, and execution validated |
| Hot-lock promotion | Functional; timing-sensitive nested promotion needs deterministic tests |
| Architecture scope | x86-64 only; NUMA-aware combining is not enabled |

This is a research prototype. Arbitrary kernel critical sections are not yet
supported safely: non-CALL recovery, spin/native interoperability,
concurrent JIT replacement, instruction/flags semantics, and per-CPU execution
context remain correctness gaps. See [docs/TODO.md](docs/TODO.md) for the
ordered implementation and acceptance plan.

Mutex shadow state now schedules requests only. The combiner acquires the
original Linux mutex and remains its real owner, including during waiter-native
continuation; the waiter sends unlock requests back and waits for acknowledgment.
Native non-target callers use that same mutex. No guest kernel source changes
were added for this protocol; existing hooks and slowpath exports are reused.

## Repository Layout

```
kdlock/
├── kernel_module/     Main kdlock kernel module (kdlock_km.ko)
│   ├── kd_main.c     Module init/exit, hook installation
│   ├── kd_lock.c     Hook implementations (spinlock + mutex)
│   ├── kd_spinlock.c Spinlock delegation protocol
│   ├── kd_mutex.c    Mutex delegation protocol
│   ├── kd_mutex_tasks.c In-flight task routing across rename/continuation
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
| 9 | Spinlock | Nested recovery topology; legacy synthetic fault injection is disabled |
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
hostcall stubs, GS/current lowering, mutex shadow lookup, and original-mutex
ownership across promotion, continuation, rename and queue handoff. The C models
are not a substitute for kernel implementation tests. Missing miasm currently makes the Python tests
print `SKIP` and exit successfully; 11/11 is valid only with no skipped tests.

### Default Integration Suite

```bash
bash tests/run_all.sh
```

This runs six scripts covering module load, JIT installation, hot-lock promotion,
spinlock delegation, mutex delegation, and daemon pipeline.

The default suite does not prove translated execution for mutex modes 3/4/5:
`test_05_mutex.sh` deliberately uses `mutex_jit=0`. Even after promotion, this
setting uses the original native mutex without entering the delegation queue.

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

Acceptance is recorded per command and source version, not inferred from
artifact generation or earlier runs. Current artifact sizes, commands,
counters, and retained logs are in
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
artifact at the instruction after CALL. Mode 4 runs B in the same translated A
stream: A's combiner acquires native B, waits if contended, and resumes JIT.
`nested_queued>0` and `nested_jit>0` prove contention and resumed B execution;
mutex B no longer uses a virtual waiter or remote combiner. Mode
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
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 0 1
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 3 1
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 1 2
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 4 2
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 8 2
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 1 3
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 4 3
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_10_native_resume.sh 8 3
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_PINNED=1 \
  bash tests/test_10_native_resume.sh 3 1
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_RENAME=1 \
  bash tests/test_10_native_resume.sh 4 3
KDLOCK_RECOVERY_CONFIRMED=1 KD_NATIVE_MIXED=1 \
  bash tests/test_10_native_resume.sh 3 1
bash tests/test_11_mutex_native_protocol.sh 0
KDLOCK_RECOVERY_CONFIRMED=1 bash tests/test_11_mutex_native_protocol.sh 1
bash tests/test_07a_mutex_jit_smoke.sh
bash tests/test_07_mutex_jit.sh
bash tests/test_08_mutex_jit_modes.sh 4
bash tests/test_08_mutex_jit_modes.sh 5
bash tests/test_04_spinlock.sh 10
bash tests/test_08_mutex_jit_modes.sh 11
```

These are excluded from `tests/run_all.sh`. Native-resume stage 1 covers single
locks, stage 2 exits after B unlock, and stage 3 exits while B is held. The test
stops the daemon before execution, requires a real miss at its native probe,
checks per-request before/call/after records, and verifies frame/queue draining.
Mutex tests explicitly use `mutex_jit=1`. Legacy `KD_SPIN_ABORT_INJECT` and
`KD_JIT_FAULT_KIND` options are rejected by `test_04`: those synthetic exits do
not model precise CALL state and now reach fail-stop, not entry retry.

`test_11` races targeted and non-targeted workers using plain lock, trylock,
interruptible and killable native APIs, checks an in-CS exclusion guard and
exact state replay, and exercises task-record allocation failure plus waiter
slot exhaustion. Successful native APIs are tested; signal cancellation is not
yet injected. `KD_TEST_MIXED=1` selects these test worker roles;
`KD_TEST_COMM=<name>` names every worker instead of the default comm.

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
| `target_process` | `"kd_test"` | Exact eligible task comm; active mutex tasks stay routed through unlock after rename |
| `mutex_jit` | 0 | 0 uses original native mutex; 1 enables delegation for eligible requests, recovery-only |
| `mutex_task_fail_once` | 0 | Test-only: 1 fails the next mutex task-record allocation and resets to 0 |
| `spin_jit_fail_after_nested_lock` | 0 | Legacy synthetic failure after nested spin acquisition; post-entry fail-stop |
| `jit_hl_fault_after_known_call` | 0 | Legacy synthetic CALL/IJ/limit exit (1/2/3); post-entry fail-stop |

The test workload module has a separate read-only `native_resume_stage`
parameter: `0` disables the probe, `1` places it inside a single lock, `2` after
B unlock, and `3` while B is held. `test_10_native_resume.sh` sets this parameter
and checks distinct request records. `KD_NATIVE_PINNED=1` adds the mode 3 case
with a CPU-0 holder and four CPU-1 waiters.
`KD_NATIVE_RENAME=1` arms the test-only writable `native_resume_rename=1`
after promotion and translation, so rename/task-lock traffic cannot redirect
the shared hot-lock sampling window. The probe
changes the native waiter's comm while it borrows a combiner-owned mutex, then
restores it after unlock. In-flight task routing must still complete its unlocks.
`KD_NATIVE_MIXED=1` adds native non-target participants to mode 3 stage 1;
it cannot be combined with rename or pinning in this harness.

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
