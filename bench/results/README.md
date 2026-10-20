# Results by physical machine

`master` retains the KD-only mutex foundation from `d2a2304`, with the shared-node
and bounded-locality implementation measured at `752fec1`, and the accepted
reader/writer semaphore (rwsem) waiting implementation from `c21345b`. See
[current performance](../../docs/PERFORMANCE.md) for results and retained
regressions, and [terminology](../../docs/TERMINOLOGY.md) for execution and
measurement definitions.

The [unified mutex API receipt](10.176.26.71/tests/mutex-api-20261020/validation.json)
records 11 basic/affected VM checks, compiled anonymous DIRECT continuations,
160,000 live API operations and four real owner ACKs across both nested release
orders. Both live probes drained; they do not claim live JIT bodies or throughput.
The receipt preserves failed development attempts and the allocator preparation
used for the successful retries.

The [continuation correctness stage](10.176.26.71/tests/native-continuation-20261020/README.md)
completed basic/affected checks, nine live probes and 16 resident-list sessions
at their recorded revisions. The separate
[public-mutex regression replay](10.176.26.71/bench/mutex-public-regressions-20261020/README.md)
completed 120 serial, valid, drained timings using the original `d21a1e3` inputs.
Four of seven losses remained separated, two overlapped, and one fell below
the provisional screen. All seven causes, two class gaps and dynamic
host-worker variability remain unresolved; that replay did not sample latency.
Performance acceptance stays open.
Original and follow-up archives, failures and ranges remain distinguishable.

The later [seven-point latency diagnostic](10.176.26.71/bench/mutex-latency-20261021/README.md)
completed 252 serial sessions, 126 exact KD retirements and 4,073,421 sampled
complete-operation observations. All basic/affected VM checks and 5,218,772
independent integrity checks passed. Its immediate host endpoint failed at
125 versus 67 threads. The report retains the earlier capacity failure, three
failed preflights, class changes, observer effects, all per-repeat results and
range/CV statistics. All seven causes remain unresolved; sampled p95 evidence
does not establish acquisition latency or performance acceptance.

The [fresh 32-byte mutex / Native / TCLock comparison](10.176.26.71/bench/mutex32-native-tclock-20261020/README.md)
records 567 accepted, drained sessions from `bd9d4ce` with unchanged `752fec1`
production: c01, c08, RCUHT, seek SET/END, pipe bytes and pipe capacity at nine
worker counts from one to sixty, three repetitions. At sixty workers KD medians
exceed both controls in all seven workloads; at eight workers KD still trails
Native on the three synthetic workloads. Synthetic entry witnesses, returned
API bodies and local NO_JIT runs remain separate, including c08's split
two-worker point. Fresh basic/runner checks, all 567 kernel logs and an
independent 668,688-check archive/arithmetic review passed. The report retains
full ranges, separate peaks, plots, source bindings and host-placement limits.

The [shared-node mutex comparison](10.176.26.71/bench/mutex32-mcs-20261020/README.md)
records 72 valid, drained timings across separate preceding-compact,
rejected-FIFO, old256 and retained `752fec1` sources: c01/post64, SEEK_SET n16
and pipebytes/query n16 at eight/sixty workers, three repetitions. The retained
32-byte, native-aligned mutex shares preallocated node storage between separate
OSQ/delegation memberships and uses a 256-body locality boundary. At sixty
workers its c01/seek/pipe medians improve 14.3%/13.6%/16.5% over the preceding
compact arm; pipe remains 9.2% below old256. Eight-worker ranges overlap and
c01's median is 2.1% lower. The rejected all-cohort FIFO policy remains at
`archive/mutex32-fifo-20261020`; results are never pooled. Each new source passed
17 basic/affected checks, runner programs and three live probes. The report
separates synthetic entry witnesses from API returned-body counts and preserves
the sequential-block, limited-repetition and remaining-gap qualifications.

The [`05876a4` taskname/xattr comparison](10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
records direct calls to the original string APIs within generated spin bodies:
567 validated, drained sessions with fresh Native/TCLock controls. At 60 workers,
KD reaches 4.521/2.368/0.573 Mops/s for taskname/xattr n16/xattr n128, above Native
and below TCLock. The report retains low-count regressions, execution shares,
profiles, failed development attempts and a separate quota-continuation check.
The [preceding dispatcher comparison](10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
and [checked-helper baseline](10.176.26.71/bench/taskname-xattr-20261018/README.md)
retain their own source and evidence; their timings are never pooled.

The [instruction-exit receipt](10.176.26.71/tests/native-instruction-exit-20261018/README.md)
records the later checked waiter-continuation feature and its failures/final
correctness checks separately from accepted throughput measurements.
The [32-byte mutex receipt](10.176.26.71/tests/mutex32-20261019/README.md)
records native geometry, automatic auxiliary-state retirement, basic and affected
VM checks, live JIT/native continuation and preserved failures. It does not
extend historical performance claims to the compact object.
The subsequent [compact-mutex screen](10.176.26.71/bench/mutex32-screen-20261019/README.md)
compares c01, c08 and RCUHT against fresh Native/TCLock controls at 1/8/32/60 workers.
All 108 sessions passed and drained; KD's contended whole-run medians trail both
controls. Peak results and all variation remain separate in that report.
The [additional compact-mutex API screen](10.176.26.71/bench/mutex32-api-screen-20261019/README.md)
adds 144 valid, drained pipebytes/pipecap/seek SET/seek END sessions. Pipe KD
stays local and beats both controls under contention; seek KD returns JIT
bodies and trails both controls in whole-run medians. The report retains
execution categories, substantial control variation and one incomplete final
per-CPU diagnostic row separately from measurement validity.
The [compact registry investigation](10.176.26.71/bench/mutex32-opt-20261019/README.md)
then compares fresh 256-byte, initial compact and optimized compact KD versions:
63 plain timings and six separate profiles, all valid and drained. `fcbacbe`
removes registry locking from reads and ordinary reference updates, recovering
1.36–3.69× throughput on the tested c01/c08/seek cases while preserving size,
alignment and protocol. The report retains remaining gaps versus the old object
and the pipe regression caused by its local-to-JIT execution change. Exact
counter meanings, affected checks, failures and source identities remain separate.
The [direct-index and reference-transfer comparison](10.176.26.71/bench/mutex32-index-20261019/README.md)
adds separate `44f8eb6` and `e999008` arms beside fresh `f0bd68d` RCU and
`0324e60` inline baselines. Both new arms keep the native-aligned 32-byte object;
the provider preallocates a 65,536-slot, 16 MiB table, and `e999008` transfers
the immediate gate reference and borrows established ownership during unlock.
All 96 plain timings and eight c01 profiles passed and drained across c01/c08,
SEEK_SET n16 and pipebytes n16 at eight/60 workers, three plain repetitions.
The final version improves pipe medians by 7.4%/7.1% against RCU at eight/60
workers, but remains 23.6%/31.1% behind the old inline object. c01 and seek
also retain gaps; all API sessions returned JIT. Independent archive, source
and statistics audits passed. Separate check bundles, source identities,
first-index results and the controller preparation failure remain retained.
Synthetic entry witnesses do not prove returned bodies; API completions, mixed execution classes and
sequential-block limitations are explicit. Earlier RCU measurements are unchanged.
The [packed-state investigation](10.176.26.71/bench/mutex32-packed-20261019/README.md)
retains fresh previous-32-byte, versioned-node and old-256-byte pipe comparisons,
separate profiles, focused checks, the initial harness compile failure and
independent archive/arithmetic audits. The candidate improves pipe throughput
while preserving the remaining gap; historical rounds remain separate.

The [reference-traffic investigation](10.176.26.71/bench/mutex32-traffic-20261019/README.md)
adds fresh `e999008`/`0324e60` controls, counted fetch-add pins, a rejected cached
index experiment and final inlined guards. All 120 plain runs and ten unscored
pipe profiles passed and drained. Final pipe medians improve 3.2%/1.9% at
eight/60 workers versus the prior 32-byte implementation, but remain
21.6%/31.0% below the old 256-byte object. Other workloads show mixed changes.
The report retains source identities, reference lifetime reasoning, three
affected-check bundles and the corrected summary-analysis refusal.
The [2026-10-18 consolidation checks](10.176.26.71/tests/main-consolidation-20261018/README.md)
validate organization and tooling separately from the measured runtime.
The [feature reintegration checks](10.176.26.71/tests/feature-reintegration-20261018/README.md)
validate the earlier ordinary-only rwsem, restored snapshots and benchmark safeguards,
including retained delegation failures. Historical owned/adaptive mutex and
owned-gate rwsem reports remain separate evidence.

The [accepted rwsem comparison](10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records the `c21345b` Native/KD c01/c08/RCUHT comparison at 1%/20% writes on the
standard 1–60-worker grid, preserving the selected KD mutex protocol. It retains
candidate screens, baseline controls, execution groups, diagnostic profiles and
source identities. Acceptance includes the substantial two-worker regressions;
the recorded report and raw measurements remain unchanged. Its separate Native/TCLock/KD spinning-rwlock reference uses
all three payloads and both mixes at 1/8/32/36/60 workers, 270 completed sessions;
those non-sleeping results are not pooled with rwsem. The
[focused validation receipt](10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records the matching functional and execution checks.

The [initial rwsem writer-delegation comparison](10.176.26.71/bench/rwsem/20261018/README.md)
remains the historical shared-queue baseline. Its high-count regressions, split
execution statuses, returned-body counts and raw evidence are preserved.

The [KD-only mutex round](10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md) contains 504 fresh accepted/drained sessions
at 1–8 workers by one and 12–60 by four, three repetitions, with accepted KD,
Native and TCLock controls. It measures the removal of Linux mutex backing while
retaining legacy delegation. At 60 workers KD-only reaches
4.838/5.130 Mops/s for c01/post64 and
pipebytes n16. Full scaling, low-count variation, separate regression follow-ups,
intermediate trials and independently replayed evidence remain in the report.

The [2026-10-17 legacy compatibility comparison](10.176.26.71/bench/comparison/mutex-legacy-compat-20261017T122742Z/README.md)
contains 504 accepted/drained sessions and a verified 20,567-file archive,
including its failed first preparation. It compares independent instruction/image
backports against fresh legacy, with Native/TCLock controls. Raw evidence is in
`10.176.26.71/raw/bench/mutex-legacy-compat-20261017T122742Z/`; the report retains all results, regressions,
plots, source identities and replay receipts.

The [latest recovered-legacy mutex grid](10.176.26.71/bench/comparison/mutex-legacy-grid-20261016T125529Z/README.md)
contains all 378 requested c01/post64 and pipebytes n16 sessions, with separate
source-verified archives and fresh Native/TCLock controls. Its raw archive is
`10.176.26.71/raw/bench/mutex-legacy-grid-20261016T125529Z/`; all samples and
failed offline-analysis invocation logs remain preserved.

Use the physical benchmark host as the machine identifier, even when the run
executes inside its VM. Source edits remain on `380G10`; all new compilation,
tests and benchmarks run in the VM on `10.176.26.71`.

| Machine | Results |
| --- | --- |
| [`380G10`](380G10/README.md) | Historical 40-vCPU tests and comparisons; retained evidence and source-host scratch files |
| [`10.176.26.71`](10.176.26.71/README.md) | Migrated VM validation and all subsequent tests and benchmarks |

Each machine directory uses the same structure:

```text
bench/results/<machine>/
  bench/<runner>/<run>/       compact benchmark reports, tables and figures
  tests/<suite>/<run>/        compact test reports
  raw/bench/<run>/            original benchmark archives and extracted evidence
  raw/tests/<run>/            original test archives and extracted evidence
```

Compact reports are tracked in Git. `raw/` is ignored and is not included in source
synchronization. Keep full raw evidence, including failures, partial runs, commands,
source/binary hashes, CPU/NUMA topology, kernel identity and final drain checks.
Do not pool measurements from different machines or VM topologies.

Live guest output must remain outside `/root/host_fs/kdlock`, as required by the
runners' frozen-input checks. New output paths are:

```text
/root/kdlock-evidence/10.176.26.71/bench/<run>
/root/kdlock-evidence/10.176.26.71/tests/<run>
```

Copy or archive those runs to the corresponding host `bench/results/10.176.26.71/raw/`
directory. Assembly exports follow the source run's parent under `assembly/`;
retain them with the run's evidence. Use a fresh run name for every execution.
Publish only compact summaries under `bench/` or `tests/`.

Historical raw files moved from `bench/.tmp/` to
`bench/results/380G10/raw/legacy/`. This includes source-host scratch files whose
individual run provenance is not established; retain their existing manifests
rather than assuming they are benchmark samples. The proven new-host migration
archive is separated into `bench/results/10.176.26.71/raw/bench/`.
`bench/.tmp` is a local compatibility symlink to the legacy directory, and its
old migration-run path redirects to the new-host archive. These links preserve
old references without duplicating evidence. A fresh checkout contains the
compact reports, without raw archives or these local links.

The migrated guest also retains original-host archives under
`/root/kdlock-evidence/380G10/legacy/`, with compatibility links at their original
top-level paths. The Python environment remains reachable through its original
path. New-host guest runs are stored separately under `10.176.26.71/`.

Frozen JSON/CSV records, captured commands and fixed Git links keep their original
paths and bytes. For retained compact reports, the relocation mapping is:

| Original path | Current path |
| --- | --- |
| `results/<machine>/<category>/` | `bench/results/<machine>/<category>/` |
| `bench/rwlock_compare/results/<report>` | `bench/results/380G10/bench/rwlock_compare/<report>` |
| `bench/tclock_compare/results/<report>` | `bench/results/380G10/bench/tclock_compare/<report>` |
| `bench/.tmp/<entry>` | `bench/results/380G10/raw/legacy/<entry>` |
| `bench/.tmp/migration-20261010T070707Z` | `bench/results/10.176.26.71/raw/bench/migration-20261010T070707Z` |
