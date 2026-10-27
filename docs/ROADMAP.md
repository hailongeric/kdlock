# Project goal and three-stage development plan

Updated October 27, 2026. This is the canonical project-level goal, sequence and
completion contract. The [project guide](PROJECT_GUIDE.md) owns working commands
and repository orientation; the [throughput campaign plan](THROUGHPUT_PLAN.md)
owns bounded measurement plans; [performance status](PERFORMANCE.md) owns measured
outcomes. Historical campaign definitions and failures keep their original scope.

Ubuntu 26.04 / Linux 7.0 is now the active adaptation platform, with OS boot
and package identity recorded in the
[migration record](history/vm-ubuntu2604-migration-20261027.md). The separate
[KD port record](../bench/results/10.176.26.71/tests/linux70-port-20261027/README.md)
tracks source/build/live gates; an OS boot or installed headers do not meet
any of the three stages below. Linux 6.1 adaptation is retired. Preserve its
results and single recovery version under the
[retirement policy](history/kernel-retirement-20261027.md). Historical passes
and nano gains remain tied to their original platform.

## Ultimate goal

Integrate KD into the Linux kernel as a replacement for the relevant native lock
implementations, and demonstrate its effect on unchanged programs such as
will-it-scale's `mmap1`. The final result must cover actual kernel objects and
their real callers, rather than only extracted critical sections or module-owned
test objects. The research objective is improved throughput and scalability while
preserving the required Linux API, execution-context and lifetime semantics.

The final evaluation goal matches TCLock's comparison of applications on modified
kernels. KD's development sequence is to establish the lock mechanism's potential,
validate a bounded kernel subsystem, then evaluate broader integration. Its
implementation and admissible execution contexts remain its own. A favorable nano
result does not establish mmap gains; a successful mmap integration does not
establish whole-kernel compatibility.

| Stage | Goal | Main evidence | Completion requirement |
| --- | --- | --- | --- |
| 1. Lock micro/nano benchmarks | Demonstrate useful KD gains, initially for mutexes, and explain the conditions that produce them | Matched Native/KD/TCLock workloads, exact correctness, returned-body evidence where delegation is claimed, regression controls | Reproducible gains on a declared favorable workload and a documented performance envelope |
| 2. Scoped mmap and page faults | Demonstrate improvement or parity with Native for actual MM work under a bounded integration | Actual mmap-lock Native/KD comparisons, `mmap1_threads`, a process control, and explicitly defined real-fault cases | Required semantics pass and the declared primary MM workloads meet the predeclared gain/parity criterion |
| 3. Relevant kernel lock replacement | Integrate the validated lock families into their real kernel call sites and measure application performance | A reproducible kernel patch series, API/context coverage, unchanged application benchmarks, Native controls and a compatible TCLock reference where available | The declared replacement scope is complete, stable, reproducible and supported by end-to-end performance evidence |

Stages are evidence gates, not a ban on parallel preparation. Stage 1 analysis
and stage 2 driver work can overlap. Broad integration must not be reported as
accepted while its required semantics or scoped performance gate remain open.
No numerical gain is guaranteed by this plan. A failed hypothesis remains a
result and determines the next investigation.

## Current position

Stage 1 has functional coverage, historical repeated comparisons and fresh
exploratory gains, but also important counterexamples. The
[fresh mutex nano campaign](../bench/results/10.176.26.71/bench/nano-mutex-20261026/README.md)
measured the 16-cacheline/post64 profile at 60 workers as Native/TCLock/KD
2.651/2.188/4.045 Mops/s: KD was 1.526 times Native and 1.849 times TCLock. It also
won at 32 workers, but lost to Native at 8, 16 and 36. The minimal one-record
profile lost to Native at every contended count. These are separate, single-round
observations, not repeated acceptance evidence or a universal best case. The
[nano guide](../bench/nano/README.md) defines the exact bodies and controls.

The user-directed promotion now selects `mutex-throughput` (one padded counter)
and `mutex-locality` (16 padded counters), both with 256 post-unlock rounds, and
sets the mutex NUMA boundary to 768 with the total cap still 1024. The
[factor screen](../bench/results/10.176.26.71/bench/mutex-profile-20261026/factor-grid/README.md)
selected the bodies under the earlier 256 boundary. The separate
[768-boundary screen](../bench/results/10.176.26.71/bench/mutex-profile-20261026/policy-numa768-vs-policy-control/README.md)
showed cross-NUMA gains alongside losses at 16 workers. These exploratory results
motivate the choice, not a guaranteed gain. The [new 21-count comparison](../bench/results/10.176.26.71/bench/nano-mutex-promoted-20261026/README.md)
at `e5b7f84c` completed all 126 timings and their warmups with exact replay and
drain. At 60 workers, one counter reached 5.567 Mops/s (3.811× Native, 1.790×
TCLock), and sixteen counters reached 4.400 Mops/s (3.426× Native, 2.080×
TCLock). KD remained below Native at four workers on the sixteen-counter body;
both profiles executed locally without JIT at one and two workers. These
single-round exploratory observations do not provide repeat variability or
close the repeatability gate. Keep their source, policy and workload identity
separate from the selection studies.

The [fixed-2.0-GHz rerun](../bench/results/10.176.26.71/bench/nano-mutex-fixedfreq-20261027/README.md)
completed the same 126 timings and warmups with identical source and workload
plans. The large one-worker gap disappeared when all host CPUs were pinned:
all three backends measured about 1.92 Mops/s for both bodies. At 60 workers,
KD measured 4.895 Mops/s for one counter and 3.831 for sixteen, respectively
3.065 and 2.643 times Native. Frequency telemetry, exact replay and drain are
recorded separately from the still-failed strict host membership gate. The
host remains at the requested 2.0 GHz; this single round does not close the
repeatability gate or replace the earlier campaign's recorded evidence.

The [expanded fixed-frequency catalog](../bench/results/10.176.26.71/bench/catalog-fixedfreq-20261027/README.md) at `a9aeb280`
adds all ten active nano profiles: 630 valid, drained measurements. At
60 workers, only the two mutex profiles exceed both Native and TCLock.
Both 1%-write rwsem profiles beat Native without JIT, and every rwsem
and rwlock nano profile remains below TCLock at that count. The
sixteen-counter, 1%-write rwlock loses to Native throughout the
cross-NUMA counts. These results bound the favorable regime; they do not
close the repeatability gate or justify promoting every selected profile
as a demonstrated KD best case.

Xattr preparation failed at 139/168 KD coordinates, versus 47/168 in the historical catalog. These attempts retained exact drain and have no throughput. The fixed eight-worker helper cohort and returned-body prerequisite are unchanged; the reason for the increased failure incidence is not established. [Preparation evidence and limits](../bench/results/10.176.26.71/bench/catalog-fixedfreq-20261027/XATTR_PREPARATION.md).

Stage 2 is in progress and its performance objective is **not achieved**.
The [October 27 fixed-frequency MM comparison](../bench/results/10.176.26.71/bench/catalog-fixedfreq-20261027/MM_INTERPRETATION.md)
completed all 126 implemented measurements. At 60 workers, the retained
`kdmm31` shared-mm kernel measured Native/KD at 132,873.54/6,441.88 complete
mmap/munmap pairs/s; KD reached only 0.04848× Native. Its local-writer admission
and wake policy remains distinct from the current external-module nano path.
The private-backing fault result is a separate local-reader comparison.

The
[October 26 MM screen](../bench/results/10.176.26.71/bench/catalog-mmap-single-20261026/README.md)
completed all 126 implemented points. At 60 workers, the existing 4 KiB shared-mm
writer workload measured 70,350.82 Native versus 6,752.42 KD cycles/s. In the
separate private-backing fault workload KD exceeded Native, but that experiment
keeps the real mmap lock Native and therefore cannot close the actual-MM gate.
Strict host qualification failed for that exploratory screen. The earlier
three-repeat matrices remain separate; the screen did not complete them.

The independent-process control, private-backing fault loop and shared-mm device
mapping are all useful diagnostics. None is the exact will-it-scale `mmap1`
workload. A maintained, validated comparison of `mmap1` on actual Native/KD
mmap-lock backends remains to be prepared. Generic actual-mmap-backend fault
throughput also remains distinct from the existing private-backing runner.

Stage 3 is a planned objective. Loading today's provider does not redirect all
kernel locks. The current TCLock module port likewise does not supply a complete
kernel mmap integration. Historical acceptance applies to its recorded source,
kernel, topology and interface; it is not inherited by a later implementation.

## Stage 1: establish the mechanism and performance envelope

### Questions and workloads

Determine when the cost of admission, publication, JIT execution, ownership
transfer and retirement is amortized by batching and shared-data locality.
Distinguish this from improvements in local lock acquisition or reader admission.

1. Use the two maintained favorable mutex profiles: `mutex-throughput` updates
   one padded counter and `mutex-locality` updates 16 independently aligned
   counters. Both use 256 post-unlock rounds. Keep each body and its parameters
   fixed during comparison.
2. Retain the historical two-word/post4 and post64 locality results. The old
   focused profile names are retired from active nano choices. Their losses
   remain evidence of cases where delegation overhead or contention patterns
   outweigh the benefit.
3. Compare public ABI2 mutex acquisition with the callable local KD control,
   Linux Native and the supported original TCLock mutex port. Record each call
   shell and its compiler/instrumentation settings separately.
4. Use matching one-/sixteen-counter, post256 bodies for rwsem and rwlock, with
   separate 1%-write and 20%-write profiles. Readers remain concurrent and local.
   Explicit writer delegation is a separate execution class from ordinary local
   acquisition. A NO_JIT reader-heavy win is not a JIT win.
5. Check transfer to existing cacheline, resident-list and RCUHT workloads, then
   the small real API cases such as seek and pipe queries. A synthetic bulk-ioctl
   loop and a syscall-per-operation workload are different experiments.

### Work and deliverables

Use the [per-workload analysis](../bench/results/10.176.26.71/bench/catalog-single-20261026/PERFORMANCE_ANALYSIS.md)
to select a small point list before further tuning. Include an uncontended point,
within-node contention, both sides of the 32/36-worker NUMA boundary and a high
count. The current nano default is the 21-count grid `1..8,12..60` in steps of
four above eight. The user has selected that full grid for all ten active nano
profiles and the full implemented catalog. Smaller explicit count sets remain
useful for diagnostics.

For every result, retain exact updates/read checks, physical ownership, source
leases, unlock ACKs and final retirement. Count completed delegated writers when
available; a published NORMAL image or entry witness alone is insufficient.
Report delegated share with its correct denominator and keep local completions.

If a mechanism needs attribution, collect a bounded, separate profile of CPU
time, scheduling/wakeup behavior and relevant coherence/cache events where
available. Compare matched local and delegated paths before assigning a gain to
JIT or NUMA locality. Profiling overhead must not silently enter the plain curve.
Change one mechanism at a time and retest the affected correctness obligations.

Deliver a fixed workload specification, source/binary manifest, per-workload
tables and scaling charts, a local/delegated comparison, and a concise account
of favorable and unfavorable regions. Preserve the seven recorded mutex
regression points in the [campaign plan](THROUGHPUT_PLAN.md); current exploratory
results do not automatically resolve their causes.

### Stage 1 completion

The mandatory initial proof is a repeatable mutex gain over Native in a declared
favorable regime, supported by correct results and execution evidence. Compare
TCLock where its interface is equivalent, without making victory over TCLock a
substitute for the Native comparison. Publish single-worker and adverse-count
costs alongside the favorable case. Rwsem reader-policy and writer-delegation
claims require their own evidence. Wider family support is expanded explicitly,
rather than inferred from a mutex result.

## Stage 2: prove scoped MM improvement or parity

### Integration boundary

Use the [Linux 7 mmap adapter](../kernel_integration/linux70/MMAP.md) to change
the lock backend and necessary API/lifetime wrappers. Preserve native mmap,
munmap, advice and page-fault algorithms and their execution on the originating
task. Each mm chooses one protocol before publication; every acquisition,
release, try, cancellation and downgrade on that object follows that protocol.

The current adapter uses local KD readers and writers. Stage 1 delegation gains
therefore cannot be assumed to appear in stage 2. Investigate phase admission,
reader drain, writer handoff, cancellation and wakeup costs on their actual
syscall paths. In particular, tuning the ordinary uninterruptible polling loop
does not directly tune mmap's separate killable writer acquisition.

Operation-specific MM delegation and prepared teardown remain retired. If local
MM locking cannot meet the performance objective, report the unresolved result
and revisit the design explicitly. Do not restore those experiments or change
native MM behavior merely to make a throughput curve favorable.

### Workload matrix

| Workload | Exact operation and topology | Backend under test | Role |
| --- | --- | --- | --- |
| `mmap1_threads` | Shared-mm pthreads; map 128 MiB with `PROT_READ \| PROT_WRITE`, `MAP_PRIVATE \| MAP_ANONYMOUS`, then unmap; no payload access | Actual Native versus KD mmap-lock implementation | Primary writer scalability target, matching TCLock's benchmark topology |
| `mmap1_processes` | The same operation in independent processes, each with its own mm | Actual Native versus KD mmap-lock implementation | Independent-mm overhead and parallel-scaling control |
| Existing shared-mm device mapping | Pthreads map/unmap untouched 4 KiB read-only `MAP_SHARED` device ranges | Actual Native versus KD mmap-lock implementation | Retained instrumented correctness and regression diagnostic; not `mmap1` |
| Actual minor-fault workload | Defined anonymous or resident-backed faults, with declared mm sharing, access type and reset method | Actual Native versus KD mmap-lock implementation; any private backing lock fixed across arms | Primary fault-path integration and reader-side comparison |
| Existing private-backing fault cycle | Independent processes; `MADV_DONTNEED` plus a checked read of a preallocated driver page | Private backing Native/KD/TCLock reader lock; mmap lock stays Native | Supporting callback/reader experiment, not actual mmap-lock substitution evidence |
| Existing independent-mm device mapping | Map/unmap untouched 4 KiB ranges in separate processes | Native only in the existing runner | Historical diagnostic; selecting its unused private KD lock would not create a KD mmap result |

The reference [upstream mmap1 source](https://github.com/antonblanchard/will-it-scale/blob/master/tests/mmap1.c)
and the [TCLock artifact's copy](https://github.com/rs3lab/TCLocks/blob/bbfb9f00a12af51dff6ca291cb9829a82960c2ef/src/benchmarks/will-it-scale/tests/mmap1.c)
define the 128 MiB operation. Pin the chosen benchmark revision and executable
hash before collection. `MAP_PRIVATE` does not give each pthread an independent
mm. Sharing an fd alone does not prove a shared mm either.

### Implementation sequence

1. **Freeze the comparison contract.** Declare the benchmark revision, kernel
   source/configuration, compiler, Native/KD mode, worker counts, CPU/memory
   placement, duration, warmup, repetitions and performance threshold. Native
   mode in a modified kernel is an in-tree control; a separately built stock
   kernel is a distinct baseline. Record both identities when both are used.
2. **Prepare the `mmap1` runner.** Run the same userspace executable in both
   modes. Retain upstream operation semantics, argument meanings and completed
   pair counting. Keep process/thread results separate. Match ASLR, page size,
   THP and overcommit settings, plus memory-accounting/cgroup conditions. Large
   untouched anonymous mappings can exercise accounting paths beyond mmap_lock.
   Record allocation failures; never turn them into completed operations.
3. **Validate before timing.** Confirm the selected backend reaches the actual
   syscall acquisition sites. Check shared/independent mm identity outside the
   hot loop, success/error behavior, exclusion, reader concurrency, killable
   acquisition, downgrade, fork/exit, VMA lifetime and required read-share
   transfers. Use the basic checks and directly affected MM tests. Diagnostic
   probes and extra per-operation accounting require separately labelled runs.
4. **Prepare actual fault throughput.** Start with one precisely defined minor
   fault class. Specify whether faults are first touches or reset-and-touch,
   whether reads or writes occur, and what setup/teardown is timed. Preallocate
   result storage. Check data and observed fault counts. Keep a private backing
   lock Native in both arms when isolating the kernel mmap backend. Name a
   reset-plus-touch result as cycles/s, not isolated faults/s. COW, major faults,
   dirty file faults and retry variants are separate later cases.
5. **Screen and diagnose.** Use a small Native/KD grid first, with one round per
   point for exploratory screening when requested. Publish each workload's table
   and chart immediately when complete. Examine the retained shared-mm regression
   before expanding. A failure stops dependent work until ownership and drain
   are established; elapsed timeout alone is not drain.
6. **Optimize and confirm.** Make a bounded change justified by measured lock-path
   costs. Repeat the affected functional checks, then run a separately declared
   repeated comparison. Preserve both the baseline and the changed version,
   including regressions. Do not pool the old device-mapping results with mmap1.

### Stage 2 completion

Correctness is required independently of performance. The primary `mmap1_threads`
and actual-fault cases must demonstrate improvement or parity against Native on
the predeclared count set; the process control must expose any independent-mm
cost. A good private-backing reader result cannot offset a failing shared-mm
writer result. A correctness-only pass cannot close this stage.

Define parity before measuring as an allowed throughput regression `epsilon`.
A proposed initial tolerance is 5% (`KD/Native >= 0.95`), subject to the declared
workload requirements and observed measurement resolution. It is a planning
default, not an accepted result or permission to ignore variability. If variance
is too large to distinguish that margin, parity is unresolved. A claimed gain
must exceed the observed noise in repeated paired observations. Select critical
points in advance and publish the full measured curve; do not choose a favorable
point after collection to waive losses at required points.
This proposed stage criterion does not change any existing runner's parity
predicate, host eligibility policy or historical acceptance decision.

Deliver the scoped patch/configuration, a semantic coverage matrix, all failures,
reproducible Native/KD tables and charts, attribution for the main gains/losses,
and the exact remaining boundary before broader replacement.

## Stage 3: replace relevant kernel locks and evaluate applications

### Define and complete the replacement scope

Create a call-site and API inventory for each targeted family: ordinary mutex,
rwsem, spinlock and rwlock. Expand by reviewed subsystem/object groups, starting
with the validated MM integration and selected mutex users. For each group,
record construction/destruction, layout and alignment, static initializers,
callable symbols, macro aliases, nested acquisition, try/killable/interruptible
operations, IRQ/BH/preemption state, downgrade and asynchronous/non-owner release.
List any unsupported variants explicitly. RT, ww_mutex, lockdep and broad
oversubscription require separate designs and validation before entering the
claimed supported configuration; they are not silently covered by replacement.

Change the representation, initialization and all access paths of each selected
object together. Never let Native and KD operations protect the same object via
independent exclusion protocols. A nondelegating acquisition on a KD object must
remain a local KD acquisition with exact unlock routing. Unsupported object
classes may stay wholly Native, with the exclusion visible in the coverage map.

Prepare a reviewable kernel patch series and configuration options, preserving a
matched Native control and recovery image. Integrate storage allocation,
CPU/task lifecycle, translation-service readiness, source-code lifetime, image
publication and exact retirement. Verify the required caller-clobber ABI at all
eligible compiled call sites, including indirect calls and aliases. Generic
provider loading or import substitution alone is not kernel-wide replacement.

### Local execution and delegation

Classify critical sections before enabling delegation. Pure protected-data work
may be eligible after admission checks; code depending on `current`, credentials,
address-space state, user access, allocation/accounting context, scheduling,
IRQ state or task-local resources requires an explicit semantic argument.
Unknown cases remain local within the selected lock protocol. Record both the
replacement coverage and the actual delegated share; these are different metrics.

Preserve the current KD-only foundation: ABI2 mutex calls, the 32-byte
native-aligned object, independent OSQ/delegation memberships in preallocated
storage, pinned published waiters, the 768-body NUMA boundary, immutable mutex images
and fail-closed admission. Broader integration does not authorize reverting to
Linux mutex backing, parked delegation producers or the rejected owned/adaptive
protocol. MM bodies stay local under the maintained contract. Any later proposal
to broaden that contract needs its own design and evidence, without assuming
TCLock's execution model is already safe for KD.

### Validation and final evaluation

For each integration increment, run the basic and affected tests before adding
the next group. Cover acquisition/release ownership, cancellation, nesting,
concurrent readers, data integrity, source/module retirement and kernel lifecycle.
Plan broader stress, boot/shutdown and subsystem checks for the final declared
configuration; full suites are explicitly selected work, not the default after
every edit. Fix reproduced failures rather than weakening admission or probes.

Evaluate unchanged userspace programs on the final kernels. Begin with
`mmap1_threads` and `mmap1_processes`, then the actual fault workloads, followed by
explicitly chosen mutex/spin/rwsem-sensitive applications. Define those additions
from the completed replacement map instead of promising improvements in
unmodified or unsupported subsystems. Retain stage 1 and stage 2 workloads as
regression checks, with their own source identities.

Use three distinct labels when applicable: stock Linux, the integration tree's
Native mode, and the integration tree's KD mode. A TCLock comparison requires a
compatible full-kernel integration and matched benchmark, kernel baseline,
hardware and settings. Our external TCLock port is sufficient only for its
supported micro/nano interfaces. Old paper curves from another kernel or machine
are contextual evidence, never same-system control measurements.

The final artifact must include the kernel/benchmark revisions, patch series,
configs and binaries, scope and exclusions, reproducible commands, correctness
receipts, throughput curves, CPU cost where measured, regression analysis and
recovery record. Revisit application latency/fairness when required by the final
acceptance contract; current throughput-only screens do not establish them.
Completion means the declared relevant replacements and application evaluation
are finished, not that every kernel lock or every deployment is supported.

## Measurement and decision rules across stages

- Keep exploratory one-round screens separate from confirmatory runs. The
  existing one-round request remains a screen policy; new repeated campaigns
  receive their own manifests. Three paired repetitions are a practical initial
  confirmation plan, not precise confidence intervals. Use more only when the
  declared question and observed variability justify them.
- Within each campaign hold source, workload, shell, compiler/sanitizer options,
  topology, NUMA placement, instrumentation and operation counting fixed. Alternate
  or balance backend order where practical and preserve boot identity. Never pool
  different configurations or treat preparation failures as zero-throughput data.
- Define throughput from complete operations and the documented elapsed interval.
  Preserve each raw count/time, ratio and repetition. Report median/range and
  variability for repeated runs, and missing optional peak statistics as missing.
  A full-cohort peak is not a replacement for whole-run throughput or progress.
- Environment qualification and functional correctness have separate verdicts.
  The October 26 exploratory permission does not turn its failed strict timing
  verdict into a pass. Freeze the appropriate host policy before future collection
  and preserve endpoint/window evidence; no retrospective gate changes.
- Keep correctness evidence strong while reducing measurement overhead. Put
  identity/probe work outside timing where valid, and label sampled/instrumented
  modes separately. New tail-latency collection remains deferred for the current
  throughput phase.

Source edits and static reviews run on `380G10`; builds, tests and timing run in
the designated VM. Follow [VM operations](operations/VM.md): synchronize only
while idle, freeze inputs, verify a real recovery snapshot before live work,
bound commands, prove drain and preserve failures. This documentation update
does not itself launch a benchmark or authorize kernel modification, installation
or reboot. Future execution follows the concrete task authorization and existing
operations rules; do not request permission again for already authorized work.

## Milestones and next actions

| Milestone | Deliverable | Current status / dependency |
| --- | --- | --- |
| M1. Mechanism specification | Fixed nano bodies, matched controls and exact execution/data accounting | Implemented; favorable and unfavorable exploratory results retained |
| M2. Stage 1 confirmation | Repeated favorable mutex result with adverse-count/local controls | Fresh exploratory evidence exists; current confirmation gate remains open |
| M3. Exact mmap1 comparison | Pinned `mmap1_threads`/`mmap1_processes` runner using actual mmap backends | Next scoped implementation task; existing 4 KiB device test remains separate |
| M4. Actual fault comparison | A validated fault class with reset/data/fault accounting and a fixed backing implementation | Correctness ingredients exist; maintained generic throughput driver needed |
| M5. Scoped MM acceptance | Correctness plus gain/parity on declared mmap/fault cases | Open; existing shared-mm loss requires investigation |
| M6. Kernel replacement map | Per-family/object API inventory, context rules and incremental patch plan | Planned; use M5 evidence to decide the first expansion |
| M7. Integrated kernel | Completed declared replacements with lifecycle and subsystem validation | Planned; depends on semantic closure for each group |
| M8. Final comparison | Unchanged applications on matched Native/KD kernels, with optional compatible TCLock | Planned; requires M7 and an explicit final experiment manifest |

The immediate sequence is to freeze the current nano evidence, prepare the exact
mmap1 contract/runner, establish a small actual-MM comparison, investigate the
measured loss, and prepare the first actual fault-throughput case. Confirm stage
1 gains and stage 2 parity/improvement before declaring their gates complete.
Only then promote the tested integration into the broader replacement series.

## TCLock reference and comparison limits

TCLock's [OSDI 2023 paper, sections 5–6.1 and Figure 3(d)](https://www.usenix.org/system/files/osdi23-gupta.pdf#page=12)
evaluates the writer side of the actual mmap rwsem with shared-address-space
threads. It reports 1.7 times Stock throughput within a socket and 3.1 times
Stock / 1.5 times ShflLock across sockets, attributing the benefit to batches of
roughly 1,000 writer requests and reduced shared-data movement. It describes an
8-socket, 224-core system with hyperthreading disabled and Linux 5.14.19. Section
7 explicitly retains task-identity and resource-accounting limitations.

The [published artifact](https://github.com/rs3lab/TCLocks/tree/bbfb9f00a12af51dff6ca291cb9829a82960c2ef)
contains a 5.14.16 kernel tree and separate Stock/CNA/ShflLock/TCLock build/boot
scripts. Its mmap1 driver launches threads with a requested 30-second interval;
the loop uses anonymous private mappings without page access. These concrete
source details take precedence over ambiguous workload prose when defining a
reproduction. Preserve the paper/artifact version difference. KD aims for the
same class of final application comparison, with independently established
semantics and performance rather than inherited claims.
