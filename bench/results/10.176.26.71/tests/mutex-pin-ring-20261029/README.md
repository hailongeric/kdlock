# Circular mutex pin window: checks and remaining performance loss

Source `209f8b4011f00cfe03b1326b8067076f2bfb2783` integrates
`18aa64df7522790b54ce67ca3f9719ea07d5aafe`. It remains isolated from `master`.
A fixed four-slot circular array replaces overlapping descriptor shifts, and
hot selection/ACK helpers are explicitly inline. Exact node/generation records,
mandatory acquire ACKs, future-pin cancellation and native/custody boundaries
remain. The selected-group bound is still four; mutex policy remains 1024/1024.

Two basic unit programs and eight affected drivers passed (10/10), including
all four ring heads, repeated wraps, cancellation, actual FULL resume and
custody mutations. The four-family basic, queued scheduling and six role cases
passed and drained. The last role case uses C2 and W33 on different NUMA nodes.
All 60 RUN/warmup task-context receipts returned zero preemption, IRQ and
migration state. [Complete live receipts](live-results.json) retain exact
source retirement and the scoped outcomes. Basic returned 1,597,244 spin,
1,587,911 mutex, 26,312 rwlock and 1,589,959 rwsem JIT bodies; each family
completed 1,600,000 operations.

The [frozen basic-provider ELF audit](basic-elf-audit.json) verifies that the
completion-path `memmove` and outlined hot pin helpers are gone. Slot clearing
still precedes wake. Remaining `memmove` calls belong to frame lock-pop code.
This is emitted-code evidence, comparing a basic provider with the prior nano
provider; it does not establish equal instrumentation or attribute throughput
loss to individual instructions.

## One-round mutex comparison

All three sources below ran on boot `677b7afa-5358-4ece-a650-5f4a4adecd55`,
Linux `7.0.0-38-kdlock1`. Settings remained c01/c16, two seconds, post256,
workers0..N-1, collector63 and 1024/1024. Baseline is `1c86d6d1`, linear
selection is `6d95745d`, and ring selection is `209f8b40`. Rates are Mops/s.
[Exact rates and candidate commands](comparison.json) retain one observation
per point and the default summary completeness fields.

| Workload | Workers | Baseline | Linear window | Ring window | Ring vs baseline | Ring vs linear |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916837 | 1.916194 | -0.01% | -0.03% |
| c01 | 8 | 3.678105 | 2.484585 | 2.767549 | -24.76% | +11.39% |
| c01 | 20 | 4.590029 | 2.788218 | 3.324957 | -27.56% | +19.25% |
| c01 | 32 | 4.486160 | 2.735999 | 3.300471 | -26.43% | +20.63% |
| c01 | 36 | 4.209552 | 3.206593 | 3.648937 | -13.32% | +13.79% |
| c01 | 60 | 4.335256 | 3.281210 | 3.692465 | -14.83% | +12.53% |
| c16 | 1 | 1.916744 | 1.916477 | 1.915829 | -0.05% | -0.03% |
| c16 | 8 | 3.548560 | 2.459460 | 2.647178 | -25.40% | +7.63% |
| c16 | 20 | 4.227567 | 2.712740 | 3.168771 | -25.05% | +16.81% |
| c16 | 32 | 4.188997 | 2.774264 | 3.194408 | -23.74% | +15.14% |
| c16 | 36 | 3.853043 | 3.078917 | 3.344820 | -13.19% | +8.64% |
| c16 | 60 | 3.946234 | 3.166728 | 3.297987 | -16.43% | +4.14% |

The ring improves all ten contended observations over linear selection by
4.14–20.63%, but still loses 13.19–27.56% against the pinned baseline.
It therefore fails the no-regression requirement and is not promoted. No rwsem
performance round was started for this rejected follow-up; its correctness
basic remains separate. No real-world API benchmark ran.

A notification-prefetch ablation and optional ACK/window diagnostics are next
investigations. An immediate ACK value may still require fetching a cacheline
written by the origin; neither logical wait counts nor source inspection alone
measure that latency. These are hypotheses, not established causes of the
remaining gap.

Three completed evidence trees are preserved in six archives, with compressed
hashes and all 7,384 paths [verified offline](archive-verification.json).
Raw files are under `bench/results/10.176.26.71/raw/tests/mutex-pin-ring-20261029/`;
guest roots are `tests/pin-ring-units-20261029`, `tests/pin-ring-live-20261029`
and `bench/pin-ring-nano-20261029` below `/root/kdlock-evidence/10.176.26.71/`.
