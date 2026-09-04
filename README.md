# kdlock

Kernel-space lock delegation via dynamic binary translation.

kdlock combines [TCLocks](https://github.com/rs3lab/TCLocks) (lock delegation)
with [BCD](https://github.com/zjyiu/BCD) (runtime binary translation) to
automatically accelerate contended kernel locks. A combiner core executes
translated critical sections on behalf of queued waiters, keeping lock-protected
data cache-local and eliminating cross-core cache-line bouncing.

## Idea

```
Problem:  4 cores compete for spin_lock(L) → cache line of L bounces 4 ways

Solution: 1 core (combiner) holds L, executes all 4 critical sections locally
          → lock-protected data never leaves the combiner's L1 cache
```

How it works:
1. Kernel lock path calls into a loadable module (hook)
2. Module records the critical-section entry address
3. Userspace daemon translates that code into a JIT sandbox binary
4. Combiner executes the sandbox on behalf of queued waiters

See [docs/DESIGN.md](docs/DESIGN.md) for the full technical design.

## Status

| Component | State |
|-----------|-------|
| Spinlock delegation (modes 0-2, 6-9) | Working; nested JIT and bounded recovery validated |
| Mutex delegation protocol (modes 3-5) | Safe mode working; bounded JIT modes 3/4/5 confirmed in recovery VM |
| Dynamic translation (daemon + miasm) | Working |
| Hot-lock promotion | Working |
| Nested spinlock handling | TCLock-style JIT delegation, recursive frames, OOO handoff, and native retry |
| NUMA-aware combining | Not yet enabled |
| ARM64 | Not supported |

## Repository Layout

```
kdlock/
├── kernel_module/     Main kdlock kernel module (kdlock_km.ko)
│   ├── kd_main.c     Module init/exit, hook installation
│   ├── kd_lock.c     Hook implementations (spinlock + mutex)
│   ├── kd_spinlock.c Spinlock delegation protocol
│   ├── kd_mutex.c    Mutex delegation protocol
│   ├── exe.c         JIT execution engine
│   ├── sys.c         /dev/kd_dev char device
│   └── kd_int3.c     Hot-lock promotion + int3 handler
├── klock_module/      Test workload module (/dev/lock_dev)
├── daemon/            Userspace translation daemon
├── disassem/          miasm-based kernel text translator
├── include/           Shared headers + wrapper.S
├── docs/              Design, component map, operating notes, TODOs
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
make -C kernel_module
make -C klock_module
make -C daemon
gcc -Iinclude bench/klock_test.c -o bench/klock_test -lpthread
```

### Run

Terminal 1 — load modules:
```bash
sysctl -w kernel.randomize_va_space=0
sysctl -w kernel.numa_balancing=0
insmod kernel_module/kdlock_km.ko target_process="klock_test"
insmod klock_module/klock_module.ko
```

Terminal 2 — start daemon:
```bash
cd daemon && ./daemon --mode 2
```

Terminal 1 — run benchmark:
```bash
./bench/klock_test 4 100000 1000 10 0
```

### Benchmark Modes

| Mode | Lock type | Scenario |
|------|-----------|----------|
| 0 | Spinlock | Contended single lock |
| 1 | Spinlock | Nested locks (A → B) |
| 2 | Spinlock | API call inside CS |
| 3 | Mutex | Contended single lock |
| 4 | Mutex | Nested locks (A → B) |
| 5 | Mutex | API call inside CS |
| 6 | Spinlock | Deep nesting (A -> B -> C) |
| 7 | Spinlock | Out-of-order unlock (unlock A before B) |
| 8 | Spinlock | Independent contention and queues on A and B |
| 9 | Spinlock | Isolated nested-JIT abort/retry |

### Inspect Results

```bash
dmesg | grep -i "delegation ok\|success_rate\|begin delegate"
```

## Testing

### User-space unit tests (instant, zero risk)

Run inside the VM from `/root/host_fs/kdlock`:

```bash
make -C tests/unit clean >/dev/null && make -C tests/unit run
```

Nine binaries cover tail encoding, bounded translation lookup/publication,
hot-lock state, spin/mutex node capacity, explicit nested execution frames,
known-call policy, mutex shadow lookup, and safe draining during promotion.
The frame tests cover parent/LIFO invariants, repeated-lock rejection,
out-of-order release, exact completion, reverse abort cleanup, and bounded
frame/lock-stack failure.

### Safe validation checklist

Run git checks on the host checkout:

```bash
git -C /home/eric/vm/vm-shared/kdlock diff --check
```

Run build/syntax checks inside the VM from `/root/host_fs/kdlock`:

```bash
make -C tests/unit clean >/dev/null && make -C tests/unit run
python3 -m py_compile disassem/disassem.py
make -C kernel_module -j"$(nproc)"
```

### Integration tests (requires VM)

```bash
bash tests/run_all.sh
```

Runs 6 test scripts covering module load, JIT engine, hot-lock promotion,
spinlock delegation, mutex delegation, and daemon pipeline.

`test_04_spinlock.sh` runs modes 0/1/2/6/7/8 by default. Modes 0 and 1 both
require complete translation artifacts, daemon write-back, actual JIT success,
exact final counters, zero waiter leaks, and clean execution-frame invariants.

The default JIT checks are staged but non-destructive: `test_02_jit_engine.sh`
now verifies endpoint resolution, hot-lock promotion, `kd_exe_add`, daemon
kernel-text reads, `jit.S` entry-label alignment, sandbox exit/miss paths,
non-empty `jit.bin`, objdump output, and `/dev/kd_dev` write-back. It does not
execute the translated critical section after write-back.

### Recovery-only nested spin JIT checks

Run these only in a confirmed recovery VM:

```bash
# Missing B artifact: safe queue handoff, no partial execution
KD_MODE8_NOT_READY=1 bash tests/test_04_spinlock.sh 8

# Same topology, then abort while B is the nested queue owner
KD_MODE8_NOT_READY=1 KD_SPIN_ABORT_INJECT=1 \
  bash tests/test_04_spinlock.sh 8

# Fast nested-B abort and runtime call/IJ/instruction-limit faults
KD_SPIN_ABORT_INJECT=1 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=1 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=2 bash tests/test_04_spinlock.sh 9
KD_JIT_FAULT_KIND=3 bash tests/test_04_spinlock.sh 9
```

The runtime-fault variants stop the daemon before executing the translated
workload. Passing therefore proves cleanup and native retry do not wait for
userspace. Every variant requires reverse cleanup of B, retry at A's original
CS entry, per-lock `jit_disabled=1`, exact counting, and zero queued waiters.

### Opt-in mutex JIT smoke

```bash
bash tests/test_07a_mutex_jit_smoke.sh
```

This is the fastest real-sandbox confirmation. It loads `mutex_jit=1`,
forces a translation, then runs a small contended mode 3 workload that must
complete exactly one sandboxed critical section.

### Opt-in mutex JIT confirmation

```bash
bash tests/test_07_mutex_jit.sh
```

This high-risk test is intentionally excluded from `tests/run_all.sh`. It loads
`kdlock_km.ko` with `mutex_jit=1`, performs promotion and translation without
contention, then runs a bounded mode 3 contention workload. Passing requires a
complete translation artifact check, a real `KD_EXE_RUN_TO_UNLOCK` completion,
`jit_success > 0`, an exact final counter, and no kernel error signatures.

As of 2026-07-02, the bounded mode 3 test passes with one confirmed delegated
critical section (`jit_success=1`, final counter `14001`). This confirms the
basic mutex JIT execution/resume path; it does not validate stress.

### Opt-in mutex JIT modes 4/5 diagnostic

```bash
bash tests/test_08_mutex_jit_modes.sh 4
bash tests/test_08_mutex_jit_modes.sh 5
```

This recovery-only test validates translation artifacts and then attempts one
real sandbox execution with exact counter accounting. On 2026-07-03, both mode
4 (nested mutex) and mode 5 (API in mutex CS) passed under `mutex_jit=1` after
fixing known-call continuation handling and nested/API call handling. Keep this
test outside the default suite: run it only with a confirmed snapshot.

### Snapshot test helper

```bash
bash tests/snapshot_test.sh 3   # test mutex contention
```

The default `mutex_jit=0` mode tests the mutex queue / combiner / fallback /
handoff protocol without executing translated mutex critical-section code. Only
load `kdlock_km.ko` with `mutex_jit=1` when explicitly debugging the experimental
mutex JIT sandbox.

The normal VM configuration includes VirtFS and VFIO, so QEMU `savevm` is not
available. For high-risk tests, use the existing guest-local repository at
`/root/host_fs/kdlock`; compare hashes and sync only changed files before
starting the VM from the host in recovery mode:

```bash
cd /home/eric/vm/qemu-scripts
./run_vm.sh recovery
```

Recovery mode omits VirtFS and VFIO, writes serial output to
`/tmp/qemu-serial.log`, and exposes `/tmp/qemu-monitor.sock`. Connect with
`./run_vm.sh monitor`, issue `savevm pre_mutex_jit`, and use `Ctrl-C` to detach.
Do not issue HMP `quit`, which exits QEMU.

On 2026-07-03, recovery mode snapshot `pre_mutex_jit_modes45_fix` protected
the successful mode 4/5 validation. Host evidence was saved under
`/tmp/kdlock-mode4-pass-*` and `/tmp/kdlock-mode5-pass-*`.

## Module Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_process` | `"kd_test"` | Space-separated process names to intercept |
| `velvet_wait_queue` | 1 | Enable velvet wait queue optimization |
| `delegate_election` | 1 | Enable delegate election |
| `mutex_jit` | 0 | Enable experimental mutex JIT sandbox execution. Bounded modes 3/4/5 are recovery-confirmed; stress remains opt-in and unverified. Default 0 remains required for normal testing. |
| `spin_jit_fail_after_nested_lock` | 0 | One-shot test fault after nested spin acquisition; validates frame cleanup and native retry. |
| `jit_hl_fault_after_known_call` | 0 | One-shot test fault after a known JIT call: 1=CALL miss, 2=IJ miss, 3=instruction limit. |

## Prerequisites

- Patched Linux kernel (6.1.x) with kdlock hook exports
- x86-64 architecture, KASLR disabled
- Python 3 + miasm 0.1.5 (for translator)
- `/proc/kcore` access from daemon

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) — Full technical design (architecture, protocols, sandbox model)
- [docs/COMPONENTS.md](docs/COMPONENTS.md) — File-by-file component and test map
- [docs/AGENTS.md](docs/AGENTS.md) — Automation operating manual and safety rules
- [docs/CRASH_LOG_PLAN.md](docs/CRASH_LOG_PLAN.md) — Crash logging and recovery plan
- [docs/plan.md](docs/plan.md) — Current execution plan and validation record
- [docs/TODO.md](docs/TODO.md) — Task list and known gaps
