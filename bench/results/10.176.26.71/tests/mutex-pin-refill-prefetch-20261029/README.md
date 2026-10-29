# Metadata prefetch for pin-window refill

Isolated source `8de65c9431c2ac89cffc25ab7467032b9402ae89`, based on circular
window `209f8b4011f00cfe03b1326b8067076f2bfb2783`, adds four read-prefetch hints
for the node beyond the four selected requests. It does not select a fifth
request or alter pins, ACKs, exact identities, ownership or retirement. The
queue reservation protects the hinted node. This candidate includes neither
optional diagnostics nor the separate immediate-successor notification hint.

Seven basic/affected checks passed. [Mutex and rwsem basic](basic-result.json)
each completed 1,600,000 operations with correct data, matching JIT entries and
returns, and final idle. Returned-body counts were 1,586,965 and 1,589,868.
The [ELF audit](elf-audit.json) confirms the four intended `PREFETCHT0` hints,
diagnostics0, unchanged 1024/1024 policy, no outlined hot pin helper or per-body
`memmove`, and unchanged stack allocations and call-target counts.
`kd_mutex_execute_cs` grows 112 bytes and adds three reloads of an existing
batch-pointer stack slot; it is not a zero-instruction-cost hint.

The [12-point round](nano-results.json) used c01/c16, two seconds, post256,
worker CPU prefixes and collector63, once per point. Every point completed and
drained. All comparisons below used boot `677b7afa-5358-4ece-a650-5f4a4adecd55`;
the earlier controls and new candidate ran at different times. Whole-run rates
are Mops/s. c01 and c16 mean one and sixteen cachelines.

| Workload | Workers | Pinned `1c86d6d1` | Ring `209f8b40` | Refill `8de65c94` | vs ring | vs pinned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c01 | 1 | 1.916302 | 1.916194 | 1.916464 | +0.01% | +0.01% |
| c01 | 8 | 3.678105 | 2.767549 | 2.818670 | +1.85% | -23.37% |
| c01 | 20 | 4.590029 | 3.324957 | 3.673793 | +10.49% | -19.96% |
| c01 | 32 | 4.486160 | 3.300471 | 3.668276 | +11.14% | -18.23% |
| c01 | 36 | 4.209552 | 3.648937 | 3.545267 | -2.84% | -15.78% |
| c01 | 60 | 4.335256 | 3.692465 | 3.551648 | -3.81% | -18.08% |
| c16 | 1 | 1.916744 | 1.915829 | 1.916625 | +0.04% | -0.01% |
| c16 | 8 | 3.548560 | 2.647178 | 2.713873 | +2.52% | -23.52% |
| c16 | 20 | 4.227567 | 3.168771 | 3.507010 | +10.67% | -17.04% |
| c16 | 32 | 4.188997 | 3.194408 | 3.573967 | +11.88% | -14.68% |
| c16 | 36 | 3.853043 | 3.344820 | 3.375828 | +0.93% | -12.39% |
| c16 | 60 | 3.946234 | 3.297987 | 3.382780 | +2.57% | -14.28% |

[Exact comparison data](comparison.json) retain the rates. Gains of about
10–12% versus the ring at 20/32 workers support further investigation of refill
cost, but do not isolate cache misses from changed code layout or run order.
Cross-NUMA signs are mixed, and all contended points remain below the pinned
reference. One round supplies no repeat variance. The candidate is not promoted
and does not close the no-regression gate. No rwsem timing or real-world API
campaign ran for this ablation.

After this round the user revised the waiter policy to a long initial pinned
spin and larger ready cohort without in-round ACK waits. That protocol is a
new candidate, not validation or retrospective acceptance of this experiment.

Both trees are preserved in four archives; hashes and all 2,473 paths were
[verified offline](archive-verification.json). Raw copies are under
`bench/results/10.176.26.71/raw/tests/mutex-pin-refill-prefetch-20261029/`.
Guest roots are `tests/pin-refill-prefetch-20261029` and
`bench/pin-refill-prefetch-nano-20261029` below
`/root/kdlock-evidence/10.176.26.71/`.
