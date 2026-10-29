# Publish ordinary mutex READY before linking

Candidate `a46bf63c44bc81a32901dfd55e3c88a16954e262` remains isolated on
`work/mutex-early-ready-20261029`. Documentation-first commit
`2de87974f23269e7ce9acad07b30adebbcf79960` precedes the implementation.
Scoped correctness passed, but all ten contended mutex points still regress.
Do not promote this candidate.

## Implementation and validation

Only `kernel_module/mutex/queue.inc` and `kernel_module/mutex/waiter.inc` change
production behavior. An ordinary successor completes all packet/count/debug work,
checks its private INIT state, release-stores READY, then release-publishes the
incoming queue link. Wait entry only observes 0/WAIT/READY/CLAIMED and rejects
INIT; it never rearms an early completion or cancellation. The helper is explicitly
always-inline inside the notrace slowpath, avoiding an instrumented function entry
after publication. Private-head INIT-to-WAIT and role-C post-frame/source
INIT-to-READY CAS transitions remain unchanged.

The owned epoch still protects READY from withdrawal. Exact current descriptors
and cold promotion to CLAIMED retain all physical-owner, source/frame/node,
exceptional ACK and removal-before-wake obligations. Keep 65536 initial PAUSE
iterations, one current descriptor, 1024/1024 delegation limits and separate OSQ
and delegation memberships. There is no ordinary proxy-response polling loop,
new parked producer protocol, fairness change or oversubscription redesign.

All fifteen selected drivers passed on the first attempt, including a new actual
C slowpath publication fixture with 52 modeled routes and ten mutations. That
fixture substitutes stack switching and proxy execution; separate source-order
checks preserve both assembly entry contracts. Early0/WAIT/CLAIMED, INIT refusal,
count/debug/link ordering, first-head behavior, generation reuse and late role-C
publication are checked. Both W=1 default-off and mode2 provider builds passed;
[unit/build receipts](unit-builds.json) preserve commands and source identity.

[Independent ELF inspection](elf-independent.json) verifies both actual builds:
count/debug/INIT check precede READY, incoming link and direct polling; no helper,
fentry call or entry RMW intervenes. Both retain the budget, withdrawal CAS,
private-head CAS, source-before-role-C READY and cold promotion-before-gate-open
ordering. Default-off execute_cs (including its cold part), run_combiner and
epoch_end bytes and relocations exactly match the retained-current predecessor.
Total text grows 16 bytes; no timing gain follows from that size observation.
Broader function-graph/role-C tracing remains unvalidated.

All eight live blocks passed: mutex/rwsem basic, queued scheduling, five local
role cases and true C2/node0-to-W33/node1 transfer. Basic runs each completed
1,600,000 operations, with 1,586,938/1,589,853 returned mutex/rwsem JIT bodies.
All 74 context records balance preemption, migration and IRQ state. Every role
case matches ownership and expected native/JIT/early-inner behavior, with zero
theft and empty exact source retirement. Unchanged local-API correctness was not
repeated. [Live verification](live-verification.json) records this limited scope.

## Initial spin counters

Optional mode2/schema4, c01/post256, one two-second observation per point:

| Workers | Helper wait episodes | Within helper budget / pin retained | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: | ---: |
| 20 | 8,032,957 | 100% / 100% | 7,882 | 99.4418% |
| 36 | 7,569,351 | 100% / 100% | 14,725 | 99.7691% |

Both points record zero expiry, withdrawal, forced cancellation, FULL resume,
unavailable selection and admission refusal. Descriptor reservations and exact
retirements match 8,025,112/7,554,650; retain-current calls are thirteen each.
[Independent counter checks](diagnostic-verification.json) verify complete
before/after subtraction and conservation. Already-completed entries count as
helper episodes: the fractions measure neither CPU spinning time nor elapsed
time since READY publication. The bounded READY prefix is sampled once per
admission, never awaited. These observations meet the spin target in this scope
and establish no universal >99% guarantee or performance score.

## One-round comparison

Mode0, c01/c16, post256, two seconds, workers 1/8/20/32/36/60, exactly one
observation per point. All 36 mutex/rwsem points have correct data, zero worker
and collector errors, and exact drain. The saved pinned baseline is
`1c86d6d1a15d96d75c09504f1041772247707804`. Both arms' 72 raw sessions,
rate calculations, CPU/NUMA/call-shell identities and actual provider defaults
were checked. Workload bytes and non-build runner AST are unchanged. Baseline
blocks ran 9.00/9.07 hours earlier in the same boot; this is not randomized adjacent A/B.

| Workload | Workers | Pinned Mops/s | Early READY Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916812 | +0.03% |
| c01 | 8 | 3.678105 | 3.584485 | -2.55% |
| c01 | 20 | 4.590029 | 4.060661 | -11.53% |
| c01 | 32 | 4.486160 | 4.009652 | -10.62% |
| c01 | 36 | 4.209552 | 3.841735 | -8.74% |
| c01 | 60 | 4.335256 | 3.865071 | -10.85% |
| c16 | 1 | 1.916744 | 1.917299 | +0.03% |
| c16 | 8 | 3.548560 | 3.337707 | -5.94% |
| c16 | 20 | 4.227567 | 3.889928 | -7.99% |
| c16 | 32 | 4.188997 | 3.812513 | -8.99% |
| c16 | 36 | 3.853043 | 3.669400 | -4.77% |
| c16 | 60 | 3.946234 | 3.724899 | -5.61% |

Contended mutex losses span 2.55–11.53%. Rwsem changes span -3.80% to +5.96%
with 1% writes and -10.02% to +2.11% with 20% writes. All individual values and
JIT status remain in [the comparison](comparison.json). One observation supplies
no repeat variance or proof of performance neutrality. c01/20 rises only from
the preceding 4.038826 to 4.060661 Mops/s and remains below pinned 4.590029.
The admission path still repeats some exact checks; consolidating only duplicate
checks at the same boundary is the next source-level hypothesis. Every logical
predicate, fresh generation validation and later completion/cold proof must remain.

A separate [offline rwsem point review](rwsem-nojit-review.md) examines the prior
retained-current c01/1%/8 loss. Its workload bytes, virtual data/lock addresses
and CPU placement match baseline/current; delegation counters are zero and the
retained writer mutex fast path records zero failed CAS. Workers consumed about
two CPU-seconds each, and whole/peak rates both fell. Reviewed local provider
instructions are identical, with a placement shift. These receipts do not support
parking or execution of the changed delegation wait path as that point's cause.
Physical page/cache placement and rwsem phase costs are unmeasured; no cause or
systematic local-API regression is established.

Kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0 and 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory. No
real-world API workload, kernel change or reboot ran here.

## Preservation

Four trees, eight archives and 8,957 paths were verified against compressed
SHA256 and complete path/type/size/mode/owner/link inventories. Raw copies are
under `bench/results/10.176.26.71/raw/tests/mutex-early-ready-20261029/`.
[Archive verification](archive-verification.json) covers unit/build, live,
diagnostic and nano evidence. No archived code ran on the source host.
