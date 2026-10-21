# Accounting-triggered full boundary capture, 2026-10-21

Status: completed and archived. One prompt sample-triggered full capture and
the fresh guest comparison passed with the prepared state retained. The
post-cleanup full capture refused; no timing or performance acceptance is
established. Fresh checks on clean
`824c6a1` found no repository writer or index lock; the same recovery VM was
drained with boot `88449cfc-cea9-4647-a294-bc601e372146`, kernel
`6.1.159-kdclobber2` and the original 73 modules. The main agent remains the
sole writer and VM executor; helpers review read-only.

The [previous bounded hold](../mutex-boundary-20261021/README.md) retained its
five full-capture refusals (75/75/70/68/68) despite eleven intervening accounting
scans with the original exact 67 identities. This follow-up asks whether a full
capture promptly requested from such a scan can pass while the prepared guest
state remains retained. The accounting scan is only a trigger. The unchanged
full host comparison and fresh guest comparison decide feasibility.

Keep one original warmup, the frozen provider/client/workload, one guest
connection and one observer connection. The guest runner and bounded hold
protocol are unchanged. A specified initial accounting scan anchors the original
67 TID/start-tick pairs. Only complete, matching before/after identities with
exact original TIDs/names/affinities and scans begun after the held marker can
trigger. Local queue residence must be at most two seconds; a separate check
requires host capture start within two seconds of host scan start. Different
clock domains are never subtracted from one another.

Observe at the existing five-second cadence. Permit at most four candidate
captures before 95 seconds, with at least 15 seconds after a refused capture
reply before another candidate. Reserve the 25-second request budget before
one unconditional terminal capture at 120 seconds. The full capture's existing
15-second internal deadline and guest's 210-second hold timeout remain in
force. Every candidate, refusal, error and actual request/reply bracket is
retained. Stale samples cannot qualify as prompt triggers even if the independent
full comparison passes. Coordination/state uncertainty retains resources;
verified safe completion uses normal unbind, retirement and drain.

No timed client command is permitted. Waiting after warmup changes admission
clock history and cache/scheduling conditions; any full pass proves only this
observed retained-boundary feasibility. It does not establish continuous
quiescence, original timing parity, variance or a performance gain. Account for
observer/capture overhead, non-atomic reads, missed lifetimes and departed tails.
All seven mutex regressions and acquisition latency remain unresolved;
complete-operation p95 is separate. Readers remain local/concurrent, mmap and
page fault remain separate, and unsupported TCLock bodies remain excluded.

## Focused validation

Implementation `2d27b4c` and deadline correction `813184e` synchronized while
idle; the final transfer verified all 3,968 tracked hashes and updated only the
three corrected diagnostic files. Review tightened the cutoff after evidence
writes and at dispatch, and kept original fixed-mode behavior.

Guest `checks-1` passed serially: two rebuilt basic programs, nine trigger-policy
tests, four held-reply protocol tests and six unchanged recovery-gate tests.
The trigger tests cover task replacement/reuse, duplicate/partial rows,
clock/queue staleness, cooldown, stream failure, absolute deadlines, candidate
budget and a deliberately delayed evidence write. All tested source hashes
remained unchanged; final idle passed on the same recovery boot. The live
probe retains every original frozen correctness, ownership/ACK and ELF
prerequisite in addition to these focused checks.

## Observed prepared-boundary pass

`probe-1` used supervisor `cd8c671`, a documentation-only successor to the
tested and synchronized `813184e`. Guest runner/protocol, provider, client,
workload, translator and original single-warmup settings remained unchanged.

| Observation | QEMU tasks | Full original gate |
| --- | ---: | --- |
| Initial preflight | 69 | Refused; no guest setup yet |
| Preflight at 15 seconds | 67 | Passed; setup then began |
| Triggered prepared-boundary capture | 67 | Passed, followed by passing fresh guest comparison |
| Immediate post-cleanup capture | 70 | Refused |

The one warmup completed **8,375,936 operations** on workers 0–4, with collector
63, all requested placements/progress verified and business checks passing.
The prepared client/source/provider stayed held for **83.971480709 seconds**.
Accounting samples 5–20 were rejected because the exact original task set
differed. Sequence 21, at host held-marker offset 83.383825348 seconds, contained
all original 67 unique TIDs/names/affinities and matching anchored start ticks.
Every row was complete with unchanged before/after identity. There were no
duplicate candidates or skipped dispatches.

That sample spent 1.493343 ms in the source queue before selection. The request
followed the decision by 10.980913 ms, and host capture began **25.431021 ms
after host scan start**, within the two-second policy. Its request was within
the 95-second cutoff; no second candidate or terminal capture was needed.
The full capture took 423.578248 ms wall time. Source receipt of its ACK preceded
the guest reply by 49.595371 ms. The nonce, sample hash, capture hash and actual
source/host request, scan, capture and reply brackets are retained separately;
no cross-machine monotonic-clock subtraction is used.

The selected full capture passed the original 67 identities/placement, QEMU
identity/arguments, frequency/NUMA/binding configuration and actual recovery
snapshot checks. The guest independently passed the unchanged recorded boot
transition, command line, preemption, dependency/Python and topology comparison.
Before/after physical idle, publication/image, source and exact drained counters
were identical. Cumulative preparation-plus-warmup JIT entries/completions were
**7,903/7,903**, with zero address-guard exits; these are not a warmup-only delta
or a rate. Source state stayed OPEN with one source module and zero frames/writers.

Normal cleanup retired to state 2 with zero modules/frames/writers. Origin
acquisitions/releases both totaled **57,525**; active waiters, reserved nodes and
active tasks were zero. The retained session had no kernel fault matches.
Final health reverified all frozen inputs and the same recovery boot/kernel
with the original 73 runtime modules. The guest reports `passed=true`,
`diagnostic_completed=true`, `measurement_skipped=true`, `final_idle=true`,
`accepted=false`. There is no client `measure` phase, measurement artifact or
throughput field.

## Scope, activity and next discriminator

The observer retained 22 accounting samples, initially 69 tasks, a maximum of
82 and a last accounting sample of 67. During the hold, counts fell from 70 to
68, rose to 82 at about 33 seconds, then returned to 67. Matched worker intervals
wholly within the hold recorded 3.592482 ms runtime, 122,880 read bytes and
643,072 written bytes. These do not include unmatched initial values or departed
tails. A burst during the command-free hold cannot be attributed to a specific
guest or host subsystem from this evidence.

The last accounting sample's **67** is distinct from the endpoint full
capture's **70**: new workers 450857/450858/450859 had no accounting sample.
Thus even this successful boundary did not persist through normal validation,
cleanup and the endpoint capture. The earlier five scheduled refusals and
eleven intervening exact-67 scans remain untouched in their separate cohort.

Observer CPU was **1.943684279 seconds over 107.986703590 seconds**, or
**1.799929% of one core**, including four full captures. Full-capture CPU costs
were 418.346306–438.475743 ms and wall costs 423.578248–443.646950 ms. The maximum
unsampled gap was 5.435593469 seconds; maximum scan wall time was 15.003294 ms.
Startup, SSH/sudo and source-supervisor costs are excluded. Reads are non-atomic;
intervening changes, short lifetimes and departed tails remain unobserved. One
feasibility session gives no estimate of repeatability or timing variance.

**Observed prepared-boundary feasibility is established for this run.** A sample
alone never passed admission, and no gate was relaxed. This does not establish
continuous quiescence, original preparation parity or an accepted performance
comparison. The post-warmup wait changes provider sampling-clock history and
cache/scheduling state. The next evidence-backed discriminator is a separately
labeled no-timing control that places the quiet wait before the one original
warmup, then requests the full gate immediately after warmup without another
quiet wait. That can test whether warmup recreates host workers; it still needs
its own changed-history record and cannot be pooled with original timing.
All seven regressions and acquisition latency remain unresolved.

## Preservation and review

Guest evidence is sealed at
`/root/kdlock-evidence/10.176.26.71/bench/mutex-boundary-trigger-20261021-archives-1`.
Local raw evidence is under
`bench/results/10.176.26.71/raw/bench/mutex-boundary-trigger-20261021/`:
`probe-1/`, synchronization/check logs, `observer-review-3.json`, final health
and `archives-1/`. The [inert review](review.json) passed **2,046 checks** and
binds all raw files through `raw_sha256`. It verifies archive/source/prerequisite
bindings, original settings, every phase/trigger/capture relationship, the
retained preflight refusal, unchanged held state and exact retirement.
Independent read-only review also verified all three archives and 165 inventory
members, nine supervisor source bindings, 78 tested-source copies and all 36
phase acknowledgement chains, and reproduced the accounting calculations.

The offline accounting reader now distinguishes a recorded original-task anchor
from a passing gate when the initial sample has extra workers. Its old first-
sample assumption and an intermediate analysis error are retained in
`offline-review-development.json`; neither changed live evidence. The corrected
reader reproduces the preceding cohort's accounting results exactly after JSON
normalization, adding only explicitly named reference-sample fields. Archived
code was never executed. Helpers remained read-only and reported no files touched.

Archive manifest SHA-256:
`c01910453dd0183e30e6e167fb5f7359df200a655958a6174658e55fb5184812`.

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `checks.tar.gz` | 144,164 | `25283f3bba04dfb837551ec76f0f47415703d48cce37ce5e5207ae0a83380820` |
| `probe.tar.gz` | 138,912 | `2fe7930044701878ba4f91424a94466d58a736cb1c1a5181f3d6c46e7ba77f38` |
| `metadata.tar.gz` | 29,150 | `432819e54d18133fe69f86455e2921331caf034ee431ad88992df86955b303c0` |
