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

See [DESIGN.md](DESIGN.md) for the full technical design.

## Status

| Component | State |
|-----------|-------|
| Spinlock delegation (modes 0-2) | Working |
| Mutex delegation protocol (modes 3-5) | Working, JIT sandbox opt-in |
| Dynamic translation (daemon + miasm) | Working |
| Hot-lock promotion | Working |
| Nested lock handling | Graceful degradation |
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

Tests: tail encoding, hash table, hot-lock state machine, count management, and
mutex shadow-table lookup semantics (`test_mutex_shadow`). The mutex shadow test
ensures the lock path can create entries while the unlock path only looks up
existing entries and does not allocate slots for never-delegated mutexes.

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

### Snapshot-protected tests (fast crash recovery)

```bash
bash tests/snapshot_test.sh 3   # test mutex contention
```

The default `mutex_jit=0` mode tests the mutex queue / combiner / fallback /
handoff protocol without executing translated mutex critical-section code. Only
load `kdlock_km.ko` with `mutex_jit=1` when explicitly debugging the experimental
mutex JIT sandbox.

Takes a QEMU snapshot before testing. If the VM crashes:
```bash
echo "loadvm pre_test" | socat - UNIX-CONNECT:/tmp/qemu-monitor.sock
```

## Module Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_process` | `"kd_test"` | Space-separated process names to intercept |
| `velvet_wait_queue` | 1 | Enable velvet wait queue optimization |
| `delegate_election` | 1 | Enable delegate election |
| `mutex_jit` | 0 | Enable experimental mutex JIT sandbox execution. Default 0 keeps mutex delegation in safe handoff/fallback mode. |

## Prerequisites

- Patched Linux kernel (6.1.x) with kdlock hook exports
- x86-64 architecture, KASLR disabled
- Python 3 + miasm 0.1.5 (for translator)
- `/proc/kcore` access from daemon

## Documentation

- [DESIGN.md](DESIGN.md) — Full technical design (architecture, protocols, sandbox model)
- [kernel_module/TODO.md](kernel_module/TODO.md) — Task list and known gaps
