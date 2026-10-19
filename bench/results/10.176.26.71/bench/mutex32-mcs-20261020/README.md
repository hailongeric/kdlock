# Shared MCS nodes and bounded NUMA cohorts

The retained implementation is **`752fec1`**. It keeps the **32-byte mutex with
native 8-byte alignment**, shares preallocated waiter storage between OSQ and
delegation, and extends the locality cohort from 128 to 256 bodies. At sixty
workers, observed whole-run medians improve **14.3% for c01, 13.6% for seek and
16.5% for pipe** over the preceding 32-byte source. Pipe remains **9.2% below
the fresh old-256-byte control**; this round narrows rather than closes that gap.

## Fresh balanced comparison

Values are whole-run median Mops/s from three plain 2000 ms repetitions per
workload/worker/source point. Higher is better. The
[complete table](comparison-table.md) retains every minimum/maximum and the
rejected FIFO trial; [comparison.json](comparison.json) preserves full precision.

| Workload | Workers | Prior 32-byte `826faa6` | Retained `752fec1` | Old 256-byte `0324e60` | Retained / prior change | Retained / old change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c01/post64 | 8 | 6.134 | 6.005 | 7.494 | -2.1% | -19.9% |
| c01/post64 | 60 | 4.251 | 4.857 | 4.959 | +14.3% | -2.1% |
| SEEK_SET n16 | 8 | 4.290 | 4.668 | 4.875 | +8.8% | -4.3% |
| SEEK_SET n16 | 60 | 3.708 | 4.211 | 4.011 | +13.6% | +5.0% |
| pipebytes n16 | 8 | 5.376 | 5.602 | 6.856 | +4.2% | -18.3% |
| pipebytes n16 | 60 | 4.199 | 4.890 | 5.385 | +16.5% | -9.2% |

The eight-worker ranges overlap for all three prior/retained comparisons;
these noisy medians do not establish a uniform single-node improvement. At
sixty workers the retained ranges are above the prior compact ranges for all
three workloads. These are descriptive results from sequential source blocks,
not randomized pairs, confidence intervals or a full scaling grid. Sources,
workloads, caller shells and instrumentation settings are never pooled.

The source blocks ran in order `826faa6`, `0324e60`, `f4d359d`, `752fec1`.
`826faa6` has the preceding retained `76af844` production. The later
`locality256` label remains `comparison_arm=false` and `cohort_role=trial` in
its original receipts; [the explicit extended analysis scope](OPERATIONS-v2.md)
includes it separately. Selecting it for maintenance does not rewrite its
collection role or rename the first candidate.

## What changed and what the experiments show

OSQ was already an abortable MCS-style queue. It now uses the same four
preallocated CPU/slot nodes as delegation. Its 24-byte link/state subrecord
occupies former padding at node offset 104, so the node remains 320 bytes with
64-byte alignment and the register packet still starts at 128. Both tails use
direct encoded CPU/slot addressing. Their links and notification fields remain
independent because cancellation and delegated completion have different
lifetimes; this is shared node storage, not one merged queue.

An initial delegation head explicitly lends its reserved node during physical
acquisition. An ordinary spinner reserves a temporary slot and releases it only
after OSQ unlink/handoff completes, before scheduling. Exhaustion follows the
existing sleeping path. The borrowed reservation remains live through sleeping
physical acquisition. No auxiliary hash, shared lock reference count, registry
lock, new RCU mechanism or caller cleanup obligation is introduced. The exact
physical owner, waiter records, source leases, frames and unlock ACKs remain
intact. See the [storage/lifetime review](source-review.md).

The first trial `f4d359d` rejoined all deferred NUMA work at 128 bodies and then
continued FIFO to the existing 1024 total cap. Its sixty-worker whole-session
ratios reached about 1008/1013/1020 bodies per combiner for c01/seek/pipe, but
throughput fell 28.8%/30.9%/13.3% versus the prior compact source. It passed its
correctness checks, but is rejected as a performance policy and retained at
`archive/mutex32-fifo-20261020`, with all measurements and source unchanged.

`752fec1` keeps exactly that shared-node implementation and changes the batch
policy. A cohort uses a 256-body locality boundary and the existing finite
64-node scan budget. Eight or more deferred requests receive handoff with their
complete prefix rejoined first; smaller prefixes are serviced by the current
owner before FIFO continuation. The total cap remains 1024. Refusal, native
completion, terminal-link retirement and early outer release retain their own
boundaries. The [locality review](source-review-locality256.md) explains ordering
and the twenty terminal scenarios.

At sixty workers, whole-session bodies/combiner medians change from
129.912/128.049/128.027 to **257.267/255.517/255.504** for c01/seek/pipe.
These ratios include warmup/checks and are not measured-phase chain-length
histograms. The FIFO and locality trials differ only in batching production,
which supports retaining locality-aware handoff over maximal FIFO continuation
in this setup. No isolated timing attributes a gain to node sharing alone,
and no new HITM/cache-transfer profile was collected. A locality cohort does
not guarantee that every body is local after the scan budget is exhausted.

## Execution evidence, environment and checks

All **72 timings** completed with validated worker results and drain. The 24
c01 sessions witness actual generated-body entry; that workload has no returned
completion probe. The 48 API sessions witness both entries and matching returned
completions. A NORMAL image alone is never treated as execution evidence.
At sixty workers the retained measured API return shares are 97.305% for seek
and 97.440% for pipe. No timing/profile classes are mixed.

The workloads are c01 with 64 dependent post-work rounds, SEEK_SET n16 and
pipebytes/query n16, using 64-byte API values. Workers use CPUs 0 through N-1;
collector 63 is separate. All workers warm up for at least 48000 operations;
API warmup also lasts at least 1000 ms. NUMA is enabled, total batch limit is
1024, entry ratio is 2, prefetch is 2 and provider UBSAN is off. See the exact
frozen commands in [the collection plan](OPERATIONS.md) and matrix receipts.

All builds/tests/live work ran in the regular `10.176.26.71` VM: 64 vCPUs,
24 GiB RAM, NUMA CPUs 0-31/32-63, kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, and boot
`b65f0205-c8f9-4385-8b13-039cbce243a6`. The real recovery snapshot remained
`before-mutex-kdonly-20261017T140354Z`. Kernel, boot policy, host pins and
frequency policy were unchanged; transient QEMU service workers remained on
CPU 63. The guest is idle with checked `752fec1` production retained.

Both `f4d359d` and `752fec1` separately passed dependency checks, provider
`W=1` builds, daemon `-Werror` builds, **17/17 basic and affected checks**,
11 runner-plan cases and 13 runner-report cases. Each passed ordinary mutex,
rwsem and instruction-exit live probes with drain. Each provider log retains
48 warning lines, including locale, macro and assembly/objtool diagnostics;
these are successful builds, not warning-free builds. The new OSQ fixture
passes 13 scenarios and detects ten negative controls. The retained terminal
fixture covers twenty scenarios and detects thirteen negative controls.
Serial fixtures do not prove every weak-memory or scheduler interleaving.
No full suite, kernel rebuild/reboot, RT/ww_mutex, lockdep or oversubscription
validation was performed. [validation.json](validation.json) binds the checks
to measured production; [health.json](health.json) binds all **78 kernel logs**
with zero recorded runtime-fault matches and final drain.

## Preserved evidence

All source snapshots (including private `.inc` files), prepared providers,
source/ELF manifests, generated images, per-worker samples, kernel logs,
commands and both trial versions are preserved. The seven grouped raw archives
and inventory are under the ignored
[raw evidence directory](../../raw/bench/mutex32-mcs-20261020/);
[archives.json](archives.json) records their hashes. The compact export is a
review aid, not a substitute for those archives. Versioned v2 analysis helpers
extend scope explicitly while the original collectors remain unchanged.

Independent [source/archive review](archive-review.json) passed **145,186
checks** over 12,226 archive members and 22 source manifests, with zero issues
or ancillary exceptions. The [source binding](source-review.json) retains exact
Git identities, prepared-source reconstruction and private include coverage.
The separate [arithmetic audit](statistics-review.json) passed **85,095 checks**,
reconstructing all 72 timing windows and 24 source-specific groups. Its
[independent ratio calculation](statistics-retained-ratios.json) agrees with
the table above. These audits read inert archive/Git bytes on `380G10`; they
did not execute archived source or run tests outside the VM.
