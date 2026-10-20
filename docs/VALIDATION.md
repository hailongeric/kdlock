# Validation index

Validation applies to the recorded inputs and scope. Publishing generated code,
returning from actual just-in-time compiled (JIT) execution, producing correct
results, finishing all outstanding ownership work (drain), and matching another
implementation's throughput (performance parity) are distinct observations.
Basic plus affected checks are the default; an old pass is not a current full pass.
The [terminology guide](TERMINOLOGY.md) explains status labels and other technical
terms used in the receipts below.

## Unified mutex API checks

The [unified API receipt](../bench/results/10.176.26.71/tests/mutex-api-20261020/validation.json)
records provider/daemon builds, two basic programs and nine affected drivers
(11 passed, zero failed) on the captured `6.1.159-kdclobber2` VM. The new fixture
compiles the actual public headers, translates anonymous DIRECT continuations
under production admission, and executes generated root COMPLETE/FULL and nested
B-A/A-B control paths. Physical control services are substituted in that fixture.
Production routing/frame tests retain their mutation controls. Public C
identifiers link to distinct `kd_mutex_api_lock/unlock` exports; the live probe's
symbol audit rejects accidental references to the kernel's legacy mutex symbols.

The live API probe passed 160,000 operations with eight workers, 2048 reused
objects, native 32-byte/8-byte geometry, sleeping nested owners, cancellation,
ring handoff, initialization, function-pointer and real cleanup-macro coverage.
The separate owner/ACK probe used CPUs 0/32/33 and confirmed both release orders,
four ACKs, two deferred frees and three registry workers with 4096 iterations
each. Both probes retired sources and unloaded normally; final health was idle.
They execute zero JIT bodies and do not replace live delegated-body validation.

Failed attempts remain in the receipt: a legacy export-name collision, two
fixture compile/extraction failures, and an initial reserved-per-CPU allocation
failure before provider initialization. The existing allocator guard's ordinary
page allocation/free enabled the live retries; no kernel changes, reboot or
system-module removal occurred. Final provider builds retain 15 macro/objtool
warning lines. Recorded source hashes match the checked-in source. Scope remains
basic plus affected validation, with no performance, whole-kernel, RT/ww_mutex,
lockdep or oversubscription claim.

## Fresh mutex benchmark and report validation

The [Native/TCLock/KD comparison](../bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/README.md)
uses `bd9d4ce` with unchanged `752fec1` production. Fresh VM validation passed
dependency and provider/daemon builds, the two basic C programs, and 86 cases
across the direct-runner, peak, API-plan and API-report programs. The provider
build retains 48 warning lines. No full suite or separate protocol/live-probe
rerun is claimed for this documentation and benchmark change.

All 567 planned timings completed correctly and drained, with 567 kernel logs
and zero matched runtime faults. Among 189 KD sessions, 68 witness synthetic
entry, 78 record matching returned API bodies and 43 record no generated entry.
The c08/two-worker split remains separate; no entry-positive synthetic sample
is promoted to returned-body proof. The independent inert archive review passed
668,688 checks and reconstructed every timing window; a separate compact
numeric review passed 6,952 checks. Final health confirms an idle VM and the
recorded host/guest policy. Performance outcomes and remaining regressions are
separate from these correctness and preservation checks.

## Mutex shared-node and bounded-locality checks

The [shared-node receipt](../bench/results/10.176.26.71/bench/mutex32-mcs-20261020/README.md)
records retained `752fec1` and the separately checked FIFO trial `f4d359d`.
The object remains 32 bytes with native 8-byte alignment; four preallocated
320-byte, 64-byte-aligned nodes per CPU now contain independent OSQ membership
in existing padding. Borrowed delegation heads retain their reservation and
packet, temporary native slots retire before scheduling, and full pools fall
back to the existing physical sleeping path. The retained policy uses a
256-body locality boundary with larger-cohort handoff and a total 1024-body cap.

Each frozen source passed dependencies, provider/daemon builds, two basic
programs and fifteen directly affected drivers (17 passed, zero failed),
11 runner-plan and 13 runner-report cases, and the ordinary mutex, rwsem and
instruction-exit live probes with drain. The added OSQ fixture covers
13 scenarios and detects ten mutation controls, including delayed links,
cancellation losing to grant, predecessor movement, encoded slots, pool
exhaustion and borrowed versus temporary retirement. The retained terminal
fixture detects 13 controls for bounded cohort/handoff and existing retirement
rules. Each provider build retains 48 warning lines.

All four source blocks completed 72 valid, drained timings. The 48 API sessions
counted returned JIT bodies; the 24 c01 sessions witnessed entry only and do not
prove returned bodies. All 78 retained kernel logs have no matched runtime
faults, and final health records the unchanged captured kernel/topology and an
idle VM. The rejected FIFO trial remains at `archive/mutex32-fifo-20261020`;
correctness passes do not erase its measured regressions. Scope is basic plus
affected checks, not a full suite, weak-memory proof, whole-kernel
replacement, RT/ww_mutex, lockdep or oversubscription validation.

## Earlier mutex queue-head and ownership-validation checks

The [cache-line investigation](../bench/results/10.176.26.71/bench/mutex32-cacheline-20261019/README.md)
checks and times `76af844`, whose production was retained after reverting the
separate `de30588` prefetch trial with `044e351`. The mutex remains 32 bytes with
native 8-byte alignment. The queue head avoids a tail RMW when a successor is
known; the gate hint and unchanged exact ownership predicate are inlined.
Physical owner, gate, source, frame and unlock-ACK checks remain intact.

Both separately frozen candidate and trial bundles passed dependency checks,
provider/daemon builds, two basic programs and fourteen affected drivers
(16 passed, zero failed), plus 11 runner-plan and 13 runner-report cases.
Each passed the ordinary mutex, rwsem and instruction-exit live probes with
drain. The added queue-head fixture detects six negative controls covering
unnecessary tail access and loss of the exact retirement CAS or delayed link.
It does not establish all weak-memory interleavings. Each provider build retains
48 warning lines; neither bundle is described as warning-free.

All 24 plain timings, eight separate profiles and twelve placement diagnostics
returned JIT bodies and drained. All 50 retained kernel logs have no matched
runtime faults. The captured kernel, boot, topology, pins and frequency policy
remained unchanged. The idle VM was restored to the checked candidate bytes.
Independent source/archive review passed over 10,246 members and 20 source
manifests, with zero exceptions or issues. The arithmetic/profile audit passed
59,560 checks, reconstructing all 44 windows and 109,590 profile samples.
The small prefetch median differences are inconclusive, and that trial remains
archived. This round does not establish performance parity, a full suite,
whole-kernel replacement, RT/ww_mutex, lockdep or oversubscription support.

## Earlier versioned mutex waiter-record validation

Runtime `c2f0d9c`, checked as `35718f5`, keeps the native 32-byte size and 8-byte
alignment while moving exact waiter accounting into existing node padding.
Its [focused VM validation](../bench/results/10.176.26.71/bench/mutex32-packed-20261019/README.md)
passed dependencies, provider/daemon builds, two basic programs and thirteen
affected drivers (15 passed, zero failed), plus live ordinary mutex, rwsem and
instruction-exit probes. State, snapshot, resource and balance tests detect
17, 12, 27 and seven negative controls. Snapshot tests cover same-key reuse,
impossible mixed counts, sparse CPU IDs, concurrent writers and explicit
`-EAGAIN`/`-ENOMEM`; existing ownership, frame and ACK checks remain.

The initial check attempt is preserved: 14/15 unit checks passed, and the
shadow-stack harness failed to compile because it lacked `u64`. Test-only fix
`35718f5` supplied that typedef; the successful rerun used a new frozen snapshot.
Neither the compile failure nor a skipped live probe is counted as a pass.
The provider build retains 48 warning lines.

All 18 plain pipe timings and six separate profiles returned JIT bodies and
drained. Twenty-seven kernel logs have no matched runtime faults; the captured
kernel, boot, topology and frequency policy remained unchanged. The source/archive
audit passed over 6,175 members and 12 source manifests with zero exceptions or
issues. The independent arithmetic/profile audit passed 34,386 checks, reconstructing
24 windows and 82,268 profile samples. The checked source remains in the idle VM.
No full suite, full workload grid, whole-kernel replacement, RT/ww_mutex, lockdep
or oversubscription validation is claimed.

## Earlier embedded mutex validation

Runtime `372be89` removes the auxiliary hash and shared reference count while
keeping native 32-byte size and 8-byte alignment. Its
[basic plus affected VM checks](../bench/results/10.176.26.71/bench/mutex32-embedded-20261019/README.md#validation-and-preserved-evidence)
passed dependencies, provider/daemon builds, two basic programs, twelve affected
drivers (14 passed, zero failed), and live ordinary-mutex, rwsem and
instruction-exit probes. The local probe adds head/middle/tail ring cancellation
and HANDOFF, retaining address reuse without destruction and exact drain.
Embedded-state, resources and balance fixtures detect 22, 26 and six negative
controls respectively. Provider diagnostics retain 48 warning lines.

All twelve fresh pipe sessions returned JIT bodies and drained. Fifteen retained
kernel logs contain no matched runtime faults. Independent archive/source review
passed with zero exceptions/issues, and the independent arithmetic audit passed
17,613 checks, reconstructing all twelve windows. The VM was restored to the
checked source and remains idle. The measured pipe slowdown is retained as a
performance limitation, separate from correctness checks. No full suite,
whole-kernel replacement, RT/ww_mutex, lockdep or oversubscription validation is
claimed.

## Compact mutex counted-pin validation

The [reference-traffic round](../bench/results/10.176.26.71/bench/mutex32-traffic-20261019/README.md)
retains separate checks for fetch-add `113b317`, rejected cached-index
`cd49d65` and final inline-pin `ba98937`. Each passed dependency checks,
provider/daemon builds, two basic programs and 12 affected drivers (14 passed,
zero failed), plus ordinary-mutex, rwsem and instruction-exit live probes.
All 120 timing sessions and ten unscored pipe profiles completed and drained;
139 retained kernel logs contained no matched runtime faults.
Independent archive/source and statistics audits passed without issues or
source exceptions, including all 130 reconstructed windows and 136,990 profile
samples. The provider builds retain 51 warning lines per check bundle.

The final auxiliary fixture has 20 negative controls and exercises LIVE-zero
revival, delayed retirement CAS across generation reuse, rejected pins spanning
publication/retirement/failure, state/count guard boundaries, exact owner/frame/ACK
references, collisions, allocation refusal and concurrent reuse. These fixture
checks do not replace kernel ordering review or live validation. The original
summary refusal and corrected field validation are retained separately from
workload outcomes. Scope remains basic plus affected checks, not the full suite,
whole-kernel replacement, RT/ww_mutex or lockdep validation.

## Compact mutex direct-index and transfer validation

Revisions `44f8eb6` and `e999008` retain the 32-byte, native-aligned caller object.
The first preallocates 65,536 auxiliary slots (16 MiB), removes auxiliary
registry locking/RCU, and uses exact references plus sequence-validated
observations. The second transfers an invocation reference only on immediate
gate acquisition before node reservation and borrows the current task's existing
owner reference for synchronous unlock. Queued/frame/native-ACK references and
the KD physical protocol remain unchanged; caller cleanup does not increase.

Their [separate frozen check bundles](../bench/results/10.176.26.71/bench/mutex32-index-20261019/README.md#checks-and-retained-evidence)
each cover provider/daemon builds, dependencies, two basic C programs and 12
affected drivers, plus live ordinary-mutex, rwsem and instruction-exit probes.
Each bundle passed 14 unit checks with zero failures, and all six live probes
passed and drained. The original working-tree labels remain in their receipts;
exact production hashes bind each bundle to its own benchmark commit.

The index fixture covers collision and lifecycle-reservation refusal, reference
acquisition versus retirement, post-acquisition key checks, sequence-validated
observations including A→B→A reuse, allocation failure at provider startup,
sequence exhaustion and concurrent publication/retirement. Its three negative
controls remove key validation, sequence validation or ordered retirement.
The transfer bundle adds three borrowed-owner controls and five transfer/unlock
controls, including wrong-owner/key/sequence borrowing, a dropped transferred
reference, release before opening the gate and an erroneous owner put on failure.
Exact retained frame/ACK references remain independently exercised.

All 104 benchmark sessions passed and drained: 96 plain timings and eight
diagnostic profiles. All 110 required kernel logs were retained with no matched
faults. Profiles reported zero lost samples. Independent audits verified source
and archive identities, all 104 peak windows and 109,687 weighted sample lines.
The retained controller preparation failure happened before workloads started;
its original directory and the corrected fresh invocation remain separate evidence. This is
basic plus affected validation, not a full suite or universal performance-parity
claim. Synthetic timing counters witness entry; real API and instruction-exit
checks separately count returned JIT bodies.

## Compact mutex RCU lifetime validation

Revision `fcbacbe` retains the 32-byte, native-aligned KD mutex and replaces
bucket-locked auxiliary reads/reference updates with RCU and exact atomic
references. Its [focused validation](../bench/results/10.176.26.71/bench/mutex32-opt-20261019/README.md#validation-and-preservation)
passed provider/daemon builds, dependencies, both basic C programs and 12
affected drivers. Deterministic races cover lookup across final unlink,
same-address replacement, no zero-reference revival, competing puts and callback
drain before slab destruction. The ordinary mutex, rwsem and JIT/native-exit
live probes passed and drained. All 69 matched timing/profile sessions also
drained; 72 kernel logs had no matched faults.

The initial frozen test bundle omitted a kernel probe source: 13 checks passed,
one failed preparation, and that unchanged check passed from a new complete
bundle. Both attempts remain archived. The report also preserves a finalization
refusal caused by its own open output log and the successful corrected invocation.
This is basic plus affected validation, not a full suite or universal performance
parity. Synthetic timing counters witness entry; API and instruction-exit probes
separately count returned JIT bodies.

## Taskname and xattr helper validation

The version 11 direct-call path in `05876a4` passed provider/daemon builds,
basic plus affected unit coverage, and focused live checks. It keeps original
string calls inside one generated invocation while preserving their caller
contract and the selected KD mutex protocol. The
[development record](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md)
retains the initial three fixture failures, successful corrections, executable
wrapper checks and exact live counts. Candidate 2 completed 14 drained live
checks, including the unchanged recovery probes and Native/TCLock controls.
Candidate 3 passed both basic C programs and six affected drivers; its generated
wrapper fixture completed 15,663 assertions covering both incoming stack
alignments, registers, flags, actual CALL return words, quotas, truncation and
bad-return rejection. Its ten affected live checks passed and drained.

The final 18 diagnostic profile sessions completed, drained and restored tracing
controls. All six KD cases returned generated bodies with zero measured calls
to the repeated source-pin lookup, full-frame validation, continuation-save and
C string adapters. These counts explain removed dispatcher work; they do not
measure uninstrumented throughput. Two separate 36-session KD screens retain
their own generated code and are not pooled. The [full standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed all 567 sessions with correct results, complete drain and successful
evidence replay. KD returned 751,832,469 bodies across 168 sessions; 21 KD
sessions recorded no generated entry, and none entered without a completion.
All 567 session kernel logs had no matched fault reports. The independent
[archive audit](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/archive-audit.json)
verified 265 source files against `05876a4`, 16 binaries and 315 actual loaded
images, including their generated direct CALL targets. No helper bodies or
arguments are scanned by this image check. Matching before/after VM placement
and frequency policy do not establish equal effective frequencies or host load.

The separate [quota control](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/quota-result.json)
reused the measured binaries for a 129-attribute tail query at 16 workers. It
completed 329,728 correct measured operations; 329,228 generated prefixes reached
the 128-call quota and returned to the original waiter, with zero completed JIT
bodies. Its `PARTIAL_JIT` status is expected for this unscored continuation check.
Including warmup and checks, 1,070,524 quota exits matched native starts,
completions and unlocks, and 137,027,072 direct comparisons equal 128 per exit.
Exact empty frame/source retirement and final idle passed; aggregate counters
do not replace the runtime ownership and acknowledgement checks. These are
focused results, not a full-suite, universal delegation or performance-parity
claim.

Separate [development preservation checks](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/development-archive-audit.json)
cover 133 drained sessions, including the failed first profile, and eleven
planned-but-unrun sessions. The first failed profiler predates its pre-refusal
tracing snapshot: outer controls match, but its per-session before/after
comparison is unavailable. The initial audit failure and the narrowly corrected
audit remain in the development record; successful-profile requirements are
unchanged. [Quota preservation](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/quota-archive-audit.json)
passed separately. These audits verify retained evidence and do not relabel
failed checks as passes.

The preceding version 10 removes helper-specific instruction checks, string scans and
runtime destination checks. It relies on the original callers' memory and
lifetime guarantees while retaining KD ownership and saved-return bookkeeping.
Focused correctness validation passed through candidate 6. The subsequent
[`88bb5a4` comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
completed all 567 standard-grid sessions with successful evidence replay and
full drain. Among its 189 KD sessions, 167 returned delegated bodies and 22 had
no generated-code entry; none entered without a completion. All 567 session
kernel logs had no matched fault reports. The independent archive audit verified
263 source paths against the exact Git revision, 16 binaries, 189 empty source
retirement records and 315 captured images without pointer or stack-alias guards.
The comparison preserves remaining performance gaps and low-count regressions.

Its [development record](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md)
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

Candidate 3 passed 11 of 12 unit programs/drivers; its coordinator fixture
omitted required spin clobber-entry symbols. Candidate 4 also failed its
selected-C-caller driver. Later source replay showed that its expected refusals
without a special copy classification were unjustified; the ordinary copy and
return path were already emitted. The development record preserves both the
failures and that corrected diagnosis. The generic partial-CALL-alias mask
experiment is preserved on `archive/taskname-xattr-candidate4-alias-20261019` at
`66cccfab511866f095d9fbfb2ed33b909afd1d79`.

Candidate 5 removes that experiment and keeps conservative ordinary
CALL/RET analysis. Only `strcmp` and `strscpy_pad` use separate temporary control
storage. There is no `memcpy` classification or special RET path. Candidate 6
keeps the same production source and corrects a test expectation. Across
candidates 5 and 6, both basic C programs and all ten affected Python drivers
passed, covering 287 Python tests. The provider/daemon builds and runtime
fixtures passed in candidate 1; their source was unchanged, and they were not
rerun as a new full suite.

Candidate 6 completed 17 new live sessions: the original-string, checked-address
and mutex-marker probes; read-only taskname on all three backends; taskname with
20% mutations on all three backends; and eight xattr front/tail/miss/size controls
at 16/128 attributes. Read-only KD taskname and all eight KD xattr controls
returned complete delegated bodies with correct results and full drain. The
mutation runs are correctness controls: helper preparation was disabled
(`helper-waves=0`), and KD recorded zero JIT entries and completions. They do not
reverse the earlier strict delegation failure.

The [final raw archive](../bench/results/10.176.26.71/raw/tests/taskname-xattr-native-api-20261019/taskname-xattr-native-contract-through-candidate6-archives/archives.json)
retains checks, live sessions, diagnostics and metadata. Its health receipt
covers all 28 sessions, including earlier failures, with complete drain. These
focused checks establish neither a performance gain nor whole-kernel support.
The historical results below apply to the earlier checked implementation,
`c79d84f`, and remain separate evidence.

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
