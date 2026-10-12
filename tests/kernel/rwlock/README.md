# Read-write lock verification

The [public API](../../../include/kd_rwlock.h) and
[protocol guide](../../../docs/design/rwlock_implementation.md) describe the
supported ordinary task-context scope. These tests check data correctness, where
callers resume after delegation, whether every worker progresses, and whether
shutdown leaves any live lock state. They follow the TCLock comparison's approach,
with separate sessions for Linux Native, KD with delegation disabled, and KD JIT.

## Unit checks

Run in the recovery guest:

```sh
make -C tests/unit run \
  PY_TESTS='rwlock/test_rwlock.py admission/test_clobber_entry.py codegen/test_spin_paired_jit.py execution/test_jit_entry_scope.py spin/test_spin_wait.py'
```

The rwlock fixture compiles the actual public header with C atomic substitutes
for kernel primitives and an embedded-gate substitute. It forces two simultaneous
readers, a writer waiting for those readers, and a later reader that must wait
behind that writer. Ten threads then mix native/direct writers and readers. It
checks exact updates and mutual exclusion. It also verifies that writer unlock
preserves reader counts and a queued writer's WAITING bit, shutdown tracks writers
that skip the gate, and ABI3 acquires write access correctly after refusal and
retry. Other checks cover argument evaluation, preparation identity and balanced
preemption.

The fixture substitutes queue primitives; live runs are still needed to exercise
the real queue and show that JIT bodies returned. The other selected drivers check
ABI3 entry, generated completion and refusal, shared frames, and restoration to
native code. For changes to the TCLock port or performance checks, add the
[benchmark's focused checks](../../../bench/rwlock_compare/README.md#focused-checks).

## Build live inputs

Follow [operations](../../../docs/AGENTS.md): verified kernel and boot policy,
idle guest, frozen source, pinned Python environment and a confirmed QEMU recovery
snapshot. The workload uses no provider SELFTEST hooks. Build an ordinary provider
with the existing private observation overlay to count returned JIT bodies:

```sh
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH
export LC_ALL=C
RW_ROOT="$PWD"
RW_KERNEL=/root/linux-6.1.159-kdclobber2

make -C bench/spin_cacheline provider KDIR="$RW_KERNEL" UBSAN_SANITIZE=n
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
make -C bench/tclock_compare/allocator_guard KDIR="$RW_KERNEL"
make -C workload_modules/rwlock KDIR="$RW_KERNEL" RW_BACKEND=kdlock \
  KDLOCK_INCLUDE="$RW_ROOT/include" \
  KBUILD_EXTRA_SYMBOLS="$RW_ROOT/bench/spin_cacheline/.build/provider/kernel_module/Module.symvers"

RW_NATIVE_DIR="$(mktemp -d /root/kdlock-rw-native.XXXXXX)"
cp workload_modules/rwlock/Makefile workload_modules/rwlock/api.h \
  workload_modules/rwlock/module.c "$RW_NATIVE_DIR/"
make -C "$RW_NATIVE_DIR" KDIR="$RW_KERNEL" RW_BACKEND=native
```

## Run and acceptance

After confirming the recovery snapshot through the QEMU monitor:

```sh
export KDLOCK_RECOVERY_CONFIRMED=1
timeout 720s python3 tests/kernel/rwlock/run.py --backend native \
  --workload "$RW_NATIVE_DIR/rwlock_test.ko" \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwlock-native-new
timeout 720s python3 tests/kernel/rwlock/run.py --backend kdlock --delegate off \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwlock-disabled-new
timeout 720s python3 tests/kernel/rwlock/run.py --backend kdlock \
  --output /root/kdlock-evidence/10.176.26.71/tests/rwlock-jit-new
```

Use new output directories. Defaults are CPUs 0..15 and 50,000 operations per
worker per main phase. `--cpus` accepts ranges; at least four available CPUs are
required, and 16 are recommended for reliable contended JIT acceptance. The CPU
list is placement, not a fixed NUMA recipe: choose it from the verified live
topology. On the documented 64-vCPU destination, `0-7,32-39` spans both nodes.
Recheck the live mapping before a new run; historical receipts retain their own
worker placements.

The 100,000-write-per-worker warmup retains ordinary heat promotion. The test sets
`spin_entry_ratio_limit=0` to bypass that optional ratio filter, retaining the
existing CPU and lock heat checks. It does not force frames, publication or JIT.

The six phases cover one writer, concurrent readers, writer warmup, writers only,
50/50 reads/writes and 87.5% reads. Every phase checks exact progress for every
worker, all eight protected values, reader/writer and writer/writer exclusion,
balanced preemption/IRQ state, and zero final reader count and gate state. The
concurrent-reader phase must show readers overlapping.

Native controls and reader-only phases must return zero JIT bodies. The JIT
session must return at least one JIT body in both the writer-only and 50/50 phases;
publishing code is not enough. The read-heavy phase records its actual JIT count
because it may have too little contention to sustain delegation.

The runner captures kernel identity, boot arguments, kernel logs, source/image
hashes, worker commands/PIDs/results, compilation/publication state and returned
body counts. Operations preflight independently confirms native qspinlock policy;
an old boot printk can rotate out of the kernel ring. On success, callers join,
the daemon and translators stop, source retirement validates frame/queue/ACK
drain, and the workload unloads before its provider. Timeouts or kernel faults
retain the modules and evidence; do not infer drain or force unload.

## Recorded verification

The [frozen ABI3 verification](https://github.com/hailongeric/kdlock/blob/792db45f28d775da667572ebd1e2080025cfd88a/tests/kernel/rwlock/README.md#abi3-verification-on-2026-10-10)
records the 2026-10-10 affected checks and KD-native/KD-JIT correctness sessions
on the original 40-vCPU host. The
[frozen ABI1 verification](https://github.com/hailongeric/kdlock/blob/792db45f28d775da667572ebd1e2080025cfd88a/tests/kernel/rwlock/README.md#historical-abi1-verification-on-2026-10-09)
retains the earlier caller ABI, controls, failed preflight and raw archive identity.
Use [validation](../../../docs/VALIDATION.md) for other receipts and limits; rebuild
current callers and verify the actual guest placement before new runs.
