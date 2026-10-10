# Read-write lock verification

The [public API](../../../include/kd_rwlock.h) and
[protocol guide](../../../docs/design/rwlock_implementation.md) describe the
supported ordinary task-context scope. Tests use the same style of data,
continuation, progress and drain checks as the TCLock comparison, with separate
Linux Native, KD delegation-disabled and KD JIT sessions.

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
checks exact updates, mutual exclusion, writer-byte release preserving reader
increments and queued intent, ungated writer drain references, ABI3 admission
and refusal/retry, argument evaluation, preparation identity and balanced
preemption.
These are protocol checks; the live workload supplies real queue/JIT evidence.
The other selected drivers cover ABI3 clobber admission, generated completion and
refusal, shared frame execution and native restoration. For changes to the TCLock
port or performance oracle, add the [benchmark's focused checks](../../../bench/rwlock_compare/README.md#focused-checks).

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
  --output /root/kdlock-evidence/rwlock-native-new
timeout 720s python3 tests/kernel/rwlock/run.py --backend kdlock --delegate off \
  --output /root/kdlock-evidence/rwlock-disabled-new
timeout 720s python3 tests/kernel/rwlock/run.py --backend kdlock \
  --output /root/kdlock-evidence/rwlock-jit-new
```

Use new output directories. Defaults are CPUs 0..15 and 50,000 operations per
worker per main phase. `--cpus` accepts ranges; at least four available CPUs are
required, and 16 are recommended for reliable contended JIT acceptance. The CPU
list is placement, not a fixed NUMA recipe: choose it from the verified live
topology. The historical cross-node `0–7,20–27` placement below belongs to the
original 40-vCPU guest. On the documented 60-vCPU destination, `0-7,30-37` would
span both nodes, after migration verification.

The 100,000-write-per-worker warmup retains ordinary heat promotion. The test sets
`spin_entry_ratio_limit=0` to bypass that optional ratio filter, retaining the
existing CPU and lock heat checks. It does not force frames, publication or JIT.

The six phases cover one writer, concurrent readers, writer warmup, writers only,
50/50 reads/writes and 87.5% reads. Each checks every worker's exact progress,
all eight protected values, reader/writer and writer/writer exclusion, balanced
preemption/IRQ state, and drained reader/gate state. Concurrent readers must
overlap. Native controls and readers-only phases must have zero returned JIT
bodies. The JIT session requires nonzero returned bodies for both the write-only
and 50/50 phases; publication alone cannot pass. The read-heavy phase records its
actual JIT count without assuming it will maintain sufficient contention.

The runner captures kernel identity, boot arguments, kernel logs, source/image
hashes, worker commands/PIDs/results, compilation/publication state and returned
body counts. Operations preflight independently confirms native qspinlock policy;
an old boot printk can rotate out of the kernel ring. On success, callers join,
the daemon and translators stop, source retirement validates frame/queue/ACK
drain, and the workload unloads before its provider. Timeouts or kernel faults
retain the modules and evidence; do not infer drain or force unload.

## ABI3 verification on 2026-10-10

The two basic unit programs and five affected groups passed: rwlock protocol,
clobber admission, generated ABI1/2/3 completion and refusal, execution entry
scope, and real shadow-wait/continuation restoration. The execution fixture
checked 4,359 assertions and detected its 30 injected mutations. The rwlock
benchmark's 13 focused tests also passed.

With the final ABI3 fast-writer and separated-gate implementation, KD-native and
KD-JIT live sessions each completed 4,801,000 operations on CPUs `0–7,20–27`
in the original 40-vCPU guest.
Both observed 16 simultaneous readers, preserved writer exclusion and exact
updates, and drained with zero count/gate state. KD-native returned no JIT bodies.
The JIT session recorded:

| Phase | Writes | Returned JIT bodies |
| --- | ---: | ---: |
| Writer warmup | 1,600,000 | 1,156,371 |
| Writers only | 800,000 | 523,035 |
| 50/50 reads/writes | 400,000 | 141,651 |
| 87.5% reads | 100,000 | 547 |

The RCUHT functional probes at 16 and 36 workers also passed, with 23,021 and
26,964 returned JIT writers respectively. These are correctness checks, not
performance samples. The [RCUHT report](../../../bench/rwlock_compare/results/20261010-rcuht/README.md)
links the complete evidence, including the corrected missing-Makefile preflight
and retained rejected optimization trials. No full test suite or kernel rebuild
was run.

## Historical ABI1 verification on 2026-10-09

The five selected unit groups passed. The observation provider and both workload
variants built with `W=1`, UBSAN off, against verified `6.1.159-kdclobber2`, Build
ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Existing provider stack-switch
objtool warnings remain. The 16-CPU Linux Native, KD-disabled and KD-JIT sessions
each completed 4,801,000 operations, observed 16 concurrent readers, passed exact
data/progress checks and unloaded cleanly with zero remaining reader/gate state.

| JIT session phase | Writer operations | Returned JIT bodies |
| --- | ---: | ---: |
| Writer warmup | 1,600,000 | 1,537,898 |
| Writers only | 800,000 | 774,557 |
| 50/50 reads/writes | 400,000 | 185,813 |
| 87.5% reads | 100,000 | 83 |

Both native controls and the readers-only phase returned zero JIT bodies. No
performance claim or TCLock rwlock benchmark comparison follows from these runs.
Core spin/execution/translator sources matched the host checkout; the unrelated
local mutex-header edit was excluded from this isolated guest build.

One added preflight stopped before loading modules because the boot printk had
rotated out. Reading the live `pv_ops` lock/unlock pointers through `/proc/kcore`,
using the verified vmlinux type offsets, confirmed both native implementations.
The failed preflight and its source remain alongside the corrected control run.
Original functional source and the later attribution/ABI-check updates are
preserved separately. Evidence is under guest
`/root/kdlock-evidence/rwlock-20261009/`; `native-policy.json` records dispatch
addresses and boot ID, and `native/`, `jit/`, `kd-native-final2/` contain the
successful sessions. The archive is guest
`/root/kdlock-evidence/rwlock-20261009-evidence.tar.gz` and host
`bench/.tmp/rwlock-20261009/guest-evidence.tar.gz`, SHA256
`73608664642fa7bd4617197d21fac36f43a1bafc69cb694aa4c75bea38d65df6`.
No full suite, kernel modification or performance matrix was run.
