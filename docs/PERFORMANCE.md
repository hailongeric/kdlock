# Performance status

The spin/mutex optimization phase closed on **2026-10-09**. The completed
[report](../bench/tclock_compare/results/20261008-protocol-simplification/README.md)
contains the final comparison, failed candidates and evidence identities.
KD does not match the stronger of TCLock and Linux Native across the requested
thread set. Closing the work does not establish performance parity.

## Completed measurements

The final baseline contains 540 sessions: KD, TCLock and Native; spin and mutex;
cacheline and hash; three rounds at 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24,
28, 32 and 36 threads. The complete trial archive contains 2,286 performance
sessions, including rejected candidates and their rechecks.

Runs use the existing `6.1.159-kdclobber2` recovery kernel with `nopvspin`,
2.5 GHz host frequency limits, NUMA on, UBSAN off for the KD provider and
48,000 warmup operations per worker. Measurements last two seconds; peak
selection uses a valid 300 ms window after 300 ms settling. All samples,
whole-run rates, min/median/max/spread and worker/node progress are retained.

The measured source is `d2868e3`. Unrelated working-tree changes were excluded.
Every required KD returned-body JIT and TCLock mutex delegation witness passed,
as did business results and drain. Allowed native-route controls are recorded
separately. TCLock spin delegation counts remain unmeasured.

## Outcome

Spin/hash still trails TCLock with almost all contended bodies executed by JIT.
Mutex/hash has a large sustained-throughput gap even where a selected peak is
competitive. Minority-node service remains uneven. Positive worker progress and
a bounded batch do not establish starvation freedom.

No runtime change from the final translator/memory trials was promoted. The
combined terminal-proof/backing candidate repeatedly lost mutex/hash-36 whole-run
throughput. Memory-only backing repeated a mutex/cacheline-16 peak loss above 3%
against the opening baseline; closing-baseline peak losses stayed below 3%.
Both were reverted. The eager code pool remains current.

Earlier profiles point to translated traversal/request costs and mixed
native/delegated coordination. More JIT coverage and fewer isolated instructions
did not reliably improve throughput. Aggregate cache misses and ordinary cycle
samples do not identify remote-memory latency. Earlier profiles and failed
experiments remain in [benchmark history](../bench/tclock_compare/results/HISTORY.md).

## Implementation and deferred designs

Current contracts live in the [spin](design/spin_implementation.md) and
[mutex](design/mutex_implementation.md) guides. KD retains the two-word wrapper
ABI, mandatory mutex JIT, native-first mutex acquisition, exact Linux ownership,
source leases, final ACK and frame retirement. The maximum KD combiner batch is
**1,024 bodies**, with a separate bounded spin NUMA scan and existing prefetch
defaults. Mutex's accepted queue is FIFO.

Stable task caches, mutex NUMA grouping, broad prefetch and register-residency
trials were rejected or did not establish repeatable gains. They are not current
features. The [outlined operation/context API](design/protocol_simplification.md)
is an unimplemented design alternative; it requires separate validation and
matched callers. No additional optimization run is scheduled by this document.

[Known limitations](TODO.md) remain documented. Reproduction settings and
acceptance rules belong to the [runner guide](../bench/tclock_compare/README.md);
source cleanup is not a performance rerun.
