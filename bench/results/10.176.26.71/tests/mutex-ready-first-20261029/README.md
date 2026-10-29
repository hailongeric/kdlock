# READY-first initial waiter polling

Candidate `2dbcd7afbf141dd63dcf0086b65fd0da4b32d6f7` remains isolated on
`work/mutex-ready-first-20261029`, following documentation-first commit
`28723e536c84efd4a7a1d4f2892818c9b40ca5ac`. It starts from
`99f383624faa872a76521d1b5be7faea586591c1` and includes neither joint COMPLETE retirement, the specialized
exact-phase predicate nor the READY-prefetch experiment. This report records
scoped evidence without promoting the runtime or assuming performance parity.

Only `kd_mutex_wait_for_result` changes at runtime. During the positive initial
budget, one acquire-loaded READY equality proves the common state; all other
values still take exact zero, WAIT or CLAIMED handling and invalid-state rejection.
Each READY/CLAIMED observation spends one PAUSE and one budget decrement. Once
the budget expires, a separate loop considers scheduling/withdrawal using the
state sampled before the final initial PAUSE, without an extra threshold reload.
A lost withdrawal CAS still reaches the next acquire observation before choosing
completion or forced cancellation. Reservation release, one pinned diagnostic
finish, the withdrawn wait and restoration of the original pin are unchanged.

The helper remains always-inline inside the existing notrace/shadow-stack contract.
Publication, private epoch, source/frame ownership and lifetime, cold CLAIMED
promotion, queue retirement and generic APIs are unchanged. So are the 65,536-PAUSE
default, override limits, 32-byte mutex, 320-byte node and 1024/1024 delegation
limits. Counter schema and merge code are byte-identical to the parent; the new
control flow is explicitly reviewed instead of claiming the queue source is unchanged.

All eight selected drivers and both W=1 ordinary/mode2 builds passed on their
first attempt. This includes two basic C drivers and the directly affected
wait-budget, proxy-pin, pin-diagnostic, publication, resource and outer-progress
drivers. [Unit/build verification](unit-build-verification.json) records exact
commands and observed outcomes; this is not a full suite.

The new fixture composes the actual waiter, full-word gate helpers, origin-local
accumulator and pinned merge with deterministic peer/scheduler substitutes.
Guest logs report:

| Configured PAUSE budget | Cases | Event/state/count checks |
| --- | ---: | ---: |
| 1 | 29 | 1,150 |
| 4 | 34 | 1,641 |

All 12 negative mutations were detected. Exact traces
cover final-PAUSE state changes, CLAIMED through expiry, gate/node CAS losses,
WAIT-to-zero before the next load, successful withdrawal, zero at unpin, and invalid
states in each phase. The existing notification-load mock retains its narrow
noinline boundary. These checks preserve episode counts and race ordering without
establishing hardware weak-memory or live scheduling behavior.

[Independent emitted-code review](elf-independent.json) is retained separately for
both actual providers. The common initial READY cycle executes six instructions,
versus thirteen in the parent and four in the saved pinned baseline. It performs
one notification-byte load and one PAUSE, without a call, GS access or stack access
inside that cycle. This instruction count is not a cycle estimate or throughput gain. Compiler layout,
register allocation and PAUSE cost remain relevant; source-level branch reduction
alone does not identify the prior gap's cause.

All eight serial live blocks passed and drained: mutex/rwsem basic together,
queued scheduling, five local role cases and actual C2/node0-to-W33/node1 exchange.

| Family | Operations | Returned JIT bodies |
| --- | ---: | ---: |
| mutex | 1,600,000 | 1,588,592 |
| rwsem | 1,600,000 | 1,587,448 |

All 74 joined-task context rows balance preemption, migration and IRQ state.
Expected owner transfer, native/JIT completion, early outer unlock with an inner
lock held, zero theft and exact source retirement passed in all six role cases.
[Live verification](live-verification.json) retains the bounded scope and source
identity. The queued probe establishes eventual scheduling under a held lock;
it does not measure budget duration, parking or sleep frequency. These test-ioctl
mechanisms do not substitute for real-world syscall workload evaluation.

Optional mode2/schema4 observations use c01/post256, one two-second observation
per point, separate from diagnostics-free nano scores.

| Workers | Helper episodes completed within budget | Initial pin retained | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: | ---: |
| 20 | 7,919,761 / 7,919,761 (100.0000%) | 7,919,761 | 7,751 | 7,730 (99.7291%) |
| 36 | 7,696,687 / 7,696,687 (100.0000%) | 7,696,687 | 14,971 | 14,936 (99.7662%) |

[Diagnostic verification](diagnostic-verification.json) retains exact subtraction,
conservation and the changed helper's source proof. Nonzero boundary counters and
every selection outcome are explicit:

- Workers 20: no nonzero boundary counters; selection results {"claimed": 7912025, "current_not_ready": 0, "self_current": 0}.
- Workers 36: no nonzero boundary counters; selection results {"claimed": 7681739, "current_not_ready": 0, "self_current": 0}.

The denominator remains result-wait helper entries, including already-zero entries,
not all acquisitions, elapsed READY-to-completion time, CPU spinning time or parking
rate. The budget starts in the helper after publication. Final-PAUSE completion
still marks expiry before the next observation; the split does not redefine a
within-budget episode. Logical descriptor claims are not CLAIMED stores, and
READY prefixes are sampled once at admission, never awaited. No universal
more-than-99-percent guarantee follows from these two observations.

The diagnostics-free round covers c01/c16, post256, workers 1/8/20/32/36/60:
one two-second observation for each of twelve mutex and twenty-four rwsem points.
All 36 record correct data, zero worker/collector errors and exact drain; 72 archived
candidate/baseline sessions were verified for workload/call-shell/placement,
provider defaults and recomputed rates. The pinned baseline
`1c86d6d1a15d96d75c09504f1041772247707804` began 12.93/13.01 hours earlier in the same boot. This saved-baseline
comparison is not adjacent randomized A/B.

| Workload | Workers | Pinned Mops/s | READY-first Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916123 | -0.01% |
| c01 | 8 | 3.678105 | 3.533741 | -3.92% |
| c01 | 20 | 4.590029 | 4.165138 | -9.26% |
| c01 | 32 | 4.486160 | 4.045703 | -9.82% |
| c01 | 36 | 4.209552 | 3.945769 | -6.27% |
| c01 | 60 | 4.335256 | 3.946459 | -8.97% |
| c16 | 1 | 1.916744 | 1.916703 | -0.00% |
| c16 | 8 | 3.548560 | 3.520214 | -0.80% |
| c16 | 20 | 4.227567 | 3.924135 | -7.18% |
| c16 | 32 | 4.188997 | 3.910883 | -6.64% |
| c16 | 36 | 3.853043 | 3.737431 | -3.00% |
| c16 | 60 | 3.946234 | 3.704002 | -6.14% |

10 of ten contended mutex observations are below the pinned baseline.
The complete ranges are:

- mutex_contended: 10 points, -9.82% to -0.80%.
- mutex_uncontended: 2 points, -0.01% to -0.00%.
- rwsem_w1: 12 points, -24.89% to +7.25%.
- rwsem_w20: 12 points, -2.21% to +2.13%.

[Every point](comparison.json) retains individual JIT status, one valid round and
`complete:false`/`expected_rounds:3`. No repeat variance or confidence interval is
available. NO_JIT points cannot establish a delegated-body effect, and workload-
specific rwsem deltas do not themselves identify a cause. No runtime promotion or
performance acceptance is inferred automatically from these observations.

The [rwsem c01/1%-write/8-worker outlier](rwsem-outlier.md) records
8.709909 Mops/s versus 11.595956 (-24.89%), with NO_JIT in both arms. Additional
raw candidate counters show every mutex slowpath/combiner statistic is zero.
Per-CPU hotlock totals sum to 178,291 entries, exactly 174,451 measured writes
plus 3,840 warmup writes, with no hidden reset. Source routing proves the changed
wait helper did not execute. Its runtime cost cannot explain this retained point;
indirect layout/cache or rwsem phase effects remain unresolved. Approximately two
seconds of CPU time per worker is not itself a parking measurement.

A [source-only readiness-certificate review](readiness-certificate-review.md)
considered proving an entire queue ready through a conservative gate bit. It is
not implemented: clearing the bit at a stale empty-queue observation can lose a
concurrent withdrawal, and a sound reset protocol needs broader changes. Exact
physical-owner, frame, key/generation and CPU checks would still be required,
with only limited unmeasured savings. This is not a safe basis for accepting the
current performance gap or removing existing ownership probes.

Kernel `7.0.0-38-kdlock1`, build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0 and 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory. No real-world
API workload, kernel modification or reboot is established by this campaign.

[Archive verification](archive-verification.json) covers 4 trees,
8 archives and 8,957 inventoried paths. Raw evidence
is under `bench/results/10.176.26.71/raw/tests/mutex-ready-first-20261029/`.
Compressed hashes and complete inventories were verified without executing
archived code on the source host.
