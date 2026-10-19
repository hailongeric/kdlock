# Direct original-API calls: investigation and validation

This revision optimizes execution of the original `strcmp` and `strscpy_pad`
inside delegated taskname and xattr bodies. It preserves the selected KD mutex
protocol. These workloads use spin delegation; they do not exercise a replacement
mutex algorithm. The previous implementation and full comparison remain fixed
at [`88bb5a4`](../taskname-xattr-native-api-20261019/README.md).

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
under candidate 2. The candidate 3 screen, diagnostic profiles and standard-grid
comparison are pending. Taskname mutation delegation and whole-kernel lock
replacement remain unvalidated.

Frozen guest inputs and logs are under
`/root/kdlock-evidence/10.176.26.71/tests/taskname-xattr-direct-api-20261019/`.
The VM remains the 64-vCPU, two-node recovery topology, kernel
`6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`,
boot ID `b65f0205-c8f9-4385-8b13-039cbce243a6`. The listed recovery snapshot was
`before-mutex-kdonly-20261017T140354Z`. Builds, tests and timing ran only in this
VM; source edits and Git work ran on `380G10`.
