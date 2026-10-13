# Validation index

[Tests](../tests/README.md) owns check selection and commands;
[operations](AGENTS.md) owns the verified guest environment, recovery and drain.
Receipts apply to the source, kernel, boot policy and topology they record.
Publication, actual JIT execution and performance acceptance are separate results.
Known failures remain in [TODO](TODO.md).

## Current mutex verification

The [2026-10-14 owned-protocol receipt](../bench/results/10.176.26.71/bench/mutex_owned/20261014-hybrid/validation.json)
records the unified outcome/grant protocol, optional bounded OSQ preflight and
separate capture-first/prepared entries. Final verification includes two basic
fixtures and nine affected groups, core/preflight/OSQ/queue mutation checks,
73 runner checks and 17 study-auditor checks. Both caller policies execute real
JIT continuations; six live nested/early FULL cases complete owner acknowledgments.
Cooling and queued-work probes pass with polling budgets 0, 1024 and 4096.
The failed initial mutation-driver attempt and its narrowly corrected retry
remain archived separately.

The [report](../bench/results/10.176.26.71/bench/mutex_owned/20261014-hybrid/README.md)
audits 708 scored sessions and 72 unscored diagnostics. Every audited benchmark
sample has correct results, worker progress and final drain. The final finite
and refill grids pass their same-policy higher-thread regression gates, but fail
the primary 97% Native target. Builds, warnings, source identities, recovery
snapshot, kernel identity and final idle state remain explicit in the receipt.
No full suite, other-workload, RT/debug-kernel or 64-worker acceptance is claimed.

## Earlier owned-mutex verification

The [owned-mutex receipt](../bench/results/10.176.26.71/bench/mutex_owned/20261013/validation.json)
records the 32-byte KD-owned protocol, final ordinary-unlock fix, seven core
mutations, sixteen refill FIFO mutations, 80 runner/auditor tests and live
nested/early FULL continuation at 4/16 workers. A final legacy JIT compatibility
smoke returns 414,157/7,964,008 bodies at 4/16 workers on the same provider,
with explicit original owner/list/OSQ drain. Earlier affected admission,
entry/outer ABI, parking/cooling and owner/ACK receipts retain their own source
identities. Refilling repeats only its affected subset. W=1 builds pass with
warnings; selected earlier fixture-source gaps remain explicit. The
[report](../bench/results/10.176.26.71/bench/mutex_owned/20261013/README.md)
retains the archived failures, 426 scored sessions and 114 separate diagnostics.
Every audited sample progresses and drains, but no candidate meets performance
acceptance. No full suite, other-workload or 64-worker acceptance is claimed.

## Earlier mutex protocol verification

The [64-round protocol receipt](../bench/results/10.176.26.71/bench/mutex_protocol/20261013/validation.json)
and separate [eight-round receipt](../bench/results/10.176.26.71/bench/mutex_protocol/20261013-post8/validation.json)
retain basic and affected frame/cookie/ABI, admission, task-reference, parking,
terminal and owner/ACK checks. They distinguish compiled JIT fixtures, live
resource probes and returned benchmark bodies. The reports preserve rejected
frame/layout/capture/epoch candidates and initial corrected harness failures.
Correct results and drain do not establish performance acceptance: no candidate
meets the full 97% target. No full suite or other-workload acceptance was run.

## Earlier optimistic-spin verification

The [optimistic-spin receipt](../bench/results/10.176.26.71/bench/mutex_optimistic/20261013/validation.json)
records six rejected retry/OSQ candidates, 369 audited performance sessions,
affected fixtures, 62 runner/auditor checks and live parking/cooling and owner/ACK
probes. The accepted provider is restored to `9b76719`; the retained workload
drain check passes two basic fixtures, its OSQ-on/off state fixture and a separate
single-round Native/TCLock/KD live check. The
[report](../bench/results/10.176.26.71/bench/mutex_optimistic/20261013/README.md)
distinguishes candidate tests, restored-source verification and performance gates.
The 97% Native target remains unmet; no full suite or other-workload acceptance
was run.

## Earlier cost-study verification

The [c01 cost-study receipt](../bench/results/10.176.26.71/bench/mutex_c01_cost/20261013/validation.json)
records the successor-prefetch checks, live resource probes and exact candidate
sources. The [report](../bench/results/10.176.26.71/bench/mutex_c01_cost/20261013/README.md)
keeps the fresh three-way comparison, separate diagnostics and rejected
experiments. The 97% Native target remains unmet; no other-workload acceptance
or full test suite was run.

## Earlier admission verification

The [2026-10-13 admission receipt](../bench/results/10.176.26.71/bench/mutex_admission/20261013/validation.json)
records 14 basic/affected groups, 54 runner tests and six acceptance-auditor tests,
normal and SELFTEST builds, plus live cooling/parking and cross-NUMA owner/ACK
checks. All 543 study sessions have correct results, worker progress and drain.
The [performance report](../bench/results/10.176.26.71/bench/mutex_admission/20261013/README.md)
keeps 48 diagnostics unscored and all eight rejected thresholds. The default
remains 256; higher-thread regression gates pass but the 97% Native target does
not. No full suite or other-workload acceptance was run.

## Earlier blocking-only verification

The [blocking-only mutex receipt](../bench/results/10.176.26.71/tests/mutex-blocking-only-20261012/validation.json)
records seven basic/affected groups, 101 context-admission cases and 87 runner/report
tests on 2026-10-12. Normal and SELFTEST `W=1` builds had no mutex wait-mode selector.
The scheduler probe passed with polling budgets 0, 1024 and 4096. The task/ACK
probe passed across NUMA nodes. A 16-worker/eight-cacheline functional run returned
308,209 JIT bodies across 320,000 operations and fully drained. The receipt retains
build warnings, the initial corrected test assumptions, archive hashes and exact
working-tree inputs. No full suite or new performance matrix was run.

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
