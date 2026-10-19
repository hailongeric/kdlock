# Compact mutex direct-index and reference-transfer comparison

The caller-owned KD mutex remains **32 bytes, aligned to 8 bytes**. This comparison
measured modest improvements over the fresh RCU baseline after replacing the
auxiliary registry with a preallocated direct-index table and transferring an
existing reference on immediate gate acquisition. The final candidate still trails
the 256-byte inline baseline on c01, SEEK_SET and pipe FIONREAD. All 104 sessions
completed and drained; the basic and affected checks passed for both new candidates.

At eight / 60 workers, the final candidate's median whole-run throughput versus
RCU changed by **+6.83% / +2.22% for c01**, **+3.12% / −0.35% for SEEK_SET**, and
**+7.37% / +7.10% for pipe FIONREAD**. The corresponding gaps to the 256-byte
baseline remain **−18.64% / −15.29%**, **−13.88% / −5.70%**, and
**−23.63% / −31.11%**. These are ratios of medians from three repeats in sequential
source blocks, with substantial variation in some groups; they do not establish
statistical significance or isolate a per-operation registry cost.

## Source versions and changes

| Recorded arm | Source revision | Caller object | Auxiliary-state handling |
| --- | --- | --- | --- |
| `precompact-256` | `0324e60` | 256 B, 128-byte alignment | Legacy state embedded in the lock |
| `compact-rcu` | `f0bd68d` | 32 B, native 8-byte alignment | Address hash, RCU lookup/reclamation, exact atomic references |
| `compact-index` | `44f8eb6a7d7ee89f08be57b464208a67121d2762` | 32 B, native 8-byte alignment | One preallocated slot per address hash; exact references and sequence checks |
| `compact-transfer` | `e999008cf7035c03271f8622afa3a9ef88cb197c` | 32 B, native 8-byte alignment | Same direct-index table; immediate gate acquisition transfers its invocation reference to ownership; synchronous unlock borrows that owner reference |

The RCU arm retains `f0bd68d`, the source label used for this fresh block. The
[source audit](source-review.json) verifies that all 90 production files under
`include/` and `kernel_module/` match `fcbacbe`. Earlier measurements remain in
their original reports and do not enter this comparison. The first direct-index
candidate remains a separate arm; its samples are not replaced by or pooled with
the later transfer candidate.

The direct-index provider allocates 65,536 slots, **16 MiB**, during startup.
Address collisions or reserved slots fall back to local KD physical locking
before queue publication. Ordinary mutex object count is not limited by the
delegation table, and ordinary uncontended locking does not access it. Auxiliary
lookup and retirement use no registry lock or RCU; the separate task-routing
registry retains its existing RCU protocol. Exact references prevent slot reuse,
and read-only observations validate the lifecycle sequence. The last reference
retires the slot automatically, without a caller destroy obligation.

The transfer candidate changes ownership of an already-held reference on the
immediate gate path before node reservation. Queued requests, frames, native ACKs
and early outer release keep their separate required references. Checked unlock
borrows only the current task's established owner reference, releases physical
exclusion and the scheduling gate, then performs the owner put without further
slot access. The KD physical protocol, wrapper ABI, pinned published waiters,
batching, immutable images and fail-closed instruction admission remain the same.
This validation does not establish whole-kernel replacement compatibility.

## Matched workload results

The completed matrix contains **104 valid sessions: 96 plain timings and eight
unscored c01 profiles**. Every source arm has c01, c08, SEEK_SET n16 and
pipebytes/query n16 at eight and 60 workers, with three plain repetitions per
group. All 32 timing groups are complete and have a uniform execution class.

The primary metric is **median whole-run Mops/s**. Each cell below is
`median [minimum, maximum]`, rounded to three decimals. The
[comparison JSON](comparison.json), [comparison CSV](comparison.csv) and
[session CSV](sessions.csv) preserve the repetitions, counters and separate
300 ms peak statistics. Peaks do not enter these whole-run medians.

| Workload | Workers | 256 B inline | 32 B RCU | 32 B direct index | 32 B index + transfer |
| --- | ---: | ---: | ---: | ---: | ---: |
| c01 | 8 | 6.987 [5.512, 7.498] | 5.321 [4.178, 5.578] | 5.760 [4.155, 5.954] | 5.685 [4.183, 5.727] |
| c01 | 60 | 4.998 [4.850, 5.033] | 4.141 [3.969, 4.151] | 4.238 [4.119, 4.259] | 4.234 [4.197, 4.405] |
| c08 | 8 | 4.762 [4.511, 4.825] | 5.002 [4.543, 5.107] | 4.914 [4.832, 5.158] | 4.926 [4.911, 5.231] |
| c08 | 60 | 3.591 [3.543, 3.640] | 3.870 [3.726, 3.891] | 3.985 [3.753, 4.007] | 3.984 [3.597, 4.066] |
| SEEK_SET n16 | 8 | 4.816 [4.652, 5.020] | 4.022 [3.872, 4.055] | 4.069 [3.983, 4.144] | 4.148 [3.977, 4.182] |
| SEEK_SET n16 | 60 | 3.987 [3.971, 4.007] | 3.774 [3.666, 3.790] | 3.792 [3.750, 3.924] | 3.760 [3.672, 3.900] |
| Pipe FIONREAD n16 | 8 | 7.020 [6.571, 7.029] | 4.993 [4.512, 5.001] | 4.977 [4.718, 5.216] | 5.361 [5.212, 5.542] |
| Pipe FIONREAD n16 | 60 | 5.394 [5.361, 5.415] | 3.470 [3.418, 3.490] | 3.631 [3.621, 3.644] | 3.716 [3.715, 3.717] |

Against the first direct-index candidate, the transfer candidate changes c01 by
−1.30% / −0.10%, SEEK_SET by +1.92% / −0.83%, and pipe FIONREAD by
+7.73% / +2.35% at eight / 60 workers. The extra transfer change therefore does
not show a general throughput improvement. The c08 guard workload changes by
+3.45% / +10.95% versus the inline baseline and −1.52% / +2.95% versus RCU.
The standalone plot is [comparison.svg](comparison.svg), also available as
[PNG](comparison.png).

Synthetic `jit_bodies` is an **entry witness**, with its completion probe
disabled. All synthetic groups are `WITNESSED_JIT`; that does not prove the body
returned, and their completion counts and returned shares remain null. All 48
real API timing sessions have explicit completion evidence and are classified
`RETURNED_JIT`; there is no JIT/NO_JIT class change in this fresh matrix. Returned
JIT shares still differ: the final candidate's SEEK_SET shares are 79.98% / 95.43%
and its pipe shares are 87.79% / 86.54%, versus 89.39% / 95.09% and
96.77% / 94.98% for inline. These shares use summed measured completions divided
by summed measured operations within each three-repeat group. Equal class labels
do not imply equal delegation fractions. NORMAL image publication alone is not
completion evidence.

The direct-index and transfer arms each report zero address collisions,
generation-race refusals, exhausted slots and injected refusals. They also report
65,525 and 62,207 BUSY refusals, respectively, across each arm's 26 whole sessions,
including warmup and profiles. These are **whole-session diagnostic totals**;
they do not give a measured-phase fallback rate or show that fallback was absent.

## Profiles and configuration

The [profile analysis](profile-analysis.json) contains one c01 profile at eight
and 60 workers for each version. Independent raw-line reconciliation checked
**109,687 samples**, with zero reported loss and exact agreement between retained
period sums and each report's event-count total. The table gives the auxiliary
symbol filter's share of the `sc_worker` period denominator; it includes the
matching auxiliary helpers and is not a count of auxiliary operations.

| Version | Eight workers | 60 workers |
| --- | ---: | ---: |
| 256 B inline | 0.00% | 0.00% |
| 32 B RCU | 13.80% | 5.29% |
| 32 B direct index | 11.28% | 3.95% |
| 32 B index + transfer | 12.96% | 3.82% |

The transfer profile still attributes 7.96% / 1.93% to `aux_try_ref` and
4.87% / 1.87% to `aux_put` within the worker denominator. Its auxiliary share at
eight workers is higher than the first index profile, so these profiles do not
show a uniform reduction from the second change. The mutex slowpath still
accounts for 64.80% / 91.44% of the worker denominator. Exact reference operations
remain visible, but changing delegation shares and enclosing-symbol attribution
prevent assigning the full remaining gap to those operations. Weights are
observed `cycles:k` sample periods, with separate denominators for all retained client-tree kernel
samples and `sc_worker` samples. Profiles are diagnostic and excluded from timing
aggregates. Flat instruction-pointer sampling has skid and no caller attribution;
inlined work can be charged to an enclosing symbol. Overlapping filters must not
be added as disjoint costs. Percentages are not elapsed-time or exact
cycles-per-operation measurements.

The recorded VM has 64 vCPUs, two NUMA nodes and collector CPU 63; workers use
CPUs 0–7 or 0–59. Kernel release is `6.1.159-kdclobber2`, with `nopvspin` and the
captured clobber interfaces. Each timing lasts two seconds; peak windows use a
300 ms settling interval, a 300 ms minimum window and 10 ms samples. Synthetic
warmup is 48,000 operations per worker. Real API warmup is 48,000 operations with
a 1,000 ms minimum. The provider uses UBSAN off, NUMA batching on and a 1,024-body
cap. Exact arguments, topology, source and binary hashes remain in the collection
records. The existing recovery snapshot is
`before-mutex-kdonly-20261017T140354Z`; the captured boot ID is
`b65f0205-c8f9-4385-8b13-039cbce243a6`.

Versions ran as **sequential blocks** in the order RCU, inline, direct index,
then transfer. Three repeats and observed min/max ranges do not eliminate time,
scheduling or frequency drift, establish statistical significance, or provide
confidence intervals. For c01 at eight workers, the range width is 26–31% of the
median across these arms. Ratios of medians are not paired estimates. The inline
and compact versions also differ in object layout and delegation fractions, so
the remaining gap cannot be assigned solely to auxiliary lookup. This bounded
screen does not establish performance for other workloads or topologies.

A separate [prior ELF/cacheline inspection](prior-elf-cacheline-review.json)
checks the retained old-inline and RCU API binaries from the preceding screen.
In all 18 inspected seek/pipe sessions, the hot target globals occupy a different
cacheline from the compact lock; only the setup/teardown `hook_addr` shares its
line in the inspected symbol set. This does not support that particular adjacent
hot-global false-sharing explanation. It does not rule out general alignment or
coherence costs, or establish identical placement in the new candidates.

## Checks and retained evidence

[validation.json](validation.json) records separate passing check bundles for
the index and transfer candidates. Each includes dependency checks, a `W=1`
provider build with UBSAN off, a daemon build with `-Wall -Wextra -Werror`, two
basic programs, 12 affected drivers, and live ordinary-mutex, rwsem and
instruction-exit probes. Both unit logs report **14 passed, zero failed**;
all six live probes passed and drained. Provider build logs retain 51 warning
lines per bundle, including objtool and locale warnings. This is not a full-suite
claim.

The ordinary probe verifies 32-byte size, 8-byte alignment and containing-layout
equality with the captured native mutex, plus 2,048 objects, address reuse,
no destroy obligation and no auxiliary use for ordinary locking. The index
bundle detects its three registry negative controls. The transfer bundle also
detects three borrowed-owner and five reference-transfer/unlock negative controls,
for 11 total. The check receipts preserve labels `f0bd68d-index-working-tree`
and `44f8eb6-transfer-working-tree`; exact production hashes bind them to their
respective benchmark commits rather than treating those labels as commits.

The controller preparation failure is preserved in
[preparation-failure.json](preparation-failure.json) and the archived original
`compact-rcu-preparation` directory. Hashing `__file__` under a standard-input
invocation failed before workloads started. The reviewed controller was then
executed from a file using a new directory. This is not a timing sample or an
omitted failed repetition.

[health.json](health.json) records final idle, the unchanged boot identity and
host pin/frequency-policy snapshots, and hashes for **110 kernel logs**: 104
benchmark sessions plus six live probes. The configured fault scan found no
runtime fault markers. [postprocess-commands.json](postprocess-commands.json)
retains the successful VM report commands and their exit statuses.

The seven compressed raw archives total **130,445,131 bytes**. The offline
[archive audit](archive-review.json) verifies all compressed hashes and exact
inventory membership: **16,102 members, 13,887 regular files and 212 symlinks**,
without omissions or duplicates. It checks retained file metadata and symlink
targets, all 26 source manifests, 132 binary-manifest entries and 154 JIT binaries
with their assembly/object or publication companions. The
[source audit](source-review.json) binds the current 90 production files,
including 39 private `.inc` files, to `e999008`; ten expanded provider snapshots
are independently reconstructed from original Git bytes and observation patches.
The eight API collections retain original source, preparation recipes and exact
built binaries, but do not retain expanded private provider trees. That limitation
is preserved in the source receipt.

The independent [statistics audit](statistics-review.json) also passed with no
issues: 104 raw-bound sessions, 96 plain timings, 32 groups, 104 reconstructed
peak windows and 109,687 reparsed profile samples. Source, archive and statistics
audits read retained bytes and Git objects without executing archived code or
running builds or tests on the source host. Raw archives and the hashed input
inventory remain under
[`raw/bench/mutex32-index-20261019`](../../raw/bench/mutex32-index-20261019/);
their coverage and preservation limits are recorded in the audit receipts.
