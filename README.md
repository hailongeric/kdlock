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
| Spinlock delegation (modes 0-2, 6-9) | Working; nested JIT, mode 2 native hostcalls, and bounded recovery validated |
| Mutex delegation protocol (modes 3-5) | Safe mode working; mode 3 stress JIT and mode 4 nested A/B JIT proxy confirmed |
| Dynamic translation (daemon + miasm) | Working |
| Hot-lock promotion | Working |
| Nested spinlock handling | TCLock-style JIT delegation, recursive frames, OOO handoff, and native retry |
| Nested mutex handling | A remains delegated while contended B is queued and executed by a B combiner |
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
| 2 | Spinlock | JIT CS exits to an allowlisted native API and resumes after CALL |
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

### Unit And Build Checks

Run inside the VM from `/root/host_fs/kdlock`:

```bash
make -C tests/unit clean >/dev/null && make -C tests/unit run
python3 -m py_compile disassem/*.py
make -C kernel_module -j"$(nproc)"
make -C klock_module -j"$(nproc)"
make -C daemon
```

Nine C binaries plus one Python code-generation test cover tail encoding,
bounded translation lookup/publication, hot-lock state, spin/mutex node
capacity, explicit nested execution frames, hostcall/call-miss policy, generated
hostcall stubs, mutex shadow lookup, and safe draining during promotion.

### Default Integration Suite

```bash
bash tests/run_all.sh
```

This runs six scripts covering module load, JIT installation, hot-lock promotion,
spinlock delegation, mutex delegation, and daemon pipeline.

The default suite does not prove translated execution for mutex modes 3/4:
`test_05_mutex.sh` deliberately uses `mutex_jit=0` to validate the queue and
handoff protocol without entering the experimental mutex sandbox.

### Modes 0/1/2/3/4 JIT Acceptance

After confirming a recovery snapshot, run:

```bash
KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 600s \
  bash tests/test_09_jit_execution_modes.sh 0 1 2 3 4
```

Selectors may be supplied individually. A pass requires complete translation
artifacts, kernel write-back, actual translated completion (`jit_success`), an
exact final counter, drained queues/frames, and clean kernel diagnostics. Modes
3/4 additionally verify that `mutex_jit=1` is active. Mode 2 also requires a
named `ktime_get` hostcall stub, no service callee translation or runtime
recompilation, and matching nonzero exit/execute/resume counters.

The latest independent mode 2 rerun on 2026-09-04 installed and executed the
1407-byte artifact for entry `0xffffffffc071ee7b`. It recorded
`jit_success=4`, `exits=4 executed=4 resumed=4`, exact counters of 12009, one
initial JIT write-back, and zero hostcall, queue, or invariant failures. The
command output and kernel log retained in the recovery guest are listed in
[docs/VALIDATION.md](docs/VALIDATION.md).

| Mode | `tests/run_all.sh` | Real JIT acceptance |
| --- | --- | --- |
| 0 | Yes, translated spin CS executes | `test_04_spinlock.sh 0` |
| 1 | Yes, translated nested spin CS executes | `test_04_spinlock.sh 1` |
| 2 | Yes, translated spin CS executes around a native hostcall | `test_04_spinlock.sh 2` |
| 3 | No, default uses `mutex_jit=0` | `test_07_mutex_jit.sh` |
| 4 | No, default uses `mutex_jit=0` | `test_08_mutex_jit_modes.sh 4` |

Mode 1 executes one translated outer A stream through the nested B lock/unlock
known-call path; B's nested counters prove those boundaries were crossed without
native fallback. Mode 2 exits that stream at an allowlisted time API, executes a
typed native handler while retaining outer-lock ownership, and resumes the same
artifact at the instruction after CALL. Mode 4 forms independent A and B queues
and requires both entry RIPs to execute, including remote B proxy evidence. See
[docs/VALIDATION.md](docs/VALIDATION.md) for the exact latest results and this
distinction.

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
```

These are intentionally excluded from `tests/run_all.sh`. The mode 9 variants
exercise transactional cleanup and native retry after nested JIT faults. The
mutex tests explicitly opt into `mutex_jit=1`.

### Recovery VM

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

## Module Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_process` | `"kd_test"` | Space-separated process names to intercept |
| `velvet_wait_queue` | 1 | Enable velvet wait queue optimization |
| `delegate_election` | 1 | Enable delegate election |
| `mutex_jit` | 0 | Enable experimental mutex JIT sandbox execution. Mode 3 repeated/stress execution, mode 4 nested A/B proxy execution, and bounded mode 5 are recovery-confirmed. It remains opt-in; default 0 is required for normal testing. |
| `spin_jit_fail_after_nested_lock` | 0 | One-shot test fault after nested spin acquisition; validates frame cleanup and native retry. |
| `jit_hl_fault_after_known_call` | 0 | One-shot test fault after a known JIT call: 1=CALL miss, 2=IJ miss, 3=instruction limit. |

## Prerequisites

- Patched Linux kernel (6.1.x) with kdlock hook exports
- x86-64 architecture, KASLR disabled
- Python 3 + miasm 0.1.5 (for translator)
- `/proc/kcore` access from daemon

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md) — Full technical design (architecture, protocols, sandbox model)
- [docs/JIT_REGISTER_ABI.md](docs/JIT_REGISTER_ABI.md) — Current JIT entry/exit, virtual-register, stack, and continuation ABI
- [docs/COMPONENTS.md](docs/COMPONENTS.md) — File-by-file component and test map
- [docs/AGENTS.md](docs/AGENTS.md) — Automation operating manual and safety rules
- [docs/VALIDATION.md](docs/VALIDATION.md) — Latest reproducible JIT execution evidence
- [docs/MODE2_HOSTCALL_IMPLEMENTATION.md](docs/MODE2_HOSTCALL_IMPLEMENTATION.md) — Mode 2 hostcall protocol, implementation steps, and acceptance checklist
- [docs/TODO.md](docs/TODO.md) — Open tasks and known gaps
