# Plain mmap throughput: admission stop, October 25

The freshly authorized `plain-v1` attempt stopped at its first full host
admission: **68 QEMU tasks versus the required 67**. No candidate boot, payload
check or measurement ran. All **12 measured sessions and six unscored checks
remain unrun**; qualified current performance count is zero.

This is a new capture and rejection, separate from the preserved earlier
[73-versus-67 stop](../mmap-kdmm31-paired-20261025/README.md). Neither failure is
replaced by a later quiet observation. No throughput, latency or optimization
gain is claimed.

## Inputs and bounds

Execution used the tested source checkout at
`02e6294d0e9dbaaa5eba7a74bd9b0bffdb0772d6` on `master`, with audited lock
implementation `e6fc371b032cc0444dba34ee9025e7d939811125`. The separate documentation
commit `3f1565322621791b9febf436f1c9280ffa512069`, its branch/worktree, and the
unrelated empty cleanup README were preserved. The user's October 25 23:29
(Asia/Shanghai) ownership choice assigned this session sole benchmark/VM
execution responsibility for the already requested bounded throughput cycle.

The [prepared plan](../../../../mmap_lock/README.md#plain-throughput-plan) uses
the same installed `6.1.159-kdmm31` image and existing build-3 payload/clients:
Native/KD, 1/16 shared-mm writers, three paired repetitions, plain only.

| Activity | Authorized maximum | Consumed |
| --- | ---: | ---: |
| Full host captures | 31 | 1 |
| Boots, including recovery | 6 | 0 |
| Payload load/check/unload cycles | 18 | 0 |
| Unscored checks | 6 | 0 |
| Measured sessions | 12 | 0 |

Measurements: attempted 0, completed 0, qualified 0, rejected 0, **unrun 12**.
Admission failed before measurement. No source synchronization, kernel build,
installation, provider/JIT/TCLock load or separate live diagnostic ran. All
remote commands completed with known status; no tool denial or timeout occurred.
The [ledger](../../raw/bench/mmap-plain-v1-20261025/ledger.json) records the bounds
and actual actions.

## Fresh readiness and retained checker errors

Read-only checks found no active source build/Git job or guest project process
or open project file. QEMU discovery matched PID 257489, start ticks 42969155,
command SHA-256
`08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917`
and host boot `2b39cf56-2146-4c87-9fa5-28c66dcee12c`.

All 13 prepared source/binary bindings, both prior API receipts, four installed
candidate boot files, 73 installed candidate modules and the recorded recovery
boot files matched. The existing fixed client, timed client and payload retain
SHA-256 values `398e608687d47c76419480ba2ec8c497d917d20c2fad77525169a211afdb0dd4`,
`20fa73ab725999e6c293fb45869b9c2a139507f8b4f8c4ae484e97a2b4d44e8e`
and `78210ced79da6b70132e41cc2c7a9ac289f83f0380479d1d24556c5a5403686f`.
Candidate identity verified 44 source and 11 build files plus configuration;
recovery verified 20 source and nine build files, configuration and running
Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. The live recovery BTF and all
73 loaded recovery module files matched their retained hashes. The recovery
manifest has 5,686 installed file entries; this attempt checked the 73 loaded
module files, not all 5,686 files.

Two local collector errors are retained as failures. The first used the saved
manifest entry count as a hash map and raised `AttributeError`; the follow-up
incorrectly equated 5,686 manifest entries with 73 loaded modules and raised
`AssertionError`. Neither reported an artifact mismatch. The corrected
continuation completed the remaining manifest/identity/health checks before
host admission. It did not change the admission predicate. See the
[initial partial check](../../raw/bench/mmap-plain-v1-20261025/artifact-check.json),
[failed follow-up](../../raw/bench/mmap-plain-v1-20261025/artifact-remaining.json),
[completed remaining checks](../../raw/bench/mmap-plain-v1-20261025/artifact-remaining-corrected.json)
and [combined readiness record](../../raw/bench/mmap-plain-v1-20261025/artifact-readiness.json).

Among the 22 inspected runner bindings, only `paired.py` and `report.py` differed
between the maintained guest runner and tested current source; they still need
the reviewed idle sync before a
future `plain-v1` execution. No sync was necessary for this stopped admission:
the exact `host_check` function matched current source, SHA-256
`3f4762c9bf68d901cd3fc1dfe30d38e8472151e8741924846e4c2eea0c11b41e`.
This readiness reused the 137 Native/161 KD actual-mmap assertions and the
separate 352 standalone assertions/two basics; none was newly executed.

Guest root had 4,171,517,952 bytes free, data storage 694,603,776 and `/dev/shm`
5,740,777,472. The actual QEMU image backing filesystem had 142,951,632,896 bytes
free. Capacity supported the 512 MiB evidence allowance; no deletion was needed.

## Current admission failure

At **23:40:49 (Asia/Shanghai)** the one full readonly root capture completed,
verified pins and listed the actual snapshot
`before-mutex-kdonly-20261017T140354Z`. Capture transport success is distinct from
admission. At **23:41:42**, the unchanged maintained
`paired.host_check(captured_record, fresh=True)` rejected it with
`Failure('strict original QEMU thread set differs')`.

The extra task was **TID 552994**, `comm=worker`, affinity `[63]`, state `S`,
start ticks `132994043`. All original 67 task identities/names/affinities
matched; none was missing. Its role and initiating I/O remain unknown. This
record does not attribute it to the collector or infer harmlessness from its
name/state. See the [capture](../../raw/bench/mmap-plain-v1-20261025/capture-00-precycle/host-endpoint.json),
[predicate result](../../raw/bench/mmap-plain-v1-20261025/admission-check.json)
and [saved task comparison](../../raw/bench/mmap-plain-v1-20261025/admission-review.json).
No second capture, quiet retry, worker kill, QEMU restart or gate change followed.

## Recovery, retention and next step

Final read-only health at **23:43:26 (Asia/Shanghai)** passed: recovery
`6.1.159-kdclobber2`, boot `d32e2e18-c340-4a98-8105-335bccec0b5d`, the original
73 modules, taint **12288**, 64 CPUs, voluntary preemption, unchanged kernel log
with no matched fault reports, no project processes/open files and empty
`next_entry`. Recovery never stopped running, so no return boot or module drain
was needed. The
[health record](../../raw/bench/mmap-plain-v1-20261025/final-health-check.json)
binds these checks to the initial guest observation.

Raw data remain under the source checkout at
`bench/results/10.176.26.71/raw/bench/mmap-plain-v1-20261025/`. The
[manifest](../../raw/bench/mmap-plain-v1-20261025/manifest.json) binds 38 files,
1,446,396 bytes excluding the manifest; its SHA-256 is
`3483416a9cb765a2da8ffeddf74325bbe78868cb8a76b336123eafe53a4ad647`.
The [executed commands](../../raw/bench/mmap-plain-v1-20261025/commands.txt), streamed
inputs and transport receipts retain the exact operations and both checker errors.

The next useful performance step is separately approving the already prepared
[60-second phase diagnostic](../../../../mmap_lock/DIAGNOSTIC.md) to investigate
the extra-task mechanism, then reviewing fresh benchmark admission. That
diagnostic did not run and remains outside this cycle's authorization. Current
evidence selects no lock bottleneck or optimization. Preserve the validated
one-jiffy reader-drain baseline and all rejected observations.
