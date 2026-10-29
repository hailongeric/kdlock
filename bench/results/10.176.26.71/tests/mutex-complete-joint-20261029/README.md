# Ordinary COMPLETE frame and queue retirement together

Source `965156ff660b0c2ae5942b73033f743585270bbf` remains an isolated candidate on
`work/mutex-complete-joint-20261029`, following documentation-first commit
`2c273302ea15320e62886223871b0bb53392aa1b`. Runtime `3232d47ca4d9d90a4ec576d55ac028be3c9da7ba` starts from
`99f383624faa872a76521d1b5be7faea586591c1`; it does not carry the exact-phase predicate or READY-prefetch
experiments. The later source commit changes only two fixture integer types.
No runtime promotion or performance acceptance follows from this report.

Only the ordinary ABI2 first-wrapper COMPLETE path uses the new joint transition.
After wrapper/timing callbacks, it freshly checks every frame shape, packet/routing
pair, exact current node/key/generation, strict READY, private epoch, unreleased
outer, physical owner and separate origin-owner predicate. One nonblocking tail
attempt precedes frame retirement. On success the frame becomes inaccessible,
the node packet becomes COMPLETE, the descriptor is removed, counters advance,
and the last node access publishes the wake. A private result prevents the caller
from replaying completion or accessing that node after wake. A failed terminal
attempt preserves the exact descriptor and source lease, ends the ordinary loop,
and uses the existing CLAIMED promotion and cold delayed-link retirement.
Generic external frame-retirement behavior, SELFTEST observers, legacy/FULL/native
and role-exchange paths remain separate. Layouts, 65,536-PAUSE budget, 1024/1024
limits, publication and source-trust policy are unchanged.

The [unit/build record](unit-build-verification.json) preserves three attempts:

1. Runtime3232's initial gate ran twelve selected drivers: eleven passed; the new
   complete driver failed compilation on three fixture signedness comparisons.
   The controller stopped before any provider build or live test.
2. Source965 corrected only the CPU-ID mock type and encoded-tail comparison.
   Only the failed driver was repeated: ordinary composition passed 62 cases and
   2,585 checks, SELFTEST composition passed 8 cases and 1,041 checks, and all
   fourteen negative mutations were detected. Ordinary and mode2 W=1 builds
   passed. SELFTEST preparation omitted `tests/kernel/hotlock/lifetime_selftest.c`,
   so that build failed and its controller remains `completed:false`.
3. A fresh SELFTEST-only tree copied the required correctness source types with
   a hash manifest, then the W=1 build passed. The manifest contains
   49 tracked files matching committed bytes
   and 4 separately listed
   untracked generated files; it is not an all-tracked-input claim. No runtime
   source changed.

The final applicable unit gate therefore combines the unchanged eleven passes
with the corrected-driver pass; it is neither a full suite nor twelve fresh
passes. The actual composed fixture covers frame/node pairing, owner/origin
changes, terminal delayed links, packet/descriptor ordering, immediate node reuse,
post-wake poisoning, caller private outcomes, exact diagnostic classification and
SELFTEST observers. [Emitted-code review](elf-independent.json) is retained as a
separate artifact for the ordinary, mode2 and SELFTEST providers. Successful
SELFTEST compilation and its userspace fixture do not constitute a live SELFTEST
provider run.

All eight serial live blocks recorded pass and drain: basic spin/mutex/rwlock/rwsem
in one block, queued scheduling, five local role cases and actual C2/node0 to
W33/node1 role exchange. The basic results are:

| Family | Operations | Returned JIT bodies |
| --- | ---: | ---: |
| spin | 1,600,000 | 1,595,124 |
| mutex | 1,600,000 | 1,589,275 |
| rwlock | 1,600,000 | 26,245 |
| rwsem | 1,600,000 | 1,589,421 |

All 74 joined-task context rows balance preemption,
migration and IRQ state. Expected owner transfer, native/JIT completion and early
outer-unlock behavior, zero theft and exact source retirement were checked in
all six role cases. [Live verification](live-verification.json) records the scope
and source identities. The queued probe establishes eventual scheduling while
an owner holds the lock, not actual parking or a measured spin-budget duration.
These test-ioctl mechanisms are not real-world syscall workload substitutes.

Optional mode2/schema4 observations use c01/post256, one two-second observation
at each worker count. Their rates are not nano scores.

| Workers | Helper episodes completed within budget | Initial pin retained | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: | ---: |
| 20 | 8,444,737 / 8,444,737 (100.0000%) | 8,444,737 | 8,260 | 8,238 (99.7337%) |
| 36 | 7,763,861 / 7,763,861 (100.0000%) | 7,763,861 | 15,091 | 15,066 (99.8343%) |

[Diagnostic verification](diagnostic-verification.json) independently checks
before/after subtraction and conservation. Nonzero boundary counters and every
selection outcome are retained explicitly:

- Workers 20: no nonzero boundary counters; selection results {"claimed": 8436493, "current_not_ready": 0, "self_current": 0}.
- Workers 36: no nonzero boundary counters; selection results {"claimed": 7748787, "current_not_ready": 0, "self_current": 0}.

The denominator is result-wait helper entries, including already-zero entries;
it is not every acquisition, CPU time, READY-to-completion elapsed time or a
parking rate. `claims` counts logical exact-current descriptors, not CLAIMED
stores. READY prefixes are sampled once at successful admission, never awaited.
No universal greater-than-99-percent guarantee follows from these two points.

The diagnostics-free round covers c01/c16, post256, workers 1/8/20/32/36/60,
one two-second observation per point: twelve mutex and twenty-four rwsem points.
All 36 have correct data, zero worker/collector errors and exact drain; 72 archived
sessions across the candidate and pinned baseline were compared. Provider defaults,
workloads, call shells, CPU/NUMA placement, source and recomputed rates were verified.
The saved pinned baseline is `1c86d6d1a15d96d75c09504f1041772247707804`; its mutex/rwsem blocks began 12.50/12.58
hours earlier in the same boot. This is not adjacent randomized A/B.

| Workload | Workers | Pinned Mops/s | Joint COMPLETE Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916705 | +0.02% |
| c01 | 8 | 3.678105 | 3.642237 | -0.98% |
| c01 | 20 | 4.590029 | 4.040063 | -11.98% |
| c01 | 32 | 4.486160 | 4.157263 | -7.33% |
| c01 | 36 | 4.209552 | 3.931976 | -6.59% |
| c01 | 60 | 4.335256 | 3.987721 | -8.02% |
| c16 | 1 | 1.916744 | 1.916686 | -0.00% |
| c16 | 8 | 3.548560 | 3.402946 | -4.10% |
| c16 | 20 | 4.227567 | 4.089316 | -3.27% |
| c16 | 32 | 4.188997 | 3.999449 | -4.52% |
| c16 | 36 | 3.853043 | 3.678703 | -4.52% |
| c16 | 60 | 3.946234 | 3.707582 | -6.05% |

10 of ten contended mutex observations are below the pinned baseline.
All ranges and individual JIT statuses remain explicit:

- mutex_contended: 10 points, -11.98% to -0.98%.
- mutex_uncontended: 2 points, -0.00% to +0.02%.
- rwsem_w1: 12 points, -5.39% to +9.11%.
- rwsem_w20: 12 points, -3.94% to +0.49%.

[Every point](comparison.json) retains one valid round and the default
`complete:false`/`expected_rounds:3` summary fields. There is no repeat variance
or confidence interval. NO_JIT points cannot establish an executed joint-path
effect; mixed rwsem deltas do not by themselves identify a cause. This report
does not claim that the candidate closes the gap or is suitable for promotion.

The [waiter instruction review](waiter-cost-review.md) identifies a separate
source cost: the saved baseline's steady poll executes four instructions, while
the parent candidate's READY poll within budget executes thirteen. This joint
candidate leaves that waiter source unchanged. Finishing before expiry therefore
does not remove the extra per-poll state and budget work. Instruction counts do
not establish its cycle cost or contribution to the throughput gap; the counter
sessions are also separate from default-off performance sessions. A separate
READY-first branch layout will test this hypothesis while preserving every state
check and exact threshold/CAS ordering. It starts from `99f38362`, without this
joint transition, so their effects are not pooled.

Kernel `7.0.0-38-kdlock1`, build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0 and 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory. No real-world
API workload, kernel modification or reboot is established by this campaign.

[Archive verification](archive-verification.json) covers 6 trees,
12 archives and 10,604 inventoried paths, including
both failed preparation/gate attempts and the separate SELFTEST retry. Raw evidence
is under `bench/results/10.176.26.71/raw/tests/mutex-complete-joint-20261029/`.
Compressed hashes and complete inventories were verified without executing
archived code on the source host.
