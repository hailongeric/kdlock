# Known limitations and deferred work

The [terminology guide](TERMINOLOGY.md) explains lock, generated-code and
measurement terms used here. In particular, rwsem means a sleeping reader/writer
semaphore; JIT means just-in-time compiled code used to execute a waiting task's
work; and final drain means all requests, references and release confirmations
have finished.

The [KD-only mutex contract](design/kd_only_mutex.md) is the current replacement
assumption. Whole-kernel rebuilding, lockdep/RT/ww_mutex integration and broad
oversubscription remain unvalidated. Removing the Linux mutex bridge does not
resolve historical pinned-producer scheduling failures.

Current scope: x86_64 kernel spin/mutex/rwlock delegation and sleeping rwsem
with local readers and explicit outer writer delegation. Implementation contracts
live in [DESIGN](DESIGN.md); [performance status](PERFORMANCE.md) distinguishes the
accepted KD-only mutex, accepted `c21345b` rwsem results, the separate spinning-rwlock
reference and historical comparisons. These unresolved issues remain documented;
this list does not schedule new work. Historical evidence is
indexed in [VALIDATION](VALIDATION.md).

## Current checkpoint

KD has explicit spin, ordinary mutex, rwlock and rwsem APIs. Spin/mutex/rwlock
workloads compare KD, TCLock and Native; sleeping rwsem compares KD with Native
because this port has no TCLock sleeping rwsem. KD tracks real lock owners and
unlock acknowledgements, keeps source modules loaded while needed, and shares
register packets between waiter and combiner. It does not intercept global lock
calls. Historical comparisons retained configuration-specific throughput gaps;
see the [spin/mutex report](../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md)
and [RCUHT rwlock report](../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md).

Rwlock ABI3 moves reader drainage and write admission before the prepared body,
resolving the older hash-writer translation refusal. Native writers have a fast
path, and the count and gate occupy separate cachelines in a 128-byte object.
The historical 40-vCPU RCUHT matrix completed 270 runs correctly and drained,
but met both throughput targets at only 21/30 points. That captured version and
placement had read-heavy cross-NUMA and two-worker writer gaps; those results do
not establish a universal or current KD rwlock limitation. The separate fresh
spinning reference is source- and topology-specific and remains distinct from
sleeping-rwsem performance. All 270 sessions completed correctly and drained.
KD is slower than both comparators at c08/20%/one worker and slower than TCLock
at RCUHT/1%/60 workers; it meets both measured criteria at 29/30 points against
Native and 28/30 against TCLock. These
comparisons retain repetition ranges and do not establish statistical
significance. TCLock's stack-delegation share remains unmeasured.

The accepted `c21345b` [rwsem implementation](../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
uses separate queues for waiting to enter and waiting for readers to finish,
separates frequently written fields across cachelines, and checks conditions
repeatedly for a limited number of attempts before sleeping. These changes
precede delegation publication and preserve the accepted KD mutex protocol. All 756
sessions completed correctly and drained. KD meets both observed throughput
criteria at 117/126 points against Native, with six misses and three split
execution-status groups. Against the initial KD there are 110 passes, 12 misses
and four split comparisons. Low-count regressions remain substantial: c01/c08
at 20% writes and two workers reach only 0.286×/0.276× the initial KD whole-run
throughput, approximately 71–72% slower. The user accepted this version with
those measured limitations; acceptance does not remove them. The six Native
misses are the three 20%/one-worker cases,
c08/1%/two workers and c01/c08 at 20%/36 workers. Split comparisons completed
all planned sessions; execution groups and variability remain in the report.
The limit of 16,384 condition checks is accepted platform-specific tuning, not a
universal optimum. The first-repetition Native variation in both baseline and selected focused screens
remains unexplained; governor-policy equality does not isolate its cause.
Continuous outer-writer arrivals can delay readers or ordinary writers, and no
Linux rwsem fairness or bounded-wait guarantee is provided.

The [initial rwsem report](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
preserves the `485729f` shared-queue baseline: 756 correct, drained sessions,
26/126 observed parity points, seven JIT-positive KD sessions and 371 local
fallback sessions. Its high-count regressions are historical evidence, not
current performance numbers. Neither waiting-path changes nor favorable
measurements resolve the correctness limits below.

Known failures are still open:

- Concurrent cold promotion stalled with an RCU warning in c16/t4 preparation.
  Single-CPU preparation avoids that phase rather than fixing it. The fixed
  [failure record](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md)
  retains the original inputs.
- Seven-role/two-CPU mutex mode4 soft-locked with pinned polling. Other passes
  do not replace that case; see the fixed
  [mutex failure](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#mutex-pinned-mode4-failure).
- An older oversubscribed mode5 published code but lacked actual JIT. Its former
  scheduling strategy does not validate today's pinned waiters; see
  [the recorded assessment](VALIDATION.md#mutex-oversubscription-assessment).

## Delivery scope

The user reopened the seven public-mutex regressions and requested subsequent
rwlock/rwsem comparisons, real mmap/fault integration and nano/list measurements.
The active [stage record](../bench/results/10.176.26.71/bench/mutex-regression-diagnosis-20261020/README.md)
tracks those dependencies and results. Their prior deferred status is not a
reason to skip the requested investigation; unsupported behavior still requires
an explicit ownership/context design and validation before execution.

The entry-inlining experiment passed focused correctness checks but did not
resolve the seven mutex losses in its separate 120-session comparison. It is
not accepted as a performance fix. The stage record retains all repetitions,
class gaps and the failed post-run QEMU thread-set check; latency and runtime
host interference remain unmeasured. The experiment is preserved at
`archive/mutex-entry-inline-20261020` (`7062887`). The common entry and its test
extraction marker are restored to their pre-experiment bytes; the separate
`mutex-entry-restored-20261020/checks-1` basic and affected checks passed.
Its first live attempt failed before provider initialization with reserved
per-CPU ENOMEM and is preserved. After the unchanged allocator guard completed
normal allocation/free preparation, all four `live-2` probes passed with exact
retirement and final idle. The complete archive review passed 31,957 checks.
This restores validated correctness scope, while all seven performance points
and the remaining environment/class/latency gaps stay explicitly unresolved.
The next [shared-lock comparison stage](../bench/results/10.176.26.71/bench/shared-lock-followup-20261020/README.md)
retains the current recovery VM and pinned environment, with separate fresh
Native/KD rwsem and Native/TCLock/KD rwlock controls. All 756 rwsem sessions
completed correctly and drained, with 378 exact KD retirements. Its independent
562,530-check review passed archive/source/arithmetic checks and retained one
failed post-run host-thread comparison (115 versus 67). The observed Native
comparison has 118/126 throughput passes, six misses and two split-class
points, with substantial repetition variation. Acceptance remains open.
The separate 270-session rwlock reference completed correctly and drained, with
90 exact KD retirements and 208,412 independent checks without issues.
Observed parity is 27/30 against Native and 28/30 against TCLock. Both captured
host endpoints match, but the after receipt is delayed 117.556 seconds; that
interval and runtime interference remain unobserved. These results cannot
resolve the mutex comparison by implication.
The [mmap/fault source capture](../bench/results/10.176.26.71/tests/mmap-fault-followup-20261020/README.md)
completed in the idle guest: 46 source/configuration files, including 21 newly
captured callback/helper files, with unchanged kernel identity. The independent
1,470-check review passed and 24 hashed source intervals establish concrete
object/API, ownership/mode, context/lifetime and validation blockers. Real
integration remains explicitly unresolved; no kernel was changed and no KD
mmap/fault test ran. The
[resident-list timing plan](../bench/results/10.176.26.71/bench/nano-list-followup-20261020/README.md)
retains the previously selected 264 sessions at eight and 60 workers.
`timing-1` stopped after 147 attempts: 144 spin/mutex sessions and two shared
controls passed, then the first KD rwlock case failed the retained JIT
requirement. The remaining 69 rwlock cases are unresolved; its 48 unstarted
rwsem cases subsequently ran as the separate `rwsem-1` continuation. Its
immediate host endpoint failed at 83 versus 67 QEMU threads. The independent
250,374-check review preserves all failures, verifies evidence integrity and
reports separate ranges/CVs; no acceptance is claimed. Its first strict preflight failed at 70 versus 67
QEMU threads with zero measured sessions; the failure and later thread turnover
are preserved. A fresh full 67-thread receipt and exact unchanged-plan preflight
passed before `timing-1` started. No admission check or host setting was relaxed.
The rwsem continuation separately passed all 48 cases with 24 exact KD
retirements and 6,734,206 matching entries/completions. Its 71,582-check
independent review passes evidence integrity but preserves an immediate
86-versus-67 host-thread failure. Four of eight Native parity comparisons miss;
maximum KD/Native spreads are 165.98%/22.91%. The prior 73-thread admission
failure and subsequent strict 67-thread admission both remain recorded.
All runs are idle. The failed rwlock execution requirement and 69 missing cases,
host endpoint mismatches, variance and earlier mutex/class/latency gaps remain
open; do not weaken a gate or repeat a failed case for a favorable class.

The [2026-10-21 diagnosis](../bench/results/10.176.26.71/bench/nano-rwlock-diagnosis-20261021/README.md)
continues that unfinished work. Read-only host captures bind the QEMU binary
and show extra workers performing disk writes. Matched RAM/ext4 diagnostics
also observe background root-disk writes, so historical timing interference
remains unresolved. An isolated provider observation patch and fixed matched
comparison will distinguish rwlock ratio/time, lock-heat and queue-prefix
refusals. The original 69 unstarted cases remain a separate strict coverage
plan. No admission threshold, failed record or acceptance gate is changed.

Keep the two-word wrapper ABI, separate backend identities, exact KD physical owners,
exact acquisition references and final ACKs. Shared storage must survive its final
reader. Builds/tests/benchmarks run in the recovery guest; default work does not
change its kernel. Published KD waiters remain pinned polling.

Userspace/futex, other architectures and oversubscription redesign remain
deferred. Real mmap-lock replacement is requested work with unresolved
integration requirements. The [rwsem phase protocol](design/rwsem_implementation.md)
drains readers before writer publication and excludes ordinary downgrade during
an outer-writer cohort. It preserves pinned mutex producers and their existing
oversubscription limits. Outer downgrade, post-publication cancellation, Linux
rwsem fairness and general nested rwsem JIT controls remain unsupported.
Basic plus directly affected checks are the default; full suites need
explicit selection. Extremely uncommon scheduling/resource/alias combinations are
optional coverage, while reproduced supported-path failures must remain visible.

## P0: Correctness contracts

### C1. Forward continuation after partial execution

The supported CALL/PENDING, post-acquisition spin, checked mutex instruction exits
and limited ABI1 pointer-load exits resume from the current state. Earlier stores,
lock acquisitions and releases must happen exactly once. Fixing a recovery defect
must not restart those operations. Typed string argument refusals also preserve
the original unexecuted CALL; a helper that has run cannot be replayed. Generic
faults, indirect-jump misses and instruction-budget errors still stop execution; they cannot
be used as arbitrary native fallback points. Broader combinations of remote
execution and resource exhaustion remain optional coverage.

For rwlock ABI3, writer admission can be cancelled only before the body starts.
A body that already made progress keeps exclusive write access while finishing
natively. Its matching unlock releases the writer byte, and the request must still
complete the required ACK and retirement steps.

### C2. One protocol per physical lock

KD spin owns its word; TCLock/Native own theirs. KD mutex owns its physical
owner word, wait list and legacy scheduling gate. Linux mutex objects or calls
cannot be mixed on it. Preserve ledger identity, local/delegated exclusion,
frame pop, owner ACK and storage retirement as separate operations.
KD rwlock owns its count and KD gate. Ungated native writers retain exact
nondelegated references; gate quiescence alone does not establish count or reader
drain. No Linux/TCLock operations may access the same KD rwlock object.

### C3. Immutable JIT publication and lifetime

The current KD mutex implements complete staged publication,
immutable mutex generations, frame binding and stale-miss rejection. Published
versions use the existing bounded pool and remain until session teardown; there
is no in-session generation reclamation. ABI1 spin entries now transition to
immutable generations when first publishing checked pointer loads or the bounded
`strcmp` or `strscpy_pad` service; every later generation remains immutable, and
older frames keep their earlier image binding.
Ordinary spin/rwlock entries still use in-place storage. General immutable
publication for those entries and in-session reclamation remain open. See
[image lifetimes](design/lifetimes.md#executable-images-and-guarded-spin-transition)
and [the mutex backport comparison](history/legacy_mutex_compatibility.md).

### C4. Instruction, flags, and fault semantics

Mutex ABI2 can emit a checked exit marker before the reviewed instructions listed
in [instruction admission](design/admission.md#checked-instruction-exits).
An executed marker resumes the original waiter at that instruction and disables
future delegation of the entry. Its image preserves arithmetic flags across
generated checks and restores them at that boundary. Unknown instructions,
unreviewed processor-state operations and equivalent context helpers still fail
static admission. Interrupt instructions are never silently replaced with no-ops.
General flag repair outside marker-bearing images and floating-point/vector
virtualization remain deferred. Packet comparisons alone do not prove live
processor-flag restoration.

### C5. Origin context and nested boundaries

Current analysis screens emitted scope, CALL/RET, aliases and static per-CPU ranges;
GS/logical current are not a hardware context switch. Arbitrary hidden calls,
context-object lifetimes, runtime pointers and concurrent replacement remain open.

#### Limited pointer-load checks and remaining address policy

ABI1 spin can now check a restricted pointer load against tracked stack writes
at the point of access. A failed check resumes the original waiter before that
load and disables future delegation. Admission requires proof that incoming
arithmetic flags are unused by the original remainder; a body whose branches
were simplified is conservatively refused by this retry. See the exact
[pointer-load contract](design/admission.md#checked-spin-pointer-loads).

This does not provide general checks for every memory access, arbitrary object
lifetimes, concurrent pointer changes, nested spin ownership or ABI3 rwlock.
Those broader checks remain deferred. Entry guards, the mutex stack checkpoint
and these limited pointer-load checks do not close the
[dynamic-address gap](design/admission.md#721-dynamic-address-gap). Functional
continuation evidence and workload performance acceptance remain separate.

The original [`strcmp`](design/admission.md#original-strcmp-service) and
[`strscpy_pad`](design/admission.md#original-strscpy_pad-writing-service)
services require stable, resident ordinary source strings and one outer spin
owner. They do not infer object lifetime or authorize general copying. `strcmp`
has a private 128-call allowance; on the dispatcher route, `strscpy_pad`, scalar
services and lock controls share the existing 16-call allowance. The direct-call
route has separate per-invocation limits of 128 comparisons and 16 padding calls;
exhaustion transfers the pending original call to the waiter before its effects.
The implementation removes helper code checks, argument scans and runtime
destination checks, using the original C
caller's guarantees. For these two services in selected reviewed C callers,
analysis records temporary CALL return-address storage separately from ordinary
object data. The source
CALL write and its runtime return handling remain unchanged; the caller promises
that ordinary data accesses do not inspect or overwrite this storage. Known
violations are refused, and other calls and ordinary writes retain conservative
alias analysis. The generic refinement for partially overlapping CALL-return
bytes remains archived. The current implementation retains conservative ordinary-CALL/RET
behavior and separate control storage only for `strcmp` and `strscpy_pad`.
Decoded `memcpy` has no special classification or return handling; its original
loads and writes remain analyzed. Focused VM validation passed for read-only
taskname, all eight xattr controls and the string/exit probes; the
[preceding development record](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md)
preserves the failed intermediate checks and the final receipts. See the
[selected-caller contract](design/admission.md#original-call-word-aliases).
The preceding [`88bb5a4` standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
is complete: 567 correct, fully drained sessions cover read-only taskname and
xattr tail queries at 16 and 128 attributes, with fresh Linux Native and TCLock
controls. KD returned generated bodies in 167 of its 189 sessions; 22 recorded
no generated entry. These execution outcomes remain separate in the report.
That version's whole-run throughput at 60 workers is below both comparators in
all three cases. Subsequent profiles identified repeated dispatcher work: one
source-pin lookup per string call and 7/37/261 frame validations per returned
taskname/xattr-n16/xattr-n128 body. Version 11 calls the original helpers within
one generated invocation and pins the code at immutable-image publication.
All six new KD diagnostic cases returned bodies with zero calls to those
dispatcher routines. Registers, actual source CALL words, exact ownership,
quotas and completion checks remain. Fixed request and translated-call costs
remain visible in source, but their individual time costs are unmeasured. The
[current report](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
keeps the new full grid, earlier screens and diagnostic profiles separate.
Its 567-session matrix is complete: 168 KD sessions returned bodies and 21 had
no generated entry. At 60 workers, KD reaches 4.521/2.368/0.573 Mops/s for
taskname/xattr n16/xattr n128, above fresh Native but below TCLock. Six of the
61 compatible historical points have lower whole-run throughput, with the
largest regression about 3.65%; low- and mid-count gaps to fresh controls remain.
The unscored 129-comparison control passed original-waiter continuation and
exact retirement, but its generated prefixes do not count as completed bodies.

The 20% taskname mutation control is correct but has no returned delegated
bodies; its delegation acceptance remains open, and the earlier strict failure
is retained. Xattr front, miss and size-only queries have correctness evidence
but no separate throughput matrix in this round. Full live-task/procfs
integration and arbitrary-caller safety also remain unvalidated. Historical
checked-helper timings retain their own source identity and are not pooled
with this revision.

## P1: Evidence and services

- Complete fresh-checkout reproducibility. Pinned dependencies, frozen source and
  offline checking exist; bundled compiler/dependency bytes and reproducible kernel
  builds do not.
- Add only typed bounded services with argument/result, context, sleeping, overflow
  and side-effect contracts. Clock/int_sqrt exist; arbitrary pointer or variadic
  printk services do not.
- Expand randomized/exactly-once fixtures when useful; do not confuse synthetic
  passes with forced live remote schedules.

### Main-plan acceptance audit

A JIT pass requires the generated and published identities to match, an observed
returned JIT body, correct data, the required physical-owner ACKs and complete
drain. Report publication, native controls and refusals separately. Combining
old passes or selected checks does not establish a current whole-project pass;
see [the historical audit](VALIDATION.md#main-plan-acceptance-audit).
