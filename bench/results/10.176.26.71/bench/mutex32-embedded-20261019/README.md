# Embedded 32-byte mutex: implementation and fresh pipe comparison

Runtime **`372be892f3e87538a204ab9f6eddc32ca332d047`** embeds the delegation root
in the native-sized mutex and removes the auxiliary address hash, 16 MiB slot
table and shared auxiliary reference count. Basic and affected VM checks passed.
The fresh pipe comparison still trails the old 256-byte implementation by
**40.7% at eight workers and 37.0% at sixty workers**.

## Implementation

The object remains **32 bytes, aligned to 8 bytes** on the captured kernel.
It contains owner (offset 0), physical wait lock (8), OSQ (12), sleeping-waiter
ring head (16), packed delegation phase/exact waiter count (24), and encoded
CPU/slot tail (28). A circular ring of stack waiters replaces the native list
sentinel; insertion, head removal and cancellation remain O(1) under the
existing physical wait lock. OSQ retains its independent queue and lifetime.

FREE → ACQUIRING → HELD/COMBINER → RELEASING → FREE makes physical acquisition
and release explicit without a separate auxiliary owner pointer. Only current's
completed physical acquisition, with PICKUP clear, authorizes delegation unlock.
Masked atomic phase changes preserve the high 24-bit exact waiter count.
The encoded tail still addresses four independently reserved nodes per CPU.
Each node remains 320 bytes; packet and completion offsets are unchanged.

KD physical exclusion, legacy queue/batching, ABI2, pinned published waiters,
immutable images, fail-closed admission, source leases, native unlock ACKs and
frame retirement remain. No caller cleanup or auxiliary allocation is added.
No auxiliary registry lock or RCU lifetime is introduced. Existing physical
wait-lock serialization and task-routing RCU/cache locks remain unchanged.
The exact task, node and frame/source/ACK records still determine controlled
drain. See the [source review](source-review.md) and
[maintained implementation guide](../../../../../docs/design/mutex_implementation.md).

## Fresh pipe results

Both arms ran pipebytes/query n16 with the outer clobber call shell, 2000 ms
measurement, three repetitions per point, workers 0 through N−1, and collector
CPU 63. The 64-vCPU/24-GiB recovery VM has two 32-CPU NUMA nodes with matching
host pins. Host frequency policy, topology, snapshot and guest boot remained
unchanged. Kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, `nopvspin`, `nokaslr` and voluntary
preemption were verified. Provider UBSAN was off in both arms; NUMA batching,
batch cap 1024, prefetch and admission settings matched.

The old arm is **`0324e60d6791948e9762a9916a50e8e026f073b0`**. The table shows
whole-run Mops/s median [minimum, maximum], not selected peak throughput.

| Workers | Old 256-byte | Embedded 32-byte | New / old | Change |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 6.994 [6.027, 7.118] | 4.147 [4.056, 4.496] | 0.593× | −40.7% |
| 60 | 5.409 [5.164, 5.415] | 3.408 [3.344, 3.480] | 0.630× | −37.0% |

All **12 sessions** returned generated bodies, passed the workload/worker-progress
oracles and drained. These are sequential source blocks, embedded32 followed by
old256, with three repetitions each; they are not randomized paired trials or
confidence intervals. Earlier 32-byte results are not pooled or used as a fresh
pre-change comparator. The controlled pipe workload uses a private redirected
FIONREAD body; it is not whole-kernel pipe-lock replacement.

| Workers | Old measured returned-JIT share | New measured returned-JIT share | Old whole-session bodies/combiner median | New whole-session bodies/combiner median |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 96.593% | 93.011% | 320.344 | 99.481 |
| 60 | 94.899% | 96.187% | 127.495 | 127.914 |

The JIT shares are measured-phase ratios. Bodies/combiner counters cover the
whole session, including warmup and checks, and cannot be used as measured-phase
fallback rates. At eight workers, lower delegation and shorter session-level
batches accompany the gap. At sixty workers, delegation is higher and batch
length is similar, so a universal lower-delegation explanation is contradicted
by the measurements.

The [admission diagnostic](diagnostics.md) retains one unexplained residual of
16,384 calls in embedded32/eight-worker repeat 0 under the conditional startup
accounting model; the other eleven residuals are zero. These sampled admission
estimates do not replace measured business/JIT counters or exact lifetime checks.

Packing places the gate, tail exchange and exact count RMWs in the object's last
eight bytes. Physical fields can share that cacheline; native 8-byte alignment
also permits the object to straddle two lines. Additional coherence traffic and
masked phase CAS retries are
plausible costs, but this round contains no profiles or isolated ablation that
attributes the slowdown. Removing auxiliary references has not established
performance parity. The requested layout remains implemented; the pipe gap is
an explicit remaining performance limitation.

## Validation and preserved evidence

- Dependency check, provider `W=1` build and daemon `-Werror` build passed.
  The provider log retains **48 warning lines**; it is not warning-free.
- **Two basic programs plus twelve affected drivers: 14 passed, zero failed.**
  Embedded-state tests detect 22 negative controls, resources 26, and exact
  balance/drain checks six. Existing terminal, outer-progress, wrapper,
  native-ACK, frame, immutable-image and source checks remain selected.
- Live ordinary mutex, rwsem and instruction-exit probes passed and drained.
  The ordinary probe verifies native size/alignment and containing offsets,
  160,000 operations, 2,048 reused objects freed without destroy, sleeping and
  nested owners, interruptible/killable cancellation, and head/middle/tail ring
  cancellation with HANDOFF. No full suite was run.
- All 15 retained kernel logs contain no matched runtime faults. The VM was
  restored to the checked embedded source and confirmed idle; no kernel was
  modified, installed or rebooted.
- Independent inert-byte archive/source review passed: 3,285 members, 2,882
  regular files, eight source manifests, 26 binary-manifest entries, 25 JIT
  binaries, and **zero source exceptions or issues**.
- Independent arithmetic review passed **17,613 checks**, reconstructing all
  12 whole/peak windows and the exported groups, with zero issues.

The [comparison](comparison.json), [validation](validation.json),
[health/topology](health.json), [source/archive review](archive-review.json) and
[arithmetic review](statistics-review.json) bind the actual frozen inputs and
outcomes. [Archives](archives.json) retain the initial build, checked snapshot,
both benchmark arms, source/ELF/JIT bytes, samples and logs under the ignored raw
directory `bench/results/10.176.26.71/raw/bench/mutex32-embedded-20261019`.
The [operations receipt](OPERATIONS.md) records bounded collection and audit
commands. Whole-kernel replacement, oversubscription redesign, RT/ww_mutex and
lockdep integration remain separately unvalidated.
