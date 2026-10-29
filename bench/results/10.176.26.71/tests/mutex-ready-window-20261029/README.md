# Long initial spin with eight READY claims

Runtime `43418d5a3c8659311b0d008310f70e78f245eeee`, validated with fixture/parser
corrections through `406c679bd70c1589754c5083039b95051aba297a`, remains isolated on
`work/mutex-ready-window-20261029`. Runtime bytes did not change between these
commits. Correctness passed in the recorded scope; the performance gate failed.
Do not promote this candidate.

## Policy and correctness

The initial budget is 65,536 PAUSE iterations. An origin publishes READY while
pinned; a competing READY-to-CLAIMED versus READY-to-WAIT CAS arbitrates proxy
execution and expiry. Eight exact invocation descriptors form the rolling
cohort. Ordinary claims do not poll an acknowledgement. A completed terminal
body with a delayed producer link exits the execution loop and retains its
claim/source/node until cold retirement and one result wake. Native ownership
ACKs remain. Physical OSQ and delegation links remain separate. Withdrawal uses
runnable polling and cond_resched, not a new parked-producer protocol.

First unit attempt at `43418d5a`: 9 passed, 5 failed to compile due to fixture
declaration/observer lifetimes. At `b8e242379b2a9ddd184d6f6fae3acee9a101206c`,
8 passed and one negative mutant failed compilation because its removed call
left an unused mock function. The inline accessor correction at `406c679b`
passed the remaining driver and its required failing mutants. All 14 selected
basic/affected drivers therefore have successful applicable receipts; failures
remain archived. No warning flags or ownership assertions were removed.

The VM-built default-off provider passed W=1 compilation. ELF metadata reports
budget 65536, cohort 8, total/local caps 1024/1024, diagnostics 0 and TSC shift 0;
static per-CPU storage remains 7600 bytes and no mutex pin diagnostic symbols
remain. This does not establish performance neutrality.

Live mutex and rwsem basic each completed 1,600,000 operations with
1,586,318/1,590,670 returned JIT bodies. Queued scheduling passed after 400,000
warm operations, four final effects and exact idle. All five local role cases
and actual C2/node0-to-W33/node1 exchange passed. The queued 14 and role 60 context
rows all restore preemption, migration and IRQ state. Role cases retain exact
C-to-W physical transfer, zero thefts, source retirement and expected JIT/native
routes. See [independent receipt verification](live-verification.json).

## Initial-spin observations

Separate mode2 instrumented c01/post256, two-second single observations:

| Workers | Wait episodes | Completed before budget | Retained initial pin | Full eight-slot selections |
| --- | ---: | ---: | ---: | ---: |
| 20 | 5,467,322 | 100% | 100% | 99.2956% |
| 36 | 5,619,598 | 100% | 100% | 98.3328% |

Both points recorded zero expiry checks, withdrawals, cancellations, FULL
resumes and failed readiness claims. Claims/retirements match 5,461,981 and
5,608,685. These are actual delegation wait episodes, including result/head
handoff, not all acquisitions, CPU time or returned JIT bodies. The measurements
meet the >99% target at these two points only. They do not prove a universal
bound. No parking inference is needed: no measured origin withdrew its pin.
Instrumented rates are not used as performance scores.

## One-round nano results

Diagnostics-free c01/c16, post256, two seconds, workers 1/8/20/32/36/60,
one observation per point: mutex 12 and rwsem 24 (1%/100% writes). All 36 finished
with correct data, placement, positive worker progress and exact retirement.
The session field `functional=false` denotes timed mode, not a failed check.

Mutex comparison against saved pinned
`1c86d6d1a15d96d75c09504f1041772247707804` on the same boot:

| Workload | Workers | Pinned Mops/s | READY Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.915022 | -0.07% |
| c01 | 8 | 3.678105 | 2.594055 | -29.47% |
| c01 | 20 | 4.590029 | 2.759128 | -39.89% |
| c01 | 32 | 4.486160 | 2.807282 | -37.42% |
| c01 | 36 | 4.209552 | 2.930186 | -30.39% |
| c01 | 60 | 4.335256 | 2.957989 | -31.77% |
| c16 | 1 | 1.916744 | 1.914548 | -0.11% |
| c16 | 8 | 3.548560 | 2.335097 | -34.20% |
| c16 | 20 | 4.227567 | 2.673785 | -36.75% |
| c16 | 32 | 4.188997 | 2.735088 | -34.71% |
| c16 | 36 | 3.853043 | 2.768517 | -28.15% |
| c16 | 60 | 3.946234 | 2.896619 | -26.60% |

Contended mutex losses span 26.60–39.89%. Thus frequent scheduling or response
ACK polling cannot explain this candidate's loss at the two instrumented
points. Per-request atomic claim traffic and cohort bookkeeping remain
hypotheses requiring isolated measurement; this evidence does not apportion
cycles to either cause. Increasing the already-unexpired budget cannot remove
that synchronization cost.

Rwsem 1% changes versus saved pinned points range -2.24% to +6.86%; w100 has no
matched point in the saved w1/w20 baseline, so no percentage is inferred.
[All 36 measurements](comparison.json) preserve those distinctions.

All runs retain kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`, CPUs 0–31/node0 and 32–63/node1,
collector 63 and configured 2.0 GHz/no_turbo. Saved baseline points are earlier
in the same boot; one round supplies no repeat variance or strict timing
qualification. No real-world API workload, kernel change or reboot ran here.

## Preservation

Six evidence trees, twelve archives and 8,806 paths were copied and verified
against compressed SHA256 and complete path/type/size/mode/owner/link inventories.
Raw copies reside under
`bench/results/10.176.26.71/raw/tests/mutex-ready-window-20261029/`.
[Verification](archive-verification.json) retains all failures and successful
runs. No archived workload was executed on the source host.
