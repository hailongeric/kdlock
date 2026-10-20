# Shared-lock comparison after mutex correctness restoration

Status: rwsem collection running; rwlock reference not started. This stage
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
No completed comparison is claimed yet. Each family must complete, drain,
preserve its frozen inputs and pass archive review before its coverage can be
reported as complete.

`rwsem-preflight-1` passed with the host receipt captured at
2026-10-20 15:32:23.798415 UTC: QEMU PID 257489 and the original 67-thread set,
frequency policy, NUMA memory bindings, CPU pins, boot, pinned dependencies and
actual recovery snapshot all matched. It checked all 497 source files and the
exact 756-session dry-run plan. Driver `f8aede3` then started the unchanged serial
supervisor as `rwsem-1`, with workload evidence under `rwsem-1/rwsem-grid`.
The rwlock phase requires a separate fresh preflight after this run completes
and drains. No parallel test, observer or profiler is running.
