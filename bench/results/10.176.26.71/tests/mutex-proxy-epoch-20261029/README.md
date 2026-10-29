# Batch-gate admission for READY mutex waiters

Runtime `41d887bd2bbf7e11b16635db3fb0f812290d9b02`, validated through
`2d6e313b294632485ee973606813c1c14b6c3cc9`, remains isolated on
`work/mutex-proxy-epoch-20261029`. The later commits change fixtures only.
Correctness passed in the recorded scope, but performance failed the acceptance
gate. This candidate must not be promoted.

## Protocol and validation

The candidate retains 65,536 initial PAUSE iterations and eight exact claimed
requests. After expiry and `need_resched`, an origin must reserve WITHDRAW in the
existing full-word gate before withdrawing READY. The physical owner admits an
ordinary proxy batch with one HELD-to-COMBINER CAS; a reservation conflict causes
handoff without waiting. Admitted claims use READY loads and CLAIMED stores,
without per-node claim CAS or response polling. Every gate update preserves a
concurrent withdrawal reservation. The reservation clears before origin unpin.

Epoch admission ends before every registration, FULL/generic dispatch, sleepable
service, native custody, early release and delayed terminal polling boundary.
The current claim stays pinned when required; future claims are cancelled and
READY origins may withdraw again. Exact source/frame/node and exceptional native
ownership ACK obligations remain. Physical OSQ and delegation memberships remain
separate. Withdrawal remains runnable polling with `cond_resched`; no parked
producer protocol is introduced. Total and NUMA limits remain 1024/1024.

The first 18 selected unit drivers produced 12 passes and six failures. Fixture
linkage and a negative-test oracle correction produced four further passes and
two failures on retry. Both remaining failures shared an optimized proxy-load
mock: GCC 15.2 IPA inlining marked complementary pointer-check call paths
unreachable, after which a later pass emitted an unconditional state failure.
The preserved 21 diagnostic arms include eight passes and thirteen failures.
Keeping only that mock out of inlining passed at O2 with all production
predicates, negative mutations and warning flags intact. The final two drivers
and the default-off W=1 provider build passed. Thus all 18 selected drivers have
successful applicable receipts; earlier failures remain preserved. See
[unit attempts](unit-attempts.json) and [compiler evidence](compiler-diagnosis.json).
No broader compiler root cause or absence of all undefined behavior is claimed.

[Independent inspection](elf-independent.json) of the actual VM provider verifies
the correct initial state branch, 65536-budget-before-scheduling order, reservation
clearance before unpin and ordinary byte-store claims. Diagnostics and TSC sampling
are off; static per-CPU storage is 7600 bytes. The provider does not reproduce the
fixture's malformed path.

All nine serial live blocks passed: mutex/rwsem basic, local API correctness,
queued scheduling, five local role cases, and C2/node0-to-W33/node1 exchange.
Basic runs completed 1,600,000 operations each with 1,587,473/1,590,206 returned
JIT bodies. Local API checks covered 160,000 operations and 2,048 objects,
including cancellation, signal, handoff, sleep and I/O paths. All 74 queued/role
context rows restore preemption, migration and IRQ state. Exact retirement is
empty, physical C-to-W ownership changes and expected native/JIT routes match,
and theft probes record no theft. The two modified gate checks permit only
HELD with an optional WITHDRAW bit during W's native suffix; owner, waiter-count
and unknown-bit checks remain. [Live verification](live-verification.json)
records this bounded scope, not arbitrary nesting support.

## Initial-spin observations

Optional mode2 instrumentation, c01/post256, one two-second observation per point:

| Workers | Wait episodes | Within initial budget | Retained initial pin | Full eight-slot selections |
| --- | ---: | ---: | ---: | ---: |
| 20 | 5,653,830 | 100% | 100% | 99.2946% |
| 36 | 6,493,518 | 100% | 100% | 98.3261% |

Both points recorded zero expiry checks, withdrawals, forced cancellations,
FULL resumes and epoch admission refusals. Successful admissions were 5,533 and
12,632; claims and exact retirements match 5,648,314 and 6,480,903. At 36 workers,
five future candidates were not READY, causing immediate selection stop without
waiting. These counters measure actual delegation wait episodes, not all lock
acquisitions, CPU time or JIT completions. They meet the >99% initial-spin target
at these two points only. Instrumented observations are not performance scores.

## One-round nano comparison

Diagnostics-free mutex and rwsem, c01/c16, post256, two seconds, workers
1/8/20/32/36/60, one observation per point. All 36 points completed with correct
data, zero worker/collector errors, expected execution status and exact drain.
The saved pinned baseline is `1c86d6d1a15d96d75c09504f1041772247707804`.
Both arms' 72 raw sessions, CPU/NUMA/call-shell identities, rate calculations,
provider defaults and actual diagnostic-off metadata were checked. Workload bytes
are unchanged; the runner diff adds build-only diagnostic controls with unchanged
non-build execution. The baseline ran about 6.8 hours earlier in the same boot.

| Workload | Workers | Pinned Mops/s | Epoch Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916446 | +0.01% |
| c01 | 8 | 3.678105 | 2.564894 | -30.27% |
| c01 | 20 | 4.590029 | 2.996456 | -34.72% |
| c01 | 32 | 4.486160 | 3.030260 | -32.45% |
| c01 | 36 | 4.209552 | 3.334995 | -20.78% |
| c01 | 60 | 4.335256 | 3.365203 | -22.38% |
| c16 | 1 | 1.916744 | 1.914466 | -0.12% |
| c16 | 8 | 3.548560 | 2.433546 | -31.42% |
| c16 | 20 | 4.227567 | 2.851246 | -32.56% |
| c16 | 32 | 4.188997 | 2.919250 | -30.31% |
| c16 | 36 | 3.853043 | 3.163629 | -17.89% |
| c16 | 60 | 3.946234 | 3.250630 | -17.63% |

All ten contended mutex points regress, by 17.63–34.72%. Rwsem changes span
-22.49% to +3.47% with 1% writes, and -9.11% to +1.41% with 20% writes.
[All 36 matched rows](comparison.json) retain the individual results. No average
across workloads or source versions is used as an acceptance result.

Removing per-node claim CAS does not close the gap. The instrumented samples
show no origin withdrawal or response waiting; extending their unexpired spin
budget would not reduce the observed ordinary-path bookkeeping. Future-claim
selection and repeated descriptor/CPU checks remain a performance hypothesis,
not a measured cycle attribution. The next isolated candidate keeps one exact
current descriptor while the admitted epoch protects all READY origins from
withdrawal. It retains current identity checks, every cold-path epoch closure,
existing successor prefetch and the 65536/1024/1024 settings. Observing eight
READY candidates once per epoch, only in optional diagnostics, must not become
a requirement to wait for eight arrivals.

Kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0 and 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory; one round
supplies no repeat variance or proof of zero regression. No real-world API
workload, kernel change or reboot ran here.

## Preservation

Nine trees, eighteen archives and 9,784 paths were verified against compressed
SHA256 and complete path/type/size/mode/owner/link inventories. Raw copies reside
under `bench/results/10.176.26.71/raw/tests/mutex-proxy-epoch-20261029/`.
[Archive verification](archive-verification.json) covers failed attempts, compiler
dumps, successful checks and measurements. Archived code was not executed on
the source host.
