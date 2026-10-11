# Performance status

KD does not yet match both TCLock and Linux Native at every requested thread
count. The [mutex waiting-policy report](../bench/results/10.176.26.71/bench/mutex_wait/20261012/README.md)
documents the new blocking mode, its comparison with the retained spin policy,
Native/TCLock baselines, real API critical sections and unchanged spin/rwlock
controls. It keeps timing variation, rejected implementations and scheduler
validation separate from throughput claims.
All 2,430 sessions passed and drained. At 60 workers, the nine mutex configurations
retain 94.5–99.2% of spin's median whole-run throughput; blocking beats Native and
TCLock on that metric in all nine and on best peak in eight. C16 loses 12.6% at
eight workers. The single-worker hash slow-start discrepancy, separate paired
diagnostic and CPU costs are retained in the report; universal parity is unmet.

The earlier [mutex c01/hash optimization](../bench/results/10.176.26.71/bench/comparison/mutex-opt-20261011T045425Z/README.md)
measures task caching, polling layout, retirement loads and bounded NUMA selection
across all 22 worker counts. The earlier [all-lock c01/hash rerun](../bench/results/10.176.26.71/bench/comparison/full-matrix-20261011T025525Z/overview.md)
retains the spin/rwlock comparison and the pre-optimization mutex baseline.
The [NUMA/mutex investigation](../bench/results/10.176.26.71/bench/comparison/numa-mutex-20261010/README.md)
retains their causes, rejected candidates and focused checks.
The original-host spin/mutex optimization phase ended on **2026-10-09**, with
those gaps still open. Its [report](../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md)
keeps the final comparison, rejected candidates and the source and binary identities
used for each run.

## Real kernel API contention, 2026-10-11

The [mutex and reader/writer extension](../bench/results/10.176.26.71/bench/real_api/20261011-sync/RESULTS.md)
adds FIONREAD, F_GETPIPE_SZ, shared-file lseek and bounded private UTS reads/writes:
**504 accepted/drained sessions**, three rounds at 1/8/16/32/48/60 workers under
Stock, matched Native, TCLock and KD. KD meets both median whole-run and best-peak
parity against Native and TCLock at **32 of 35 multithreaded points**. The three
exceptions are 128-buffer FIONREAD at 8/16/32 workers.

At 60 workers, the short pipe cases reach 5.330–5.639 Mops/s, 2.92–2.95× Native
and 2.07–2.20× TCLock. Shared-file seeks reach 3.839 Mops/s, 2.77–2.92× Native
and 1.46–1.57× TCLock. Mutex JIT shares at 16–60 workers are 96.78–99.79%.
UTS has favorable throughput but only 0.01–3.16% of writes execute through JIT
at those counts; all eight-worker UTS rounds are NO_JIT. Its private Native rwsem
sleeps while KD/TCLock use bounded reader/writer spinlocks, and KD's CPU time per
operation exceeds Native's. The 60-worker domain case has only a 0.29% best-peak
lead over TCLock. The report retains these limits, all failed pilots and the
scope correction; it does not claim a general rwsem, mmap or FxMark integration.

The earlier [spinlock API results](../bench/results/10.176.26.71/bench/real_api/20261011/RESULTS.md)
map OFD conflict queries to `file_lock_context.flc_lock` and close-on-exec bitmap
updates to `files_struct.file_lock`. These spinlock comparisons contain 288
accepted, drained sessions, with stock plus matched Native/TCLock/KD and three
rounds at 1/8/16/32/48/60 workers. KD meets both median whole-run and best-peak
parity against Native and TCLock at 13 of 20 multithreaded points.

The strongest 60-worker bitmap case reaches 7.549 Mops/s: 2.55× matched Native
and 1.60× TCLock. Eight-worker regressions, single-thread overhead and the xattr
admission refusal remain documented. The report distinguishes the stock helper's
instrumentation from matched Native and actual JIT execution from `NO_JIT`.
These are scoped API stress measurements; whole-application performance and
global kernel-lock replacement were not evaluated.

## Mutex c01 optimization, 2026-10-11

The [new comparison](../bench/results/10.176.26.71/bench/comparison/mutex-opt-20261011T045425Z/README.md) contains **396 drained sessions**,
**396 accepted**: Native, TCLock and KD, three rounds at each
of the 22 worker counts, with c01 and hash only. c02/c08/c16 were excluded.
KD meets the multithreaded strict comparison at **14 of 42 points** and falls
short at **28**. This requires both best warmed peak and median whole-run
throughput to match both alternatives.

C01 meets that target at **2 of 21 multithreaded points**, at 60 and 64 workers.
Hash meets it at **12 of 21**, at 16–36 and 44–64 workers in steps of four;
40 workers remains below Native. One-worker controls are excluded from these
counts. Selected c01 median whole-run rates are shown below, in Mops/s. The
strict result also checks best warmed peak, so a whole-run lead alone is
insufficient, as the 36-worker result shows.

| Workers | Native | TCLock | KD | Strict target |
| --- | --- | --- | --- | --- |
| 4 | 9.850 | 3.748 | 4.395 | FAIL |
| 16 | 8.670 | 3.567 | 7.551 | FAIL |
| 36 | 5.749 | 3.357 | 5.798 | FAIL |
| 64 | 3.173 | 3.305 | 4.946 | PASS |

Short batches and mixed native/delegated routing remain an unresolved c01
bottleneck. The four-worker placement stays within NUMA node 0, so cross-node
handoff cannot explain that point's remaining gap. Measured JIT share is 47–75%;
session-lifetime counters, including warmup, show only 4.8–16.2 successful bodies per combiner,
versus 892–972 at sixteen workers. Short batches repeatedly pay physical lock
acquisition and queue/frame setup for a very small protected body. This supports
the coordination-overhead explanation but does not isolate each instruction's cost.

Historical whole-run comparisons show a 69.8% c01 gain at 64 workers and a
25.4% gain at 36, alongside drops of 44.4% at three workers, 6.3% at four,
and 4.7% for hash at 40. The earlier three-worker c01 peak spread was 51.2%;
those differences do not isolate source effects from run variability, and the
regressions remain unresolved. Hash at 36 workers is KD **3.436**, Native
**2.459** and TCLock **2.119 Mops/s**. The report keeps every point and spread.

Selected changes retain inactive task identities in a bounded RCU cache while
keeping exact active references, separate completion polling from metadata,
prevent a widened retirement load, and use bounded NUMA request grouping.
Small remote cohorts are serviced without moving the physical owner. Shorter
batches, capped admission, extra retry, frame reuse and broader prefetch were
rejected. Separate PMU diagnostics show fewer store-forwarding blocks, but total
store-buffer stalls did not improve; they are excluded from throughput scores.
The selected implementation and report are committed in `319ef8f`. Measured
inputs also contain the nine pre-existing working-tree edits captured in the
report's frozen source manifests; the commit alone does not identify all measured
source bytes.

The selected source passed seven basic/affected checks, four runner checks and
the cross-NUMA owner/ACK/RCU probe. Final KD acceptance includes
**126 ACTUAL_JIT** and **6 NO_JIT** sessions.
Raw source/ELF/JIT hashes, client totals, placement, worker progress and drain
were audited, and archive replay reproduced the audit CSV bytes. Validation
limits and rejected candidates remain in the report. The regular 64-vCPU boot
was restored after verified archiving; the final comparison uses the documented
temporary 66-vCPU placement, including physical collector contention at 64 workers.

## Earlier all-lock c01/hash comparison, 2026-10-11

The [rerun](../bench/results/10.176.26.71/bench/comparison/full-matrix-20261011T025525Z/overview.md) contains **1,584 drained sessions**, with **1,582 accepted**:
Native, TCLock and KD, three rounds at 1–8 and 12–64 workers. Spin, mutex and
rwlock use only c01 and hash payloads; rwlocks cover 1%/20% writes.
Cacheline c02, c04, c08 and c16 were excluded. Two drained NO_JIT rejections
at spin c01/20 workers remain archived and excluded from scores, leaving one
incomplete comparison point. Measured source is `0e1112e` plus the nine captured
working-tree edits. No implementation changed for this rerun.

At 36 workers, spin c01 median whole-run throughput is KD **6.164**,
Native **4.956** and TCLock **4.850 Mops/s**.
Mutex c01 is KD **4.624**, Native **5.691**
and TCLock **3.373 Mops/s**. Mutex hash is KD **2.659**, Native **2.466**
and TCLock **2.124 Mops/s** at that count. The full report supplies rwlock,
peak, range and scaling results, including the remaining gaps at other counts.

Accepted KD sessions include 356 ACTUAL_JIT and 170 NO_JIT controls.
Status-separated statistics preserve that distinction. All accepted peak windows,
source/binary/JIT hashes and exported CSV bytes passed the independent archive audit.
The temporary 66-vCPU layout and unchanged `ondemand` policy match the documented
complete-matrix setup. At 64 workers the last worker shares its physical core with
the collector and QEMU services. The regular 64-vCPU boot was restored and verified.

## NUMA spin and mutex fixes, 2026-10-10

The focused investigation used the regular 64-vCPU VM, collector 63 and 16/36
workers. It retained 354 accepted, drained timed sessions, six separate profile
sessions and failed candidates. The final comparison is 72 sessions: Native,
TCLock and KD, three rounds, one-cacheline and hash payloads. Subsequent default
comparisons exclude multi-cacheline scenarios, including c08 and c16.

Spin's empty-link policy ended short batches as soon as remote work was deferred.
The accepted bounded refill raises cross-NUMA cacheline median peak from 4.684
to 6.047 Mops/s (+29.1%). Hash falls from 4.104 to 3.944 (-3.9%) while remote
progress improves. Larger aggregate gains from long local batches were rejected
because they substantially reduced remote progress. Placement, post-work and
historical worker-progress controls explain the limits of the 380G10 comparison;
the full hardware difference remains unproven.

Mutex's global task-registry lock, shared polling/register and gate cachelines,
and failed owner/gate CAS traffic compounded each other. Per-bucket exact
registry accounting, cacheline separation, busy-read guards and targeted write
prefetch raise cross-NUMA cacheline median peak from 1.293 to 4.563 Mops/s and
hash from 1.024 to 2.682. Physical ownership, references, probes and final ACKs
remain exact. Mutex still trails fresh Native results; hash whole-run throughput
is close (2.582 versus 2.606), while cacheline remains 4.497 versus 5.508.

Basic and affected fixtures, concurrent registry/ACK probes, nested/early spin
and rwlock regression runs passed. All four final groups' frozen input hashes
matched after rejected candidates were restored. The report preserves full
ranges, JIT execution, per-node progress, raw archives and validation limits.
This bounded investigation is not a rerun of the full matrix.

## Complete destination matrix, 2026-10-10

The [complete report](../bench/results/10.176.26.71/bench/comparison/full-matrix-20261010T094831Z/README.md)
contains **3,960 accepted, drained sessions**: all three backends, three rounds,
and 22 worker counts (1–8 by one, then 12–64 by four). Spin/mutex include all
supported cacheline sizes and RCUHT; rwlocks include all five cacheline sizes
and RCUHT at 1%/20% writes. Every warmed peak was independently recomputed from
raw progress. Source, binary and JIT-image hashes passed verification.

KD returned JIT bodies in 824 sessions; 496 were NO_JIT controls. Descriptive
comparisons have 312 PASS, 115 FAIL and 13 MIXED_EXECUTION points out of 440.
These rate comparisons do not establish JIT gain for NO_JIT controls or satisfy
strict rwlock parity by pooling mixed execution types. Original runner parity
and status-separated statistics remain available.

The temporary 66-vCPU VM placed 64 workers on distinct physical cores, with
32 worker cores per NUMA node. Collector vCPU 65 and QEMU services share the
last worker's physical host core at 64 workers; that point includes collection
contention. The `ondemand` governor and captured kernel stayed unchanged.
An interrupted idle scan left 94 completed, drained sessions; its evidence is
retained separately and the entire group was rerun without changing measured
source. The final scores use three rounds throughout. The archive reproduced
all exported CSV bytes from an extracted copy, and the regular 64-vCPU boot
was restored and verified afterward.

## Earlier bounded 64-vCPU destination, 2026-10-10

The [bounded report](../bench/results/10.176.26.71/bench/comparison/performance-20261010T081816Z/README.md)
contains tables and scaling charts for 72 RCUHT rwlock, 36 spin/cacheline and
36 mutex/cacheline sessions. All 144 passed correctness and drained. KD met
the strict target of matching both alternatives on best warmed peak and median
whole-run throughput at 10 of 16 selected configurations: seven of eight rwlock,
three of four spin and none of four mutex configurations. Mutex remains the
largest measured throughput gap.

The run used the Ubuntu host at `10.176.26.71`, 64 pinned vCPUs with 32 per NUMA
node, collector CPU 63 and the host's `ondemand` governor. It included the nine
captured working-tree edits; spin/mutex used 64 post-work rounds and rwlock used
four. Of 48 KD sessions, 33 returned JIT bodies and 15 were `NO_JIT`; the report
keeps those execution types explicit. This bounded selection is not the full
matrix and does not establish a performance gain over another physical host.

The [initial migration receipt](../bench/README.md#vm-migration-validation) used
60 vCPUs. The historical measurements below used the original 40-vCPU guest on
`380G10`. Keep source identity, topology, workload and frequency policy separate
when reproducing any report; the current environment is in
[the project guide](PROJECT_GUIDE.md#guest-workflow).

## Original-host RCUHT rwlocks, 2026-10-10

The [rwlock comparison](../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md)
ran 270 RCUHT sessions: 1% and 20% writes, fifteen thread counts, three backends
and three rounds. All runs produced correct results and shut down cleanly.

The target was to match or exceed **both** Native and TCLock on **both** best peak
and median whole-run throughput. KD met that target at 21 of the 30 combinations
of write percentage and thread count. It fell short at nine. At 1% writes, TCLock
still leads when workers span NUMA nodes. At 20%, KD's largest gap is at two threads.

ABI3 allowed hash writers to execute through JIT. The tested implementation also
added native fast writers and separated the count and gate into different cache
lines. Those changes improved the screened results but increased the lock to
128 bytes. The report keeps all trials and raw data, and separates runs with
observed JIT bodies from NO_JIT runs. These results belong to the rwlock work,
not the earlier spin/mutex phase.

## Original-host spin/mutex measurements

The final baseline contains 540 sessions: KD, TCLock and Native; spin and mutex;
cacheline and hash; three rounds at 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24,
28, 32 and 36 threads. The complete trial archive contains 2,286 performance
sessions, including rejected candidates and their rechecks.

Runs use the existing `6.1.159-kdclobber2` recovery kernel with `nopvspin`,
2.5 GHz host frequency limits, NUMA on, UBSAN off for the KD provider and
48,000 warmup operations per worker. Measurements last two seconds; peak
selection uses a valid 300 ms window after 300 ms settling. All samples,
whole-run rates, min/median/max/spread and worker/node progress are retained.

The measured source is `d2868e3`. Unrelated working-tree changes were excluded.
Every run that required KD JIT or TCLock mutex delegation recorded the required
execution count. Data and shutdown checks also passed. Allowed native controls
are listed separately. TCLock spin delegation counts were not measured.

## Spin/mutex outcome

Spin/hash still trails TCLock even though JIT runs almost all contended bodies.
Mutex/hash may have a competitive short peak while completing much less work over
the whole run. Work is also distributed unevenly between NUMA nodes. Seeing every
worker make some progress, or limiting batch size, does not prove that a worker
can never starve.

Neither final translator/memory candidate was kept. The combined candidate changed
terminal-completion proofs and code-buffer allocation, but repeatedly reduced
whole-run mutex/hash throughput at 36 threads. The memory-only candidate repeatedly
lost more than 3% of mutex/cacheline peak throughput at 16 threads against the
opening baseline. Its losses against the closing baseline stayed below 3%.
Both candidates were reverted, so the provider still allocates the code pool at
initialization.

Earlier profiles suggest that translated traversal, request handling and coordination
between native and delegated work contribute to the cost. Increasing the JIT share
or removing a few instructions did not reliably improve throughput. Total cache
misses and ordinary cycle samples cannot isolate remote-memory latency. Earlier profiles and failed
experiments remain in [benchmark history](../bench/results/380G10/bench/tclock_compare/HISTORY.md).

## Implementation and deferred designs

Current contracts live in the [spin](design/spin_implementation.md),
[mutex](design/mutex_implementation.md) and [rwlock](design/rwlock_implementation.md)
guides. KD retains the two-word wrapper ABI, mandatory mutex JIT, native-first
mutex acquisition, exact Linux ownership,
source leases, final ACK and frame retirement. The default KD combiner cap is
**1,024 bodies**, with separate bounded NUMA scans. Spin allows at most
eight refill PAUSEs; with deferred remote work, only before body 128. Mutex
defers at most 64 linked remote nodes, services or hands them off at the 128-body
cohort boundary, and uses targeted successor write prefetch. Its task cache
keeps exact acquisition references and disables routing at the zero transition;
inactive identity lifetime is separately bounded and protected by RCU.

Earlier versions of task retention and mutex NUMA grouping were rejected on the
original host. The current implementations and new-host evidence are documented
in the [mutex guide](design/mutex_implementation.md). Broad prefetch and
register-residency trials did not establish repeatable gains. The
[outlined operation/context API](design/protocol_simplification.md)
is an unimplemented design alternative; it requires separate validation and
matched callers. No additional optimization run is scheduled by this document.

[Known limitations](TODO.md) remain documented. Reproduction settings and
acceptance rules belong to the [spin/mutex](../bench/tclock_compare/README.md) and
[rwlock](../bench/rwlock_compare/README.md) runner guides;
source cleanup is not a performance rerun.
