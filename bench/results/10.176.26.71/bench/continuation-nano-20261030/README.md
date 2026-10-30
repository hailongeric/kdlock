# Continuation candidate nano evidence: 8617e97c

The completed current campaign contains **210 KD points, one measurement round per point**. Its archive/source/provider/settings audit passes. The no-regression requirement does **not** pass: compared separately with `acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f`, 112 points lose either metric; compared with `8446f4ecb08816380a4c233197a8ce5e4d333aac`, 126 do. These are observed single-round differences, not causal estimates. No negative point is dismissed or removed.

The measured current source is `8617e97c02432a7c0b931aa8263d5edd0f6eb5b8`, before the subsequent performance correction. This report does not claim that the correction has been built, tested or measured. Current data are KD-only; Native/TCLock results from the earlier 8446 campaign are historical and are not relabeled as current competitors.

`c01` and `c16` mean 1 and 16 cachelines. `w1`, `w20` and `w100` mean 1%, 20% and 100% writes. Workers are 1–8, then 12–60 in steps of four. Each point uses the matched 2-second measured interval after 48,000 warmup iterations per worker. CPUs and NUMA mappings, call shells, instrumentation and all matched settings are verified per point. Workers through 32 occupy node 0; 36 and above span nodes. Raw captured identifiers remain unchanged in receipts.

| Reference | Whole-rate losses | Peak-rate losses | Either metric | Matched/scored |
| --- | ---: | ---: | ---: | ---: |
| acfa33a5 | 107 | 106 | 112 | 210/210 |
| 8446f4ec | 120 | 120 | 126 | 210/210 |

Strict host timing qualification remains false. Endpoint identity and the archive audit do not establish uninterrupted host isolation or explain the losses. Functional completion, source identity and performance acceptance remain separate. [validation.json](validation.json) preserves this distinction and exact invocation paths; [current/campaign.json](current/campaign.json) records endpoints, topology, kernel and archives.

## Profile and worker detail

Each profile has 21 points. Cells count whole/peak/either losses; no rates are averaged across workers or sources.

| Workload | vs acfa33a5 | vs 8446f4ec |
| --- | ---: | ---: |
| mutex c01 w100 | 12/13/13 | 16/15/16 |
| mutex c16 w100 | 13/15/15 | 16/16/16 |
| rwsem c01 w1 | 7/7/7 | 13/13/14 |
| rwsem c01 w20 | 10/9/10 | 13/14/15 |
| rwsem c16 w1 | 10/9/10 | 9/9/9 |
| rwsem c16 w20 | 7/6/7 | 7/9/9 |
| rwlock c01 w1 | 12/11/12 | 11/9/11 |
| rwlock c01 w20 | 16/16/17 | 15/15/15 |
| rwlock c16 w1 | 9/9/10 | 9/9/10 |
| rwlock c16 w20 | 11/11/11 | 11/11/11 |

Whole-rate changes at the specifically requested worker counts are below. The two references are independent comparisons of the same current point.

| Workload | vs acfa: 20 / 32 / 60 | vs 8446: 20 / 32 / 60 |
| --- | ---: | ---: |
| mutex c01 w100 | -0.18% / -4.68% / +0.13% | -2.66% / -4.55% / -0.36% |
| mutex c16 w100 | +3.32% / -3.20% / -0.22% | +1.80% / -5.70% / -2.34% |
| rwsem c01 w1 | +0.53% / +0.36% / +0.28% | -0.18% / -1.07% / +1.89% |
| rwsem c01 w20 | +0.92% / +0.55% / +1.68% | +1.52% / +1.90% / -1.70% |
| rwsem c16 w1 | +7.17% / +4.06% / +1.52% | +0.23% / +1.52% / +1.60% |
| rwsem c16 w20 | -3.49% / -0.54% / -0.96% | -1.17% / +0.34% / -0.91% |
| rwlock c01 w1 | -1.56% / +0.96% / +2.16% | -3.49% / +3.94% / +0.50% |
| rwlock c01 w20 | -1.85% / -2.20% / +2.34% | -1.90% / +3.34% / +3.89% |
| rwlock c16 w1 | -1.43% / +1.22% / -2.38% | -3.11% / +0.65% / -1.04% |
| rwlock c16 w20 | -1.91% / -2.78% / -0.20% | +1.17% / -1.09% / -0.26% |

All worker coordinates and both metrics are retained in [vs-acfa/points.csv](vs-acfa/points.csv) and [vs-8446/points.csv](vs-8446/points.csv). [analysis/all-points.csv](analysis/all-points.csv) adds actual JIT counts/shares. [analysis/measured-summary.json](analysis/measured-summary.json) gives exact loss counts for each worker, profile, cohort and JIT transition.

Whole-rate loss magnitudes are descriptive bands, not tolerances: **all negative values remain losses**.

| Whole-rate loss | vs acfa | vs 8446 |
| --- | ---: | ---: |
| Greater than 0, below 1% | 43 | 34 |
| At least 1%, below 5% | 41 | 62 |
| At least 5%, below 10% | 13 | 19 |
| At least 10% | 10 | 5 |

The five largest losses against 8446 are rwsem c01 w1/7 workers (−28.81%), mutex c01 w100/4 (−20.09%), rwlock c16 w1/5 (−18.60%), rwlock c01 w1/7 (−15.03%), and rwlock c01 w20/8 (−11.80%). Four are NO_JIT→NO_JIT. Against acfa the largest is again rwsem c01 w1/7 (−29.18%). Every ≥5% whole-rate loss is retained with exact coordinates in [analysis/whole-losses-at-least-5-percent.csv](analysis/whole-losses-at-least-5-percent.csv).

The worker cohorts 1–8, 12–32 and 36–60 contain 80, 60 and 70 points. Their whole-rate loss counts are respectively 43/32/32 vs acfa and 41/38/41 vs 8446; counts of losses ≥5% are 10/10/3 and 8/13/3. Thus large losses concentrate more at low/middle counts, while the cross-NUMA cohort still contains numerous negative points. This is a count of observations, not a pooled performance rate.

## JIT execution and interpretation

The current run has 130 RETURNED_JIT points and 80 NO_JIT points, with no PARTIAL_JIT points. Against 8446, 41 of 79 NO_JIT→NO_JIT points and 78 of 129 RETURNED_JIT→RETURNED_JIT points lose whole rate. One RETURNED_JIT→NO_JIT point loses; one NO_JIT→RETURNED_JIT point does not. Against acfa, the corresponding stable-class loss counts are 41/78 and 66/129. All three changed-class points vs acfa improve their observed whole rate. Exact changes are in [analysis/changed-execution-class.csv](analysis/changed-execution-class.csv).

RETURNED_JIT means at least one observed completed JIT body, not that most operations delegated. In mutex c01 w100/4, JIT completion share rises from 0.193% at 8446 to 0.430%, while whole rate drops 20.09%. In mutex c16 w100/12, the share remains about 99.44%→99.42% while rate falls 8.60%; at 16 and 32 workers, shares remain about 99.4% while rates fall 6.79% and 5.70%. The regressions therefore span sparse and sustained JIT execution. They are not explained merely by fewer points carrying a returned-JIT classification.

NO_JIT is not evidence that translation ran asynchronously during timing. In the unchanged `bench/rwlock_compare/session.py`, preparation requires NORMAL publication and stops/reaps the daemon before warmup (lines202–211); measurement requires publication with zero writers before release (lines238–247) and checks it afterward (263–267). The need for an entry is independent of worker count (34–37). `require_jit` is false for this matrix, so a published image with no measured returned body is retained. This audit does not establish why each particular point failed to execute a JIT body.

## Actual provider code identity

[analysis/actual-provider-identity.json](analysis/actual-provider-identity.json) binds all ten measured provider ELFs to their archive hashes. Every allocated section, including all executable bytes and NOBITS sizes/alignment, matches the earlier unit provider except `.note.gnu.build-id`. All **8,740 allocated-target relocation records** match after resolving symbol identity, section, value, size, type and addend. The unit provider SHA256 is `e602695d23676fa0e05f467ff92e23abe25b373d2f8792449af23d679f02c33d`; current `.text` is 134,694 bytes, SHA256 `5f9f0f0761376034f5d5a41d2ae8405201baa0980b169510ebb4a0aacc13ecb2`. Full ELF hashes differ; runtime load addresses and cache behavior are not proved equal.

This extends the prior static inspection to the actual measured code. [binary-inspection/comparison.json](binary-inspection/comparison.json) and retained disassemblies show:

- All 19 inspected rwsem API/helper instruction bodies are identical before relocation across acfa, 8446 and 8617. This does not make the entire writer path identical: it calls the shared mutex machinery.
- `__kd_mutex_lock_slowpath` grows 1119→1170 bytes from 8446 to 8617. The repeated PAUSE/locked-node poll is unchanged, but ordinary `native_resume==0` handling changes from fall-through to a taken branch. The nonzero path now distinguishes instruction service. This is a concrete candidate cost, not a measured attribution.
- `run_combiner` has the same normalized instructions in 8446 and 8617, retaining a 208-byte `kd_spin_batch`, 0x120-byte stack reservation and 25-qword prefix clear. acfa used 200, 0x110 and 24. Context capture still runs after generic execution even when the result terminates the batch and its refreshed value has no consumer.
- `kd_exe_dispatch` shrinks 12229→12016 bytes from 8446 to 8617, while total provider text grows 130009→134694 and functions move. This does not establish an instruction-cache cause. `kd_mutex_run_combiner` retains the same normalized instructions.

No changed mutex queue/parking mechanism explains these observations from source. The local rwsem code identity and stable spin instructions also prevent attributing all recent losses to newly added instructions in those functions. Generated critical-section image bytes and dynamic branch/hardware event rates have not been compared here.

## Bounded next candidate

The following three small changes target actual code/storage costs while retaining the context and lifetime protocol. They are hypotheses to validate, not recovered performance:

1. Mark the nonzero `native_resume` branch `unlikely()` in `kernel_module/mutex/waiter.inc:62`. This requests normal zero-result fall-through; verify the rebuilt ELF actually restores it. Leave the inner PAUSE loop, instruction-service rearm/ACK, repeated state reads and owner routing untouched. Broad mutex losses (32 of 42 whole-rate points vs 8446) make this the most direct new-generation target; it cannot explain or repair all rwlock/read-heavy negatives by itself.
2. In `kernel_module/spin/combiner.inc`, suppress executor-context refresh only after NO_RUN, RUN_ERROR or released outer ownership, which terminate before the next root check. Retain refresh on every nonterminal generic return, including changed IRQ/preemption context before another root. The saved-waiter compatibility check remains mandatory.
3. Repack the local spin batch control fields with a `u16 counter` before `u8 proxy_context`; the enforced 1..1024 cap fits. Verify that the built batch returns to 200 bytes and that stack/clear size actually improve. Keep all counters, membership and NUMA boundaries semantically identical.

The latter two address overhead already present at 8446; they do not identify the cause of the 8617-vs-8446 loss. If timed together, the result evaluates the bundle and cannot isolate each contribution. Run basic plus affected ownership/service/context/queue checks on the VM, inspect the resulting ELF, then use separately identified one-round matched measurements. Retain every remaining negative; a functional pass or smaller binary does not meet nano acceptance.

## Functional prerequisites and reproduction

[prerequisites/unit.json](prerequisites/unit.json) records the successful current provider build and three fresh checks. It explicitly reuses 14 previously passed checks from `28d479d4de96cf038829176124abb29039f7ff19`, after comparing all 5,864 tracked inputs and allowing only the result README and context-format correction to `observation.patch`. The prior overall failed receipt remains failed: its provider preparation failed after the passing checks. This is bounded reuse, not a claim that the full set reran at 8617.

Exact basic, origin instruction service, prepared rwsem writer and mixed mutex→spin owner/result receipts are copied under [prerequisites/](prerequisites/), together with the three detailed sessions. Basic remains linked to its original live campaign; the later live modes reference it by exact path/hash and are not relabeled as fresh basic runs. The original pre-child origin host-admission failure is preserved as `failed-origin-pre-child-admission-owner.json`; it is not a kernel/test execution failure or a pass.

[receipts/](receipts/) retains the exact run/archive owners, archive index and host endpoint captures. The raw archives remain separately retained under `bench/results/10.176.26.71/raw/bench/continuation-nano-8617e97c-20261030/`. [copied-evidence.json](copied-evidence.json) records exact source paths, byte counts and hashes of the copied evidence.

The source-host offline audit is preserved in [tools/audit_compare.py](tools/audit_compare.py), with `nano_core.py` and `archive_helpers.py`. Its exact original arguments are in `validation.json`; select a fresh output directory when reproducing. It checks complete archives and provider preparation from frozen Git blobs, retains both historical comparisons independently, and never executes archived source or ELF files. Its trusted checkout oracle is separately hash-bound. [tools/findings.py](tools/findings.py) reads that completed output plus the retained unit ELF to regenerate the detail tables and provider equivalence checks; exact arguments and tool/input hashes are in [analysis/findings-receipt.json](analysis/findings-receipt.json). These are host-only offline inspections, not newly executed benchmarks or unit tests.
