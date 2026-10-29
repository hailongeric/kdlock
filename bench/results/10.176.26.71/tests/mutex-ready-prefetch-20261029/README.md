# Read-prefetch the next mutex READY line

Candidate `bb3b78e98b28fa049841964fea8bddbf28f32cd8` remains isolated on
`work/mutex-ready-prefetch-20261029`, following documentation-first commit
`fe7d9aeb61c6acfd04b151653cb570b709886628`. Correctness checks passed; the
single hint did not close the performance gap. It is not promoted or carried
into the next experiment.

The only runtime change from `99f383624faa872a76521d1b5be7faea586591c1` is
`prefetch(&next->locked)` at the existing live-successor prefetch site in
`kernel_module/mutex/combiner.inc`. It hints the notification cacheline for a
later acquire READY read. It does not claim a waiter, change state or authorize
borrowed execution. All owner/PICKUP, epoch, exact node/key/generation, READY,
source/frame and retirement checks remain. Keep 65,536 PAUSE iterations,
1024/1024 limits, 32-byte mutex and 320-byte node. OSQ and delegation memberships
remain separate; ordinary combiner body loops do not wait for queue replies.

Five selected unit drivers passed: the two basic C drivers and pin-window,
terminal and outer-progress checks. The outer-progress fixture extracts the real
prefetch helper with address-only hint stubs; terminal and pin-window checks do
not execute hardware prefetch. Both W=1 ordinary/mode2 builds passed. No new
fixture was needed for this metadata-only hint. [Build receipts](unit-builds.json)
retain commands and exact source.

[Independent ELF verification](elf-independent.json) finds exactly one new
seven-byte `prefetcht0 0x131(%rax)` in run_combiner, before the existing body call,
in each mode. Removing that hint and rebasing internal targets makes normalized
combiner instructions and relocations match the parent. No call, outlined helper
or fentry is added. Executor differences are diagnostic line-number constants
and layout displacements; its owner/PICKUP/READY/key/generation checks remain.
Epoch-end bytes and relocations match exactly. Ordinary text size stays 136,911
bytes; mode2 grows 64 bytes. These facts establish emitted-code scope, not speed.

Three serial live blocks passed: mutex/rwsem basic together, queued scheduling,
and true C2/node0-to-W33/node1 role exchange. Each basic family completed
1,600,000 operations, with 1,587,960/1,589,821 returned mutex/rwsem JIT bodies.
All 24 context rows balance preemption, migration and IRQ state. Cross-NUMA
ownership and queue exchange, zero theft and exact empty retirement passed.
[Live verification](live-verification.json) preserves this smaller affected
scope; the parent's other five role cases and local APIs were not rerun.

Optional mode2/schema4 counters, c01/post256, one two-second observation each:

| Workers | Helper episodes within budget / retained pin | Admitted epochs | Epochs observing at least eight READY origins |
| --- | ---: | ---: | ---: |
| 20 | 8,334,328 / 8,334,328 (100%) | 8,166 | 8,135 (99.6204%) |
| 36 | 7,885,026 / 7,885,026 (100%) | 15,343 | 15,308 (99.7719%) |

Claims equal exact retirements at 8,326,183/7,869,709; retained-current calls are
20/12. Both points record zero expiry checks, withdrawals, forced/cancelled claims,
FULL resumes, unavailable/self selections and admission refusals. [Counter
verification](diagnostic-verification.json) checks all subtraction/conservation
identities. Helper episodes include already-zero entries; these are not CPU-time
fractions or universal guarantees. The bounded READY prefix is sampled, never awaited.

The diagnostics-free round uses c01/c16, post256, workers 1/8/20/32/36/60,
two seconds and one observation per point. All 36 mutex/rwsem points have correct
data, no worker/collector errors and exact drain. Both arms' 72 archived sessions,
actual metadata, workload identity, placement and recomputed rates passed offline
verification. The saved pinned baseline is
`1c86d6d1a15d96d75c09504f1041772247707804`; its blocks started 10.76/10.84 hours earlier
in the same boot. This is not adjacent randomized A/B.

| Workload | Workers | Pinned Mops/s | Read hint Mops/s | Change |
| --- | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.917081 | +0.04% |
| c01 | 8 | 3.678105 | 3.546007 | -3.59% |
| c01 | 20 | 4.590029 | 4.057464 | -11.60% |
| c01 | 32 | 4.486160 | 4.147038 | -7.56% |
| c01 | 36 | 4.209552 | 3.939634 | -6.41% |
| c01 | 60 | 4.335256 | 3.997362 | -7.79% |
| c16 | 1 | 1.916744 | 1.916054 | -0.04% |
| c16 | 8 | 3.548560 | 3.499466 | -1.38% |
| c16 | 20 | 4.227567 | 4.025104 | -4.79% |
| c16 | 32 | 4.188997 | 3.909225 | -6.68% |
| c16 | 36 | 3.853043 | 3.760349 | -2.41% |
| c16 | 60 | 3.946234 | 3.823019 | -3.12% |

All ten contended mutex points remain below the pinned baseline, by 1.38–11.60%.
c01/20 is 4.057464 Mops/s versus the immediate parent's 4.054040 and pinned
4.590029. Mixed small changes against the parent do not establish a hint benefit.
Rwsem changes span -36.49% to +4.58% with 1% writes and -6.82% to +2.09% with
20% writes. The large c01/1%/8 loss is explicitly retained: 7.364028 versus
11.595956 Mops/s, both NO_JIT. Its [archived counters](rwsem-outlier.json) show zero slowpath, combiner and
failed writer fast-CAS entries. The only hint call follows the unconditional
combiner counter increment, so it was not executed here; NO_JIT alone would
not establish that. The cause of the throughput loss remains unresolved. [All points](comparison.json)
retain JIT status and one observation, without a variance estimate or performance
acceptance. Default summary `complete:false`/`expected_rounds:3` fields remain.

Kernel `7.0.0-38-kdlock1`, build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot
`677b7afa-5358-4ece-a650-5f4a4adecd55`; CPUs 0–31/node0, 32–63/node1,
collector 63, configured 2.0 GHz/no_turbo. Timing remains exploratory. No real-world
API workload, kernel modification or reboot ran here.

Four trees, eight archives and 6,151 inventoried paths passed compressed SHA256
and complete inventory verification. Raw evidence is under
`bench/results/10.176.26.71/raw/tests/mutex-ready-prefetch-20261029/`.
[Archive verification](archive-verification.json) covers builds, live checks,
counters and nano. Archived code was not executed on the source host.

The next bounded candidate starts again from `99f383624faa872a76521d1b5be7faea586591c1`.
It combines the generic HELD-or-COMBINER test and the following COMBINER test
into one fresh exact-masked-phase predicate at the same existing boundaries.
Every physical-owner/PICKUP/current-task, origin pin and later lifetime check must
remain; no earlier result may be cached across a body or callback. Profiling did
not establish shared owner checks as the cause, and this source simplification
is another measured hypothesis, not a promised gain.
