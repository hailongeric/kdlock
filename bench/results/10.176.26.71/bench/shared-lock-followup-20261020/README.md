# Shared-lock comparison after mutex correctness restoration

Status: rwsem collection, verification and archival complete; rwlock reference
running. The rwsem post-run host-thread check failed and acceptance is open. This stage
follows the validated `a768361` mutex restoration, recorded in `f48b90e`.
The seven public-mutex performance regressions and the
environment/execution-class/latency gaps remain
[explicitly unresolved](../mutex-regression-diagnosis-20261020/README.md).
This stage cannot establish acceptance of that separate comparison.

All builds and measurements use the same current recovery VM and setup as the
2026-10-20 mutex reruns: `root@10.176.26.71:2222`, 64 vCPUs, 24 GiB,
kernel `6.1.159-kdclobber2`, boot `b65f0205-c8f9-4385-8b13-039cbce243a6`,
workers on CPU prefixes and collector 63. The current pinned translation
environment is `/root/kdlock-translation-venv-20261019/bin/python3`.
The source host `380G10` remains the only writer; tests run serially.

The comparison geometry comes from the prior
[rwsem final grid and separate rwlock reference](../rwsem-optimization-20261018/README.md):

| Collection | Controls | Workloads and mixes | Worker counts | Sessions |
| --- | --- | --- | --- | ---: |
| Sleeping rwsem | Linux Native and KD | c01, c08, RCUHT; 1% and 20% writes | 1–8, 12–60 by four | 756 |
| Spinning rwlock reference | Linux Native, TCLock and KD | Same payloads and mixes | 1, 8, 32, 36, 60 | 270 |

The selected source is `f48b90e`; all 497 manifest entries are byte-identical to
the restored `a768361` validation inputs. The new commits add evidence and
orchestration, without changing those runtime/collector inputs.

Each point keeps three repetitions, two-second measurements, 48,000 warmup
iterations per worker, four post-work rounds, 300 ms peak/settling windows and
10 ms samples. NUMA policy, batch 1024, entry ratio 2 and UBSAN-off provider
settings remain explicit. The unchanged runner alternates backend order.
There is no sleeping TCLock rwsem backend. No spinning control substitutes for
one, and no real mmap/fault integration is claimed.

These are fresh within-stage comparisons, with separately frozen source and
binaries for each family. The 2026-10-18 results retain their historical source
and interpreter-path identities; they are not pooled or silently treated as
identical inputs. The current runner's 26 focused checks passed at `a4eb4eb`,
and every file under `bench/rwlock_compare/` remains byte-identical. The
restoration's basic, affected and four live checks cover the current mutex
entry. No additional full correctness suite is selected.

The [task plan](task-plan.json) retains the historical argument lists except
for the new output destinations, with current source/interpreter identities.
The previously validated serial supervisor is reused without modification.
A fresh preflight checks the exact current host against the pinned original
2026-10-20 environment, including the QEMU thread set, and captures the real
recovery snapshot before each family. Failures stop further work; a timeout
does not prove drain. Post-run placement differences, missing execution classes
and benchmark failures remain visible. No latency or runtime-interference
measurement is added to these throughput runs.

Planned guest evidence is
`/root/kdlock-evidence/10.176.26.71/bench/shared-lock-followup-20261020/`.
Each family must complete, drain and preserve its frozen inputs before its
functional coverage can be reported as complete. Archive review must retain
failed environment checks separately from source, arithmetic and outcome checks.

`rwsem-preflight-1` passed with the host receipt captured at
2026-10-20 15:32:23.798415 UTC: QEMU PID 257489 and the original 67-thread set,
frequency policy, NUMA memory bindings, CPU pins, boot, pinned dependencies and
actual recovery snapshot all matched. It checked all 497 source files and the
exact 756-session dry-run plan. Driver `f8aede3` then started the unchanged serial
supervisor as `rwsem-1`, with workload evidence under `rwsem-1/rwsem-grid`.
The rwlock phase requires a separate fresh preflight after this run completes
and drains. No parallel test, observer or profiler is running.

The [VM verifier](verify-comparison.py) checks the completed task,
all frozen sources and binaries, every worker oracle, immutable publication,
exact retirement and both environment endpoints. It retains a failed endpoint
as a failure and leaves acceptance open. It copies the hash-pinned original
environment receipts into the completed evidence for independent review.

The [source-host audit](offline-comparison.py) checks the complete archive
inventory, binds sources to both `f48b90e` and validated `a768361`, reconstructs
the observation provider, and independently recomputes worker effects, peaks,
execution classes and repetition ranges. Its raw arithmetic reader is pinned
to SHA-256 `425e5bf0b637e9a20dede0ecda32ef085cdd9ae15d59f1c011c506785a4ee1cc`.
No archived code is executed. Only homogeneous three-repetition groups receive
ratios; partial or unmeasured KD execution remains unscored. TCLock comparisons
will keep its delegation evidence labelled `UNMEASURED`. Both verifiers have
completed for rwsem; they do not change measured inputs.

## Completed rwsem run

Run `shared-lock-followup-20261020/rwsem-1` finished on 2026-10-20 at
16:22:49 UTC. All **756 sessions passed their functional checks and drained**.
[Final health](rwsem-1/health.json) records 378 exact KD retirements
(`state=2`, zero modules/writers/frames), 838 verified source hashes, nine
verified binaries and no per-session kernel fault matches. It records
13,634,932,480 operations: 12,722,668,383 reads and 912,264,097 writes.
The 7,767,589 KD entry witnesses exactly match completed bodies. There are
152 KD sessions with returned bodies, 226 KD `NO_JIT` sessions and 378 Native
controls. `NO_JIT` is retained as a separate execution class.

The immediate [post-run host receipt](rwsem-1/host-after.json), captured at
16:22:57.854954 UTC, has **115 QEMU threads versus the original 67**. CPU
affinities, QEMU identity/arguments, frequency policy, NUMA bindings, guest
identity, pinned dependencies and recovery snapshot still match. The strict
thread-set comparison failed; it was not relaxed or replaced with a later
receipt. Within-run host interference and operation p95 latency remain
unmeasured. These results do not establish performance acceptance.

The [independent audit](rwsem-1/offline-review.json) completed **562,530 checks**.
Archive/source/binary preservation, provider reconstruction, raw worker
arithmetic, protected effects, peak reconstruction and retirement passed.
Its sole issue is the post-run QEMU thread-set mismatch. All 21,067 files and
756 retained symlinks are covered. Full raw evidence is under
`bench/results/10.176.26.71/raw/bench/shared-lock-followup-20261020/rwsem-1/archives/`;
the [archive manifest](rwsem-1/archives.json) SHA-256 is
`990aa76adcfad3576826764f161ec9df9e775d9e386c7b73896c8bca8cf30b82`.
The matrix archive is 53,997,201 bytes, SHA-256
`a54631ebd0f3bd70490450d198959c0d756bc874c7af0faa2d7f070033c61340`.
The metadata archive is 154,443 bytes, SHA-256
`07b9f8c556b85701a2efc822ac78dce68833443f837ea2c79bc811b697beb553`.
The initial report export is retained beside the raw archives in
`review-initial/`. The final export uses LF CSV line endings for the repository;
its repeated inert audit has identical evidence and numerical results, with
only the exporter hash and CSV line endings changed.

### Throughput and variance

Against fresh Native controls, KD meets both observed criteria at **118/126
points**, misses at six and has two incomplete class comparisons. Each scored
point uses three repetitions per arm in one execution class; a pass requires
both median whole-run and best-peak ratios at least one. Whole-interval JIT
counts do not establish the peak window's execution mix.
The [complete CSV](rwsem-1/comparisons.csv) and independent audit retain all
points, sample names, classes, medians and ranges.

Every throughput miss is listed below. Rates are million operations/second;
ratios are KD/Native. Ranges are all three repetitions, not confidence intervals.

| Payload / writes / workers | Whole median ratio | Best peak ratio | KD whole range | Native whole range |
| --- | ---: | ---: | ---: | ---: |
| c01 / 20% / 1 | 0.8554 | 0.8631 | 53.115–53.865 | 61.941–62.386 |
| c01 / 20% / 36 | 0.9845 | 0.9546 | 2.245–2.391 | 1.275–2.420 |
| c08 / 1% / 2 | 0.9202 | 0.9212 | 18.242–21.629 | 17.194–22.496 |
| c08 / 20% / 1 | 0.8771 | 0.8815 | 53.097–53.814 | 60.585–61.029 |
| c08 / 20% / 36 | 0.9350 | 0.9276 | 1.760–2.330 | 1.306–2.460 |
| RCUHT / 20% / 1 | 0.9603 | 0.9584 | 28.158–28.184 | 29.168–29.351 |

Only the c01/c08 20%-write, one-worker losses have a KD maximum below 95% of
the Native minimum. This is an observed separation screen, not statistical
significance. The two unscored points are c01/20% at six and seven workers:
each has two KD `NO_JIT` repetitions and one with returned bodies.
No repetitions were added to obtain a preferred class.

Variance is material. The largest homogeneous KD whole-run spread is 89.10%
at c08/1%/36 workers (5.317–10.055 Mops/s); the largest Native spread is
227.88% at c01/1%/36 workers (1.476–4.840 Mops/s). Spread is
`(maximum - minimum) / minimum`. All six 60-worker points meet the observed
criteria, with whole-run KD/Native ratios from 1.5072 to 2.3916.
These observations remain subject to the failed host endpoint and are not
pooled with the historical 2026-10-18 source or the separate mutex reruns.

## Rwlock reference in progress

`rwlock-preflight-1` passed after rwsem completion, archival and independent
review. Its host receipt was captured at 2026-10-20 16:31:19.687477 UTC and
again matched the original 67-thread QEMU configuration, pins, frequency and
memory policies, boot, dependencies and real recovery snapshot. It checked
all 497 source hashes and the exact 270-session dry-run plan.

The unchanged serial supervisor started `rwlock-1/rwlock-reference` at
16:32:10 UTC, using the same source manifest and the planned five worker counts.
There is one active benchmark and no observer or profiler. This fresh admission
does not replace or repair the failed immediate rwsem post-run check.
Rwlock results are not complete or accepted yet.
