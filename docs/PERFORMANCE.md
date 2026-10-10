# Performance status

KD does not yet match both TCLock and Linux Native at every requested thread
count. The spin/mutex optimization phase ended on **2026-10-09**, with those gaps
still open. Its [report](../bench/tclock_compare/results/20261008-protocol-simplification/README.md)
keeps the final comparison, rejected candidates and the source and binary identities
used for each run.

## RCUHT rwlocks, 2026-10-10

The [rwlock comparison](../bench/rwlock_compare/results/20261010-rcuht/README.md)
ran 270 RCUHT sessions: 1% and 20% writes, fifteen thread counts, three backends
and three rounds. All runs produced correct results and shut down cleanly.

The target was to match or exceed **both** Native and TCLock on **both** best peak
and median whole-run throughput. KD met that target at 21 of the 30 combinations
of write percentage and thread count. It fell short at nine. At 1% writes, TCLock
still leads when workers span NUMA nodes. At 20%, KD's largest gap is at two threads.

ABI3 allowed hash writers to execute through JIT. The tested implementation also
added native fast writers and separated the count and gate into different cache
lines. Those changes improved the screened results but increased the lock to
128 bytes. The report keeps all trials and raw data, and separates runs with
observed JIT bodies from NO_JIT runs. These results belong to the rwlock work,
not the earlier spin/mutex phase.

All recorded comparisons below and the RCUHT rwlock report used the original
40-vCPU guest. The 60-vCPU destination has a separate
[migration validation record](../bench/README.md#vm-migration-validation).
Preserve each report's placement, frequency policy and source identity when
reproducing it; do not combine samples across those environments.

## Completed spin/mutex measurements

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
Every run that required KD JIT or TCLock mutex delegation recorded the required
execution count. Data and shutdown checks also passed. Allowed native controls
are listed separately. TCLock spin delegation counts were not measured.

## Spin/mutex outcome

Spin/hash still trails TCLock even though JIT runs almost all contended bodies.
Mutex/hash may have a competitive short peak while completing much less work over
the whole run. Work is also distributed unevenly between NUMA nodes. Seeing every
worker make some progress, or limiting batch size, does not prove that a worker
can never starve.

Neither final translator/memory candidate was kept. The combined candidate changed
terminal-completion proofs and code-buffer allocation, but repeatedly reduced
whole-run mutex/hash throughput at 36 threads. The memory-only candidate repeatedly
lost more than 3% of mutex/cacheline peak throughput at 16 threads against the
opening baseline. Its losses against the closing baseline stayed below 3%.
Both candidates were reverted, so the provider still allocates the code pool at
initialization.

Earlier profiles suggest that translated traversal, request handling and coordination
between native and delegated work contribute to the cost. Increasing the JIT share
or removing a few instructions did not reliably improve throughput. Total cache
misses and ordinary cycle samples cannot isolate remote-memory latency. Earlier profiles and failed
experiments remain in [benchmark history](../bench/tclock_compare/results/HISTORY.md).

## Implementation and deferred designs

Current contracts live in the [spin](design/spin_implementation.md),
[mutex](design/mutex_implementation.md) and [rwlock](design/rwlock_implementation.md)
guides. KD retains the two-word wrapper ABI, mandatory mutex JIT, native-first
mutex acquisition, exact Linux ownership,
source leases, final ACK and frame retirement. The maximum KD combiner batch is
**1,024 bodies**, with a separate bounded spin NUMA scan and existing prefetch
defaults. Mutex's accepted queue is FIFO.

Stable task caches, mutex NUMA grouping, broad prefetch and register-residency
trials were rejected or did not establish repeatable gains. They are not current
features. The [outlined operation/context API](design/protocol_simplification.md)
is an unimplemented design alternative; it requires separate validation and
matched callers. No additional optimization run is scheduled by this document.

[Known limitations](TODO.md) remain documented. Reproduction settings and
acceptance rules belong to the [spin/mutex](../bench/tclock_compare/README.md) and
[rwlock](../bench/rwlock_compare/README.md) runner guides;
source cleanup is not a performance rerun.
