# Mutex owner, gate and tail contention investigation

The retained implementation is `76af844`: it avoids unnecessary queue-head
tail updates and inlines the existing gate hint and exact ownership predicate.
The mutex remains **32 bytes with native 8-byte alignment**, using the same
KD physical exclusion, delegation queue, batching and lifetime protocol.
No auxiliary hash, shared lock reference count, registry lock or auxiliary RCU
mechanism is introduced. Existing task-routing and physical-waiter mechanisms
are unchanged.

Fresh pipe medians are **5.574 Mops/s at eight workers and 4.181 Mops/s at
sixty**, respectively 5.0% and 0.9% above the preceding compact implementation.
The repetition ranges overlap. These are small descriptive changes from three
repetitions in sequential source blocks, not evidence of a uniform speedup or
statistical significance. The retained version remains **18.8% and 22.4% below
the fresh old-256-byte control**. This round does not close the pipe gap.

## Fresh ordinary comparison

Each cell is whole-run median [minimum–maximum] Mops/s from three unprofiled
2000 ms repetitions. These measurements are separate from all earlier rounds,
the placement diagnostic and the eight unscored profiles.

| Workers | Previous compact `0987358` | Retained compact `76af844` | Old 256-byte `0324e60` | Prefetch trial `de30588` |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 5.310 [4.875–5.718] | 5.574 [4.509–5.664] | 6.862 [6.115–7.011] | 5.659 [5.233–5.741] |
| 60 | 4.144 [4.125–4.154] | 4.181 [4.136–4.220] | 5.387 [5.213–5.399] | 4.238 [4.133–4.240] |

The later prefetch trial adds owner-line read hints before successor preparation
and after the translated body returns. Its medians are 1.53% and 1.36% above
`76af844`, with overlapping ranges. That evidence is inconclusive, so the hints
were reverted by `044e351`; the maintained production matches checked
`76af844`. No regression is claimed for the trial. Its source remains reachable
through `archive/mutex32-prefetch-20261020`, and its checks and measurements
remain separate. The original `comparison_arm=false` receipt and explicit
`cohort_role=trial` are preserved. See the [full precision table](comparison-table.md)
and [comparison receipt](comparison.json).

The source blocks ran in this order: `0987358`, the placement diagnostic,
`0324e60`, `76af844`, then `de30588`. They were not randomized or interleaved.
`0987358` contains the preceding `c2f0d9c` production. Candidate `76af844`
includes `0c5dbfe`; there is no separately measured `0c5dbfe` arm. This combined
change does not identify an individual contribution for each optimization.

## What changed and what the diagnosis establishes

An already linked successor proves that the head is no longer the queue tail.
The candidate therefore avoids touching the shared tail in that case. Without
a visible link it reads the tail first; only an exact match attempts the
existing retirement CAS. A changed tail or losing CAS still waits for the
publisher's owed link. Acquire link loads, the reserved node lifetime and the
full CAS preserve publication ordering and the delayed-link handshake.

The inline gate hint keeps the same bounded eight owner probes and full
zero-owner acquisition CAS. The inline ownership predicate retains owner
identity, PICKUP rejection and HELD/COMBINER phase checks. Independent physical
owner probes remain at body entry and retirement. No admission check, source
lease, frame validation, native unlock ACK or drain requirement was removed.
The [source review](source-review.md) gives the ordering argument;
the [machine-code review](code-review-manual.md) checks the actual retained ELF
control flow and retained validation sites.

A separate diagnostic changes only the private benchmark object's position,
using unchanged `0987358` provider bytes. Moving from offset 32 to offset 40
within a cache line separates the physical owner from gate/tail. The observed
medians rise **13.4% at eight workers but only 0.7% at sixty**. Gate readers and
tail writers still share one line. This shows placement sensitivity at eight
workers, but does not establish owner sharing alone as the major cause of the
remaining sixty-worker gap. The dedicated padded diagnostic object also differs
from the standard object's neighbors. These values never enter the ordinary
comparison medians. [Diagnostics](diagnostics.md) retain actual addresses,
placement ranges, delegation rates and profile interpretation limits.

At sixty workers the retained compact implementation returns JIT bodies for
95.463% of measured operations, compared with 94.924% for old256; both have
whole-session ratios near 128 bodies per combiner. Lower delegation or smaller
batches cannot explain the gap uniformly. Flat cycle samples concentrate in
the slowpath, especially at sixty workers, but do not measure HITM, cache-line
transfers or failed-CAS counts. No measured cost is assigned to an individual
atomic operation or cache-line interaction.

## Environment and validation

The workload is `pipebytes/query`, 16 entries, 64-byte values, outer clobber
caller, with 48000 warmup operations per worker and a 1000 ms minimum warmup.
Workers use CPUs 0 through N−1; collector 63 is separate. NUMA is enabled,
batch limit is 1024, entry-ratio limit is 2, prefetch setting is 2 and provider
UBSAN is off. Helper waves/workers are configured but unused by pipe.

All live work ran on `10.176.26.71`, the regular 64-vCPU, 24 GiB VM with two
NUMA nodes (CPUs 0–31 and 32–63). Kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`b65f0205-c8f9-4385-8b13-039cbce243a6`, host pinning and frequency policy
remained unchanged. The real recovery snapshot was
`before-mutex-kdonly-20261017T140354Z`. Host captures and final
[health](health.json) retain those identities; the guest was idle with checked
candidate production restored before preservation.

Both `76af844` and `de30588` passed the two basic and fourteen directly affected
drivers (**16/16 each**), the separate runner planning/report programs
(**11/11 and 13/13 cases each**), and the ordinary mutex, rwsem and
instruction-exit live probes. There were no skips. The provider builds retain
48 warning lines each; warnings are not suppressed or represented as a clean
warning-free build. [Validation](validation.json) binds frozen inputs and
checked production to each measured source. The public geometry remains 32/8;
reserved nodes remain 320/64.

All **24 ordinary timings, eight profiles and twelve placement sessions**
returned JIT bodies, passed their oracles and drained. Finalization inventories
all **50 kernel logs**, including both sets of live probes, with no detected
kernel faults. Source, collector and instrumentation identities remain separate.
This is basic plus affected validation, not a full suite or full workload grid.
Whole-kernel replacement, RT/ww_mutex, lockdep, weak-memory portability and
oversubscription remain outside this evidence.

## Preservation and independent review

[Archive review](archive-review.json) and [source review](source-review.json)
passed with 10246 archive members, 8849 regular files, 20 source manifests,
106 binary-manifest entries and 90 retained JIT binaries, with no ancillary
source exceptions. The independent [statistics audit](statistics-review.json)
passed 59560 checks, reconstructed all 44 ordinary/profile/placement windows
and reparsed 109590 profile samples without an issue. These are evidence
consistency checks, not statistical significance tests or concurrency proofs.

An additional [independent ELF review](independent-review.md) passed 25 binding
checks and confirmed the five manual control-flow obligations. Its two earlier
audit-helper bookkeeping refusals are preserved there. They were offline
schema/revision-comparison errors; no workload failed or measurement changed.

[archives.json](archives.json) binds eight archives under
`bench/results/10.176.26.71/raw/bench/mutex32-cacheline-20261019/` on `380G10`.
The original guest evidence lives under
`/root/kdlock-evidence/10.176.26.71/bench/mutex32-cacheline-20261019`.
[OPERATIONS.md](OPERATIONS.md), [PLACEMENT.md](PLACEMENT.md) and
[FINALIZATION.md](FINALIZATION.md) preserve the collection recipes; actual
completed source selections and results are recorded above and in the receipts.
This final narrative and the offline audit receipts were written on the source
host after collection and do not change the frozen guest evidence.
