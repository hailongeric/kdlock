# Direct original-API calls: investigation and validation

This revision optimizes execution of the original `strcmp` and `strscpy_pad`
inside delegated taskname and xattr bodies. It preserves the selected KD mutex
protocol. These workloads use spin delegation; they do not exercise a replacement
mutex algorithm. The previous implementation and full comparison remain fixed
at [`88bb5a4`](../taskname-xattr-native-api-20261019/README.md).

The final `05876a4` round completed all 567 sessions, replay and independent main
archive audit. The separate n129 quota control also passed and drained. Export
and independent preservation audits of that control and all six development
archive sets are complete. Earlier failures below remain failures, separate from subsequent
successful checks and the final performance results.

## Measured overhead in the previous implementation

Separate function profiles used the ordinary payloads at 16 and 60 workers,
one diagnostic repetition per backend and case. Function tracing changes cost
and the proportion of work delegated, so these runs have no throughput score.
Function times include nested calls and must not be added together. Preparation,
warmup and teardown were outside the profiling interval.

Every original string call returned to the C service dispatcher. That path
checked the frame, read the pending source CALL return word, looked up and pinned
the source target, invoked the original API, saved the continuation and reentered
generated code. The first such exit also materialized the full execution frame.
The source pin lookup takes a shared lock even when that code is already resident.
Three global counters were incremented for each service exit, success and resume.
These operations are consequences of the implementation, not inherent string
validity requirements. The caller already guarantees valid memory and lifetime.

At 60 workers, the profiles recorded:

| Workload | Source-pin lookups per returned body | Frame validations per returned body |
| --- | ---: | ---: |
| Taskname | 1 | 7 |
| Xattr tail, 16 attributes | 16 | 37 |
| Xattr tail, 128 attributes | 128 | 261 |

For xattr n16, 85,683 returned bodies caused 1,370,928 source-pin lookups and
3,170,271 frame validations. For n128, 12,343 returned bodies caused 1,579,904
lookups and 3,221,523 validations. Counts include the profiled control interval;
the source-pin and frame-validation counts in these rows match the body totals
exactly. Other functions, such as module lookup, also include background work.

TCLock executes the native critical section using the waiter's stack. Its native
helper calls stay within that execution interval and do not cross KD's service
dispatcher per comparison. This explains a structural difference; the diagnostic
profiles do not assign every throughput difference to one function.

The first profiling attempt completed all six taskname sessions but stopped at
xattr preparation: its tracing preflight mistook the adapter's own
`simple_xattr_get` callback for unrelated tracing. The callback is what substitutes
the controlled benchmark function. The failed attempt drained and restored tracing.
The correction permits exactly that callback while requiring its complete state
to remain unchanged. A separate second run completed all 12 xattr profiles and
restored tracing. Both attempts are retained.

## Implementation

The [direct-call contract](../../../../../docs/design/admission.md#direct-original-helper-calls)
keeps the original APIs, arguments, memory effects and actual source return words.
It moves helper and continuation source pins to immutable image publication and
calls the original helper without a dispatcher round trip. A successful body
can finish through the existing minimal completion path. The two wrapper argument
words, exact physical owners, source leases and unlock acknowledgements remain.

This path is limited to a fresh ABI1 spin request with one physical lock and an
eligible source graph. ABI1 is the calling agreement between the spin caller and
generated code. The wrapper preserves the required registers and stack alignment.
It allows 128 comparisons and 16 padding calls per invocation. Exceeding a quota
returns the unexecuted pending call to the original waiter; it cannot reenter
the same image and reset the quota. Ordinary unknown calls also continue on the
waiter. Invalid return targets and instruction-budget exhaustion remain errors.

Provider capability version 11 adds optional bit 10. Generated relative CALL
operands are filled before publication in a separate preallocated pool near
kernel text. The existing pool and 64-image limit are retained. No helper code,
source CALL encoding, string contents, destination bounds or blanket stack
overlap is checked. The benchmark saves both uploaded placeholders and actual
loaded image bytes, read outside worker timing, with their separate hashes.

## Candidate 1 checks

The VM dependency check, provider build (`W=1`, UBSAN disabled) and daemon build
(`-Wall -Wextra -Werror`) passed. The selected unit batch passed 17 drivers and
failed three. This failed batch is retained; it is not a full-suite pass.

| Failed driver | Cause | Correction |
| --- | --- | --- |
| Native-call admission | The new pad test expected a source CALL one byte too early | Derive the expected address from the explicit encoded prefix length |
| Executable native-call wrapper | C bounds checking rejected reads before a separate linker end-symbol array | Validate the image span and derive footer reads from its start |
| Immutable image publication | Empty fixture logging macros triggered an empty conditional-body warning treated as an error | Use ordinary `do { } while (0)` logging stubs |

These corrections change fixtures only. The production builds and the other 17
selected checks were not rerun unnecessarily.

## Candidate 2 checks

Both basic C programs and the three corrected drivers passed: five selected
programs/drivers, zero failures. The actual generated wrapper fixture completed
5,037 assertions, covering volatile register clobbers, stack alignment, actual
source CALL writes and returns, padding/truncation, both quotas, refusal to
reenter, and minimal terminal completion. This userspace fixture runs in the VM;
it is separate from live kernel acceptance. The publication checks exercised
private relative-call relocation, source pins, image lifetime and the shared
64-image limit, including deliberately broken variants that must fail.

All 14 live sessions passed and drained:

- Original `strcmp` with short and 300-character valid strings.
- Existing spin address-guard recovery and mutex instruction-marker recovery.
- Read-only taskname on Native, TCLock and KD, each with 3,200,000 operations.
- Eight KD xattr controls: front, tail, missing and size-only queries, each at
  16 and 128 attributes with 64-byte values and 16 workers.

Taskname returned 3,163,469 KD bodies. Xattr returned matching entry/completion
counts in every control:

| Query | 16 attributes | 128 attributes |
| --- | ---: | ---: |
| Front | 3,045,370 | 3,071,807 |
| Tail | 1,145,629 | 188,397 |
| Missing | 1,192,631 | 187,803 |
| Size only | 1,185,488 | 184,091 |

These are correctness and delegation observations, not throughput scores.

## Candidate 2 performance screen

All 36 KD sessions passed and drained: three cases at 4, 5, 16 and 60 workers,
three repetitions per point. The settings match the ordinary two-second round.
This screen contains no fresh Native or TCLock control measurements and is kept
separate from the full comparison.

| Workload | 4 workers | 5 workers | 16 workers | 60 workers |
| --- | ---: | ---: | ---: | ---: |
| Taskname | 2.978 | 3.682 | 5.054 | 4.314 |
| Xattr tail, 16 attributes | 1.482 | 1.111 | 1.183 | 0.951 |
| Xattr tail, 128 attributes | 0.201 | 0.204 | 0.191 | 0.159 |

Values are median whole-interval million operations per second. Candidate 3
below changes generated code, so its measurements must not be pooled with this
screen.

## Candidate 3 checks

The final bridge aligns the execution stack once at wrapper entry. Eight saved
caller registers keep each original helper call aligned. Quota and return-word
bookkeeping uses instructions that preserve flags, eliminating the repeated
flag and stack-alignment save/restore around every comparison. It retains the
same source CALL word, quotas, register contract and eligibility rules.

Both basic C programs and six affected drivers passed: eight selected checks,
zero failures. The executable wrapper fixture completed 15,663 assertions with
zero failures. It exercises both incoming stack alignments, all six arithmetic
flags, RCX preservation, success, exhausted quotas and corrupted return words.
The fixture observes generated exits before the common packet export; it does
not replace the actual wrapper or establish kernel acceptance by itself.

All ten affected live sessions passed and drained: the original-string probe,
read-only KD taskname, and eight KD xattr controls. The earlier address-guard,
mutex instruction-marker and Native/TCLock taskname checks remain recorded
under candidate 2.

The candidate 3 screen completed all 36 sessions with matching generated-body
entries and completions, correct results and full drain. Its separate KD-only
whole-interval medians in Mops/s are:

| Workload | 4 workers | 5 workers | 16 workers | 60 workers |
| --- | ---: | ---: | ---: | ---: |
| Taskname | 3.542 | 3.652 | 5.312 | 4.494 |
| Xattr tail, 16 attributes | 1.903 | 1.868 | 2.807 | 2.371 |
| Xattr tail, 128 attributes | 0.701 | 0.737 | 0.697 | 0.576 |

The implementation is committed as `05876a44f841979eae776f0146f0fe9e5c3c8f26`.
All mutex protocol files match the preceding `88bb5a4` revision; the changed
shared dispatcher permits the new direct images only for spin callers.

## Final diagnostic profiles

All 18 sessions completed correctly and drained: three cases, Native/TCLock/KD,
16 and 60 workers, one diagnostic repetition. All writable tracing controls
were restored, including the xattr adapter's separate callback. The source
manifests match `05876a4`; the earlier profiles match `88bb5a4`.

| Workload | Returned bodies, 16 workers | Returned bodies, 60 workers |
| --- | ---: | ---: |
| Taskname | 10,805,312 | 7,197,856 |
| Xattr tail, 16 attributes | 5,548,409 | 4,596,684 |
| Xattr tail, 128 attributes | 1,383,883 | 1,114,461 |

Every KD row recorded zero calls to `kd_source_pin_target`,
`kd_exec_frame_validate`, `kd_exec_frame_save_continuation` and the two C string
service adapters during measurement. The direct route keeps the request in the
existing minimal spin completion path instead of repeatedly entering the full
dispatcher. Exact physical ownership and lifetime checks remain in request
binding and completion, and source pins are acquired before image publication.
These counts do not mean that ownership checking was disabled.

The [profile comparison](profile-comparison.json) preserves exact function and
completion counts, input hashes and separate source identities. No profiled
throughput enters the scored comparison. The final standard-grid results below
remain separate from these instrumented runs. Taskname mutation delegation and
whole-kernel lock replacement remain unvalidated.

## Final standard-grid comparison

All 567 sessions completed correctly and drained: read-only taskname, xattr tail
n16/v64 and xattr tail n128/v64, each on Native/TCLock/KD at the standard 21 worker
counts with three repetitions. The [health receipt](health.json) records 567
retained kernel logs without fault matches. Schema-2 replay completed with hash
`a6ec71e2e317a292f7c63b8279a02e80cc0c0e9baf9ab79546c875f934f5a315`.

The 189 KD sessions contain 168 PASS, 21 NO_JIT and zero PARTIAL_JIT, with
751,832,469 completed generated bodies and no address-guard exits. PASS means at
least one measured generated body completed; it does not establish a large
delegated fraction. NO_JIT means no measured generated entry. All one- and
two-worker KD measurements were NO_JIT. Three-worker taskname and xattr n16 mix
statuses and are excluded from a single three-repetition comparison.

| Case at 60 workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD / old KD | KD / TCLock |
| --- | ---: | ---: | ---: | ---: | ---: |
| Taskname | 3.860 | 5.008 | 4.521 | 1.838× | 0.903× |
| Xattr tail, n16/v64 | 2.182 | 2.412 | 2.368 | 4.901× | 0.982× |
| Xattr tail, n128/v64 | 0.562 | 0.600 | 0.573 | 6.528× | 0.956× |

These are whole-interval medians; peak estimates remain separate. Historical
comparison admits 61 of 63 points after source/environment checks. Of those,
55 meet or exceed old KD in both whole-run and peak medians. Observed whole-run
regressions remain at taskname 4/5, xattr n16 1/2 and xattr n128 1/3 workers;
the [historical CSV](historical-kd-full-grid.csv) retains every value and exclusion.
Fresh comparisons meet or exceed Native at 21 whole-run points and 16 points
for both measures, and TCLock at one point for both. No claim of universal parity
or statistical significance follows from these three-repetition medians.

The [comparison audit](comparison-audit.json) binds both source revisions and
unchanged measurement validators. Current and historical host-placement and
frequency-policy checks each passed all nine checks; effective frequency and
host load remain unmeasured. The [report](README.md) includes settings, full-grid
tables, plots, low-count gaps and changed returned shares. Profiles and the two
candidate screens were not pooled into these measurements.

## Main archive audit

The independent [main archive audit](archive-audit.json) passed without
discrepancies: 567 session records, 265 captured source paths matching Git
`05876a44f841979eae776f0146f0fe9e5c3c8f26`, 16 binaries and 315 distinct loaded-image
captures, including all 189 measured KD images. It verified generated CALL
relocations against the separately captured original symbol addresses. It did
not inspect helper bodies or execute archived code. The
[archive receipt](archives.json) records byte sizes and SHA-256 values for the
taskname, xattr and metadata groups; raw exports are under
`bench/results/10.176.26.71/raw/bench/taskname-xattr-direct-api-20261019/`.

## Native continuation after the comparison quota

After preserving the main round, a separate unscored control reused its source
and binaries for the original xattr tail workload with 129 attributes, 64-byte
values and 16 workers. Preparation used zero helper waves and measurement lasted
one second. Correctness and final idle checks passed; the
[quota result](quota-result.json) retains the original receipt.

Measured operations totalled 329,728, including 329,228 generated prefixes and
zero completed generated bodies. Its expected PARTIAL_JIT status means the
128-call allowance ends generated execution before the next comparison, and
the original waiter completes the native suffix. It is not returned-body
acceptance or an additional performance sample.

Across the entire session, including warmup and checks, 1,070,524 quota exits
matched 1,070,524 native starts, completions and unlocks. Direct comparisons
totalled 137,027,072, exactly 128 per quota exit. Ordinary service exits,
executions, resumptions, rejections and failures were all zero. Source retirement
was exactly `state=2, modules=0, frames=0, writers=0`, with no kernel fault matches.
Aggregate counters and sampled boundary messages do not replace exact runtime
ownership, source leases or unlock acknowledgements; boundary messages are
rate-limited samples, not a count of every exit.

## Development and quota archive preservation

The [quota archive audit](quota-archive-audit.json) verified its separate
575-path archive, 496 regular-file hashes and one fully drained session.
The [development audit](development-archive-audit.json) verified all six sets:
22,207 paths, 19,642 regular-file hashes, 1,617 private include files, 133 drained
sessions and 106 empty KD retirement records. It retains 37 profile-restoration
receipts, 2,304 raw per-CPU profile files and eleven planned-but-unrun sessions.
The [export receipt](development-export.json) binds all seven archives to their
guest receipt hashes. Large raw files remain under the ignored machine-specific
`raw/bench/taskname-xattr-direct-api-20261019/development/` and
`raw/tests/taskname-xattr-direct-api-20261019/` directories.

The first [preservation audit](development-archive-audit-initial.json) failed
because it expected `controls-observed.json` for the first rejected xattr
profile. That historical profiler predates the observation capture. Its exact
source hash is `45b10994ffb348f2325664f7649ee7658e1747b8a46a830bd7772d1db13fc4e5`;
static review shows preflight rejected the adapter callback before any filter
or profiler-enable write. Only the post-refusal restoration receipt exists.
The outer initial/final controls match, but **the per-session before/after
comparison is unavailable**. No missing observation has been reconstructed.

The revised audit recognizes only that exact hashed failed session, profiler,
exception and restoration receipt, and explicitly reports the coverage gap.
Successful profiles still require their prior controls, restored controls and
complete raw per-CPU hashes. The original failed audit, both audit programs and
logs are retained with the host orchestration evidence. Candidate 1's failed
unit batch and the failed first profile remain failures. Archive preservation
does not turn them into accepted tests or throughput samples.

The [orchestration copy receipt](orchestration-copy.json) binds 73 host-side
scripts, logs and captured inputs to their byte-identical preserved copies.
They are retained under the main raw export's `orchestration-final/` directory.

## Execution environment

Frozen guest inputs and logs are under
`/root/kdlock-evidence/10.176.26.71/tests/taskname-xattr-direct-api-20261019/`.
The VM remains the 64-vCPU, two-node recovery topology, kernel
`6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`,
boot ID `b65f0205-c8f9-4385-8b13-039cbce243a6`. The listed recovery snapshot was
`before-mutex-kdonly-20261017T140354Z`. Builds, tests and timing ran only in this
VM; source edits and Git work ran on `380G10`.
