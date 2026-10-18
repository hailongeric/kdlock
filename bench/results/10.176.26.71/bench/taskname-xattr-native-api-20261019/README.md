# Taskname and xattr: original kernel API revision

Focused functional acceptance passed for the simplified implementation:
read-only taskname, all eight xattr controls and three provider probes. The
20% mutation controls were correct and drained but recorded zero KD JIT bodies;
mutation delegation remains unaccepted. The standard 1–60-worker performance
comparison is pending, so no throughput improvement is claimed.

Candidate 6 has the same production code as candidate 5, with one corrected test
operand. The [development record](DEVELOPMENT.md) preserves the passing basic and
affected checks, exact live counts, earlier failures and the archived generic
partial-CALL-alias experiment.

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

Aliasing means two accesses can refer to the same memory. Ordinary CALLs retain
conservative memory analysis. Only `strcmp` and `strscpy_pad` use a separate
reviewed-C-caller contract that records temporary return-address storage as
control state: the selected caller promises
not to inspect or overwrite it through ordinary data accesses. The source CALL,
all workload loads/stores and actual return handling remain unchanged. This
contract does not make arbitrary pointers valid. Decoded `memcpy` retains all
ordinary copy effects and its normal return dispatch, with no copy classification
or special RET path. The [focused validation below](#focused-validation-and-evidence)
covers this implementation. The broader generic partial-word refinement is an
[archived experiment](DEVELOPMENT.md#archived-alias-experiment-and-next-scope),
not the maintained design. The
[admission guide](../../../../../docs/design/admission.md#original-call-word-aliases)
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

## Focused validation and evidence

The final candidate 6 batch completed 17 sessions with correct results and full
drain. Basic checks and all ten affected Python drivers passed across candidates
5 and 6, covering 287 Python tests without skips. The production bytes were
unchanged between those candidates. This is focused coverage, not a full-suite
claim.

| Check | Recorded outcome |
| --- | --- |
| Original `strcmp` | Short strings and valid 300-character strings completed delegated bodies through the same image; zero guard exits. |
| Read-only taskname | All three backends completed 3,200,000 correct reads at 16 workers; KD returned 3,192,951 delegated bodies. |
| Xattr front/tail/miss/size, n16/n128, v64 | All eight 16-worker KD controls passed with matching body entries/completions and correct syscall results. Tail completions were 556,535 at n16 and 100,071 at n128. |
| Spin address guard and mutex marker | Both passed: one triggered native exit, preserved effects, no later JIT entry after the ban, and full retirement. |
| Taskname 20% mutation | All three backends completed 2,560,000 reads and 640,000 writes correctly. These used `helper_waves=0` and did not require delegation; KD recorded zero JIT entries/completions. |

The mutation control is correctness evidence only. It does not erase the earlier
strict preparation failure or establish delegated mutation performance. Taskname
checks normal copying and every padding byte but ignores the helper's return
value. The production-dispatcher unit fixture tests return propagation and
truncation through a substitute helper, not actual-kernel truncation.

The [API-image receipt](candidate6-api-images.json) covers ten KD API sessions and
14 published images. Their only requirement values are 4 for `strcmp` or 8 for
`strscpy_pad`; none includes entry or address guards. The
[host audit](candidate6-host-audit.json) independently checked these image bytes,
assembly, log markers and hashes. The [batch receipt](candidate6-live-result.json)
and [development record](DEVELOPMENT.md#final-live-acceptance) preserve exact
operation and completion counts.

All 28 archived live/diagnostic sessions drained, including 11 earlier attempts
and their failures. The [health receipt](health-through-candidate6.json) records
an idle guest and 28 kernel logs without recorded fault matches. The
[archive manifest](candidate6-archives.json) retains source snapshots, binary and
image hashes, commands and raw receipts; all four copied archive hashes matched
the independent host audit. The 13 new KD sessions retired with zero source
modules, frames and writers.

The standard-grid comparison remains separate and pending. Its results must
retain exact source/binary identities, observation-provider inputs, kernel and
CPU placement, correctness/progress records, images and teardown receipts.
Failed or incomplete sessions must remain visible. These focused checks do not
establish whole-kernel replacement or arbitrary caller safety.
