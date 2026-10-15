# Validation index

[Tests](../tests/README.md) owns check selection and commands;
[operations](AGENTS.md) owns the verified guest environment, recovery and drain.
Receipts apply to their recorded source, kernel, boot policy and topology.
Publication, actual JIT execution and performance acceptance are separate results.
Known failures remain in [TODO](TODO.md). New runs use exactly CPUs 0–63:
NUMA node 0 has CPUs 0–31 and node 1 has CPUs 32–63, with no extra vCPUs or
unused spare CPU. Historical receipts retain their original topology; they
do not authorize reusing a superseded placement.

<a id="current-owned-protocol-verification"></a>

## Recorded owned-protocol verification

The owned ABI4/reuse-32 extension at `585335b` has a source-specific
[verification receipt](../bench/results/10.176.26.71/bench/mutex_owned/20261014-linux-local/validation.json):
basic and affected unit/mutation checks, live queued cooling/task probes,
returned JIT with forced FULL/owner ACKs, normal build and final idle state.
The [c01/post64 1–8-worker result](PERFORMANCE.md#active-c01-18-worker-study)
passes its independent performance screen and both confirmations. These are
source-specific checks, not a full-suite or general fairness result.

Later source adds immutable owned-image generations and opt-in origin-readiness
and NUMA policies. The [test selection guide](../tests/README.md#unit-checks)
lists their affected checks, and the
[policy comparison](../bench/tclock_compare/README.md#owned-origin-and-numa-comparison)
requires fresh controls. The receipts below do not validate those later additions.

The earlier `d8d14a1`
[protocol receipt](../bench/results/10.176.26.71/bench/mutex_owned/20261014-hybrid/validation.json)
records affected unit/mutation checks, real JIT/FULL acknowledgments and queued
cooling. The [later restoration receipt](../bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/validation.json)
separately records restoration, normal build and idle state after the rejected
native-first experiment; it is not a fresh performance run or a full-suite pass.

That acceptance is limited to 1–8 workers on the regular 64-vCPU boot. It does
not revise historical failures or accept other payloads. The later broader
measurement below retains a separate topology and acceptance verdict.

## Full-grid c01 verification

The [2026-10-14 full-grid audit](../bench/results/10.176.26.71/bench/mutex_owned/20261014-full-grid/verification.json)
checks 198 Native/TCLock/KD samples at 1–8 workers in steps of one and 12–64 in
steps of four. Every sample has correct results, progress by every worker and
complete drain. The audit recomputes all warmed peaks and checks frozen source,
binary and JIT identities. All 63 multithreaded KD sessions return JIT, while at
least 99.5% of each KD sample executes SELF. Plain runs record no FULL
continuations; they do not replace the separate nested/FULL/ACK tests above.

The [report and closeout](../bench/results/10.176.26.71/bench/mutex_owned/20261014-full-grid/README.md)
record the unchanged implementation, temporary 66-vCPU topology, physical
collector contention at 64 workers and restoration of the regular 64-vCPU boot.
The new regular snapshot was `normal64-after-mutex-owned-full-20261014`.
This is one three-round comparison block: the three-worker peak misses the
97% Native target, and no broader confirmation blocks or new unit suite were run.

## Archived native-first mutex verification

The [native-first receipt](../bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/validation.json)
ties ABI4, owner spinning, leaf unlock and guarded-release checks to each frozen
candidate. It preserves corrected fixture failures, actual JIT/FULL/ACK runs,
queued cooling and the failed profiler load. The implementation is archived at
`9a5305e`; [performance acceptance failed](../bench/results/10.176.26.71/bench/mutex_owned/20261014-native-first/README.md).
These historical checks do not replace the new source-specific receipt above.

## Earlier mutex receipts

The linked receipts own exact test counts, source hashes, build warnings and
inherited-versus-rerun coverage. No row implies a current full-project pass.

| Scope | Receipt and limits |
| --- | --- |
| <a id="earlier-owned-mutex-verification"></a>Owned redesign, 2026-10-13 | [Receipt](../bench/results/10.176.26.71/bench/mutex_owned/20261013/validation.json): core/refill, outer/FULL/ACK and legacy compatibility; earlier-source coverage remains distinct. |
| <a id="earlier-mutex-protocol-verification"></a>Legacy protocol trials, 2026-10-13 | [Receipt](../bench/results/10.176.26.71/bench/mutex_protocol/20261013/validation.json): frame/cookie/ABI, admission, task references, parking and terminal/owner checks; candidates rejected on performance. |
| <a id="earlier-optimistic-spin-verification"></a>Legacy optimistic retry, 2026-10-13 | [Receipt](../bench/results/10.176.26.71/bench/mutex_optimistic/20261013/validation.json): rejected candidates and restored-provider drain verification kept separate. |
| <a id="earlier-cost-study-verification"></a>Cost study, 2026-10-13 | [Receipt](../bench/results/10.176.26.71/bench/mutex_c01_cost/20261013/validation.json): prefetch/counter checks and live resource probes; exact candidate sources retained. |
| <a id="earlier-admission-verification"></a>Admission study, 2026-10-13 | [Receipt](../bench/results/10.176.26.71/bench/mutex_admission/20261013/validation.json): affected admission/caller checks, parking/cooling and owner/ACK; no broader workload acceptance. |
| <a id="earlier-blocking-only-verification"></a>Blocking policy, 2026-10-12 | [Receipt](../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json): scheduler/task probes and contended JIT; historical oversubscription scenarios are not thereby rerun. |

## Historical receipts

| Scope | Evidence |
| --- | --- |
| Destination host, including migration, 64-vCPU setup and later comparisons | [10.176.26.71 index](../bench/results/10.176.26.71/README.md) |
| Original-host spin/mutex/rwlock measurements | [380G10 index](../bench/results/380G10/README.md) |
| Rwlock ABI3 correctness, 2026-10-10 | [Frozen verification](https://github.com/hailongeric/kdlock/blob/792db45f28d775da667572ebd1e2080025cfd88a/tests/kernel/rwlock/README.md#abi3-verification-on-2026-10-10) |
| Original-host mandatory mutex JIT, 2026-10-08 | [Frozen verification](https://github.com/hailongeric/kdlock/blob/792db45f28d775da667572ebd1e2080025cfd88a/tests/README.md#mandatory-mutex-jit-2026-10-08) |
| Optimization closeout and duplicate-artifact cleanup, 2026-10-09 | [Frozen maintenance record](https://github.com/hailongeric/kdlock/blob/792db45f28d775da667572ebd1e2080025cfd88a/docs/VALIDATION.md#closeout-maintenance) |
| Unimplemented outlined/native-register proposals | [Archived design note](https://github.com/hailongeric/kdlock/blob/792db45f28d775da667572ebd1e2080025cfd88a/docs/design/protocol_simplification.md) |

Raw archives include failed and interrupted runs. A fresh checkout contains
compact reports, not those ignored archives. Offline hash/consistency checks do
not execute code again or establish a current full-project pass.

## Repository maintenance

The [2026-10-15 documentation and file cleanup](../bench/results/380G10/tests/documentation-cleanup-20261015.json)
records the current guide/command/link audit, generated-cache removal and three
archive-backed duplicate extractions removed from the source host. File bytes,
permissions and logical symlink destinations were checked before deletion;
canonical archives and differing copies remain. No compilation, executable tests
or benchmarks were run for this cleanup.

The [2026-10-15 documentation refresh](../bench/results/380G10/tests/documentation-refresh-20261015.json)
records source-host static link/anchor, option/default, result-table and Git
inventory checks. It updates maintained guides to the owned protocol and the
full-grid evidence, preserving historical reports and frozen worktrees. It
contains no new compilation, kernel tests or performance measurements.

The [2026-10-12 documentation cleanup](../bench/results/380G10/tests/documentation-cleanup-20261012.json)
records static document/CLI checks, removed empty reports and the byte/symlink
proof for four redundant extracted copies. Their canonical archives remain
available. This source-host maintenance record contains no new execution results.

## Fixed records

The full earlier index is preserved at commit
[17f146e](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md).
Read locally with `git show 17f146e:docs/VALIDATION.md`. The stable anchors below
retain incoming references without duplicating the old investigations.

| Topic | Evidence |
| --- | --- |
| <a id="mutex-oversubscription-assessment"></a>Mutex Oversubscription Assessment | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-oversubscription-assessment) |
| <a id="context-symbol-matching"></a>Context-Symbol Matching | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#context-symbol-matching) |
| <a id="main-plan-acceptance-audit"></a>Main-Plan Acceptance Audit | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#main-plan-acceptance-audit) |
| <a id="dynamic-pointer-screening-gap"></a>Dynamic Pointer Screening Gap | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#dynamic-pointer-screening-gap) |
| <a id="real-mutex-stack-mutation"></a>Real Mutex Stack Mutation | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#real-mutex-stack-mutation) |
| <a id="mutex-control-stack-check"></a>Mutex Control Stack Check | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#mutex-control-stack-check) |
| <a id="source-and-hook-lifetime-review"></a>Source And Hook Lifetime Review | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#source-and-hook-lifetime-review) |
| <a id="native-registration-phase-guard"></a>Native Registration Phase Guard | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#native-registration-phase-guard) |
| <a id="captured-kernel-baseline"></a>Captured Kernel Baseline | [Fixed record](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#captured-kernel-baseline) |
