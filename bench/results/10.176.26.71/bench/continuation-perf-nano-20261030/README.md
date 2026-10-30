# Continuation performance correction: f7a84065

The completed campaign contains **210 KD points, one measurement round per
point**. Source, build, archive and point accounting validation passes. Nano
performance acceptance remains **false**: 111 coordinates lose whole or peak
rate against `8617e97c02432a7c0b931aa8263d5edd0f6eb5b8`, and 122 against
`acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f`. All negative observations are retained.
Passing functional checks and the intended compiled changes do not establish
zero regression or a causal explanation for these differences.

The measured candidate is `f7a84065e84474380faa37eeadfdf534abd72a68`. It contains
the three bounded changes proposed in the [8617 report](../continuation-nano-20261030/README.md):
normal mutex waiter wake fall-through, omission of spin executor-context refresh
only when a generic return terminates the batch, and smaller spin batch control
storage. The runtime first landed at `6bf690204fdf954ab9076a762000833ec18e6261`;
f7 changes only the failed fixture's unused-accessor annotation and its record.
The failed 6bf check is preserved below, not relabeled as a pass.

| Reference KD source | Whole-rate losses | Peak-rate losses | Either metric | Matched/scored |
| --- | ---: | ---: | ---: | ---: |
| 8617e97c | 106 | 110 | 111 | 210/210 |
| acfa33a5 | 114 | 118 | 122 | 210/210 |

These are separate sequential comparisons, not pooled sources or randomized
pairs. There is no variance estimate. Strict host timing qualification remains
false: the captured auxiliary QEMU worker set changes between endpoints, with
those workers restricted to CPU 63. Fixed vCPU placement and endpoint checks do
not prove uninterrupted isolation. No current Native or TCLock measurements are
created from historical observations. [validation.json](validation.json) has
SHA256 `1ed01930d09da234b2158b9298310dab086f9f1e3c6c94fd24ca07bca9f3422d`.

The user explicitly authorized continuing the later actual-syscall and MM
comparisons on this isolated f7 candidate despite these nano losses. Those
comparisons remain pending in this record. This authorization does not accept
the nano regression or promote the candidate as meeting the performance gate.

## Workload and observed changes

`c01` and `c16` mean 1 and 16 cachelines; `w1`, `w20` and `w100` mean 1%, 20%
and 100% writes. Each of ten workloads has 21 worker counts: 1–8, then 12–60
in steps of four. Each point uses a 2-second measured interval, 48,000 warmup
iterations per worker and 256 rounds of post-lock work. Whole rate is completed
operations divided by measured wall time; peak rate uses the recorded
300-millisecond window after 300 milliseconds of settling. All exact matched
fields and rate numerators/denominators are in [current/points.json](current/points.json).

The VM uses `7.0.0-38-kdlock1`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, with active lazy preemption.
The 64 vCPUs map to two 32-CPU nodes; workers through 32 occupy node 0, while
36–60 span nodes. Collector CPU is 63. Call shells, NUMA policy, instrumentation,
source and provider settings match per coordinate. KD mutex total/local limits
are **1024/1024**, with deferred handoff 8 and scan budget 64; the spin total
limit is 1024. The earlier 768 cutoff is absent from these recorded settings.
This matrix contains mutex, rwsem and rwlock workloads; it does not add a separate
spin-only performance matrix.

Cells below count whole/peak/either losses out of 21 points. A small negative
remains a loss; rounding in this prose does not discard it.

| Workload | vs 8617e97c | vs acfa33a5 |
| --- | ---: | ---: |
| mutex c01 w100 | 13/14/14 | 13/15/15 |
| mutex c16 w100 | 9/10/10 | 11/12/12 |
| rwsem c01 w1 | 14/14/14 | 14/14/14 |
| rwsem c01 w20 | 8/9/9 | 10/11/11 |
| rwsem c16 w1 | 10/10/10 | 9/9/9 |
| rwsem c16 w20 | 15/15/15 | 11/11/11 |
| rwlock c01 w1 | 11/13/13 | 13/15/15 |
| rwlock c01 w20 | 7/7/7 | 9/10/10 |
| rwlock c16 w1 | 10/10/10 | 9/9/10 |
| rwlock c16 w20 | 9/8/9 | 15/12/15 |

The specifically requested 20/32/60-worker whole-rate changes are:

| Workload | vs 8617: 20 / 32 / 60 | vs acfa: 20 / 32 / 60 |
| --- | ---: | ---: |
| mutex c01 w100 | -0.39% / +4.23% / -0.62% | -0.57% / -0.65% / -0.49% |
| mutex c16 w100 | -2.28% / -0.50% / +0.81% | +0.97% / -3.69% / +0.59% |
| rwsem c01 w1 | -0.74% / -2.84% / -5.20% | -0.21% / -2.48% / -4.93% |
| rwsem c01 w20 | -0.75% / -2.54% / +1.52% | +0.16% / -2.00% / +3.23% |
| rwsem c16 w1 | +0.50% / -1.33% / -3.88% | +7.72% / +2.68% / -2.42% |
| rwsem c16 w20 | +3.20% / +0.18% / -0.60% | -0.40% / -0.36% / -1.55% |
| rwlock c01 w1 | +1.68% / -2.05% / -0.96% | +0.09% / -1.11% / +1.17% |
| rwlock c01 w20 | -7.17% / -0.60% / -0.47% | -8.89% / -2.78% / +1.87% |
| rwlock c16 w1 | +3.32% / +4.06% / +0.38% | +1.84% / +5.34% / -2.00% |
| rwlock c16 w20 | +1.27% / +0.40% / -2.42% | -0.66% / -2.39% / -2.62% |

All 210 coordinates and both metrics are preserved byte-for-byte in
[vs-8617/points.csv](vs-8617/points.csv) and [vs-acfa/points.csv](vs-acfa/points.csv).
Their captured CSV line endings are unchanged. The three worker cohorts
1–8, 12–32 and 36–60 contain 80, 60 and 70 points. Whole-rate losses are
41/27/38 against 8617 and 46/35/33 against acfa; losses of at least 5% are
7/5/5 and 5/4/3 respectively. Both local-node and cross-NUMA observations
therefore remain adverse at many coordinates.

The mutex bundle shows partial, uneven recovery against 8617: c16 improves
7.379% at 12 workers and 3.304% at 16, but loses 2.276% at 20 and 0.501% at 32.
Mutex c01 improves 4.229% at 32 while losing 2.306% at 12 and 2.657% at 16.
There are still 22 whole-rate mutex losses out of 42 versus 8617 and 24 versus
acfa. These observations do not isolate the contribution of any one change.

The five largest whole-rate losses versus 8617 are rwlock c16 w1/6 workers
(16.03%), rwsem c01 w1/48 (12.86%), rwlock c16 w1/52 (12.26%), rwlock c01 w1/8
(10.74%) and rwsem c01 w20/6 (8.51%). Versus acfa, the largest is rwlock c01
w1/7 (24.96%), followed by mutex c01 w100/4 (17.77%). The detailed findings
below retain their execution and worker-accounting context.

## Functional prerequisites

[prerequisites/unit.json](prerequisites/unit.json) records three fresh checks:
the two basic checks and `spin/test_spin_batch_context.py`, followed by the
provider build. The production context fixture reports **1,195 checks with zero
failures for each NUMA setting**, with batch sizes 192 and 200 bytes; the intended
mutants are then rejected. Six other unchanged Python drivers are reused from
6bf after comparing all **5,922 tracked inputs** and allowing only the fixture
annotation and result README changes. The effective selection is nine checks,
not nine fresh checks or a full suite. Exact logs and failed owner/controller/sync
inputs are retained under [prerequisites/](prerequisites/).

The original 6bf selection was **8 passed, 1 failed**, because an intentional
missing-refresh mutant failed to compile under `-Werror` when its accessor became
unused. No provider build or live test followed that failed attempt. Its owner
remains `completed=false`, with SHA256
`313a1ad0a38891530ec29cd2ceb5aa781d1236056b94ea21fbb47738d32a7bea`.
The f7 corrected selection and build completed, with final idle true and no live
modules in its owner.

All four subsequent f7 live modes passed and drained, on the same source and
boot; exact owners, results and detailed continuation sessions are copied.

| Live evidence | Recorded result |
| --- | --- |
| Basic spin/mutex/rwlock/rwsem | 1,600,000 operations per case; returned JIT completions 1,596,523 / 1,588,908 / 20,732 / 1,587,866 |
| Original-task instruction service | Seven phases including warmup; two taken phases return 158,778 and 158,491 JIT bodies, with exactly four services/reentries per returned body: 635,112 and 633,964 |
| Forced post-instruction suffix | 56,585 services and native suffixes; zero reentries/completions; the following cold phase returns 158,136 JIT bodies |
| Prepared rwsem writer | Five phases including warmup; each phase has 150,000 writes and 10,000,000 local reads; taken phases record 136,053 and 137,963 services/reentries/completions |
| Mixed mutex→spin | Five phases including warmup; taken phases retain the before-instruction native suffix, with 35,781 and 37,059 native exits and zero JIT completions; the intervening cold phase returns 158,559 bodies |

The service probe checks repeated RDTSC/RDTSCP/CPUID effects, original-task CPU
results and supported flag/branch witnesses, with prefix/suffix counts and final
idle. In the extended mutex run, all four effects end at 480,000 each and
prefix/suffix at 1,120,000 each, including forced native execution. These are
bounded mechanism checks. Rwsem reads remain local. The mixed result does not
prove arbitrary generic CALL reentry or the still-unimplemented queued role
exchange. These kernel probes do not substitute for actual syscall validation.

## Compiled changes and performance limits

[binary-inspection/README.md](binary-inspection/README.md) records the inspected
unit provider SHA256
`93a892843297888e1a000d41dcc560de4fd9fabd74d3d90f95ef68406b3b3c6d`.
The actual compiled mutex zero-result path falls through; its slowpath shrinks
1170→1145 bytes. The spin batch shrinks 208→200 bytes, stack reservation
0x120→0x110 and both initialization sites 25→24 qwords. Terminal generic returns
bypass context capture, while nonterminal returns retain the refresh before
another root. The spin combiner function nevertheless grows 5169→5207 bytes;
total provider `.text` remains 134,694 bytes. All 19 inspected rwsem routines,
`kd_exe_dispatch` and `kd_mutex_run_combiner` retain identical instruction bytes
before relocation. Shared mutex dependencies and loaded placement can still
change the full execution path.

[analysis/measured-elf-proof.json](analysis/measured-elf-proof.json) connects
this inspection to all ten actual measured provider ELFs: all allocated section
bytes/sizes/alignment except Build ID, and all **8,740 recorded allocated-target
relocation recipes**, match the inspected f7 unit artifact. Each profile's ELF
hash is checked against its 21 point records. Full ELF hashes differ; this is
not a loaded-address, physical-placement or causation proof.

Current measurement has **133 RETURNED_JIT and 77 NO_JIT points**, with no
PARTIAL_JIT points. A returned-body classification proves at least one completion,
not that most operations delegated. Against 8617, 69 of 128 stable RETURNED_JIT
points and 34 of 75 stable NO_JIT points lose whole rate. Against acfa, the
corresponding counts are 68/129 and 42/75. Retaining eligibility and positive
publication alone do not guarantee a returned body.

No causal claim follows from function size or virtual addresses. The campaign
did not record module-load CPU, physical page frame or page NUMA-node placement;
a virtual displacement of 4096 bytes is not evidence of physical relocation or
NUMA locality. CPU time, exact completion accounting and prior warmup behavior
can narrow hypotheses, but do not prove an instruction-cache, allocation-node,
parking or scheduling cause. The module-loading placement proposal is separate
future work and is not retroactively applied to these points.

## Read-heavy and cross-NUMA observations

[analysis/README.md](analysis/README.md) and [analysis/summary.json](analysis/summary.json)
retain the detailed observations, with exact selected warmup/measurement/session
bytes under `analysis/points/` and archive bindings in `point-provenance.json`.
The rwsem c01 w1/7-worker point recovers from **7.407581 to 10.437620 Mops/s**
against 8617 (+40.905%), yet remains 0.208% below acfa's 10.459416 Mops/s.
All three versions report zero returned JIT bodies. F7's provider log reports
zero slowpaths, combiners, handoffs and JIT successes; there is just one failed
mutex CAS and zero heat checks across CPUs 0–6. This point cannot supply runtime
evidence that the changed delegation wake path caused its recovery.

The measured wall interval changes only from 2010.308 to 2002.529 milliseconds,
while completed operations rise from 14,891,520 to 20,901,632. Worker CPU time
occupies 99.492% and 99.873% of the respective seven-worker wall budgets. The
already-captured fixed-work warmup also improves: 336,000 operations take
46.013 versus 33.126 milliseconds. These are preparation observations from the
same point, not another measured round. The lock virtual address is unchanged
between 8617 and f7, `0xffffffffc0ca05c0`; its physical placement was not recorded.

Remaining cold losses also show less useful progress while workers account for
nearly the whole interval. Rwlock c16 w1/6 loses 16.030% versus 8617 with 99.502%
CPU occupancy; its warmup rate loses 18.218%. Rwlock c01 w1/7 loses 24.957%
versus acfa with 99.501% occupancy and a 24.227% warmup loss. These observations
do not support attributing the full loss to time spent sleeping. They do not
provide park/event counts, host-steal traces or hardware-cycle measurements,
so reader spinning, shared-state RMW traffic, placement and external execution
conditions remain hypotheses. No percentage is assigned to any cause.

At rwsem c01 w1/48, only 3.8804% of writes complete through JIT despite its
RETURNED_JIT classification and 12.856% whole-rate loss versus 8617. All reads
still execute locally. The local-to-cross-NUMA step also remains adverse:

| Rwsem workload | f7 rate at 32 / 36 workers (Mops/s) | f7 change 32→36 | 8617 change 32→36 |
| --- | ---: | ---: | ---: |
| c01 w1 | 8.352332 / 6.913302 | −17.229% | −13.883% |
| c01 w20 | 5.099569 / 3.935657 | −22.824% | −22.537% |
| c16 w1 | 11.084365 / 9.730956 | −12.210% | −11.749% |
| c16 w20 | 4.735317 / 3.784350 | −20.082% | −19.087% |

F7's 36-worker points are 6.610%, 2.896%, 1.846% and 1.051% below 8617 in that
order. The recorded **1024/1024** policy applies to every matched point; these
losses are not evidence that a 768 delegation-count limit remains. The records
establish worker topology, not every lock/data page's NUMA residency.

## Evidence and reproduction

[receipts/](receipts/) retains the exact run/archive owners, archive index,
transfer receipt, source synchronization and host captures. Full raw archives
remain under `bench/results/10.176.26.71/raw/bench/continuation-perf-nano-f7a84065-20261030/`.
The new report does not rewrite the older source reports or their numbers.
[copied-evidence.json](copied-evidence.json) records every copied source path,
byte count and SHA256, including captured CSVs and prerequisite logs.

The first local postprocessing watcher waited on a receipt path missing the
`kdlock-` prefix. It was stopped before any fetch/audit child started; its failed
owner and stop receipt are retained. A separate r2 watcher corrected the path
and completed archive fetch and offline validation. This repeated neither a
measurement nor a kernel test. The archive and measurement owners are distinct
from watcher transport status.

[tools/audit_compare.py](tools/audit_compare.py), `nano_core.py`,
`archive_helpers.py` and `prerequisites.py` preserve the exact offline validation
implementation. Original arguments and tool hashes are in `validation.json`;
reproduction requires the retained raw archives and frozen source oracle and a
new output directory. These tools read captured source and ELF bytes; they do
not execute the inspected artifacts. [analysis/analyze.py](analysis/analyze.py) and
[analysis/compare_measured_elf.py](analysis/compare_measured_elf.py) preserve the
additional derivation, with their original fixed input paths. The initial
analysis member-prefix mistake and stopped draft are retained in
`analysis/analysis-attempts.txt` and `analysis/analyze-first-attempt.py.txt`; its
correction changed no raw input or measurement. This report was assembled
on the source host using read-only archived evidence; it performs no new VM
build, unit test or performance measurement.
