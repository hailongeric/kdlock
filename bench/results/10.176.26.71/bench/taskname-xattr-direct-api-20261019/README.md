# Taskname and xattr: direct calls to the original kernel APIs

This revision removes the repeated service-dispatcher transition around
`strcmp()` and `strscpy_pad()` inside eligible delegated spin critical sections.
The implementation is frozen at local Git commit
`05876a44f841979eae776f0146f0fe9e5c3c8f26`.
Focused builds, unit checks and live correctness/delegation checks passed.
**All 567 standard-grid sessions validated and drained.** At 60 workers, KD
improved by 1.838×, 4.901× and 6.528× over the previous KD dispatcher on taskname,
xattr n16 and xattr n128 respectively. It remained below TCLock on all three;
the gains do not establish parity or eliminate the low-worker-count gaps.

The original payloads, kernel APIs and selected KD mutex protocol are unchanged.
Taskname and xattr here use spin delegation: a lock owner executes another
task's protected work. JIT means just-in-time generated code, which translates
that protected work for execution by the owner. This change improves how that
code calls the original functions; it is not another mutex algorithm.

The comparison baseline is the completed
[`88bb5a4` original-API round](../taskname-xattr-native-api-20261019/README.md).
That version already removed helper-specific checks. The earlier checked-helper
`c79d84f` results remain historical and are not pooled into this comparison.

## Why the previous path was expensive

Each string call returned to a C service dispatcher, which checked the execution
frame, read the CALL return address, pinned source code, invoked the API, saved
the continuation and reentered generated code. A frame records execution state
and ownership; a source pin keeps code resident until execution finishes.
The first exit saved full register state. Each call took the source-pin shared
lock and incremented three shared counters. Xattr repeated this per name.

Separate function profiles of `88bb5a4` recorded these exact relationships at
60 workers:

| Workload | Source-pin lookups per returned body | Frame validations per returned body |
| --- | ---: | ---: |
| Taskname | 1 | 7 |
| Xattr tail, 16 attributes | 16 | 37 |
| Xattr tail, 128 attributes | 128 | 261 |

Xattr n16 returned 85,683 bodies, with 1,370,928 lookups and 3,170,271 frame
validations. Xattr n128 returned 12,343 bodies, with 1,579,904 lookups and
3,221,523 frame validations.

A returned body completes through its validated outer unlock; publication alone
does not demonstrate execution. These profiles include measurement control reads
but exclude preparation, warmup and cleanup. Tracing changes cost and delegation
frequency; nested function times overlap. They are diagnostic, unscored evidence.
TCLock executes the native body on the waiter's stack without KD's dispatcher
transition. This structural difference does not assign the entire throughput
gap to one function. [DEVELOPMENT.md](DEVELOPMENT.md) retains both profiling
attempts, including the first xattr preparation failure.

The final 18 diagnostic sessions completed and drained with tracing restored.
In all six KD cases, measured source-pin lookup, full-frame validation,
continuation-save and C string-adapter calls fell to zero while delegated bodies
returned. The [profile comparison](profile-comparison.json) retains the exact
counts and source identities. This confirms avoidance of the repeated dispatcher
work; exact ownership and lifetime remain checked by the existing minimal spin
request path and publication rules.

## What changed

Generated code calls the original `strcmp` or `strscpy_pad` directly and continues
in one invocation. “Direct” means a machine CALL without the dispatcher round
trip. Original argument pointers are retained; the helper runs on the executor's
stack. The caller supplies valid objects, storage and lifetime as for native C.

Neither helper receives extra instruction checks, source-CALL encoding checks,
string scans, destination-bound checks or runtime overlap checks, at translation,
publication or execution. Ordinary analysis of captured inputs and memory effects
remains: `strcmp` writes no caller memory, while `strscpy_pad(..., 64)` can write
all 64 destination bytes. Its statically known count and local destination let
analysis represent those writes accurately. The original helper retains its
padding and truncation semantics.

The route supports a fresh ABI1 spin request holding one physical lock. An ABI
is the agreement about registers and data layout. “Fresh” means execution has
not begun or created a nested continuation; the waiter differs from the executor.
Other resumable services, nonterminal lock controls and runtime address guards
exclude this route. Ordinary translated callees and the final unlock are allowed.

The wrapper aligns its execution stack once, preserves the required caller
registers and uses bookkeeping that preserves arithmetic flags around the
helper. It retains the actual source CALL's return-address write on the waiter's
stack, reads and consumes that word once, and accepts only the allowed return.
It permits 128 comparisons and 16 padding calls per invocation. If a quota runs
out, the pending helper has not executed: the original waiter receives that
call and finishes the native suffix under the existing lock. Unknown ordinary
calls similarly end the generated invocation. Reentry cannot reset these quotas.
Malformed state, invalid returns and instruction-budget exhaustion remain errors.

Provider version 11 advertises optional capability bit 10. **Relocation** fills
generated CALL offsets after the image address is known. A separate preallocated
pool near kernel text reserves up to 40 MiB, sharing the 64-image limit.
Unavailable support retains the dispatcher; later pool exhaustion refuses
publication. Helper and continuation code are pinned at publication, and images
remain immutable while used. Only generated CALL locations and offset ranges
are checked. Helper counts are exported once per wrapper return.

The two-word wrapper ABI, exact owners, source leases, unlock acknowledgements
and frame retirement remain required. Counters never replace ownership proof.
KD mutex keeps its legacy queue/batching and ABI2; this route does not apply to
it. See the canonical
[direct-call contract](../../../../../docs/design/admission.md#direct-original-helper-calls)
for the implementation boundaries.

## Remaining execution cost

KD still prepares a request, binds its ownership record, enters the wrapper and
validates completion before retiring and waking the waiter. Each direct helper
call still saves eight registers, records and consumes the original CALL word,
updates its quota and validates the return. Translated list traversal also has
register bookkeeping and a branch-block execution budget. A successful minimal
completion does not export a full register packet.

Native executes the same protected body locally. TCLock has its own queue and
stack-switch work, but runs native instructions on the waiter's stack without
KD's translated helper bridge. Fixed request costs plausibly matter more for
short taskname bodies, while xattr repeats bridge work for every comparison.
This is a source-level explanation of remaining work, not a measured allocation
of time or cache contention to individual operations.

## Validation and evidence

Provider and daemon builds passed. Candidate 1's three fixture failures and
corrected retries remain in [DEVELOPMENT.md](DEVELOPMENT.md). Candidate 2 passed
14 live sessions, including short/300-character strings, recovery probes,
three-backend taskname and eight KD xattr controls; all drained.
Candidate 3 passed both basic C programs, six affected drivers and ten live
sessions. Its actual generated-wrapper fixture passed 15,663 assertions for
stack alignment, registers/flags, return words, quotas, truncation and rejection
of corrupt returns. These are focused checks, not a full suite.

Each candidate's separate 36-session KD-only screen uses 4/5/16/60 workers.
Those source versions, screens and profiles are not pooled into final results.
Outside timing, [report.py](report.py) compares uploaded CALL placeholders with
actual loaded bytes, publication identity and independently captured helper
addresses. Replay hashes include loaded bytes and receipts, without inspecting
helper instructions.

## Standard-grid comparison

The round contains **567 measurements**: three cases, 21 worker counts,
three backends and three repetitions. The backends are current KD, Linux Native
and TCLock. Worker counts are:

```text
1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60
```

| Case | Protected operation | Measurements | KD measured status |
| --- | --- | ---: | --- |
| Read-only taskname | Original `strscpy_pad` into a 64-byte local result | 189 | 56 PASS, 7 NO_JIT |
| Xattr tail, n16/v64 | Find the last of 16 attributes and copy its 64-byte value | 189 | 55 PASS, 8 NO_JIT |
| Xattr tail, n128/v64 | Find the last of 128 attributes and copy its 64-byte value | 189 | 57 PASS, 6 NO_JIT |

Taskname uses the same ordinary call shell and module-owned snapshot; it is not
a complete `ps` or procfs test. Xattr retains the original comparisons and value
copy, with one validated syscall per operation. Each measurement targets two
seconds. KD preparation uses 16 workers and at most eight learning rounds; warmup
and preparation are excluded. Taskname warms up for 48,000 operations per worker;
xattr also requires at least one second. Workers occupy CPUs 0 through N−1 and
CPU 63 collects progress. The guest has 64 CPUs in two NUMA nodes, or groups
with different memory-access locality, containing CPUs 0–31 and 32–63.
Taskname retains four post-lock work rounds. KD and TCLock retain NUMA-aware
selection and a 1,024-request batch limit. Progress is sampled every 10 ms;
peak windows start after 300 ms of settling and require progress from every worker.

Rates are three-repeat medians in million operations per second (Mops/s).
Whole-interval rates and qualifying 300 ms peak rates remain separate.
`PASS` requires a returned generated body; `NO_JIT` means
no measured generated entry; `PARTIAL_JIT` means entry without a returned body.
Preparation counts and a `NORMAL` published image do not establish measured
delegation. The 189 KD sessions contain **168 PASS, 21 NO_JIT and zero PARTIAL_JIT**,
with **751,832,469 returned bodies** and no address-guard exits. Mixed-status
repetitions are not pooled into one ratio.

### Fresh controls at 60 workers

These are whole-interval medians. Ratios use unrounded values; returned share
is the median fraction of measured operations completed by generated bodies.

| Workload | Native | TCLock | KD | KD / Native | KD / TCLock | KD returned share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Taskname, read-only | 3.860 | 5.008 | 4.521 | 1.171× | 0.903× | 99.89% |
| Xattr tail, n16/v64 | 2.182 | 2.412 | 2.368 | 1.085× | 0.982× | 99.90% |
| Xattr tail, n128/v64 | 0.562 | 0.600 | 0.573 | 1.020× | 0.956× | 99.89% |

All nine KD repetitions here returned delegated bodies. The separate peak
KD/Native ratios are 1.106×, 1.059× and **0.956×**: xattr n128's whole-run lead
over Native does not extend to the peak measure.

### Historical KD comparison

Only matching settings and complete three-repetition status groups are compared.
Fresh controls above are never replaced by historical Native/TCLock samples.

| Workload at 60 workers | `88bb5a4` KD | `05876a4` KD | New / old | Old → new returned share |
| --- | ---: | ---: | ---: | ---: |
| Taskname | 2.460 | 4.521 | 1.838× | 99.88% → 99.89% |
| Xattr tail, n16/v64 | 0.483 | 2.368 | 4.901× | 99.89% → 99.90% |
| Xattr tail, n128/v64 | 0.088 | 0.573 | 6.528× | 91.03% → 99.89% |

Of 63 workload/worker points, 61 qualify. Taskname and xattr n16 at three
workers mix PASS and NO_JIT repetitions and are excluded. Among the eligible
points, 55 have both whole-run and peak medians at least as high as old KD.
The six exceptions are taskname at 4/5 workers, xattr n16 at 1/2, and xattr n128
at 1/3. Their whole-run ratios are 0.999×, 0.964×, 0.988×, 0.999×, 0.998× and
0.972× respectively. These small-sample median differences are retained without
claiming statistical significance.

The remaining gaps are substantial at some low counts. At four workers,
taskname reaches only 0.522× Native and 0.887× TCLock, with a median returned
share of 0.01%. Xattr n16 reaches 0.628× Native and 0.766× TCLock there, despite
improving 3.234× over old KD; its returned share falls from 98.41% to 28.59%.
At one and two workers all three KD cases remain NO_JIT, measuring local locking.
Across the 61 eligible current points, KD meets or exceeds Native at 21 points
for whole-run rate and 16 for both measures. It meets or exceeds TCLock at only
one point for both: xattr n16 at 52 workers. This is an improvement over the
dispatcher, not a universal lead over either competing lock.

[Full tables](tables.md) retain all 21 worker counts and both measures.
Machine-readable data are in [current-full-grid.csv](current-full-grid.csv),
[historical-kd-full-grid.csv](historical-kd-full-grid.csv),
[groups.csv](groups.csv) and [sessions.csv](sessions.csv). The plots show fresh
controls; status and returned-share details remain in the tables.

| Taskname | Xattr n16 | Xattr n128 |
| --- | --- | --- |
| [PNG](taskname.png) · [SVG](taskname.svg) | [PNG](xattr-tail-n16-v64.png) · [SVG](xattr-tail-n16-v64.svg) | [PNG](xattr-tail-n128-v64.png) · [SVG](xattr-tail-n128-v64.svg) |

### Identity, replay and preserved evidence

[compare.py](compare.py), [comparison-policy.json](comparison-policy.json) and
[comparison-audit.json](comparison-audit.json) bind both revisions and their
source manifests. Recorded environments match except for output paths; the
four measurement validators are unchanged. Both the current
[before/after host checks](host-comparison.json) and
[historical host checks](historical-host-comparison.json) passed all nine checks,
including the same VM, 64 CPU pins, service CPU and frequency policy. Effective
frequency and host load were not measured. These runs compare complete source
revisions and changing delegation shares; they do not isolate the cost of one
dispatcher operation.

The [health receipt](health.json) records 567 drained sessions and 567 kernel
logs without fault matches. The schema-2 replay hash is
`a6ec71e2e317a292f7c63b8279a02e80cc0c0e9baf9ab79546c875f934f5a315`.
The independent [main archive audit](archive-audit.json) passed: 567 sessions,
265 source files matching Git, 16 binaries and 315 loaded image captures,
including all 189 measured KD images. Uploaded CALL placeholders and loaded
relocated bytes are checked separately; no helper instructions are inspected.

Exact runner arguments and successful exits are retained in
[taskname.command.json](taskname.command.json), [xattr.command.json](xattr.command.json),
[replay-final.command.json](replay-final.command.json) and
[comparison-final.command.json](comparison-final.command.json). Run those tools
only in the documented idle recovery VM with a new output directory.
The main guest evidence is
`/root/kdlock-evidence/10.176.26.71/bench/taskname-xattr-direct-api-05876a4`.
Exported archives are under
`bench/results/10.176.26.71/raw/bench/taskname-xattr-direct-api-20261019/`.
[archives.json](archives.json) binds their complete membership:

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `taskname.tar.gz` | 15,602,605 | `09e50c19616b8029e5f1ade36fe2605e4d73f7ba9d35bd06b951551db744e8e5` |
| `xattr.tar.gz` | 19,663,550 | `62e303e6a8c6c9a88c60e618f30726d0c2b6029a22c5a460584f1a9957f9badd` |
| `metadata.tar.gz` | 1,024,488 | `f4caff1ddcdad513d337839f82a976673b4fbe60517700c42207377f4dc2e365` |

## Quota recovery control

A separate unscored n129 xattr tail control reused the final source and binaries
at 16 workers. It passed correctness and drained. Its measured 329,728 operations
include 329,228 generated prefixes and **zero completed generated bodies**:
the expected PARTIAL_JIT status demonstrates native continuation, not full-body
delegation. Across the entire session, including warmup and checks, 1,070,524
quota exits matched 1,070,524 native starts, completions and unlocks, after exactly
137,027,072 direct comparisons (128 per exit). Exact retirement recorded zero
frames, modules and writers. [quota-result.json](quota-result.json) retains the
receipt; aggregate counters do not replace runtime ownership or unlock checks.
Its [archive audit](quota-archive-audit.json) passed separately from the main
matrix. The [six development archive audits](development-archive-audit.json)
also passed preservation checks, retaining failed attempts and eleven planned
but unrun profile sessions. The first failed profile lacks a pre-refusal tracing
snapshot; that limitation and the corrected preservation audit are recorded in
[DEVELOPMENT.md](DEVELOPMENT.md#development-and-quota-archive-preservation).

## Remaining scope

The recovery guest uses kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, with boot and snapshot identities in
the development record. Builds, checks and timing run only in that VM. Source
editing and Git work run on 380G10. Development archives retain failed attempts
alongside successful checks; archive completion is distinct from test acceptance.

The previous 20% taskname mutation controls were correct and drained but had
zero measured KD JIT bodies; mutation delegation remains unaccepted. Whole-kernel
replacement, other lock types and oversubscription are not established by this
spin-workload round. The main grid, comparison, loaded-image audit and all
development/quota archive checks are complete. Preservation does not change
the recorded failed outcomes or supply missing observations.
