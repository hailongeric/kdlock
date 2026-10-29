# Notification-prefetch ablation

Isolated source `3e6a623ef07cd9fce2c3fb5f66fc543d7b0a5415` adds only
`prefetch(&next->locked)` to the existing successor preheat, on circular-window
source `209f8b4011f00cfe03b1326b8067076f2bfb2783`. The published queue
reservation keeps that node live. The hint neither observes an ACK nor bypasses
the mandatory acquire acknowledgement before stack/GS use. No layout, window
bound, ownership or cancellation change is included.

Two basic unit programs and the affected outer-progress, terminal and policy
drivers passed (5/5). Mutex/rwsem live basic each completed 1,600,000 operations
and final idle, with 1,587,845 and 1,590,456 returned JIT bodies respectively.
[Exact checks and observations](results.json) are retained.

The same-boot round used c01/c16, two seconds, post256, workers0..N-1,
collector63 and 1024/1024, on boot `677b7afa-5358-4ece-a650-5f4a4adecd55`.
Each of twelve mutex points ran once. Rates are whole-run Mops/s; baseline is
pinned `1c86d6d1`, ring is `209f8b40`, and prefetch is `3e6a623e`.

| Workload | Workers | Baseline | Ring | Prefetch | vs ring | vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916194 | 1.916365 | +0.01% | +0.00% |
| c01 | 8 | 3.678105 | 2.767549 | 2.772067 | +0.16% | -24.63% |
| c01 | 20 | 4.590029 | 3.324957 | 3.363148 | +1.15% | -26.73% |
| c01 | 32 | 4.486160 | 3.300471 | 3.368181 | +2.05% | -24.92% |
| c01 | 36 | 4.209552 | 3.648937 | 3.654829 | +0.16% | -13.18% |
| c01 | 60 | 4.335256 | 3.692465 | 3.711188 | +0.51% | -14.40% |
| c16 | 1 | 1.916744 | 1.915829 | 1.916164 | +0.02% | -0.03% |
| c16 | 8 | 3.548560 | 2.647178 | 2.707778 | +2.29% | -23.69% |
| c16 | 20 | 4.227567 | 3.168771 | 3.170607 | +0.06% | -25.00% |
| c16 | 32 | 4.188997 | 3.194408 | 3.175785 | -0.58% | -24.19% |
| c16 | 36 | 3.853043 | 3.344820 | 3.286381 | -1.75% | -14.71% |
| c16 | 60 | 3.946234 | 3.297987 | 3.524750 | +6.88% | -10.68% |

At twenty workers c01 improved only 1.15% over the ring, to 3.363148 Mops/s,
while remaining 26.73% below the pinned baseline. Other contended changes versus
ring range -1.75% to +6.88%; one round supplies no repeat variance. This does
not close the performance gap or prove/disprove a particular cache-miss cause.
The candidate remains isolated and is not promoted. No rwsem timing round or
real-world API benchmark ran for this ablation.

The next diagnostic scope separates retained-window occupancy, repeated FULL
resumes/cancellation, logical ACK waiting and sampled ACK-access cycles. Those
instrumented rates are not comparable performance scores.

Two completed trees are preserved in four archives, with hashes and all 2,462
paths [verified offline](archive-verification.json). Raw copies are under
`bench/results/10.176.26.71/raw/tests/mutex-pin-prefetch-20261029/`. Guest
roots are `tests/pin-prefetch-20261029` and `bench/pin-prefetch-nano-20261029`
below `/root/kdlock-evidence/10.176.26.71/`.
