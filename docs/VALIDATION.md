# Historical validation index

Current behavior lives in [DESIGN](DESIGN.md); commands and fresh evidence live in
[tests](../tests/README.md) and [benchmarks](../bench/README.md). Historical passes
apply only to their frozen source and do not combine into a current full pass.
Known failures and deferrals remain in [TODO](TODO.md).

## Completed optimization phase

The phase closed on 2026-10-09. Its
[final report](../bench/tclock_compare/results/20261008-protocol-simplification/README.md)
contains 540 baseline sessions at all 15 requested thread counts and a complete
2,286-session trial audit. Source, ELF, generated-code, business-result,
execution-witness and drain checks passed. Five targeted guest test groups and
an ordinary UBSAN-off `W=1` build passed; existing objtool warnings remain.
These results do not establish a full-suite pass or performance parity.

The final source measurement is frozen `d2868e3`; evidence and documentation were
committed as `cb1629a`. The later closeout changes documentation and removes
superseded reports and derived files. It does not execute new benchmarks or
change runtime behavior.

## Closeout maintenance

Closeout removed 32 superseded report, chart and data artifacts. Their exact
bytes remain at `cb1629a`; [benchmark history](../bench/tclock_compare/results/HISTORY.md)
provides fixed retrieval paths. The open performance plan was replaced by
[performance status](PERFORMANCE.md).

Two obsolete extracted copies under `bench/.tmp/protocol-simplify-20261008/`
(`export` and `export-rejected-memory-1009`) were removed after every regular
file and logical symlink matched the retained canonical guest archive. They
contained about 2.40 GiB of duplicate file data. The current
`export-complete-restored-1009`, all raw archives and kernel provenance bundles
remain. Seven regenerable cache directories and the ignored daemon executable
were also removed; no host daemon was running.
Five unused historical directory trees containing only empty directories were
removed after confirming they had no tracked files or current source references.

The local cleanup inventory and exact preservation proof are under
`bench/.tmp/closeout-20261009/`. Existing unrelated edits were preserved.
Documentation links, fixed Git records, final-report hashes and the staged diff
were checked. No runtime code changed and no build/test/benchmark was rerun.

Older reports and rejected experiments are indexed in
[benchmark history](../bench/tclock_compare/results/HISTORY.md). Raw ignored/guest
archives are preserved; a new checkout does not include them. Offline consistency
checks are not fresh execution or authentication of every historical artifact.

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
