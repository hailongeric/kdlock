# Basic functional delivery

Status: **basic functional handoff complete**. All four lock families have
returned-JIT smoke passes across the two recorded attempts. The
user requested a basic version across all original tasks before more performance
analysis. This stage changes no production lock, admission, ownership, ACK,
cancellation or teardown protocol.

Source ownership at 2026-10-22 06:12:54 UTC: clean `9e9df64`, neither previous
coordinator present, no visible checkout writer or test runner; 551 processes
were inaccessible. The guest check at 06:13:23 UTC confirmed idle recovery boot
`97c45a77-3ce3-4d3f-87b4-4ef3e880af64`, the exact 73-module set, 64 CPUs and no
build/profile tasks. No in-flight run was stopped. The main agent is the sole
writer and executor; existing helpers remain finished and touched no files.

`bench/basic/run.py` runs both basic programs, focused runner guards and four
existing fixed-work list cases serially: KD spin, public mutex, rwlock and
rwsem, 16 nodes, 100,000 iterations per worker. Shared families keep
20% writes and local concurrent readers. Every case requires positive returned
JIT bodies and complete drain. Additional CPU-63 I/O workers are recorded in
this unscored functional mode; the original timing gates are unchanged.

Attempt `run-1`, frozen `6237f5e`, passed dependencies, both basic programs and
four runner tests. Spin and public mutex each completed 1,600,000 operations;
matching JIT entry/completion counts were 1,591,572 and 1,533,374. The 16-worker
mixed rwlock case completed and drained with zero returned JIT bodies. Its
strict `NO_JIT` failure stopped the runner before rwsem. This is retained as a
failed delegation check, not relabeled as delegated support. The separate
post-run guard confirms the same idle recovery boot and exact 73 modules.

The basic preset uses the already exercised 60-worker mixed rwlock case;
spin, public mutex and rwsem retain 16 workers. `run-2`, frozen `c04a7b0`, selected
only rwlock and rwsem, preserving passed cases and the failed original attempt. It retained
`--require-jit`, list/data/reader checks and full retirement. This geometry change
is a functional preset, not a comparable timing rerun or causal correction.

## Completed smoke

| Family | Attempt / source | Workers | Completed operations | Matching JIT entries / returns |
| --- | --- | ---: | ---: | ---: |
| Spin | `run-1` / `6237f5e` | 16 | 1,600,000 | 1,591,572 |
| Public DIRECT mutex | `run-1` / `6237f5e` | 16 | 1,600,000 | 1,533,374 |
| Rwlock | `run-2` / `c04a7b0` | 60 | 6,000,000 | 7,166 |
| Rwsem OUTER writer | `run-2` / `c04a7b0` | 16 | 1,600,000 | 50,857 |

Each attempt passed both basic programs and all four focused runner tests,
including rejected safety-condition changes, local/partial execution and the
four real child command plans. No tests were skipped. Both host captures had
67 threads; allowance for additional correctly pinned I/O workers is covered by
the focused guard test, not a claim about observed extra workers in this run.
Both attempts used 90-second post-idle settling and the same recovery boot.

The successful rwlock case completed 4,800,000 reads and 1,200,000 writes;
rwsem completed 1,280,000 reads and 320,000 writes. Readers remained local.
All five sessions, including the failed strict rwlock case, passed data and
worker-progress checks, drained and retired with exactly
`{state:2, modules:0, frames:0, writers:0}`. Their five kernel logs contain no
matches for the existing fault scan. The final guest health confirms the same
idle recovery boot and exact 73 modules. No kernel was changed or rebooted.

This stage changes only the functional runner and documentation. Production
provider, translator, API, workload and kernel-adapter sources are unchanged
from `47fa612`. Historical continuation and actual-MM results below retain their
original identities; they were not rerun or relabeled as new measurements.

Existing evidence keeps its original identities:

- [Nine continuation/ownership probes and 16 resident-list cases](../native-continuation-20261020/README.md)
  cover reviewed markers, exact handback, sticky refusal and family functionality.
  Later shared type/initialization refactoring retains separate
  [kernel integration validation](../mmap-kd-kernel-20261021/README.md).
- [Actual-MM Native/KD correctness](../actual-mm-plain-20261021/README.md)
  separates untouched mapping from faults. MM readers and writers are local;
  no TCLock MM or arbitrary delegated MM support is claimed.
- [Deterministic observer controls](../mmap-phase-controls-20261022/README.md)
  are complete; further causal observer work is deferred.

The [quick start](../../../../../docs/PROJECT_GUIDE.md#basic-working-version)
provides commands and scope. Causal profiling, wake attribution, the seven
regressions, qualified variance and p95 remain unresolved/deferred. Earlier
failed receipts and rejected timings are preserved.

## Evidence and remaining work

Guest evidence is under
`/root/kdlock-evidence/10.176.26.71/tests/basic-version-20261022`.
Local raw evidence is under
`bench/results/10.176.26.71/raw/tests/basic-version-20261022`.
The [guest archive manifest](../../raw/tests/basic-version-20261022/guest-archives-2/archives.json)
seals both attempts and final health. The [offline audit](../../raw/tests/basic-version-20261022/audit.json)
passed 17,731 checks with zero mismatches: 2,488 regular files, 321 directories,
10 symbolic links, 1,429 frozen source bindings and all five session/retirement
receipts. It reads archive members without extracting or executing them.
The three archives total 17,251,118 compressed bytes and 64,108,064 payload bytes.

| Artifact | SHA-256 |
| --- | --- |
| `guest-archives-2/archives.json` | `1ce4b032f6d8cce6e17d40eb18c46dd12b8b12d0d18d8f83c06b308a98118de3` |
| `guest-archives-2/attempt-1.tar.gz` | `223be5de2e65068ed31e46ebe889cfcdef77be0c7b9aed649de27eaa67632c57` |
| `guest-archives-2/attempt-2.tar.gz` | `81e4e626e2b2a12be2054513e92f3295fd9d44aef3f06470817d47b35d3c674e` |
| `guest-archives-2/metadata.tar.gz` | `118d8122c605f3961ae33cee4bf935c6ea64e0267704eba6dcd319502b027c27` |
| `final-health.json` | `faaa66b94951cf3c8e51f42ce0555b582ed43d098ee225d875d4a842bb9896ea` |

The first copy-back approval review timed out before execution. Its permitted
retry reached the transfer but rejected a trailing `/.` directory name. The
failure log remains in `copy-archives.log.stderr`; copying the explicit directory
name succeeded in `copy-archives-2.log`. No security check was bypassed, and the
guest archives were unchanged.

Deferred optimization order:

1. Diagnose low-cohort rwlock delegation variability; the 16-worker `NO_JIT`
   result remains unresolved and the larger preset does not repair it.
2. Resume the seven mutex-regression and MM wake-cause investigations with
   separate frozen inputs, unchanged timing gates and reported rerun variance.
3. Address broader MM callback/fairness coverage, then optional p95 and larger
   matrices. Whole-kernel replacement, RT/ww_mutex and lockdep remain unvalidated.
