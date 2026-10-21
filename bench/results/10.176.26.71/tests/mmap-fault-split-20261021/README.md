# Separate mmap and page-fault validation

Status: split correctness and all 48 serial timing sessions completed. Performance
acceptance remains open because the strict host endpoint failed. This stage
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

`timing-prepare-2` at `77cadf5` passed both basic programs and all eight new timed
client checks (Native mmap-only and Native/KD/TCLock fault readers, at 1/16
workers). The validated `9291000` provider/payload binaries were reused without
modification. Every case joined and drained; exact callback counts, all samples,
source identities, per-session logs and normal retirements are retained. These
single preparation runs are correctness evidence, not the three-repeat timed
comparison. Timing acceptance remains pending the strict host check and the
separate measurement stage.

## Controlled timing at 77cadf5

`timing-run-1` completed all 48 sessions, 299,528,608 operations and 2,363,615
sampled complete-operation observations. All workers joined and all 36 KD-hosted
sessions retired with state 2 and zero modules, writers and frames. Twelve
TCLock sessions confirmed quiescence. There were no recorded kernel fault
matches. Every arm reused the validated `9291000` payload/provider binaries;
new client and collector sources are identified separately at `77cadf5`.
The frozen plan uses 1/16 workers, three rotated repetitions, two-second
windows, collector 63, 300 ms settling/peak windows and 10 ms progress samples.
No parallel test, kernel change, admission change or forced cleanup occurred.

These are two distinct workload tasks. Mmap-only is one `mmap`/`munmap` pair
without touching the range; its callbacks and backing acquisitions stay zero.
The fault task maps before measurement and counts `MADV_DONTNEED` plus a checked
CPU read as one operation. All fault callbacks execute on the origin and keep
shared reader ownership. Each process has its own native mm; the backing object
is shared. This does not measure contended same-mm mmap writers or isolated
hardware-fault/lock-acquisition time. Mmap is a Native control, with no fictitious
KD/TCLock mmap-lock arms. TCLock's unsupported task/GS-dependent, sleeping or
user-accessing combined bodies are excluded.

Whole-run throughput below uses unsampled sessions. P95 comes from separate
sampled sessions, every 64th operation, without combining repetitions. Rates
are millions of complete operations per second; brackets give three-repeat
minimum–maximum. The coefficient of variation (CV) uses population standard
deviation. The same binary and prefaulted sample storage are used in both modes.

| Task | Workers | Backing arm | Whole Mops/s median [range] | Whole CV | Operation p95 μs median [range] |
| --- | ---: | --- | ---: | ---: | ---: |
| mmap-only | 1 | Native mmap control | 0.647434 [0.362298–0.651447] | 24.45% | 1.607 [1.599–2.907] |
| mmap-only | 16 | Native mmap control | 0.636509 [0.625237–0.636650] | 0.85% | 29.501 [29.495–30.853] |
| fault cycle | 1 | Native reader | 0.599191 [0.596918–0.605257] | 0.59% | 1.847 [1.784–1.853] |
| fault cycle | 1 | KD local reader | 0.586062 [0.583515–0.594073] | 0.77% | 1.841 [1.835–1.898] |
| fault cycle | 1 | TCLock reader | 0.589830 [0.575169–0.594835] | 1.42% | 1.918 [1.891–2.070] |
| fault cycle | 16 | Native reader | 7.084178 [5.729899–7.134005] | 9.78% | 2.878 [2.873–2.883] |
| fault cycle | 16 | KD local reader | 7.601296 [7.577628–7.636943] | 0.32% | 2.379 [2.378–2.498] |
| fault cycle | 16 | TCLock reader | 7.494494 [7.460055–7.521518] | 0.34% | 2.491 [2.472–2.495] |

[All per-repeat rows](per-repeat.csv) and the [full statistics](timing-summary.json)
retain whole rates, conservative full-cohort peaks, p95 ranges/CV and paired
observation ratios. Sampled/plain whole-rate ratios span 0.976420–1.252952;
scheduling variance prevents interpreting that entire range as isolated sampling
cost. The low one-worker mmap repetition and low sixteen-worker Native fault
repetition remain included. Instrumentation and workload work are identical
within each supported comparison, including callback/reader accounting; those
counters can contribute to contention. No mutex optimization or causal gain
is established by these separate reader results.

The original strict host preflight passed with exactly the original 67 QEMU
threads. The immediate endpoint captured **73**, so that check **failed**.
CPU pins, QEMU identity/arguments, NUMA configuration, frequency policy, recovery
snapshot, guest boot and kernel identities matched. The endpoint is not replaced
by a later quiet snapshot, and the condition is not waived. Results remain
provisional; `accepted=false` is preserved in every stage receipt.

## Preservation and unresolved scope

The [final health receipt](final-health.json) verifies 2,080 retained/current
input hashes and actual idle. The [independent offline review](offline-review.json)
passed 78,261 integrity and arithmetic checks over 3,365 archive members,
3,084 files and zero symlinks. It independently reconstructs peaks, p95,
per-repeat variance, sampled/plain ratios, source Git bindings and the retained
failed preparation. It separately records the failed host acceptance check;
evidence consistency is not performance acceptance.

The [archive manifest](archives.json) has SHA-256
`4acfa86add5b2e15dc117e4ade0059292b36cbeb0824d1713c3b4011363e53dd`.
Five archives separately preserve fixed-work correctness, the preparation
failure, timed-client validation, timing, and control/health metadata. Copies
are retained in the original VM's
`/root/kdlock-evidence/10.176.26.71/tests/mmap-fault-split-20261021-archives-1`
and source-host `bench/results/10.176.26.71/raw/tests/mmap-fault-split-20261021/archives`.
Archived source is inspected inertly, never executed on the source host.

The [final disposition](final-status.json) leaves all seven original mutex
causes unresolved: c08 at 3/4/5 workers, pipebytes at 3/5, pipecap at 5 and RCUHT
at 2. Their original controlled replays and later latency/ownership diagnostics
remain separate evidence; this reader workload does not rerun or close them.
Strict host stability, sampling-cost isolation, same-mm mmap contention,
whole-kernel mmap-lock conversion, generic fault replay and signal-driven
cancellation also remain unresolved. No delegated-reader result is required or
claimed for the intentionally concurrent reader workload. A genuinely exclusive
backing writer would need its own supported contract and returned-body evidence.
