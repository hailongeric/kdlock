# Controlled replay of the public-mutex regressions

The selected [correctness stage](../../tests/native-continuation-20261020/README.md)
is complete. Controlled replay `mutex-public-20261020-replay-2` completed
**120/120 valid, drained sessions** on the original recovery VM. Four of the
seven original losses remain separated across observed ranges; two have
overlapping ranges, and one falls below the provisional 5% screen.
**Performance acceptance remains open.** No causal correction has been measured.
Two execution-class comparisons, p95 latency and host worker-thread variability
remain unresolved. [Final status](final-status.json) records these dispositions.

The fixed selection is 120 serialized sessions: c08 at 2/3/4/5 workers, RCUHT
at 2, pipe bytes at 3/4/5, and pipe capacity at 4/5; three repetitions and the
same four arms at every point. Original execution order and arm rotation are
preserved. [Selection provenance](selection.json) binds the selected original
records to the original matrix archive. Collection ran from
2026-10-20 12:00:09.868159 UTC to 12:08:25.513872 UTC. No tests ran in parallel
and no in-flight run was interrupted. All three helpers completed read-only
reviews and reported no files touched; the main agent was the sole writer.

## Seven outcomes and remaining gaps

Ratios below are public DIRECT / frozen OUTER full-run medians. Each ratio uses
three repetitions in the same execution class. Original and replay collections
remain separate.

| Point | Class | Original ratio | Replay ratio | Replay median loss | Outcome |
| --- | --- | ---: | ---: | ---: | --- |
| c08/t3 | WITNESSED_JIT | 0.812460 | 0.681982 | 31.80% | Overlapping ranges |
| c08/t4 | WITNESSED_JIT | 0.706642 | 0.533785 | 46.62% | Separated loss reproduced |
| c08/t5 | WITNESSED_JIT | 0.789000 | 0.764036 | 23.60% | Separated loss reproduced |
| pipebytes/t3 | NO_JIT | 0.840544 | 0.967176 | 3.28% | Below provisional screen |
| pipebytes/t5 | RETURNED_JIT | 0.874075 | 0.919470 | 8.05% | Overlapping ranges |
| pipecap/t5 | RETURNED_JIT | 0.597685 | 0.748197 | 25.18% | Separated loss reproduced |
| rcuht/t2 | WITNESSED_JIT | 0.919323 | 0.887614 | 11.24% | Separated loss reproduced |

[Rates and ranges](regression-table.md) retain every median/minimum/maximum.
[Per-repeat CSV](per-repeat.csv) includes all 240 original/replay/control
observations; [investigation JSON](investigation.json) retains class-separated
groups and same-round paired ratios. Spread is `(maximum − minimum) / median`;
the largest public/OUTER spreads among the seven replay points are
28.95%/41.39% at c08/t3. Native and TCLock controls are retained as well,
including Native's 71.37% spread at c08/t2.

Separation means public's best repetition is below 95% of OUTER's worst.
Three repeats provide observed variation, not confidence intervals or
statistical significance. The 5% screen was a coordinator proposal, not a
user-approved acceptance threshold. The pipebytes/t3 result does not prove
that the original loss is fixed. **All seven causal resolutions remain
unresolved**, including those whose ranges now overlap.

The three original class gaps were also rerun:

- c08/t2 remains incomparable: public has three NO_JIT runs; OUTER has one
  NO_JIT and two WITNESSED_JIT runs.
- pipebytes/t4 remains incomparable: public has three RETURNED_JIT runs;
  OUTER has three NO_JIT runs.
- pipecap/t4 has three NO_JIT runs on both arms in this replay, ratio 0.939063
  and 6.09% median loss with overlapping ranges. This does not rewrite its
  original mixed-class result.

WITNESSED_JIT establishes generated entry, not returned completion.
RETURNED_JIT establishes positive returns, not universal delegation.
NO_JIT is retained as an execution class. NORMAL publication proves neither
entry nor completion. Operation latency was not sampled; p95 remains
**unmeasured**.

## Measurement identity and environment

Replay uses the original `mutex-public-20261020-r2` provider, caller, client,
daemon, translation sources and collector. Collection source is `d21a1e3`;
OUTER inputs retain their separate production `752fec1` identity. The new
selection/provenance scheduler is from `b345db3`. Its 12 VM tests passed in
[checks-5](../../tests/native-continuation-20261020/checks-5/result.json).
Later continuation and prefetch corrections are not substituted into the
frozen performance inputs. This rerun makes no performance claim for those
later revisions. The original 1,764-session matrix remains unchanged.

The environment uses the same QEMU process, PID 257489, and guest boot on
`10.176.26.71`, 64 vCPUs, 24 GiB, two NUMA nodes, prefix worker CPUs and collector
63. Kernel is `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot ID
`b65f0205-c8f9-4385-8b13-039cbce243a6`. The listed recovery snapshot remains
`before-mutex-kdonly-20261017T140354Z`. No guest kernel change or reboot occurred.
The pinned translation environment remains miasm 0.1.5, future 1.0.0,
pyparsing 2.4.7 and pyelftools 0.27.

Measurements remain two seconds, warmup 48,000 operations per worker with at
least one second for API warmup, 300 ms peak/settling windows and 10 ms samples.
API objects are n16, post work is 64, entry ratio/prefetch are 2, batch limit
1024, NUMA on and provider UBSAN off. Diagnostic/PMU/perf instrumentation is off.
All selected workers are on node 0, with collector 63 on node 1.

[Preflight comparison](replay-2/environment-comparison.json) confirms the same
configuration, thread set/pins, frequency policy, NUMA bindings, dependencies,
kernel and topology at admission. Actual resident page counts differ within
those unchanged bindings and are retained in that receipt.

The strict offline post-run check found **one environment discrepancy**:
the [after receipt](host-replay2-after.json), at 12:09:48 UTC, has one additional
QEMU `worker` on CPU 63, compared with the preflight set of 67 threads.
The original matrix's after receipt had 30 such workers. A separate
[later receipt](host-after-archive.json), at 12:22:31 UTC, again has the original
67-thread set after natural retirement. Configuration and original thread
affinities remain unchanged. This is consistent with dynamic background
worker creation, but the timing or collector interference of those workers
during measurement was not sampled. [Environment diagnosis](environment-gap.json)
retains this **unresolved performance confounder**. The failed exact-thread-set
check remains in the audit; later retirement does not erase it.

## Investigation limits

Static inspection gives a hypothesis, not an established cause. OUTER can
acquire inline with a local owner cookie and route physical unlock directly.
Public DIRECT crosses the clobber entry and routes unlock through provider
task/ownership lookup. Both retain the same bounded physical probe and
contention admission. Additional calls, spills, lookup cost and changed binary
layout could affect these small critical sections. No profile or controlled
optimization isolates their contribution.

Control movement also matters: at c08/t4, public's replay median is about 1.6%
below its original value, while OUTER's is about 30.3% higher. The larger
relative loss therefore does not demonstrate a new code regression; the same
frozen inputs were measured. Changes in delegation class at c08/t2 and the
retained host variation prevent attributing all differences to the API.

The next performance stage needs causal profiling or a separately identified
candidate, measurements under the same setup, and explicit treatment of
background worker variability and p95 latency. The other full-grid losses
in the original report were outside this focused rerun and remain open.
Whole-kernel replacement, RT/ww_mutex and lockdep integration remain unvalidated.

## Preservation and verification

`mutex-public-20261020-replay-1` failed preflight before any measurement because
two extra QEMU workers on CPU 63 differed from the original set. Workers retired
naturally before replay-2 admission; no check was changed or bypassed.
[Its later receipt](replay-1/preflight-outcome.json) is explicitly retrospective,
preserves all original partial files, and does not label that attempt a pass.

[Replay-2 health](replay-2/health.json) verifies 4,088 original bundle files and
336 retained collector files unchanged, all 120 sessions valid/drained, exact
`state=2, modules=writers=frames=0` retirement for all 60 KD sessions, and no
matched faults in the session kernel logs. There are 60 control, 19 NO_JIT,
26 WITNESSED_JIT and 15 RETURNED_JIT sessions.

The [inert archive review](offline-review.json) performed 886,984 checks and
reconstructed all 120 peak windows. All archive, cross-archive link, input,
worker, business-oracle, retirement and arithmetic checks passed. Its one
reported issue is the post-run thread-set discrepancy described above.
The first [review-script attempt](offline-review-initial.json) failed because
affinity lists were used as Counter keys; its source is preserved and the
corrected reader uses immutable tuples. That was an offline script error.
No archive or live result was changed.

Complete archives are on the VM under
`/root/kdlock-evidence/10.176.26.71/bench/<run>-archives/` and locally under
`bench/results/10.176.26.71/raw/bench/<run>/`. New workspace links intentionally
refer to the original frozen bundles; the audit resolves them only against the
new and hash-verified original archive inventories.
Full per-session JSON remains in raw storage, with exact archive members,
local paths and hashes in [the record index](raw-records.json). To reproduce
the analysis, use the retained `analysis/` directory as `compare-rerun.py`'s
`--report` and the retained replay `records.json` as `--records`, writing into
a separate extracted copy. The preservation check was repeated after moving
the two full-record copies out of the compact report; its preceding receipt
is retained as `offline-review-before-storage-layout.json`.

| Run | Archive manifest SHA-256 | Reference |
| --- | --- | --- |
| Original `mutex-public-20261020-r2` | `7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4` | [Original archives](../mutex-public-20261020/archives.json) |
| `mutex-public-20261020-replay-1` | `d37ecf68c397103c960651e4045f7a769dca1f332cf84e45b225b135a9871ab1` | [Failure archives](replay-1/archives.json) |
| `mutex-public-20261020-replay-2` | `ade97c62143e7c172e3191837ebdd9558ab17f4ad89593e9c8ef4cc6534b28cc` | [Replay archives](replay-2/archives.json) |

Replay-2 contains `measurements.tar.gz` (2,689,543 bytes, SHA-256
`22543b917925d5dbac31d9e1eae2bdce48ab4e535dd8c88b4d6ff627f3c7e927`),
`analysis.tar.gz` (1,002,224 bytes,
`c3592133499c573e15320381bbd9e881f1fe086f1d72a82eb9a7a521b42644b5`)
and `metadata.tar.gz` (1,474,926 bytes,
`894b2109fa5ae5b50d45a5df92e439b8a89e25e9528689a707d313d683160c60`).
[Console](replay-2/kdlock-replay2-console-20261020.log),
[status/order receipts](replay-2/status.json),
[source/collector provenance](replay-2/replay-provenance.json),
[original summaries](original-summary.json) and
[replay summaries](replay-summary.json) remain separate.
