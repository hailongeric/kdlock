# One-current descriptor under batch admission

Runtime `14975b6a0522b670e334e536ba079e320e8d3c85`, validated through
`82bfc1006c25767d7a319fcf175c548dcf24824a`, remains isolated on
`work/mutex-epoch-current-20261029`. The later commits correct fixtures and
one header comment; runtime bytes are otherwise unchanged. Scoped correctness
passed, but all ten contended mutex points still regress. Do not promote it.

## Protocol and validation

The candidate removes future CLAIMED descriptors, rolling refill and duplicate
CPU scans. One exact current descriptor retains the node and invocation
generation. Each selection validates physical ownership, private admission,
gate state, origin CPU and READY, then stores CLAIMED. The admitted COMBINER
epoch prevents every READY origin from withdrawing: one current descriptor
does not mean only one origin stays pinned. All registration, FULL/generic,
native, early-unlock, role-exchange and delayed-tail boundaries close admission.
The retained current remains CLAIMED while future READY origins may withdraw.
Fresh admission and checks are required on return.

The initial budget remains 65,536 PAUSE iterations before scheduling checks.
Physical OSQ and delegation links remain separate. Ordinary proxy execution
has no response-polling loop. Exact exceptional ownership ACKs, source/frame
retirement and tail-link safety remain. Expired withdrawn producers use runnable
polling and `cond_resched`; no parked delegation protocol is introduced.
The mutex remains 32 bytes, the node 320 bytes and both delegation caps 1024.

The first 13 selected unit drivers produced nine passes and four failures.
All four shared terminal scenarios that expected cancellation of future claims.
Those nodes now remain unselected READY. Fixture correction
`4c8387a55e7ee1f24895dbf8e3b81c334e617b26` checks untouched generation,
counted lock, links, completion and native state. All four retries and the
W=1 default-off provider build passed. Thus all 13 selected drivers have
successful applicable receipts; earlier failures remain in [unit attempts](unit-attempts.json).
No production assertion was removed.

[Independent ELF inspection](elf-independent.json) confirms the initial state
guard, budget-before-scheduling order, one-current admission and plain CLAIMED
stores. Optional diagnostics/TSC sampling are absent. Static per-CPU storage
is 7600 bytes. Relative to the eight-claim candidate, execute_cs is 1204 bytes
smaller and total text 1568 bytes smaller; code size is not a timing attribution.

All eight live blocks passed: mutex/rwsem basic, queued scheduling, five local
role cases and true cross-NUMA C2/node0-to-W33/node1 exchange. Basic runs each
completed 1,600,000 operations, with 1,587,618 mutex and 1,589,124 rwsem returned
JIT bodies. All 74 queued/role context rows restore preemption, migration and
IRQ state. Every role case confirms physical C-to-W transfer and zero theft;
expected native/JIT/early-inner routes and exact source retirement match.
The unchanged local-API probe was not repeated. See [live verification](live-verification.json).

## Initial-spin observations

Optional mode2/schema4 diagnostics, c01/post256, one two-second sample per point:

| Workers | Wait episodes | Within initial budget | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: | ---: |
| 20 | 7,759,558 | 100% | 7,600 | 99.6711% |
| 36 | 7,198,750 | 100% | 14,022 | 99.6434% |

Both points recorded zero expiry, withdrawal, forced cancellation, FULL resume
and admission refusal. Claims exactly match retirements: 7,751,979 and
7,184,755. One current-not-ready event at 20 workers stops selection immediately.
The histogram observes a bounded compatible prefix once per successful epoch;
it neither claims those future nodes nor waits to reach eight. Wait percentages
use actual delegation wait episodes, not all acquisitions, CPU time or JIT
completions. These samples meet the target but provide no universal >99% guarantee.
[Diagnostic verification](diagnostic-verification.json) is separate from the
performance scores.

## One-round nano comparison

Mutex and rwsem, c01/c16, post256, two seconds, workers 1/8/20/32/36/60,
one observation per point, diagnostic mode0. All 36 points completed with correct
data, zero worker/collector errors and exact drain. The saved pinned baseline is
`1c86d6d1a15d96d75c09504f1041772247707804`. Both arms' 72 raw sessions,
CPU/NUMA/call-shell identities and rate calculations were independently checked.
Candidate provider ELF modinfo verifies claim_slots1, ready_policy epoch, budget
65536, diagnostics/TSC off and caps1024/1024 in both family builds. Workload bytes
and non-build runner AST are unchanged. The baseline blocks ran 7.69/7.76 hours
earlier in the same boot, so this is not adjacent randomized A/B.

| Workload | Workers | Pinned Mops/s | One-current Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916556 | +0.01% |
| c01 | 8 | 3.678105 | 3.505432 | -4.69% |
| c01 | 20 | 4.590029 | 3.952647 | -13.89% |
| c01 | 32 | 4.486160 | 3.821095 | -14.82% |
| c01 | 36 | 4.209552 | 3.697546 | -12.16% |
| c01 | 60 | 4.335256 | 3.736442 | -13.81% |
| c16 | 1 | 1.916744 | 1.916834 | +0.00% |
| c16 | 8 | 3.548560 | 3.440157 | -3.05% |
| c16 | 20 | 4.227567 | 3.646465 | -13.75% |
| c16 | 32 | 4.188997 | 3.595035 | -14.18% |
| c16 | 36 | 3.853043 | 3.454206 | -10.35% |
| c16 | 60 | 3.946234 | 3.501632 | -11.27% |

Contended mutex losses are 3.05–14.82%. Rwsem changes span -4.41% to +6.23%
with 1% writes, and -6.79% to +1.00% with 20% writes. Individual values remain
in [the 36-row comparison](comparison.json). One observation supplies no repeat
variance; mixed rwsem signs do not establish a source-level cause.

At c01/20, removing future-claim bookkeeping recovers throughput from the earlier
2.996456 to 3.952647 Mops/s, but remains 13.89% below the pinned 4.590029.
Instrumented samples show no expiry or withdrawal, so extending that unexpired
budget would not remove ordinary-path work. The next experiment removes the
per-body CLAIMED notification while the exact private epoch makes READY stable.
It must promote the retained current to CLAIMED before reopening withdrawal for
any cold/native/tail path. Required ownership/lifetime checks remain; correctness
and no-regression acceptance are still open.

Kernel `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0 and 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory. No
real-world API workload, kernel change or reboot ran here.

## Preservation

Five trees, ten archives and 8,804 paths were verified against compressed SHA256
and complete path/type/size/mode/owner/link inventories. Raw copies reside under
`bench/results/10.176.26.71/raw/tests/mutex-epoch-current-20261029/`.
[Archive verification](archive-verification.json) includes the failed unit attempt,
successful retry, live checks, diagnostics and all measurements. No archived
code was executed on the source host.
