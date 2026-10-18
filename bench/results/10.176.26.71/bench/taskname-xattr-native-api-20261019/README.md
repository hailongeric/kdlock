# Taskname and xattr: original kernel API revision

The revision is not yet accepted, and performance measurements remain pending.
Candidate 2 passed its focused unit follow-up and the live long-string,
read-only taskname, address-guard and mutex-marker checks. Taskname's 20% mutation
control failed KD preparation without entering measurement; xattr stopped at a
translation refusal. Candidate 3's unit batch passed 11 programs/drivers and
failed one because the new coordinator fixture omitted required entry symbols.
The [development record](DEVELOPMENT.md) retains these outcomes, the earlier
candidate 1 failures and the remaining work. No throughput improvement is claimed.

This revision removes helper-specific checks from the KD calls to the original
kernel `strcmp()` and `strscpy_pad()`. It is separate from the completed
[`c79d84f` checked-helper baseline](../taskname-xattr-20261018/README.md), preserved
on `archive/taskname-xattr-checked-c79d84f-20261019`. The final implementation
commit, frozen source hashes and live receipts will identify this new comparison;
working-tree candidate numbers do not identify interchangeable measurements.

## Implementation being evaluated

KD resolves and invokes the original kernel functions with their original
arguments. Translation, publication and execution do not inspect helper
instructions or perform helper-specific CALL checks. They do not scan strings
or check destination bounds at runtime. The original caller supplies valid
storage and lifetime, as it does for the native C API. There is no additional
helper-call registration table. Calls still use the existing service dispatcher;
this revision does not introduce direct native calls from generated code.

Translation retains the actual source CALL's saved return-address write.
`strcmp` has no caller-memory writes; `strscpy_pad(..., 64)` invalidates analysis
facts for all 64 destination bytes. The writer requires a statically known count
and local destination so that these effects are represented accurately. Native
padding and truncation behavior remains the original helper's responsibility.
Ordinary address/register analysis, physical ownership, frame lifetime, exact
return consumption and matching unlock remain in force. Neither helper supplies
an assumed proof about processor flags for a native continuation.

The revised alias analysis distinguishes a real source CALL's return-address
bytes from ordinary data writes. Aliasing means two accesses can refer to the
same memory. This analysis change preserves the workload's loads and stores;
it does not make arbitrary pointers valid. The
[admission guide](../../../../../docs/design/admission.md#original-strcmp-service)
defines the exact scope and remaining refusals.

Provider capability version 10 advertises the native API contract with feature
bit 9, alongside the separate read-only and writing-service features. This is
an interface version, not a source commit. Generated string-service images
remain immutable while callers use them. The allowance is 128 `strcmp` calls
plus 16 other services/continuations per delegated body. The selected KD mutex
protocol and the two-word wrapper calling interface are unchanged.

Taskname retains its ordinary `KD_SPIN_DIRECT_LOCK` shell and original
`strscpy_pad()` call. Xattr retains its original list traversal, comparisons and
real `memcpy()` value copy. Native, TCLock and KD receive the same protected
payload; changing the helper implementation or replacing the copy loop would
define another workload.

## Planned comparison

The intended comparison matches the historical baseline's 567-session design:

| Case | Protected work | Planned sessions | Results |
| --- | --- | ---: | --- |
| Taskname, read-only | Copy a 16-byte name into a 64-byte padded output | 189 | Pending |
| Xattr tail n16/v64 | Search 16 attributes and copy the matching 64-byte value | 189 | Pending |
| Xattr tail n128/v64 | Search 128 attributes and copy the matching 64-byte value | 189 | Pending |

Each case uses Linux Native, TCLock and KD, three repetitions and a target
duration of two seconds. The 21 worker counts are
`1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60`.
Workers use CPUs 0 through N−1 and CPU 63 collects progress. KD prepares with
a separate 16-worker group on CPUs 0–15, allowing up to eight learning rounds;
preparation and warmup are excluded from timing. Taskname mutations remain a
separate correctness workload. Taskname is an extracted snapshot, not a full
procfs or `ps` measurement. Each xattr operation includes one validated syscall.

The completed report will retain per-session evidence, all repetition groups,
full-grid comparison tables and figures. Whole-run and peak rates will use
three-repetition medians within one source, workload and execution status.
The peak policy uses at least 300 ms after 300 ms of settling, with progress
from every worker. No checked-baseline repetition will enter a revised group.

`NORMAL` means an image was published. `PASS` requires at least one returned
delegated body during measurement; `PARTIAL_JIT` means an observed entry with
no returned body, and `NO_JIT` means no entry. These statuses remain separate,
including mixed repetitions that cannot supply one three-run comparison.
Successful publication or preparation alone is not measured delegation.

## Evidence required for results

The revised run must retain its exact source and binary hashes, prepared
observation-provider inputs, kernel identity, CPU placement, recovery snapshot,
raw correctness and progress records, generated images and teardown receipts.
Workers must join and ownership records must drain before ordinary retirement
and unload. Failed checks and incomplete sessions remain visible.

The focused live string probe will check both short strings and valid
300-character strings using the same published image. Taskname checks ordinary
copying and all padding bytes. Its payload ignores the helper's return value;
the production-dispatcher unit fixture checks return propagation and truncation
through a substitute helper, not actual-kernel truncation. These scopes must
remain explicit when the validation record is updated.
