# Retain CLAIMED only across cold mutex boundaries

Runtime `e2b685157cae904ece7a2ea62379cfcf82121794`, validated through
`2af70f39a7091c34b5ccab98452f0726336cb2c0`, remains isolated on
`work/mutex-epoch-retained-20261029`. Documentation-first commit
`5478421ec23f65b3661810b00aa52382832e8536` precedes the implementation.
Scoped correctness passed, but all ten contended mutex points still regress.
This candidate must not be promoted.

## Protocol and correctness

An ordinary current request stays READY under an exact private epoch,
physical-owner/COMBINER proof, unreleased outer lock, and node/lock/generation
descriptor. Ordinary selection no longer writes CLAIMED. Before reopening
withdrawal at a cold boundary, a retained current is promoted to CLAIMED.
Cold registration, generic/FULL service, native/role exchange, early outer
unlock and delayed-tail cleanup retain explicit strict closure checks. A native
outer callback after node retirement checks saved batch state, never the old
node. Descriptor removal still precedes cancellation, completion or result0.
Exact source/frame/node and exceptional ownership ACK obligations remain.

Initial spin budget 65536, one current descriptor, the admitted READY cohort,
1024/1024 caps, 32-byte mutex and 320-byte node are unchanged. OSQ/delegation
memberships remain separate. Ordinary proxy execution does not poll for queue
responses. Withdrawn origins still use runnable polling and `cond_resched`;
there is no new parked producer protocol or oversubscription redesign.

Fourteen selected unit drivers first produced twelve passes and two failures.
Both failures occurred before fixture execution: full-line source-extraction
markers omitted the same-line node parameter. Fixture-only
`2af70f39a7091c34b5ccab98452f0726336cb2c0` corrects those two strings.
Both retries and the W=1 provider build passed. All fourteen selected drivers
therefore have successful applicable receipts; [earlier failures remain](unit-attempts.json).
Negative cases cover promotion/withdrawal races, no WAIT resurrection, later-owner
COMBINER rejection, omitted cold promotion/closure, exact generation and lock
identity, retained native/role/tail obligations and removal before wake.

[Independent emitted-code review](elf-independent.json) confirms no ordinary
CLAIMED store in execute_cs. The cold promotion store precedes private-epoch
clearance and the gate CAS that reopens withdrawal. Required READY and strict
cold proofs are emitted; the INIT guard and 65536-before-scheduling order remain.
Diagnostics/TSC are off, static per-CPU storage is 7600 bytes. Total text grows
1401 bytes; code size alone establishes no timing effect. The provider build
retains the same eight warning lines as the predecessor, including known
handwritten-return/stack objtool limits; it is not warning-free mitigation proof.

All eight live blocks passed: mutex/rwsem basic, queued scheduling, five local
role cases and C2/node0-to-W33/node1 transfer. Basic runs each completed
1,600,000 operations, with 1,588,350/1,590,220 returned mutex/rwsem JIT bodies.
All 74 context rows balance preemption, migration and IRQ state. Every role case
matches physical owner transfer and expected native/JIT/early-inner behavior,
records zero theft with at least 10,000 attempts, and retires sources to state2
with zero modules/frames/writers. The unchanged local-API probe was not repeated.
[Live verification](live-verification.json) records this bounded scope.

## Separate spin counters

Optional mode2/schema4, c01/post256, one two-second observation per point:

| Workers | Wait episodes | Within budget / initial pin retained | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: | ---: |
| 20 | 8,067,247 | 100% / 100% | 7,897 | 99.6834% |
| 36 | 7,512,139 | 100% / 100% | 14,619 | 99.7606% |

Both points record zero expiry, withdrawal, forced cancellation, FULL resume
and admission refusal. Exact current descriptors acquired/retired match
8,059,368 and 7,497,547; one not-ready selection at 36 workers stops immediately.
Retain-current calls are 14/12, not counts of CLAIMED stores. Schema4 claims
count descriptor reservations. The READY histogram samples a bounded compatible
prefix once per admitted epoch and never waits for eight arrivals. The >99%
target is met only for these measured wait episodes, not established universally
or as a CPU-time fraction. [Counter verification](diagnostic-verification.json)
checks independent subtraction and counter conservation; these are not scores.

## One-round nano results

Diagnostic mode0, c01/c16, post256, two seconds, workers 1/8/20/32/36/60,
exactly one observation per point. All 36 mutex/rwsem points completed with
correct data, no worker/collector errors and exact drain. The saved pinned
baseline is `1c86d6d1a15d96d75c09504f1041772247707804`. Both arms' 72 raw
sessions, CPU/NUMA/call-shell identities, rate calculations and provider defaults
were checked. Actual candidate ELF metadata confirms diagnostic/TSC mode0,
claim_slots1, ready_policy epoch, budget65536 and caps1024/1024. Workload bytes
and non-build runner AST are unchanged. The baseline blocks ran 8.29/8.36 hours
earlier in the same boot; this is not adjacent randomized A/B.

| Workload | Workers | Pinned Mops/s | Retained Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916188 | -0.01% |
| c01 | 8 | 3.678105 | 3.538616 | -3.79% |
| c01 | 20 | 4.590029 | 4.038826 | -12.01% |
| c01 | 32 | 4.486160 | 3.959104 | -11.75% |
| c01 | 36 | 4.209552 | 3.785354 | -10.08% |
| c01 | 60 | 4.335256 | 3.899392 | -10.05% |
| c16 | 1 | 1.916744 | 1.916337 | -0.02% |
| c16 | 8 | 3.548560 | 3.490182 | -1.65% |
| c16 | 20 | 4.227567 | 3.624824 | -14.26% |
| c16 | 32 | 4.188997 | 3.756852 | -10.32% |
| c16 | 36 | 3.853043 | 3.607032 | -6.38% |
| c16 | 60 | 3.946234 | 3.743838 | -5.13% |

Contended mutex losses span 1.65–14.26%. Rwsem changes span -24.91% to +7.07%
with 1% writes, and -4.19% to +1.79% with 20% writes. All values and execution
labels remain in [the 36-row comparison](comparison.json). In particular,
rwsem c01/1%/8 records NO_JIT in both arms: the large loss at that point cannot
be assigned to executing the changed proxied-body path from these receipts.
Single observations do not establish variance or isolate code layout, placement
and scheduling effects. No favorable aggregate replaces the failed mutex gate.

Removing the per-body notification improves c01/20 from 3.952647 to 4.038826
Mops/s, still 12.01% below 4.590029. The next isolated experiment moves ordinary
READY publication after all metadata/count/debug work and before a release
incoming queue link, then makes wait entry observe-only. This may avoid the
current post-link INIT-to-READY RMW; it is a hypothesis, not a measured gain.
Keep private-head INIT-to-WAIT and role-C post-frame/source INIT-to-READY CAS
unchanged, with early result/cancellation, publication ordering and slot reuse
checks before live validation. No fairness change is proposed.

Kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0 and 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory. No
real-world API workload, kernel change or reboot ran here.

## Preservation

Five trees, ten archives and 8,804 paths were verified against compressed SHA256
and complete path/type/size/mode/owner/link inventories. Raw copies reside under
`bench/results/10.176.26.71/raw/tests/mutex-epoch-retained-20261029/`.
[Archive verification](archive-verification.json) includes the failed unit attempt,
retry, live checks, diagnostics and all measurements. Archived code was never
executed on the source host.
