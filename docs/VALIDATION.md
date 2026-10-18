# Validation index

Validation applies to the recorded inputs and scope. Publishing generated code,
returning from actual just-in-time compiled (JIT) execution, producing correct
results, finishing all outstanding ownership work (drain), and matching another
implementation's throughput (performance parity) are distinct observations.
Basic plus affected checks are the default; an old pass is not a current full pass.
The [terminology guide](TERMINOLOGY.md) explains status labels and other technical
terms used in the receipts below.

## Taskname and xattr helper validation

The current version removes helper-specific instruction checks, string scans and
runtime destination checks. It relies on the original callers' memory and
lifetime guarantees while retaining KD ownership and saved-return bookkeeping.
Fresh VM validation is in progress. The [current development record](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md)
retains each frozen candidate's checks and failures. Candidate 2 passed all 11
focused unit programs/drivers, the 300-character `strcmp` probe, the spin
address-guard and mutex-marker probes, and read-only taskname correctness on
all three backends. Its KD read-only run completed 3,192,781 delegated bodies
among 3,200,000 operations.

The candidate 2 taskname mutation control failed KD preparation: all eight
learning waves were correct and drained, but each had zero generated-body
entries and completions despite a `NORMAL` published image. KD never entered
measurement. Linux Native and TCLock each completed their 3,200,000-operation
functional phase correctly. This differs from the historical measured
`NO_JIT` failure described below. Xattr's first 16-entry front-hit control and a
diagnostic repeat both refused the learned byte-copy instruction before
measurement. All 11 live/diagnostic sessions drained, including these failures.

Candidate 3 passed 11 of 12 unit programs/drivers. Its new coordinator fixture
failed because its setup omitted required spin clobber-entry symbols; that path
has not passed. The proposed extension to decoded `memcpy` return-storage
analysis awaits candidate 4 implementation and validation. No complete workload
acceptance or revised performance result is established. The historical results
below apply to the earlier checked implementation, `c79d84f`, and cannot establish
a pass for the revision.

The [development receipt](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
retains the initial refusals, failed acceptance attempts, corrected observation
counter, focused unit checks and live results. The exact taskname helper returned
delegated snapshots through the ordinary direct spin entry. All eight
xattr front/tail/miss/size checks at 16/128 attributes and 64-byte values returned
complete delegated bodies with correct syscall results and full drain.

Taskname's 20% mutation controls were correct and drained for all three backends.
KD returned nine snapshots during the checked preparation phase but none during
the final measured phase, so its strict measured-delegation check remains a
recorded `NO_JIT` failure. Preparation counts are never added to measured counts.

The checked-address probe and bounded-string probe each validated exact effects,
original-task resumption, permanent refusal after an unsupported runtime input,
source retirement and normal module unload. The existing mutex instruction-exit
probe also passed with the updated shared execution code. These are focused
correctness checks. ABI3 all-writer c08/RCUHT checks returned 2,411,562/2,461,265
bodies; rwsem 80%-write controls returned 413,784/164,848 bodies, with correct
data and full drain. The initial rwlock mixed-write check remains a recorded
`NO_JIT` failure; the all-writer functional check disables the optional entry
ratio filter, while the timing matrix retains its ordinary setting.
The [standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/README.md)
completed all 567 sessions with correct results and full drain; 152 KD sessions
returned delegated bodies and 37 recorded no JIT entry. These results do not
establish whole-kernel replacement or the lifetime of arbitrary pointers supplied
by other callers.

## Checked instruction exits, 2026-10-18

The [final focused receipt](../bench/results/10.176.26.71/tests/native-instruction-exit-20261018/README.md)
records a checked original-waiter continuation for twelve reviewed processor
instructions in mutex ABI2 images. ABI2 is the machine-level calling agreement
also used by rwsem outer writers. A reached instruction marker stops generated
code before that instruction, preserves current state and earlier effects, and
disables future delegation of the entry for the source session. The mutex lock
protocol and accepted rwsem waiting implementation remain unchanged.

Both basic C programs and 17 affected Python drivers passed in the VM. The
production restore fixture covered every general-purpose register and all 64
arithmetic-flag combinations with and without the kernel return-helper path.
The final live probe completed 6,400,000 operations: its cold check returned
1,479,585 JIT bodies, its taken branch produced one checked instruction exit,
and its final 1,600,000 operations produced zero JIT entries after disable and
drain. Exact updates, original task identity, flags and full retirement passed.

Ordinary c08/RCUHT rwsem controls at 16 workers and 80% writes returned
860,947/224,329 writer bodies with correct data and complete drain. These are
correctness checks, not a new throughput comparison. The receipt retains the
initial decoder/fixture failures, the worker-name `NO_JIT` failure, intermediate
results, final source hashes and build warnings. Only the safe RDTSC timestamp
read was exercised live; other reviewed instructions have fixture coverage.
Generic faults, arbitrary memory-address checks, spin/rwlock markers and general
processor-state restoration remain outside this validation.

## Accepted rwsem implementation, c21345b

The user accepted this reader/writer semaphore (rwsem) waiting implementation
with its documented performance tradeoffs. The acceptance preserves the
[two-worker regressions](PERFORMANCE.md#accepted-rwsem-implementation-c21345b)
and does not add new test coverage to the recorded 2026-10-18 checks.

The [optimization receipt](../bench/results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records **PASS** for the accepted implementation with separate waiting queues
and at most 16,384 condition checks before sleeping:
the scheduler/API probe, two basic C programs and all 44 focused workload
checks. Builds and live execution ran in the recovery VM. The
[design](design/rwsem_implementation.md) retains reader drainage before pinned
writer publication and the accepted KD mutex protocol.

| Evidence | Recorded outcome |
| --- | --- |
| Basic programs | `basic/test_control_call` and `basic/test_daemon_policy` passed without skips; source/command/log captured, but no separate executable-hash manifest |
| Sleeping/API scheduler probe | Original twelve-field result passed: eight API checks, ten cancellation cases, same-CPU reader progress, ordinary downgrade, three pre-publication checks, queue-role assertions and final idle |
| Native/KD functional workloads | 36/36 correct and drained: c01/c08/RCUHT, 0%/1%/20% writes, 1/8 workers, 100,000 iterations per worker; 343 matching JIT entries/completions in one c08/20%/eight-worker session |
| Ordinary local KD controls | 4/4 correct and drained: c08, 0%/20% writes, 1/8 workers; zero JIT |
| Strict returned-writer JIT acceptance | 4/4 correct and drained: c08/RCUHT, 80%/100% writes, 16 workers and 200,000 iterations per worker; 7,446,858 matching entries/completions |
| Standard Native/KD timed matrix | 756/756 valid and drained; 155 KD sessions with returned JIT and 223 KD NO_JIT sessions |
| Separate Native/TCLock/KD spinning-rwlock reference | 270/270 valid and drained; 48 KD sessions with returned JIT and 42 KD NO_JIT sessions |
| Diagnostic profiles | Baseline/final each completed six c01/20%/60-worker sessions; tracing restored, 768 raw per-CPU profile hashes verified; excluded from throughput scoring |
| Independent offline arithmetic replay | PASS for all 2,118 timed sessions: initial/final grids (756 each), seven screens (336) and spinning reference (270); raw effects, JIT deltas, rates, peaks and comparison groups agree |
| Frozen inputs and byte equivalence | Two final manifests each match all 233 runtime inputs; 16 selected mutex files and 112 runtime files match `d2a2304`; 115 other provider/header/translator/daemon files match `485729f` (overlapping scopes) |
| Final health | Captured idle state, unchanged boot, no Linux mutex imports and no faults in 1,423 retained session logs; tracing at `nop`, profiling disabled, no enabled functions |

The strict c08 checks returned **892,769 / 3,174,542** JIT writer bodies at
80%/100% writes; RCUHT returned **197,319 / 3,182,228**. Every check required
correct protected effects, reader consistency, worker progress and final drain.
Image publication or local execution alone does not establish returned JIT.
The ordinary probe does not register an image and supplies no JIT evidence.

The independent replay read retained plans, records and samples without
repository imports or VM access; it did not run new kernel tests. Six captured
archives passed integrity verification. The focused offline validation
directly checked 61 kernel logs in its tests/metadata/profiles scope;
the broader 1,423-log statement comes from the retained guest health receipt.
The final dmesg ring is retained and is not a complete boot-long log. The
kernel remains `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`.

The [performance report](../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
keeps candidate screens, baseline repeats, instrumented profiles and execution
statuses separate. Performance failures or split JIT groups do not mean a test
was unexecuted. TCLock has no sleeping rwsem backend. Earlier experimental
probes and rejected candidates remain distinct from selected-source results;
the selected implementation contains no asynchronous reader-grant mechanism.
These are basic plus affected checks, not a full unit-suite claim. They do not
establish whole-kernel mmap replacement, RT/ww_mutex/lockdep, Linux rwsem
fairness, or general producer-oversubscription safety.

## Historical rwsem writer-delegation validation, 2026-10-18

The [initial delegation receipt](../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md)
records the `485729f` shared-queue phase-admission implementation around the
unchanged selected mutex protocol. Its final sleeping/API probe passed same-CPU reader progress, ordinary downgrade
before outer publication, ten cancellation cases and complete drain. Twenty-four
Native/KD c01/c08/RCUHT functional sessions passed; they recorded zero JIT and are
kept separate from four successful strict acceptance runs at 16 workers.
Those c08/RCUHT runs returned 3,174,269/3,178,872 JIT bodies at 100% writes and
404,874/163,345 at 80% writes, with matching completion counts, correct data and
complete drain. The mixed c08 case had zero reader consistency errors.
Five additional c08 local/read-only controls passed with zero JIT and full drain,
bringing the focused workload checks to 33 successful sessions.

Basic and affected checks passed individually or after the documented fixture
corrections. The receipt preserves the obsolete ABI fixture, unexported probe
accessor and Python import-setup failures. It also preserves the strict
20%-write/32-worker c08 attempt: correct and drained, but no returned JIT bodies;
its following RCUHT plan item was not run. The separate
[standard performance grid](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
completed all 756 sessions correctly and drained. Final health recorded an idle
guest, unchanged boot ID, verified source/binary inputs, no Linux mutex imports
and no new faults in the retained kernel log. Per-session fault captures remain
separate from the possibly rotated final ring. These checks do not establish
whole-kernel mmap replacement or oversubscription safety.

## Feature reintegration, 2026-10-18

The [reintegration receipt](../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
records ordinary sleeping rwsem, proc snapshots and independent benchmark tools.
Basic/affected tests, two rwsem scheduler probes and 61 workload sessions passed;
two failed delegation-acceptance attempts remain visible. Timed argbounds and a
rwlock writer check have fresh complete-body evidence. Taskname delegation did
not pass preparation; its explicit local controls passed. The accepted mutex
source is unchanged. This is neither whole-kernel mmap integration nor a new
full performance matrix.

## Main consolidation, 2026-10-18

The [consolidation receipt](../bench/results/10.176.26.71/tests/main-consolidation-20261018/README.md)
records checks for branch integration, moved files, benchmark tooling and docs.
The selected provider, headers, translator, daemon, TCLock implementation and
kernel payloads are compared byte-for-byte with `d2a2304`. No lock protocol is
changed and no new performance matrix is claimed for this organization pass.

## Accepted KD-only mutex, 2026-10-17

The [acceptance receipt](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/validation.json)
records the provider W=1 build, ordinary-alias probe, two basic checks, affected
fixtures and 504 complete/drained benchmark sessions. The live probe checks
8 workers, 160,000 operations and 2,048 independent objects, plus sleeping/nested
owners, interruptible/killable cancellation, I/O accounting and trylock.

The [benchmark report](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
records 6,043,578,112 operations across four arms. Its archive has 150,984 files
and 3,916 symlinks; 143 numeric outputs were independently reproduced. These
observations do not establish whole-kernel replacement, RT/ww_mutex/lockdep,
oversubscription safety, or a full test-suite pass.

## Historical evidence

- [Compatibility backport](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md): instruction refusal and immutable mutex images with legacy delegation.
- [Recovered legacy grid](../bench/results/10.176.26.71/bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md): 378 c01/pipebytes sessions before the backport.
- [Rwlock c01](../bench/results/10.176.26.71/bench/rwlock/20261015-c01/README.md): 378 sessions, with separate JIT statuses and parity limits.
- [Earlier validation index](https://github.com/hailongeric/kdlock/blob/d2a23049a4b6e3c65cf0ff21bbfd3e21cd975761/docs/VALIDATION.md): fixed baseline, wrapper, protocol and cleanup receipts.
- [Results by machine](../bench/results/README.md): retained raw archive paths and compact reports.

### Mutex oversubscription assessment

The historical mode4 pinned-waiter soft-lock and mode5 lack of actual JIT remain
open limitations. See the [fixed assessment](https://github.com/hailongeric/kdlock/blob/d2a23049a4b6e3c65cf0ff21bbfd3e21cd975761/docs/VALIDATION.md)
and [known failures](TODO.md). Removing obsolete trace-only harnesses does not
resolve those failures.

### Main-plan acceptance audit

Acceptance requires matching generated/published identities, returned JIT bodies
where required, correct effects, exact owner ACKs and complete retirement. Current
selected checks cannot be combined with historical passes to claim whole-project
acceptance. See [tests](../tests/README.md) for commands and scope.
