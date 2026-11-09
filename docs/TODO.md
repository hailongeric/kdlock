# Known limitations and deferred work

The [roadmap](ROADMAP.md) defines completion gates. This page records current
implementation and evidence gaps; [validation](VALIDATION.md) and
[performance](PERFORMANCE.md) own source-specific outcomes and measurements.
Historical work orders do not authorize new execution campaigns.

## Current checkpoint

`master` includes retained original-JIT execution and the proxy-read correction
through merge `6badc60e`. The latest actual-syscall mmap1 process point tested
`7e3c90b4`, with selected-service counters and no compilation overlapping its
fixed application. Both roots returned every whole-application JIT entry.
It is one instrumented point, without quiet/strict-peak qualification, a Native
gain or runtime validation of the union with master's flags-stack changes.
Normal `7.0.0-38-kdlock1` keeps the mmap backend disabled; enabled profiles have
their own source/build/boot identities.

## Current implementation gaps

| Area | Remaining limit |
| --- | --- |
| Kernel replacement | Each declared object and all users require consistent routing, context and lifetime integration; provider load alone does not replace them |
| Waiting/progress | Ordinary published mutex waiters still poll pinned; isolated scheduling/window experiments and full queued role exchange are not promoted by this document |
| Context | Logical task/GS operands do not switch hardware task, IRQ/RCU, accounting or address-space context; every returning service needs its declared contract |
| Native continuation | Exact current-position handback preserves completed effects; it does not provide arbitrary flags, SIMD/FPU or IRQ/NMI restoration |
| Nested execution | Separate nested-image activation, arbitrary mixed ownership and cross-scope release routing need explicit supported contracts and validation |
| Image/source/data lifetime | Immutable mutex/retained images and source leases do not retain arbitrary lock/data allocations; exact owners, ACKs and last-user drain remain required |
| Fairness | Bounded batching and NUMA grouping do not establish starvation freedom or a maximum acquisition latency |
| APIs/configuration | ww_mutex, arbitrary NMI use and whole-kernel coverage remain unvalidated; PREEMPT_RT, debug mutexes, debug lock allocation and lockdep are refused |
| Backend fidelity | Source trust skips optional semantic proofs; it supplies no missing instruction lowering, decoded text, return routing or runtime API support |
| Returns/mitigations | Active call-depth tracking is refused and full handwritten/generated return-mitigation coverage remains unvalidated |

Current ordinary readers remain local and concurrent. Prepared writer capture,
cancellation and proxy/native downgrade have distinct contracts in the
[lock catalog](LOCKS.md) and [rwsem guide](design/rwsem_implementation.md).
The current implementations are evidence for a future redesign, rather than
automatic requirements for its storage, reader placement or adapter choices.

## MM and performance gaps

The actual `mmap1_threads` and independent-process runners already exist under
`bench/mmap1/`; their source-specific comparisons and failures remain linked
from validation. Additional matched current-source thread/process evidence,
repeat variability and predeclared improvement/parity acceptance remain open.
A generic minor-fault throughput driver using the actual backend remains
separate work. Device mappings/private-backing cycles are not substitutes.

The historical shared-device-MM comparison lost to Native at every tested
count; later mmap1 observations have separate kernels and source identities.
Preserve both gains and losses. The latest instrumented process point does not
establish a quiet result or a performance cause. Operation-specific MM bodies
and prepared teardown remain retired.

Mutex total/locality limits are 1024/1024 and spin total is 1024. Earlier
768-boundary observations do not qualify the current default. No new timing,
tail-latency collection or full suite is requested by this documentation.

## October 29 API and execution work

The [archived candidate chronology](history/documentation-20261109/TODO.md#october-29-api-and-execution-work)
retains exact API checkpoints, rejected scheduling/window experiments, role
cases, rates, source/boot boundaries and expired work orders. Existing links to
this heading remain valid. Their scoped functional passes do not establish
performance neutrality or promotion of an isolated candidate.

## Retained failures

Failed checked/trusted taskname attempts, NO_JIT controls, telemetry preflights,
MM contention witnesses, targeted handback checks and both earlier proxy-read
learning campaigns keep their original verdicts. Later cleanup and successful
points do not rewrite them. See [validation](VALIDATION.md) and the
[history index](history/README.md). Linux 6.1 is recovery/history only.
