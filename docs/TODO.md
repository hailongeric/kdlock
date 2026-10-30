# Known limitations and deferred work

The [roadmap](ROADMAP.md) owns the three-stage plan. This page records unresolved
implementation and evidence gaps; [validation](VALIDATION.md) owns outcomes and
[performance](PERFORMANCE.md) owns measurements.

## Current checkpoint

Ubuntu 26.04.1 / Linux `7.0.0-38-kdlock1` is the normal platform. The separate
`kdmm1` image supports the measured Native/KD shared-MM modes. Linux 6.1 is
recovery/history only. Fresh four-family functional checks and the selected
[3,402-point catalog](../bench/results/10.176.26.71/bench/catalog-linux70-complete-20261028/README.md)
are complete within their separate frozen scopes. All timing is exploratory,
with one round per point and failed strict qualification.

## October 29 API and execution work

The source audit starts at `6a7350291ebab8c50a43431561e11085098d628b`;
the latest implementation commit there is
`acc4dbc2e28394522992469250a31da536c39fa7`. The audit is static inspection,
not a new execution result. The user requested the following ordered work.
The documentation-first commit is `67361fee6440765e130385b2961246a41052b953`.
The integrated implementation checkpoint is
`ee7ace6684b5257ae08d82648e9e2dcb4ceb8986`; code, focused execution and timing
remain separate acceptance boundaries.

| Step | Deliverable and acceptance boundary | Status |
| --- | --- | --- |
| 1 | Permit preemption while a mutex delegation request is merely queued. Before proxy execution, request and acknowledge an origin pin; retain the pin through every executor access and completion/retirement obligation. Do not redesign oversubscription. | Strict one-request candidate passed focused/live checks but lost 42–54% at contended nano points; archived, not promoted. The user approved a small immediately selected group. The isolated four-request window at `6d95745d` passed corrected affected checks, four-family basic, queued scheduling and local/cross-node role cases. Its same-boot 36-point round lost 19.75–39.25% at contended mutex points, so it is not promoted. The circular/inline follow-up `209f8b40` passed affected/live checks and improved contended throughput over that window, but still lost 13.19–27.56% versus pinned `1c86d6d1`; it also remains isolated. Notification prefetch `3e6a623e` passed affected checks but c01/t20 remained 26.73% below the pinned baseline; optional diagnostics at `4a46795e` now show zero cancellation/FULL resumes, more than 99% full-window selection and fewer than 0.1% stalled ACK checks at c01/20 and c01/36. Refill metadata prefetch is the next isolated ablation; the gap remains open. Strict current-request preparation overlap `f9f21188` is also isolated and unexecuted. |
| 2 | One public macro layer for spin and related ordinary APIs, using the compiler clobber wrappers. Retain only required cross-module provider symbols; callable interfaces must have an explicit conventional wrapper and execution contract. | Public raw-clobber spin macros and export reduction implemented at `893c16b5`; ten selected VM checks passed. Their cold path differs from the named DIRECT benchmark shell. The separate 18-observation c01/c08 public/DIRECT comparison completed; single-round results do not establish performance neutrality. |
| 3 | Assess rwlock recursive reads, upgrades and IRQ/BH pairs. Implement only cases with a stated ownership/context contract; distinguish unsupported blocking upgrade from feasible nonblocking conversion. | Local IRQ/BH and trylock APIs plus interrupt-reader bypass implemented at `428e068a`; affected units and live IPI reader probe passed with exact drain and no JIT. Arbitrary task recursive reads, blocking upgrades and NMI use remain unsupported; nonblocking conversion is an exploration, not an exposed API. |
| 4 | One ordinary rwsem API family, with the widest compatible init/read/write/try/signal/downgrade/non-owner/annotation coverage. Explain any delegation eligibility restriction; never let a queued writer bypass a downgraded reader. | Unified ordinary API implemented at `6099baf3`; default/local downgrade and explicit prepared writer eligibility are documented. At `1b186f5d`, API/cancellation/live JIT escape and affected unit/runner checks passed. Changed prepared DIRECT shell was measured in the completed 60-point comparison at `5f96dd5c`; losses remain unresolved after the completed 44-observation frozen-input matched recheck. |
| 5 | Explicitly refuse `CONFIG_PREEMPT_RT`, `CONFIG_DEBUG_MUTEXES`, `CONFIG_DEBUG_LOCK_ALLOC` and lockdep. These configurations are excluded, not an integration milestone. | Shared public-header/provider refusal implemented at `1b186f5d`; the affected VM unit group and supported-configuration provider/probe builds passed. These configurations remain excluded. |
| 6 | Leave rwsem fairness unchanged. The writer reservation phase is distinct from the 1024-body mutex batch limit. | Deferred by user |
| 7 | For delegated mutex-to-spin acquisition, attempt one runtime CAS. On success retain exact nested spin ownership and continue JIT. On contention transfer execution and physical ownership to the original waiter, preserving exclusion, source leases, queue obligations and making the former combiner an immediately delegatable queued waiter. | Maintained `ee7ace66` implements the one-CAS path and scoped physical owner handoff; the corrected `20baf5c2` live probe passed. Full queued role exchange is implemented only on an isolated candidate. The duplicate native-mutex accounting BUG at `2d4ee3df` is preserved as a failed, undrained run. Correction `1c86d6d1` passed 11 affected checks, four-family live basic and all five role cases after the approved reset. Its 60-point nano round completed, but performance acceptance remains open and the candidate is not promoted. |
| 8 | Explain borrowing versus ownership transfer, including long-chain retention and resource bounds. Validate transfer before replacing an existing borrowed route; do not replay an executed prefix or substitute unlock/relock for uninterrupted exclusion. | Ownership guide now distinguishes root transfer from retained multi-owner borrowing and its eight-frame/eight-lock bounds. The first failed-CAS live attempt failed during setup without exercising transfer; the corrected `20baf5c2` owner-handoff probe passed. Five scoped queued-role cases passed at isolated `1c86d6d1`; long-chain qualification and promotion remain pending. |

The user's latest October 29 direction revises step 1: use a long initial pinned
spin period, check scheduling/sleep only after expiry, and maintain at least
eight ready proxy requests without response polling in the ordinary proxy round.
The proposed `READY`/`CLAIMED` arbitration and validation order are recorded in
[the mutex implementation plan](design/mutex_implementation.md#revised-waiter-requirement-october-29).
This supersedes the earlier immediate queued/preemptible requirement; it does
not authorize weakening pin proofs or physical/source/frame retirement. The
more-than-99% spinning target and nano no-regression gate require measurements.
Focused profiling is now the next step because the validated protocol still has a measured throughput gap.

The first [long-spin READY candidate](../bench/results/10.176.26.71/tests/mutex-ready-window-20261029/README.md)
at `43418d5a`, validated through fixture correction `406c679b`, passed all affected
checks and live mutex/rwsem, queued scheduling and six role placements. Its two
instrumented points recorded 100% completion before the initial budget expired,
but the one-round contended mutex measurements lost 26.60–39.89% versus the saved
pinned baseline. It is not promoted. The [batch-gate follow-up](../bench/results/10.176.26.71/tests/mutex-proxy-epoch-20261029/README.md)
at `41d887bd`, validated through `2d6e313b`, passed all 18 selected drivers and
nine live blocks; two instrumented points again completed every wait episode
before expiry. Its 36-point round still lost 17.63–34.72% at contended mutex
points, with additional negative rwsem points. It is not promoted. The
[one-current follow-up](../bench/results/10.176.26.71/tests/mutex-epoch-current-20261029/README.md)
at `14975b6a`, validated through `82bfc100`, passed all 13 selected drivers and
eight live blocks. Both instrumented points completed every wait episode before
expiry; over 99.6% of admitted epochs observed at least eight READY origins.
Its 36-point round still lost 3.05–14.82% at contended mutex points, so it remains
isolated. The [retained-current follow-up](../bench/results/10.176.26.71/tests/mutex-epoch-retained-20261029/README.md)
at `e2b68515`, validated through `2af70f39`, passed all fourteen selected drivers
and eight live blocks. Both instrumented points again met the spin target, but
contended mutex still lost 1.65–14.26%; rwsem also has negative points. It is not
promoted. The [early-READY follow-up](../bench/results/10.176.26.71/tests/mutex-early-ready-20261029/README.md)
at `a46bf63c` passed fifteen selected drivers, both ordinary/diagnostic builds
and eight live blocks. Both counter points meet the scoped spin target, but
contended mutex still lost 2.55–11.53%. It is not promoted. The [consolidated-admission follow-up](../bench/results/10.176.26.71/tests/mutex-admission-once-20261029/README.md)
at `99f38362` passed nine selected drivers, both provider builds and eight live
blocks. Its two counter points meet the helper-episode budget target; nine of ten contended mutex
points remain negative, with changes spanning -11.68% to +1.06%. It is not
promoted. The [matched c01/20 profiling pair](../bench/results/10.176.26.71/tests/mutex-matched-perf-20261029/README.md)
verified unchanged baseline executable text/relocations and all four sessions.
Candidate whole-client instructions per operation increased 42.80%; samples show
additional combiner work and waiting amplification, without establishing parking
or shared owner checks as the cause. Sampling limits remain explicit, and these
instrumented observations are excluded from nano scores.
The [successor READY read hint](../bench/results/10.176.26.71/tests/mutex-ready-prefetch-20261029/README.md)
at `bb3b78e9` passed five selected drivers, both builds and three live blocks,
but all ten contended mutex points remain below the pinned baseline (1.38–11.60%).
It remains isolated. The [exact-phase follow-up](../bench/results/10.176.26.71/tests/mutex-exact-phase-20261029/README.md)
at `ff69c57a` passed twelve selected drivers, both builds and eight live blocks,
but all ten contended mutex points remain below pinned performance (0.17–12.46%).
It is not promoted. The [joint COMPLETE follow-up](../bench/results/10.176.26.71/tests/mutex-complete-joint-20261029/README.md)
at runtime `3232d47c`, validated through `965156ff`, ultimately passed twelve
selected drivers, three builds and eight live blocks. The two failed setup/gate
attempts are preserved. Both counter points meet the scoped spin target, but all
ten contended mutex points still lose 0.98–11.98%; it remains isolated. The
[READY-first waiter follow-up](../bench/results/10.176.26.71/tests/mutex-ready-first-20261029/README.md)
at `2dbcd7af` passed eight selected drivers, two builds and eight live blocks.
The actual initial poll shrank from thirteen to six instructions, with unchanged
state/threshold semantics. Both counter points meet the scoped spin target, but
all ten contended mutex points still lose 0.80–9.82%; it is not promoted. The
no-regression gate remains open. A proposed queue-wide readiness certificate was
reviewed without implementation; reset races and limited expected savings do not
justify weakening exact ownership checks.

The spin and rwlock ordinary atomic sections still require preemption exclusion;
step 1 changes sleeping-lock delegation waiting, not native spin semantics.
The latest long-spin/readiness protocol supersedes permanent queue-wide pinning
as the current development requirement. The strict candidate is archived rather than promoted, so the maintained
implementation still pins published waiters. The latest request permits initial pinned spinning with a bounded scheduling
threshold and a larger ready cohort; it does not authorize indefinite queue-wide
pinning or close the correctness/performance gates.
The [October 29 checkpoint](../bench/results/10.176.26.71/tests/api-semantics-20261029/README.md)
retains the rejected candidate, exact rates, the completed 60-point comparison,
failed transfer setup/normal cleanup, and functional/collector outcomes. The
first thirteen trees and nine follow-up trees are archived with offline
verification. A 44-observation matched recheck completed from frozen baseline/candidate inputs. Rwlock c01/1% losses
persisted at eight and twenty workers (-4.14% and -6.12%); rwsem signs varied.
The corrected failed-CAS owner-handoff probe passed at `20baf5c2`, including
10,006 competing trylocks, zero thefts and exact retirement. It still does not
implement a full queued role exchange. Emitted rwlock fast-path
instructions are unchanged, while its contended path and subsequent code
placement change; neither is a measured explanation for the losses. The isolated
local-unlock/outlined-reader candidate `d9b2c57f` completed 60 observations without
consistent benefit and remains isolated. The separate rollback-first rwlock candidate `233f3f50`, integrated at `1ad2ef7f`,
passed affected units, live IPI and rwlock basic. Its [same-boot 48-observation pair](../bench/results/10.176.26.71/tests/rwlock-rollback-20261029/README.md)
removed the observed c01/1% eight-worker loss, but other points still lost
approximately 3–7%; it remains isolated. The gate-before-context follow-up `99b02076`, tested with the driver correction at `89aac759`, passed six affected checks, live IPI and spin/rwlock basic. Its [24-point round](../bench/results/10.176.26.71/tests/rwlock-gate-first-20261029/README.md) was mixed, including -4.75%/-11.03% at c01/c16 with 1% writes and eight workers versus `1ad2ef7f`; it also remains isolated. No observed single-round increase or completed correctness check closes the no-regression gate.

The [queued-exchange failure record](../bench/results/10.176.26.71/tests/mutex-roleswap-20261029/README.md)
records the exact duplicate-accounting cause, committed correction and preserved
`kdlock-roleswap-failure-20261029` snapshot. The same-kernel/current-disk reset
was explicitly approved and completed on the current disks, with the same
installed kernel and verified new boot `677b7afa-5358-4ece-a650-5f4a4adecd55`.
At `1c86d6d1`, 11 basic/affected unit checks, four-family live basic and all five
role cases passed. The subsequent nano round completed 60 single observations;
[its results](../bench/results/10.176.26.71/tests/mutex-roleswap-20261029/postreset-results.md)
keep the new boot separate from historical comparisons. Mutex c01 at twenty
workers measured 4.590029 Mops/s (+0.14% versus the historical baseline), while
rwlock c16/1% at eight workers measured 8.681424 Mops/s (-19.87%, `NO_JIT`).
The latter and earlier rwlock losses require matched investigation. Cross-boot
single observations cannot establish performance neutrality. The candidate
remains outside `master`. The separate [bounded-window record](../bench/results/10.176.26.71/tests/mutex-pin-window-20261029/README.md)
retains its successful scoped checks and failed performance gate. Its migration-state
probe passed local and actual C2-to-W33 exchange; this does not establish arbitrary
contexts or performance neutrality. The [circular-window record](../bench/results/10.176.26.71/tests/mutex-pin-ring-20261029/README.md)
retains its emitted-code checks, successful scoped validation and remaining loss.
The [notification-prefetch ablation](../bench/results/10.176.26.71/tests/mutex-pin-prefetch-20261029/README.md)
also leaves the performance gate open. The [optional pin diagnostics](../bench/results/10.176.26.71/tests/mutex-pin-diagnostics-20261029/README.md) retain the initial per-CPU module-load failure and its corrected dynamic-storage validation separately from ordinary performance.

Preserve a baseline source identity and matched c01/c16 nano observations before
changing runtime behavior. Use the existing workload bodies, post256, 1024/1024
mutex limits, 1024 spin limit, worker placement, kernel and instrumentation.
Run basic plus affected correctness checks before timing. Compare affected
families at uncontended, local-NUMA and cross-NUMA counts, then check the complete
maintained nano grid. Investigate any loss with matched repeated observations;
do not retain a reproducible regression or describe a noisy one-round tie as
proof of zero regression. Preserve rejected candidates and failures. Real-world
API campaigns, kernel changes/reboots, oversubscription and rwsem fairness are
outside this work.

## Current implementation gaps

The user authorized the [October 30 integration sequence](design/kernel_cs_semantics.md#october-30-implementation-plan-and-acceptance-gates): semantic/function repairs,
one-round nano and bounded syscall comparisons, localized mmap, full selected
kernel object binding, then unchanged mmap1 acceptance. The sequence started
from `acfa33a5`; prior regressed mutex candidates remain unpromoted. The selected
[original-body syscall comparison](../bench/results/10.176.26.71/bench/kernel-api-f7a84065-20261030/README.md)
completed 126 sessions and 63 pairs, with 40 KD gains and 23 losses. Scoped
functional checks passed; performance acceptance, localized mmap and unchanged
mmap1 comparison gates remain open.

The [per-lock native critical-section map](design/kernel_cs_semantics.md) retains
the pre-implementation `acfa33a5` audit. The current candidate implements exact
F3 90 PAUSE lowering, supported native-escape instruction markers that preserve
later image eligibility, stable Native inner/context CALL boundaries, and saved
ordinary spin waiter/executor context checks. Address-guard fallback still
disables the entry. The
[bounded functional record](../bench/results/10.176.26.71/tests/kernel-proxy-functional-20261030/README.md)
records earlier scoped checks; it does not validate every context or selected
bound-object syscall. Cross-function ownership coverage remains limited, and
native MM bodies continue locally on their original task; delegated mmap writers
and prepared teardown are outside the current integration plan.

Typed RDTSC/RDTSCP/CPUID service supports original-task execution followed by
same-image JIT reentry for a sole-outer ABI2 mutex or prepared rwsem writer,
retaining arithmetic flags, budget and exact ownership. Generic Native CALL
fallback still runs the callee and remaining suffix on the waiter; arbitrary
branch-only JIT return is unimplemented. The runtime candidate at
`f7a84065e84474380faa37eeadfdf534abd72a68` has
[recorded focused validation and a 210-point nano comparison](../bench/results/10.176.26.71/bench/continuation-perf-nano-20261030/README.md).
The functional checks passed, but nano performance acceptance remains false.
The user authorized later syscall/MM comparisons on this isolated candidate.
The recorded syscall checks and timing do not close the nano losses or validate
the pending MM comparisons.

| Area | Remaining limit |
| --- | --- |
| Whole-kernel replacement | Loading the provider does not convert kernel objects; each object and all its users require one protocol and lifecycle integration |
| Pinned delegation waiters | Published mutex producers poll with preemption disabled; broad oversubscription/progress redesign is deferred |
| Origin context | Saved ordinary spin context checks and typed original-task instructions do not cover arbitrary IRQ/RCU, accounting or address-space intervals; trusting source does not supply those contracts |
| Native recovery | Generic FULL exits do not restore arbitrary flags or SIMD/FPU state; only the documented instruction-exit paths preserve their declared arithmetic flags |
| Mitigations | Active call-depth tracking is rejected; complete mitigation coverage of handwritten/generated returns remains unvalidated |
| Image replacement | Mutex images are immutable; ordinary spin/rwlock entries may still replace code in place until an immutable transition |
| Source and object lifetime | Session source pins and image leases do not retain arbitrary data/lock allocations; stop/join, exact owners, ACKs and frame drain remain required |
| Fairness | Bounded batching and NUMA grouping do not establish starvation freedom or a maximum acquisition latency |
| API coverage | RT, debug mutexes and lockdep configurations are refused at build time; ww_mutex, translated rwlock/rwsem acquisition, arbitrary mixed nesting and NMI use remain outside support. Explicit local spin/rwlock IRQ/BH pairs have their own context contract. |
| Decoder/backend coverage | Source trust bypasses semantic proofs, not missing instruction lowering, text, return routing or runtime protocol support |

Production uses `trusted_source=True`, including kernel and module loops and
ordinary string callees. Earlier context/value/input proofs and string models
are optional checked regression or historical compatibility code, not pending
production admission work. Do not restore those checks as an implicit default.
See [translation policy](design/admission.md) and [register ABI](JIT_REGISTER_ABI.md).

## MM and performance gaps

The ordinary `kdlock1` kernel keeps the mmap adapter disabled. The separate
actual shared-MM comparison completed 42 points; Native was faster at all 21
worker counts. At 60 workers KD achieved 0.0436× Native throughput. A measured
cause or accepted optimization has not been established on the Linux 7 cohort.

The [unchanged upstream mmap1 runner](../bench/mmap1/README.md) is implemented
for `mmap1_threads` and the separate `mmap1_processes` control, including frozen
executable reuse and actual worker/mm identity checks. Its matched Native/KD
application comparison remains pending. A generic actual-backend minor-fault
throughput driver is still needed. Existing device mappings and private-backing
fault cycles are different workloads. Preserve native MM bodies and original-task
execution; operation-specific delegation and prepared teardown remain retired.

Favorable nano points do not establish a universal gain. Current repeated
confirmation, uncertainty estimates and performance-neutral integration remain
open. The October 28 user-selected KD mutex default is 1024/1024, removing the
earlier count-based local cutoff. Recorded 768-boundary observations remain
separate; performance under the new default needs measurement. New tail-latency
collection remains deferred.

## Retained failures

The old checked taskname preparation, the original trusted mixed-taskname timed
failure, zero-point telemetry preflight, initial enabled-MM contention witness,
and strict unscored taskname `NO_JIT` control remain failed. Later prepared,
diagnostic or timed cohorts do not change their verdicts. Their exact counts,
causes and cleanup receipts are linked from [validation](VALIDATION.md).

Linux 6.1 performance regressions, stopped three-repeat matrices and rejected
protocol experiments remain in [history](history/README.md) and frozen results.
They are not an instruction to resume old-kernel adaptation or repeat expired
campaign plans. Use [basic plus affected checks](../tests/README.md) for a concrete
change; full suites and new performance campaigns need their own requested scope.
