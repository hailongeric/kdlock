# Protocol simplification: results and restored baseline

**No optimization candidate was promoted.** The combined terminal-proof/memory
candidate and the later memory-only candidate failed the declared regression
guardrail. Their runtime changes were reverted. Current code eagerly allocates
the code pool at provider initialization; the measured provider allocated all
64 × 640 KiB blocks (40 MiB).

## Current-code comparison

All **540 sessions** completed with valid business results, required execution
witnesses and full drain. All 15 requested thread counts are represented.

Each rate is **best warmed peak / median whole-run Mops/s**.

| Workload, 36 workers | KDLock | TCLock | Native | KD / stronger peak / whole |
|---|---:|---:|---:|---:|
| spin/cacheline | 9.221 / 9.141 | 5.987 / 5.931 | 3.840 / 3.592 | 154.02% / 154.13% |
| spin/hash | 2.022 / 2.012 | 2.780 / 2.764 | 1.690 / 1.642 | 72.74% / 72.80% |
| mutex/cacheline | 6.303 / 5.766 | 5.570 / 4.469 | 5.844 / 5.608 | 107.86% / 102.82% |
| mutex/hash | 2.601 / 1.575 | 2.215 / 2.201 | 2.773 / 2.715 | 93.81% / 58.02% |

The target remains unmet. Across 60 workload/thread points, KD reaches 90% of
the stronger comparator at **28 points by peak and 27 by whole-run median**;
parity holds at only 13 and 12 points respectively. Two-thread spin/hash reaches
43.99% of Native's whole-run median without returned JIT execution. At 24 threads,
mutex/hash reaches 42.69% of Native's whole-run median despite returned JIT bodies.

[All 15 thread counts](matrix.md), [peak curves](peak-matrix.svg), [median comparisons](matrix-medians.md),
[full statistics](statistics.csv) and [per-round samples](samples.csv) keep peak
and whole-run results separate. Each point uses its contemporaneous stronger
comparator; peak parity cannot conceal sustained losses.

The runs use 2.5 GHz, NUMA on, UBSAN off for the KD provider, 48,000 warmup
operations per worker, three rounds and two measured seconds. Peak selection
uses a 300 ms window after 300 ms settling. Workers occupy CPUs `0..threads-1`;
CPU 38 collects progress. Four of 24 workers are on node 1.

Measured source is frozen `d2868e3`, restored after the candidate trials, on the
existing `6.1.159-kdclobber2` recovery kernel with `nopvspin`. All arms retain four
lock-outside arithmetic rounds; the unrelated 64-round working-tree experiment
was excluded and preserved. Mutex JIT remains mandatory.

All workers progressed. KD has 129 returned-body JIT positives and 51 allowed
native-route controls; TCLock mutex has 78/90 measured delegation positives,
including every required contended case. Over the whole run at 24 threads, node 1
completes only 0.85–0.97% of KD spin/hash operations and 8.50–9.49% of KD mutex/hash operations,
despite supplying 16.67% of workers.

[Node shares](node24-progress.csv) accompany throughput. Positive observed progress
is not a starvation guarantee. Allowed KD zero-body samples are native-route
controls, not JIT positives; TCLock spin delegation counts remain unmeasured.

## Why the candidates were rejected

The [isolated screens](screens.md) found no consistent benefit from dead packet
imports or paired traversal budgets. Original lazy allocation repeatedly hurt
spin/cacheline throughput. A cold allocation helper cleared that screen, but
broader validation exposed regressions:

- Terminal proof plus cold backing lost **5.84% and 6.62%** of mutex/hash-36
  whole-run median versus the closing baseline in its matrix and recheck.
- Cold backing alone lost **3.21% and 3.82%** of mutex/cacheline-16 peak median
  versus the opening baseline. Corresponding closing-baseline peak losses were
  **1.54% and 2.16%**, below the threshold. Whole-run loss crossed 3% only in the
  recheck; it was not the repeated rejection criterion.

The unchanged mutex/hash-36 baseline moved by 16.27% in median peak and 15.58%
in whole-run median. The conservative guardrail rejects repeated losses; it does
not establish which scheduling or processor effect caused them. Complete candidate
tables and rechecks remain separate from the current-code matrix.

The [memory-only experiment](memory-candidate/matrix.md) and its
[plot](memory-candidate/peak-matrix.svg) remain explicitly marked rejected.
With one uploaded image, it reduced total code-pool backing from 40 MiB to
640 KiB, saving 39.375 MiB (98.44%) while preserving alignment and the 64-image
limit. That excludes metadata, task records and waiter
stacks; its owner array added 512 bytes. The saving is valid experimental evidence,
but failed throughput qualification prevents presenting it as current behavior.

High JIT coverage did not close the hash gap. KD adds virtual-register, stack and
traversal machinery to each delegated body; mutex also maintains Linux physical
ownership and native/delegated lifetimes. TCLock transfers the native continuation
on the waiter's stack. These observations motivate measuring service and route
costs, not forcing more delegation. [Design alternatives](../../../../docs/design/protocol_simplification.md)
describe a restricted outlined API that still requires JIT and matched callers;
they promise no measured improvement.

## Evidence

The audit covers **2,286 performance sessions**: the current 540,
612 screen/control sessions, two separate rejected 540-session
matrices, and their 36- and 18-session rechecks. Raw names `final` and `retained`
refer to rejected candidates. `restored` identifies the current-code comparison.

The memory-only spin/hash broken pipe after 85 sessions remains recorded; only
the 50 unrun sessions were resumed after frozen source/binary checks. Original
records and failure evidence were preserved. [Evidence identities](evidence.json)
locate archives and tools; [the audit summary](audit.json) scopes source, binary,
execution, memory and resume checks. No cohort is pooled into another matrix.

Fresh targeted guest checks passed all five driver groups. The ordinary
`W=1 UBSAN_SANITIZE=n` build compiled and linked successfully; its 11 existing
objtool warnings remain. This is not a full test-suite pass. The commit contains
documentation and evidence; no experimental runtime changes remain.
