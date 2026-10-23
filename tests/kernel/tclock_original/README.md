# Original TCLock port checks

These short correctness checks exercise the original upstream spin, mutex,
rwlock and rwsem backends in the recovery VM. They count actual writer bodies
executed by a task other than the caller, verify exact writes and reads, check
two protected values, detect reader/writer overlap, and check task/preemption/IRQ
context after each operation. Reader overlap is observed separately. They do
not measure throughput or establish support for arbitrary caller contexts.

The [port guide](../../../tclock_backend/README.md) specifies upstream provenance,
minimal adaptations and unsupported APIs. The [results record](../../../bench/results/10.176.26.71/tests/tclock-original-20261023/README.md)
contains actual coverage, failed attempts and retained logs.

## Run in the recovery VM

First follow [VM operations](../../../docs/operations/VM.md): verify the intended
idle VM, kernel identity and real recovery snapshot. Keep one VM owner. Set the
recovery variables only after that verification. Use a new external build/output
directory, with enough space; the existing VM tmpfs can hold short functional
builds when disks are full, but copy its evidence to persistent storage before
reboot. Source edits and Git stay on the source host.

From an isolated source copy in the VM:

```sh
export KDLOCK_RECOVERY_CONFIRMED=1
export KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
PORT_WORK=/root/tclock-original-NEW
mkdir -p "$PORT_WORK/backend" "$PORT_WORK/probe"
cp -a tclock_backend/. "$PORT_WORK/backend/"
cp tests/kernel/tclock_original/payload/* "$PORT_WORK/probe/"
make -C "$PORT_WORK/backend" KDIR=/root/linux-6.1.159-kdclobber2 \
    TCLOCK_RWSEM=1 TCLOCK_NUMA=1
make -C "$PORT_WORK/probe" KDIR=/root/linux-6.1.159-kdclobber2 TEST_KIND=4 \
    TCLOCK_INCLUDE="$PORT_WORK/backend/include" \
    KBUILD_EXTRA_SYMBOLS="$PORT_WORK/backend/Module.symvers"
python3 tests/kernel/tclock_original/verify_source.py
python3 tests/kernel/tclock_original/run_probe.py \
    --provider "$PORT_WORK/backend/tclock_rwsem_backend_km.ko" \
    --probe "$PORT_WORK/probe/tc_original_test.ko" \
    --workers 8 --writes 20 --iterations 10000 --output "$PORT_WORK/result"
```

Use separate build directories for other families:

| Family | Provider selection | Probe `TEST_KIND` | Provider module |
| --- | --- | ---: | --- |
| spin | `TCLOCK_NUMA=1` | 1 | `tclock_backend_km.ko` |
| mutex | `TCLOCK_MUTEX=1 TCLOCK_NUMA=1` | 2 | `tclock_mutex_backend_km.ko` |
| rwlock | `TCLOCK_RWLOCK=1 TCLOCK_NUMA=1` | 3 | `tclock_rwlock_backend_km.ko` |
| rwsem | `TCLOCK_RWSEM=1 TCLOCK_NUMA=1` | 4 | `tclock_rwsem_backend_km.ko` |

The probe pins workers to CPUs 0 through N−1, limits N to 16 and accepts only
ordinary non-nested operations. Use 100% writes for spin/mutex and a mixed case
for rwlock/rwsem. Read-only and single-worker cases need no delegation to pass.
A positive `remote_writes` count proves different-task execution in that probe;
it is not a benchmark delegation percentage. The rwlock caller restores its
IRQ-enabled entry context after the pair, preserving upstream IRQ instructions
inside the lock. The user-mode assembly fixture stubs IRQ instructions and does
not replace this live context check.

Workers register before running. The probe joins them, waits up to one second
for task retirement, then drains registered references. `quiescent=1` and exact
lock-state checks are required before normal unload. On a timeout or drain
failure, the driver leaves live state intact for diagnosis; never force unload.
The optional `tc_original_reap.ko` only retries the existing rwsem drain API
when workers are already joined; it cannot make an active queue safe.

The benchmark integration has a separate short functional command:

```sh
/root/kdlock-translation-venv-20261019/bin/python3 bench/rwlock_compare/run.py \
    --lock-kind rwsem --backends tclock --workloads cacheline --cachelines 1 \
    --threads 4 --cpus 0 1 2 3 --collector-cpu 63 --write-percent 20 \
    --functional --repeats 1 --iterations 10000 \
    --kernel-source /root/linux-6.1.159-kdclobber2 \
    --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
    --output NEW_EXTERNAL_OUTPUT
```

Replace `rwsem` with `rwlock` for the restored rwlock caller. This uses the
existing warmup and client validation, not a new performance campaign. The
runner audits the emitted stack-switch assembly before loading modules.

## Scope

The original rwsem uses its original AQS reader gate and writer parking protocol.
Readers remain local. Only ordinary read/write pairs are exported. Original
killable wrappers do not implement signal cancellation; downgrade is an
unimplemented `BUG_ON` path. Those APIs are not advertised as supported. No
claim is made for arbitrary sleeping bodies, nesting, migration, oversubscription,
RT, whole-kernel replacement or Linux semaphore API equivalence.
