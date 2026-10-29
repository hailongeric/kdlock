# One fresh exact-phase ownership predicate

Candidate `ff69c57a3746634e6ba82b977c1f05ba544d065a` remains isolated on
`work/mutex-exact-phase-20261029`, following documentation-first commit
`81786e2b51c2690cc871c2fdb21d25d0ac490bf0`. It starts from
`99f383624faa872a76521d1b5be7faea586591c1` and does not include the read-hint
experiment. Scoped correctness passed; the nano no-regression gate did not.

The new private `kd_mutex_combiner_owned` replaces generic HELD-or-COMBINER plus
separate COMBINER tests at the same three boundaries: initial execute checks,
READY admission and READY pin validation. Each use freshly reads the physical
owner, rejects PICKUP and a noncurrent task, then acquire-reads the masked phase
once. Private epoch, unreleased outer, exact node/key/generation and READY checks
remain; no proof is carried across a body or callback. Generic ownership APIs,
separate origin-owner rereads, cold assertions, frame/source retirement and gate
transition helpers are unchanged. The existing phase mask deliberately ignores
high bits, including WITHDRAW; the predicate does not invent a stronger gate
transition check. The 65,536-PAUSE budget, 1024/1024 limits and layouts are unchanged.

All twelve selected drivers passed on the first attempt: two basic C drivers
plus pin-window, proxy-pin, publication, terminal, policy, outer-progress, custody,
batch diagnostics, pin diagnostics and resource checks. The actual old/new
predicates are compared over 2,880 snapshots including owner flags, null/noncurrent
tasks, all low phases, WITHDRAW and ignored high bits. Prior negative cases remain;
new mutations catch a second phase read, dropped task check and changed mask.
Both W=1 ordinary/mode2 provider builds passed. [Receipts](unit-builds.json)
retain exact commands; this is not a full-suite result.

[Independent emitted-code review](elf-independent.json) confirms fresh owner,
PICKUP/current and one masked COMBINER read at each revised boundary, with all
remaining node/origin predicates. No outlined/exported helper or new fentry appears.
Generic ownership and origin/local helpers match prior bytes and relocations;
waiter/resume instructions match after address normalization. The separate cold
phase closure deliberately retains its generic-plus-COMBINER checks. One compiler
layout difference is explicit: execute_cs has 54 static call sites instead of 53
because its unchanged cold constructor call is split between mutually exclusive
legacy and borrowed branches. No new ordinary-path helper call is introduced.
Text shrinks 165/89 bytes in ordinary/mode2 builds; that is not measured speedup.

All eight serial live blocks passed: mutex/rwsem basic together, queued scheduling,
five local role cases and true C2/node0-to-W33/node1 exchange. Both basic families
completed 1,600,000 operations, with 1,589,592/1,589,029 returned mutex/rwsem JIT
bodies. All 74 context rows balance preemption, migration and IRQ state. Expected
ownership, native/JIT and early-inner behavior, zero theft and exact retirement
passed in all six role cases. [Live verification](live-verification.json) records
this bounded scope; arbitrary nesting and unchanged local APIs are not newly validated.

Optional mode2/schema4 counters, c01/post256, one two-second observation each:

| Workers | Helper episodes within budget / retained pin | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: |
| 20 | 8,268,001 / 8,268,001 (100%) | 8,093 | 8,068 (99.6911%) |
| 36 | 7,789,653 / 7,789,653 (100%) | 15,144 | 15,118 (99.8283%) |

Claims equal exact retirements at 8,259,925/7,774,526; retained-current calls are
12 each. Both points record zero expiry checks, withdrawals, forced/cancelled
claims, FULL resumes, unavailable/self selections and admission refusals.
[Counter verification](diagnostic-verification.json) checks every subtraction and
conservation identity. Its source comparison explicitly uses this four-file change
from `99f38362`; an initial copied analyzer still expected the earlier two-file
change and was corrected before producing the receipt. Helper episodes include
already-zero entries, so these fractions are not CPU-time measurements or universal
percentages. READY prefixes are sampled once at admission, never awaited.

The diagnostics-free round uses c01/c16, post256, workers 1/8/20/32/36/60,
two seconds and one observation per point. All 36 mutex/rwsem points have correct
data, no worker/collector errors and exact drain. Both arms' 72 archived sessions,
actual provider defaults, workload identity, placement and recomputed rates passed
offline verification. The saved pinned baseline is
`1c86d6d1a15d96d75c09504f1041772247707804`; its blocks started 11.42/11.49 hours earlier
in the same boot. This is not adjacent randomized A/B.

| Workload | Workers | Pinned Mops/s | Exact phase Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916685 | +0.02% |
| c01 | 8 | 3.678105 | 3.671679 | -0.17% |
| c01 | 20 | 4.590029 | 4.018281 | -12.46% |
| c01 | 32 | 4.486160 | 4.117608 | -8.22% |
| c01 | 36 | 4.209552 | 3.959653 | -5.94% |
| c01 | 60 | 4.335256 | 3.955686 | -8.76% |
| c16 | 1 | 1.916744 | 1.915361 | -0.07% |
| c16 | 8 | 3.548560 | 3.486893 | -1.74% |
| c16 | 20 | 4.227567 | 3.828780 | -9.43% |
| c16 | 32 | 4.188997 | 3.838217 | -8.37% |
| c16 | 36 | 3.853043 | 3.736998 | -3.01% |
| c16 | 60 | 3.946234 | 3.730217 | -5.47% |

All ten contended mutex points remain below the pinned baseline, by 0.17–12.46%.
c01/20 is 4.018281 Mops/s, versus the immediate parent's 4.054040 and pinned
4.590029. Fewer phase reads did not establish a performance improvement.
Rwsem changes span -4.32% to +1.38% with 1% writes and -5.14% to +1.68% with
20% writes. [Every point](comparison.json) retains JIT status and one observation,
without a variance estimate or performance acceptance. Default summary
`complete:false`/`expected_rounds:3` fields remain.

Kernel `7.0.0-38-kdlock1`, build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0, 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory. No real-world
API workload, kernel modification or reboot ran here.

Four trees, eight archives and 8,957 inventoried paths passed compressed SHA256
and complete inventory verification. Raw evidence is under
`bench/results/10.176.26.71/raw/tests/mutex-exact-phase-20261029/`.
[Archive verification](archive-verification.json) covers builds, live checks,
counters and nano. Archived code was not executed on the source host.

The next isolated work starts again from `99f38362`, without the phase or hint
experiments. It explores a joint ordinary COMPLETE transition that validates
frame and exact pin ownership together, retires the frame, clears the descriptor
and publishes one wake without carrying a cached proof into the caller. A lost
terminal tail attempt must retain the descriptor and source lease for unchanged
cold cleanup; SELFTEST keeps its observer path. This broader change requires an
actual composed fixture, independent review, live checks and measurement. No joint-transition validation or performance gain is claimed here.
