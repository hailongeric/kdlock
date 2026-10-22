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

The user's priority is the [basic working version](PROJECT_GUIDE.md#basic-working-version)
across all original tasks. Reuse validated functionality and run focused serial
smoke/correctness checks. Causal profiling, wake-callback observer expansion,
p95, exhaustive matrices and performance tuning are deferred. All seven causes
and qualified variance remain unresolved; preserved performance refusals remain
failures. Functional delivery keeps ownership, isolation, recovery, topology,
lifetime and teardown checks without requiring timing acceptance.
The [basic handoff](../bench/results/10.176.26.71/tests/basic-version-20261022/README.md)
now records four returned-body presets and complete drain. Its failed
16-worker mixed rwlock delegation check remains unresolved; the basic preset
uses the separately validated 60-worker case without changing admission.
The completed [receipt-I/O control](../bench/results/10.176.26.71/bench/mutex-receipt-io-20261021/README.md)
passed 49 serial basic/affected and 2,626 inert archive checks, with one original
warmup, exact retirement and final drain. Seventeen writes/4,874,247 logical
bytes narrow receipt intervals; all three worker births precede export. The
unchanged endpoint fails at 70, and request/descriptor attribution remains open.
No timing or new p95 ran. The completed read-only
[RCUHT class audit](../bench/results/10.176.26.71/bench/rcuht-class-audit-20261021/README.md)
finds plain no-JIT sessions with queue entries but zero lifetime combiner calls;
their cause remains unresolved. The separate
[actual-MM plain stage](../bench/results/10.176.26.71/tests/actual-mm-plain-20261021/README.md)
passed both-mode correctness with identical frozen binaries and restored the
recovery kernel. Throughput admission refused 68 QEMU threads versus 67, so no
timing session started. The RCUHT phase diagnostic passed five focused tests but
refused at 71 threads before workload execution. All seven causes, new qualified
throughput repetitions and their variance remain unresolved; p95 stays deferred.

The [2026-10-22 continuation](../bench/results/10.176.26.71/tests/serial-continuation-20261022/README.md)
completed and archived the separate RCUHT OUTER/DIRECT phase diagnostics after
fresh full admission. Both drained exactly; fixed endpoints still failed at
110/76 threads. The phase counts are entry witnesses and provide no causal fix.
The unchanged actual-MM candidate completed six serial boot blocks and 24
validated, drained cases using the already validated binaries. Every case
retains its own admission and fixed endpoint; all endpoints failed at 68–70
threads versus 67. Recovery is restored. All-attempt ranges and CVs are
[reported](../bench/results/10.176.26.71/tests/serial-continuation-20261022/ACTUAL_MM.md),
but qualified repetitions and qualified variance remain unresolved (n=0).
All seven mutex causes remain unresolved; no performance acceptance is declared.

The [focused mmap contention investigation](../bench/results/10.176.26.71/bench/mmap-contention-20261022/README.md)
binds the actual killable writer paths to the candidate ELF and identifies
phase wakeup/reader-drain work as a hypothesis. Two basic programs and fourteen
affected checks passed. Its one planned diagnostic pair was refused before
execution at 72 QEMU threads versus 67; both profiles remained unrun in that
attempt and recovery was restored. No implementation defect or causal fix was
demonstrated, and no gate was relaxed. That stage left the matched, bounded
kernel-stack profile of the unchanged 16-worker mmap workload outstanding.

The subsequent [settled diagnostic pair](../bench/results/10.176.26.71/bench/mmap-contention-followup-20261022/README.md)
completed once per mode with full admission, business validation and drain.
Recovery is restored. Endpoints failed at 85/74 versus 67, so qualified timing
and variance remain unresolved. KD's sampled CPU contexts concentrate in writer
phase admission (1,000/1,148 selected samples), with no selected physical-gate
sample. This identifies the next investigation target, not a demonstrated cause
or fix. Preserve killable cancellation, concurrent readers, exact ownership and
downgrade/wake ordering in any follow-up. All seven public-mutex causes remain
unresolved; no performance acceptance follows.

The [writer-phase metadata stage](../bench/results/10.176.26.71/bench/mmap-phase-observation-20261022/README.md)
passed basic, receipt and serial live controls, then observed repeated failed
admission after blocking across all 16 workers: 94.04% of blocked phase-schedule
returns fail their next predicate. Original ownership, cancellation, reader,
downgrade and reference oracles passed. This does not identify wake source or
fanout, uninstrumented cost, per-acquisition retry distribution or fairness.
That stage left failed-after-block, no-switch and runnable-only coverage gaps,
which the follow-up below closes. Any selective-wake candidate still needs competing-writer,
reader-cohort, cancellation/rollback-successor and downgrade controls. The fixed
endpoint failed at 72 versus 67; qualified timing/variance and all seven original
public-mutex causes remain unresolved. Recovery is restored and idle; no protocol
change or acceptance followed this diagnostic.

The [deterministic observer controls](../bench/results/10.176.26.71/tests/mmap-phase-controls-20261022/README.md)
now close the failed-after-block, no-switch and runnable-only coverage gaps:
51 checks passed with exact identities, independent task switch counters and
complete joins, after basic/receipt checks and the unchanged 139-check baseline.
The observer and original workload bindings remain sealed. Recovery is restored
idle. A later causal stage would validate exact wait-entry/wake-callback correlation,
including stack reuse, scheduler activation, cancellation and complete callback
lifetimes, before attributing retries to fanout or changing wake policy. No
timing ran; qualified variance and all seven original causes remain unresolved.

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

The latest [regression evidence review](../bench/results/10.176.26.71/bench/mutex-causal-boundary-20261021/README.md)
narrows pipecap's class mismatch to OUTER sessions with no delegation queue entry
versus DIRECT sessions with returned bodies. Historical host-worker activity
cannot be reconstructed, and a fresh observation still fails the thread-count
gate. All seven causes remain unresolved. The subsequent
[isolated general-unlock control](../bench/results/10.176.26.71/bench/pipecap-unlock-20261021/README.md)
is implemented and passed basic/affected, ELF, live owner/ACK and four serial
syscall correctness checks. Its single timing gate failed at 68 versus 67 host
tasks, before any session. The later
[paired follow-up](../bench/results/10.176.26.71/bench/pipecap-unlock-followup-20261021/README.md)
waited for a qualifying gate and completed all six planned sessions, retaining
all paired rates and variance. Its immediate endpoint failed at 120 versus 67
tasks, with changing returned fractions and one mixed-class pair. All seven
causal resolutions remain open; no admission, ownership or environment check
may be relaxed. The allocator failure and identical-binary successful retry stay
separate from these frozen-provider workload results.

Focused [QEMU phase controls](../bench/results/10.176.26.71/bench/qemu-workers-20261021/README.md)
now reproduce extra workers during guest setup/no-op activity before a workload.
The separately bracketed workload/collection diagnosis is complete with the
original gate, frozen inputs and correctness prerequisites preserved. All six
observed workload workers were born before measurement, but the runtime count
still fails at 73 and boundary activity remains unattributed. Three archives
passed 2,340 inert checks. Observer overhead, unsampled lifetimes, delayed guest
I/O and indirect interference remain unresolved. No historical endpoint or
regression is accepted by these controls; causal unlock-path attribution and
acquisition latency remain open.

The [setup-boundary diagnostic](../bench/results/10.176.26.71/bench/mutex-boundary-20261021/README.md)
completed without timing: basic/affected checks passed, one original warmup
completed 6,724,992 operations, and the held session preserved exact state and
retired normally. Its five scheduled full captures at 0/15/30/60/120 seconds
all refused (75/75/70/68/68 tasks). Eleven intervening accounting scans saw
67, then a new worker appeared; the post-cleanup full capture was 70. Archives
passed 2,004 inert checks. Next, a bounded no-timing candidate-triggered full
capture can test the observed quiet interval; a sample alone never admits the
gate. Post-warmup waiting changes the preparation contract, so timing parity,
all seven causal resolutions and acquisition latency remain unresolved.

The [sample-triggered follow-up](../bench/results/10.176.26.71/bench/mutex-boundary-trigger-20261021/README.md)
obtained one valid full prepared-boundary pass: an exact-67 scan triggered the
capture after 25.431 ms, and the unchanged fresh guest comparison passed while
held state remained identical. One warmup completed 8,375,936 operations; no
timing was sent and retirement/drain passed. The endpoint full capture failed
at 70, distinct from the last accounting sample's 67. Basic/affected checks and
2,046 archive checks passed. This establishes observed feasibility only; the
83.971-second post-warmup wait changes preparation history. A separate no-timing
pre-warmup-wait control can test whether warmup recreates workers. Original
timing parity, all seven causal regressions and acquisition latency remain open.

The [pre-warmup control](../bench/results/10.176.26.71/bench/mutex-prewarmup-20261021/README.md)
now passed the full gate before one original warmup and in one immediate post
capture, without a post-warmup settling wait or timing command. The warmup
completed 8,272,256 operations/54,599 returns and retired exactly; 33 basic and
affected checks and 2,390 inert archive checks passed. The endpoint still failed
at 68. No accounting samples cover warmup or the later validation/cleanup gap,
so the new endpoint worker cannot be attributed. Preserve this observed boundary
feasibility separately; all seven causes, acquisition latency and performance
acceptance remain unresolved. Do not replace the failed endpoint with an
eventually quiet capture.

The [phase-accounting follow-up](../bench/results/10.176.26.71/bench/mutex-phase-accounting-20261021/README.md)
completed with 38 serial basic/affected checks and 2,446 inert archive checks.
One original warmup completed 6,975,616 operations/53,833 matched returns with
exact retirement and final drain. Full gates passed at 67 before and immediately
after warmup, but the endpoint failed at 70. All three extra workers were born
after the post capture and before the cleanup body began; initiating I/O remains
unknown. Active-window observer CPU was at least 25.758% of one core, so this
separate no-timing evidence does not establish continuous quiet or acceptance.
Keep the endpoint in place. Next independent work is a bounded receipt-I/O
diagnostic, offline actual-MM comparison plans and a retained RCUHT execution-
class audit. All seven causes, acquisition latency and timing acceptance remain
unresolved; no new user decision is needed to begin that repository work.

The entry-inlining experiment passed focused correctness checks but did not
resolve the seven mutex losses in its separate 120-session comparison. It is
not accepted as a performance fix. The stage record retains all repetitions,
class gaps and the failed post-run QEMU thread-set check; latency and runtime
host interference were unmeasured in that experiment. The archive ref
`archive/mutex-entry-inline-20261020` preserves it at `7062887`. The common entry
and its test extraction marker are restored to their pre-experiment bytes; the separate
`mutex-entry-restored-20261020/checks-1` basic and affected checks passed.
Its first live attempt failed before provider initialization with reserved
per-CPU ENOMEM and is preserved. After the unchanged allocator guard completed
normal allocation/free preparation, all four `live-2` probes passed with exact
retirement and final idle. The complete archive review passed 31,957 checks.
This restores validated correctness scope, while all seven causal performance
points and the remaining environment/class gaps stay explicitly unresolved.
The later latency stage records complete-operation p95 within its stated scope.
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
object/API, ownership/mode, context/lifetime and validation blockers. That review
made no kernel changes and ran no KD mmap/fault test. The subsequent
[opt-in mapping stage](../bench/results/10.176.26.71/tests/mmap-fault-optin-20261021/README.md)
implemented module-owned backing state and passed Native/KD/TCLock functional
checks at `21451da`, preserving three failed preparation attempts. Native mmap
ownership, origin-task callbacks, exact retry/completion releases and explicit
Native fallback remain separate from private backing locking. The later
[split-workload stage](../bench/results/10.176.26.71/tests/mmap-fault-split-20261021/README.md)
passed eighteen separate mmap/fault cases and completed 48 timings through local
readers, with complete-operation p95 and paired observation controls. Its strict
host endpoint failed (73 versus 67 threads); variance and isolated instrumentation
cost remain unresolved. Full-mm conversion, signal cancellation, generic callbacks
and all seven mutex causes remain open. Reader delegation is deliberately
absent; a real exclusive backing-writer workload needs its own supported
contract and execution evidence.

The [shared-mm Native writer stage](../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/README.md) now proves actual mmap writer
contention without payload faults and validates split, descriptor/VMA and exit
lifetimes. Its six cases, four timing-client validations, twelve measurements
and eighteen negative checks completed with drain. The strict endpoint failed
at 76 versus 67 QEMU threads. Native timing variance and sampling cost remain
unresolved. The
[historical integration audit](../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/INTEGRATION.md)
is separate from the subsequent
[actual-object kernel correctness stage](../bench/results/10.176.26.71/tests/mmap-kd-kernel-20261021/README.md),
which completed selected Native-control/KD-local tasks on `6.1.159-kdmm1`.
Readers are concurrent/local, writers stay on the original task, and mmap and
fault cases are distinct. Recovery artifacts and organization are complete.
The full transitive participant/filesystem/module scope remains unvalidated;
no arbitrary MM delegation, TCLock MM support or experimental timing is claimed.
The subsequent [plain-workload validation](../bench/results/10.176.26.71/tests/actual-mm-plain-20261021/README.md)
bound the candidate image/mode, runtime modules, prior receipts and one frozen
binary set. Both-mode correctness and default recovery payload builds passed.
Its planned timing remains unstarted because the original host gate refused
68 versus 67 threads. A future attempt must retain separate boot identities and
qualify unchanged environment/endpoint checks. No repeated organization or
already-completed correctness is needed without changed inputs or new evidence.

The
[resident-list timing plan](../bench/results/10.176.26.71/bench/nano-list-followup-20261020/README.md)
retains the previously selected 264 sessions at eight and 60 workers.
`timing-1` stopped after 147 attempts: 144 spin/mutex sessions and two shared
controls passed, then the first KD rwlock case failed the retained JIT
requirement. The remaining 69 rwlock cases did not run in `timing-1`; their
separate continuation is recorded below. Its 48 unstarted rwsem cases
subsequently ran as the separate `rwsem-1` continuation. Its
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
All runs are idle. The failed rwlock execution requirement, host endpoint
mismatches, variance and earlier mutex/class gaps remain open; do not weaken a
gate or repeat a failed case for a favorable class.

The [2026-10-21 diagnosis](../bench/results/10.176.26.71/bench/nano-rwlock-diagnosis-20261021/README.md)
records the subsequent investigation. Read-only host captures bind the QEMU binary
and show extra workers performing disk writes. Matched RAM/ext4 diagnostics
also observe background root-disk writes, so historical timing interference
remains unresolved. An isolated provider observation patch and fixed matched
comparison distinguish rwlock ratio/time, lock-heat and queue-prefix refusals.
The original 69 unstarted cases use a separate strict coverage plan. No
admission threshold, failed record or acceptance gate is changed.
The first fixed 12-case diagnosis completed: six eight-worker strict NO_JIT
failures, six sixty-worker successes, 12 exact retirements and 59,561 passing
evidence-integrity checks. Its endpoint still fails at 72 versus 67 threads.
Queue-prefix vetoes dominate the eight-worker heat behavior, while 19,699 hot
slowpath entries never start a combiner; the later focused extension classifies
that refusal. The original remaining 69 cases then completed
with 59 strict successes and ten strict NO_JIT failures, all drained. Their
76-thread endpoint fails too. Its 12,155 evidence-integrity checks and 23 exact
retirements pass. Missing-case coverage is closed; strict execution, host
interference and performance acceptance remain open. A 50-field diagnostic
extension now observes the unchanged initial combiner decisions and exact
source-lease refusal, with separate fixed matched controls.
That extension completed: all 10,441 ready eight-worker calls refused the
first non-combinable follower before evaluating the source-lease condition.
Capacity, ticket and image-readiness refusals were zero. The six eight-worker
cases still fail NO_JIT, while all six sixty-worker cases pass. All 83,603
integrity checks and 12 exact retirements pass; the 74-thread endpoint fails.
This closes the later-branch diagnosis for the observed reproduction, not
the strict execution or host-interference acceptance gaps.

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

The [focused five-worker pipecap investigation](../bench/results/10.176.26.71/bench/pipecap-causal-20261021/README.md)
is deferred under the basic-version priority. It must distinguish original route
counts, queue waits and observer effects before proposing a production change.
The initial host receipt fails; planned diagnostics are not passes. Remaining
performance and broad integration gaps retain explicit unresolved dispositions.

The [seven-point latency stage](../bench/results/10.176.26.71/bench/mutex-latency-20261021/README.md)
completed its separate 252-session follow-up after a retained capacity failure.
The larger buffer passed basic/affected checks; 4,073,421 observations and 126
exact KD retirements passed 5,218,772 independent integrity checks. The host
endpoint failed at 125 versus 67 threads. Preserve all observations, observer
effects, class changes, variance, failed preflights and missing samples from
the failed first run. Sampled complete-operation p95 is available; the seven
causes, acquisition latency, isolated observer cost and runtime interference
remain unresolved. No performance acceptance is declared.

A JIT pass requires the generated and published identities to match, an observed
returned JIT body, correct data, the required physical-owner ACKs and complete
drain. Report publication, native controls and refusals separately. Combining
old passes or selected checks does not establish a current whole-project pass;
see [the historical audit](VALIDATION.md#main-plan-acceptance-audit).
