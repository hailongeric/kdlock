# Original TCLock port validation — 2026-10-23

Added the original rwsem and its original AQS (adaptive queue spinlock) reader
gate. Restored the spin
RCUHT scheduling loop and `need_resched()` batch exit, plus the original rwlock
interrupt (IRQ) instructions. Admission, queue selection, parking/wakeup and stack handoff
use the upstream algorithms. Necessary module/type/task-storage adaptations are
listed in the [port guide](../../../../../tclock_backend/README.md) and review
patches; this is not a byte-identical build of upstream's patched kernel.

## Final serial correctness cases

Each worker completed 10,000 operations. All cases passed exact operation/data,
writer exclusion, caller-context, lock-state and normal cleanup checks.

| Backend | Workers | Writes | Reads | Writers executed in another task | Peak concurrent readers |
| --- | ---: | ---: | ---: | ---: | ---: |
| spin | 4 | 40,000 | 0 | 22,212 | 0 |
| mutex | 4 | 40,000 | 0 | 715 | 0 |
| rwlock | 8 | 16,000 | 64,000 | 7,596 | 8 |
| rwsem | 8 | 16,000 | 64,000 | 6,936 | 8 |

Readers executed locally. All four providers reported `quiescent=1` and were
unloaded normally. These counts describe correctness probes, not throughput or
performance acceptance. The short benchmark-client integration cases for rwsem
and rwlock each passed 32,000 reads and 8,000 writes after the normal warmup,
with data checks and complete cleanup. TCLock benchmark delegation counts remain
labelled unmeasured; the separate probe establishes different-task execution.

Additional validation: two basic C tests, 26 reader/writer runner tests, 59 direct
runner/auditor tests, and the three actual-assembly continuation fixtures passed.
Each assembly fixture exercised 128 switches, 64 acquisition returns and 64
unlock continuations; the mutex fixture also checked parking/wakeup races.
Provenance checks matched all 12 immutable upstream files, the restored spin
conditions, rwlock IRQ/return sequence, and the original AQS body/header. All
four providers built; the UTS and module-owned mapping caller adapters also
compiled. Those two callers were not exercised live in this milestone.

## Preserved failures and boundaries

- The first rwsem smoke completed 1,000 writes with zero data/context errors,
  then returned `EBUSY` from immediate drain because task retirement followed
  `kthread_stop`. A later call to the same drain API succeeded. The harness now
  waits for retirement outside the lock body; the lock protocol was not changed.
- Initial rwsem builds exposed missing compatibility timing macros and two
  remaining references to patched upstream task fields. The corrected build
  passed. Original stack-switch objtool warnings remain recorded.
- An affected runner test retained an old expectation that rwsem TCLock must
  be rejected. Updated support expectations passed all 26 tests.
- An isolated-copy preflight lacked the unchanged kernel verifier. It stopped
  before module work; supplying that file allowed identity validation to pass.
- The first restored-rwlock assembly audit rejected upstream's paravirtual
  IRQ-disable call as a prologue. The auditor now permits only CLI or the exact
  captured-kernel `pv_ops.irq.irq_disable` relocation before the six saves.
  Negative tests still reject unrelated calls, wrong offsets and extra frames.
  The corrected functional run passed; the rejected preparation is retained.
- A clean VM reboot interrupted a transfer before a subsequent test began.
  No TCLock modules remained loaded. The recovery kernel and boot policy were
  rechecked; the final table is entirely from the subsequent boot.

## Environment, reproduction and limitations

The existing 64-vCPU VM at `root@10.176.26.71:2222` ran the recovery kernel
`6.1.159-kdclobber2`, with `nokaslr`, `nopvspin` and voluntary preemption. No kernel
was built or installed for this work. The recovery snapshot was verified and
preserved. Workers used fixed distinct CPUs; the functional client used collector
CPU 63. Both persistent disks were nearly full, so later functional builds used
the existing VM tmpfs. Their essential evidence and temporary final binaries
were copied to the source host. Final inspection found no project test modules.

[Runnable commands and probe scope](../../../../../tests/kernel/tclock_original/README.md)
cover the isolated build, source/assembly checks and serial execution. See
[reproducibility metadata](reproducibility.json) for exact binary hashes, boot
identity and source hashes. [Raw evidence](../../raw/tests/tclock-original-20261023/)
contains per-case JSON and logs, failed preparations, compiler diagnostics and
assembly audits; it is retained on disk outside Git.

The module adapter replaces custom upstream task fields with preallocated
registered storage, restricted to one fixed-affinity worker per CPU. Rwlock
callers restore their IRQ-enabled context after a complete pair; the original
internal IRQ operations remain intact. Original rwsem signal-cancellation and
downgrade limitations are preserved and excluded from the supported API.
General nesting, migration, oversubscription and sleeping critical sections are
unvalidated. The historical nano report and its unsupported rwsem slots remain
unchanged. No nano rerun, tuning, p95 or mutex-regression campaign was started.
