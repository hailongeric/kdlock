# Separate mmap and page-fault validation

Status: split correctness passed; timing preparation is in progress. This stage
follows the user's instruction to retain concurrent, local readers and split
mmap from page-fault workloads. No admission or protocol checks are removed.
The sole source writer and VM executor is the main agent; helpers are inactive.

The unbuilt exclusive-lookup draft is preserved at
`codex/archive-mmap-exclusive-lookup-20261021`, commit
`206cfc158169d66baaa95fa3c22e4d7e9e7f210c`. Its artificial writer sequence was
rejected before any build or VM execution. No result from that draft is a pass.

The maintained source keeps the original shared reader protocol. Only the task
pointer capture moves before the backing critical section, and final release
also refuses context/data errors. Two separately named workloads have distinct
oracles: mmap-only must perform zero callbacks and zero backing acquisitions;
CPU faults must produce one callback and reader pair per successful fault cycle.
Retry/revalidation/fallback checks and real metadata-writer concurrency remain.
TCLock is included only for supported resident backing operations. Native mmap
ownership stays Native; no TCLock or KD mmap-lock replacement is claimed.

The previous [local correctness stage](../mmap-fault-optin-20261021/README.md)
is fixed historical evidence. All seven mutex regressions remain open at the
[prior investigation](../../bench/pipecap-owner-20261021/final-status.json).
New source versions, observations and future timings must remain separate from
those baselines. Acceptance is false until remaining gaps are resolved or
explicitly listed as unresolved.

## Correctness at 9291000

`live-1` (Native/KD) and `live-2` (TCLock) passed serially on the original VM.
Each run passed both basic C programs. The existing clients retained 96/96/100
checks respectively, and all 18 additional split cases passed. For each backend:

| Separate case | Completed operations | Callback/reader pairs | Writer pairs |
| --- | ---: | ---: | ---: |
| mmap-only, one worker | 1,000 | 0 | 0 |
| mmap-only, sixteen workers | 16,000 | 0 | 0 |
| faults, one worker | 5,000 | 5,000 | 0 |
| faults, sixteen workers | 80,000 | 80,000 | 0 |
| fifteen fault readers and one writer | 16,000 | 15,000 | 1,000 |
| sixteen VMA-only lifetimes | 16,000 | object freed; exact data/join and release checks | 0 |

All object/file and provider checks drained, with zero context/data/release
errors. KD retirement returned state 2 and zero modules, writers and frames.
The TCLock run had no KD provider and confirmed its own quiescent state. The
[Native/KD receipt](live-1-result.json) and [TCLock receipt](live-2-result.json)
retain the complete per-worker and fault-ownership evidence. No reader body was
submitted for delegation. Raw unbound observation counters cannot establish a
JIT execution class; the ordinary reader interface and exact callback receipts
are the scope of these results.

Host capture found 69 QEMU threads before Native/KD and 73 before TCLock, with
original CPU pins, snapshot, boot, kernel and configuration. These are functional
checks. Timing retains the original strict 67-thread identity preflight and must
record any endpoint mismatch without claiming acceptance.

`timing-prepare-1` at `8e87640` failed before module loading: the new timing
snapshot omitted `daemon/daemon.c` and its private includes, required by the
basic daemon-policy test. The control-call program compiled; neither basic
program ran. No timed client was built or executed. The failed log and source
snapshot remain immutable. The follow-up adds the complete daemon directory to
the frozen inputs and reruns preparation from a new run identifier.
