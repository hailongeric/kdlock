# Validation index

[Tests](../tests/README.md) owns check selection and commands;
[operations](AGENTS.md) owns the verified guest environment, recovery and drain.
Receipts apply to the source, kernel, boot policy and topology they record.
Publication, actual JIT execution and performance acceptance are separate results.
Known failures remain in [TODO](TODO.md).

## Current mutex verification

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
