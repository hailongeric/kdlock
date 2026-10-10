# KD rwlock comparison, 2026-10-09

Historical ABI1 results. The later [ABI3 RCUHT comparison](../20261010-rcuht/README.md)
resolves the hash-writer refusal below and uses the current 1%/20% mixes and full
thread set. Preserve these earlier measurements separately.

KD rwlock is competitive on these read-heavy workloads. Writer delegation helps
write-only throughput, but hurts balanced read/write traffic. With sixteen
protected cachelines and sixteen workers, KD reaches **3.596 Mops/s**, ahead of
Linux native's **3.162** and TCLock's **2.942**. With a one-cacheline write body,
Linux native remains faster. At this checkpoint, the KD hash writer cannot pass strict JIT
admission, so there is no hash-writer JIT performance result.

The complete comparison covers **180 cacheline sessions**: three backends, two
sizes, five read/write mixes, one/sixteen workers and three rounds. Another
**12 sessions** measure KD with delegation disabled. All passed data, worker
progress, context and drain checks. This is a selected comparison, not the full
15-point scaling matrix or a cross-NUMA experiment.

## Sixteen-worker results

Rates below are the **highest validated warmed peak in Mops/s**. Each operation
is one read or write critical section plus four arithmetic rounds outside the
lock. The JIT column is the range of whole-measurement returned JIT writer bodies
divided by completed writes; it does not describe the selected peak window.

| Cachelines | Reads / writes | Linux native | TCLock rwlock | KD rwlock | KD JIT writers |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 100 / 0 | 19.838 | 19.824 | 20.102 | No writes |
| 1 | 99 / 1 | 14.818 | 14.266 | 15.383* | 0–0.0164%* |
| 1 | 90 / 10 | 9.105 | 8.919 | 8.935 | 12.41–15.32% |
| 1 | 50 / 50 | 6.761 | 4.002 | 3.907 | 55.18–55.97% |
| 1 | 0 / 100 | 7.502 | 4.091 | 5.458 | 99.84–99.89% |
| 16 | 100 / 0 | 8.830 | 8.247 | 8.773 | No writes |
| 16 | 99 / 1 | 7.515 | 6.848 | 7.785 | 0%, NO_JIT |
| 16 | 90 / 10 | 5.201 | 5.521 | 5.236 | 7.50–8.41% |
| 16 | 50 / 50 | 3.380 | 3.131 | 2.813 | 41.10–44.31% |
| 16 | 0 / 100 | 3.162 | 2.942 | 3.596 | 99.887–99.888% |

\* The one-cacheline 99/1 KD point has **two JIT-positive rounds** (15.269 and
15.383 Mops/s, only 50 and 5 returned bodies respectively) and **one NO_JIT round**
(15.357 Mops/s). These are separate groups in the statistics; neither is a complete
three-round group. The displayed JIT peak uses only its two positive rounds.
Every other table entry has three rounds in a single execution-status group.

[Statistics](statistics.csv) retain peak min/median/max/spread, whole-run
min/median/max, JIT shares and group completeness. [Samples](samples.csv) retain
every planned primary/control case, including the failed and unrun hash cases,
exact read/write totals, per-round rates and worker completion extrema. The raw
archive additionally contains every worker and timestamped progress sample.

Small read-heavy differences should be treated as comparable performance in this
setup, not a general speedup guarantee. For example, the 99/1 sixteen-cacheline
KD peaks range from 7.558 to 7.785 Mops/s. Variation is larger in some single-worker
TCLock samples; its one-cacheline 99/1 peak spread is 37.05%.

## What delegation changes

These controls use the same workload and runtime sources. The sole frozen-input
difference is the runner's default workload list, changed to make the unsupported
hash writer opt-in; both commands explicitly select their workloads. Delegation
is disabled with the provider's `spin_delegate=0`, while preserving the same
prepared writer, ABI, post-work, NUMA, prefetch and ratio settings. Controls ran
after the comparison rather than interleaved with it.

| Cachelines | Reads / writes | KD JIT enabled | KD delegation disabled | Enabled / disabled change |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 50 / 50 | 3.907 | 6.292 | −37.90% |
| 1 | 0 / 100 | 5.458 | 3.996 | +36.57% |
| 16 | 50 / 50 | 2.813 | 3.846 | −26.86% |
| 16 | 0 / 100 | 3.596 | 2.176 | +65.29% |

The read/write mix matters more than simply achieving a high JIT share. At 50/50,
returned writer delegation is substantial, yet disabling it improves throughput.
For pure writers, nearly every write delegates and JIT improves on KD's own native
control. It also beats both external backends for the larger body: +13.74% versus
Linux native and +22.23% versus TCLock. It remains 27.25% below Linux native for the
one-cacheline write-only body.

Readers always execute locally. Writer continuations include waiting for reader
drain before touching protected data. Queue handoffs, reader/writer transitions
and continuation execution are plausible contributors to the balanced-case cost;
these runs do not profile their individual costs or establish a precise cause.
Forcing more delegation is not supported as an improvement by these measurements.

## One worker and reader scaling

Single-worker KD executes no JIT bodies. This exposes the local read path and
uncontended writer cost; every KD writer takes the embedded gate, whereas TCLock
also has an ungated writer fast path.

| Cachelines | Reads / writes | Linux native | TCLock rwlock | KD rwlock |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 100 / 0 | 43.982 | 44.770 | 54.671 |
| 1 | 50 / 50 | 55.387 | 50.648 | 45.617 |
| 1 | 0 / 100 | 56.864 | 52.350 | 41.050 |
| 16 | 100 / 0 | 35.051 | 34.252 | 36.797 |
| 16 | 50 / 50 | 37.612 | 37.217 | 35.981 |
| 16 | 0 / 100 | 39.551 | 38.770 | 35.219 |

All three locks lose aggregate read-only throughput from one to sixteen workers
here. KD goes from 54.671 to 20.102 Mops/s for one cacheline and from 36.797 to
8.773 for sixteen. Each reader still modifies a shared admission count, and these
very short bodies provide little independent work to amortize shared-cacheline
traffic. This behavior is consistent with that design; it is not evidence that
readers cannot overlap. The separate correctness test verifies overlap.

## Hash admission limit and retained attempts

The primary run planned 270 sessions. It completed all 180 cacheline sessions,
18 read-only hash sessions, and two initial native/TCLock hash writer sessions.
Case 201, `rcuht-c00-kdlock-w001-t01-r00`, stopped during preparation:

```text
CONTEXT_ADDRESS_WIDENED
MOV RAX, QWORD PTR [RAX + 0xffffffffc0c23ac0]
wide_registers: [RAX]
CONTEXT_NATIVE_ONLY
```

The strict analysis could not establish a bounded bucket address at this load.
The failure is analysis uncertainty, not an observed invalid memory access or
an exclusion failure. No timed KD hash writer ran. The runner deliberately stops
on refused publication; **69 remaining primary cases were not run**. Source
retirement reported zero frames, modules and writers, followed by successful unload.

A separate fixed-iteration probe moved bucket masks inside writer admission for
all backends, but KD still refused the address after analysis widened it. That
candidate was reverted and its frozen source, disassembly and refusal remain in
`hash-probe-v4`. No translator admission rule or runtime guard was changed.

Read-only hash is valid, with no writer publication or delegation:

| Workers | Linux native | TCLock rwlock | KD rwlock |
| ---: | ---: | ---: | ---: |
| 1 | 23.186 | 22.662 | 27.631 |
| 16 | 19.749 | 19.848 | 19.873 |

Two earlier attempts are retained separately and excluded from headline scores.
`comparison-v1` stopped in boot-policy preflight because the DWARF parser expected
a direct function pointer for the wrapped unlock member. `comparison-v2` completed
ten sessions before a client barrier race cancelled a late warmup worker; all
workers returned and the session drained. Both issues were fixed before the fresh
`comparison-v3` run. A focused barrier regression now covers the latter failure.

## Reproduction and validation

Commands ran only in the recovery guest, from the isolated ext4 source at
`/root/kdlock-evidence/rwlock-bench-20261009/source`, with the pinned Python
environment, `LC_ALL=C` and monitor-confirmed snapshot
`pre_mutex_priorities_20261008`. The main run used:

```sh
python3 -u bench/rwlock_compare/run.py \
  --workloads cacheline rcuht --cachelines 1 16 \
  --write-percent 0 1 10 50 100 --threads 1 16 \
  --output /root/kdlock-evidence/rwlock-bench-20261009/comparison-v3

python3 -u bench/rwlock_compare/run.py \
  --backends kdlock --delegate off --workloads cacheline --cachelines 1 16 \
  --write-percent 50 100 --threads 16 \
  --output /root/kdlock-evidence/rwlock-bench-20261009/cacheline-native-control-v5
```

Use a new output directory and an outer timeout, following the
[runner guide](../../../../../bench/rwlock_compare/README.md). Omitting `rcuht` reproduces the complete supported
cacheline subset. Do not treat the primary command's hash refusal as a full pass.

The kernel is the unchanged `6.1.159-kdclobber2`, live Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. Source/config/build/bundle checks passed.
The boot uses `nokaslr`, `nopvspin` and voluntary preemption; both live qspinlock
dispatch pointers matched their native implementations. Workers use guest CPUs
0 or 0–15, all on NUMA node 0; the collector uses CPU 38 on node 1. Host vCPU pins
and 2.5 GHz frequency bounds were checked before and after the runs.

Each backend uses 48,000 warmup operations per worker, three two-second rounds,
four post-work rounds, 256-operation progress batches, 10 ms sampling and the best
full-cohort 300 ms window after 300 ms settling. KD uses ratio limit 2, prefetch 2,
NUMA on and batch 1,024. The actual upstream TCLock rwlock port uses NUMA and batch
1,024; its delegation share is unmeasured. Benchmark modules have UBSAN disabled;
kernel mitigations and frame pointers remain intact. Known stack-switch objtool
warnings remain, and the emitted TCLock context audit passed before loading.

Fresh guest checks passed: the two basic unit groups, KD rwlock concurrency tests,
the real TCLock rwlock assembly fixture, all ten runner/oracle tests, and all eight
shared peak tests. These are focused checks, not a full test-suite pass. All
attempted sessions drained; the final guest idle check found no live benchmark,
translator or project module. All required data and progress checks passed for
the 212 valid primary/control sessions; 20 primary sessions returned a total of
64,208,316 JIT writer bodies.

[Evidence identities](evidence.json) locate the complete raw archive, whose SHA256
is `88651ae1c64dc7f73f1314d96a199a1a65eb88476a4a0f1e0176ecf6388b7b8d`.
It includes all attempts, frozen source/ELF hashes, build and command logs,
translation images, kernel logs, individual samples and teardown records.
The source combines the prior KD rwlock implementation (`a343662`) with the new
benchmark/port files; unrelated host mutex and spin-workload edits were preserved
and excluded from the isolated guest inputs. The archive's `host-differences.json`
records those differences. Final benchmark source matches the control's frozen
inputs; this report and navigation prose were added afterwards.
