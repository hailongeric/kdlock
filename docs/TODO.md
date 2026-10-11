# Known limitations and deferred work

Current scope: x86_64 kernel spin/mutex/rwlock delegation. Implementation contracts
live in [DESIGN](DESIGN.md); [performance status](PERFORMANCE.md) distinguishes the
closed spin/mutex phase from the later rwlock comparison. These unresolved issues
remain documented; this list does not schedule new work. Historical evidence is
indexed in [VALIDATION](VALIDATION.md).

## Current checkpoint

KD has explicit spin, ordinary mutex and rwlock APIs, with workloads comparing
KD, TCLock and Native. It tracks real lock owners and unlock acknowledgements,
keeps source modules loaded while needed, and shares register packets between
waiter and combiner. It does not intercept global lock calls. KD has not matched
both alternatives at every requested configuration; see the
[spin/mutex report](../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md)
and [RCUHT rwlock report](../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md).

Rwlock ABI3 moves the wait for readers and acquisition of write access before
the prepared body. This resolves the older hash-writer translation refusal.
Native writers now have a fast path, and the count and gate occupy separate cache
lines in a 128-byte object. All 270 runs of the 1%/20% RCUHT matrix produced correct
results and drained, but KD met both throughput targets at only 21 of 30 comparison
points. Read-heavy runs across NUMA nodes and writer performance at two threads
still have gaps. None of these results resolves the correctness limits below.

Known failures are still open:

- Concurrent cold promotion stalled with an RCU warning in c16/t4 preparation.
  Single-CPU preparation avoids that phase rather than fixing it. The fixed
  [failure record](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md)
  retains the original inputs.
- Seven-role/two-CPU mutex mode4 soft-locked with pinned polling. Other passes
  do not replace that case; see the fixed
  [mutex failure](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#mutex-pinned-mode4-failure).
- An older oversubscribed mode5 published code but lacked actual JIT. Its former
  scheduling strategy does not validate today's pinned waiters; see
  [the recorded assessment](VALIDATION.md#mutex-oversubscription-assessment).

## Delivery scope

Keep the two-word wrapper ABI, separate backend identities, original mutex owners,
exact acquisition references and final ACKs. Shared storage must survive its final
reader. Builds/tests/benchmarks run in the recovery guest; default work does not
change its kernel. Mutex spin mode retains pinned polling; the selectable blocking
mode permits sleep with migration pinned and stricter GS admission. Its new
scheduler/JIT evidence does not retroactively establish a pass for historical
oversubscription failures.

Userspace/futex, rwsem, other architectures and oversubscription redesign are outside
this phase. Basic plus directly affected checks are the default; full suites need
explicit selection. Extremely uncommon scheduling/resource/alias combinations are
optional coverage, while reproduced supported-path failures must remain visible.

## P0: Correctness contracts

### C1. Forward continuation after partial execution

The supported CALL/PENDING, post-acquisition spin and checked mutex exits resume
from the current state. Earlier stores, lock acquisitions and releases must happen
exactly once. Fixing a recovery defect must not restart those operations. Generic
faults, indirect-jump misses and budget errors still stop execution; they cannot
be used as arbitrary native fallback points. Broader combinations of remote
execution and resource exhaustion remain optional coverage.

For rwlock ABI3, writer admission can be cancelled only before the body starts.
A body that already made progress keeps exclusive write access while finishing
natively. Its matching unlock releases the writer byte, and the request must still
complete the required ACK and retirement steps.

### C2. One protocol per physical lock

KD spin owns its word; TCLock/Native own theirs. KD mutex keeps the original Linux
mutex plus a scheduling gate. Preserve ledger identity, native-peer exclusion,
frame pop, owner ACK and storage retirement as separate operations.
KD rwlock owns its count and KD gate. Ungated native writers retain exact
nondelegated references; gate quiescence alone does not establish count or reader
drain. No Linux/TCLock operations may access the same KD rwlock object.

### C3. Immutable JIT publication and lifetime

This work was deferred by user decision. Recompiling an entry overwrites the code
block indexed by its instruction address (RIP). Source leases keep modules loaded,
and ABI tags identify calling conventions, but neither gives running code its own
unchanging image version. A future design must validate complete images, identify
generations and wait for old executions before reclaiming them. Better throughput
does not resolve this lifetime problem.

### C4. Instruction, flags, and fault semantics

Deferred by user decision. INT-to-NOP, warning-only special instructions,
instrumentation flag clobbers and incomplete flags/SIMD/FPU restoration remain
limits. Packet comparisons do not prove live hardware flags restoration.

### C5. Origin context and nested boundaries

Current analysis screens emitted scope, CALL/RET, aliases and static per-CPU ranges;
GS/logical current are not a hardware context switch. Arbitrary hidden calls,
context-object lifetimes, runtime pointers and concurrent replacement remain open.

#### Deferred access-time guard

The user deferred runtime guards, pre-instruction native continuation and local
condition-code preservation on 2026-09-13. They remain unimplemented, not pending
permission. Entry guards and the mutex stack checkpoint do not close the
[dynamic-address gap](design/admission.md#721-dynamic-address-gap).

## P1: Evidence and services

- Complete fresh-checkout reproducibility. Pinned dependencies, frozen source and
  offline checking exist; bundled compiler/dependency bytes and reproducible kernel
  builds do not.
- Add only typed bounded services with argument/result, context, sleeping, overflow
  and side-effect contracts. Clock/int_sqrt exist; arbitrary pointer or variadic
  printk services do not.
- Expand randomized/exactly-once fixtures when useful; do not confuse synthetic
  passes with forced live remote schedules.

### Main-plan acceptance audit

A JIT pass requires the generated and published identities to match, an observed
returned JIT body, correct data, the required physical-owner ACKs and complete
drain. Report publication, native controls and refusals separately. Combining
old passes or selected checks does not establish a current whole-project pass;
see [the historical audit](VALIDATION.md#main-plan-acceptance-audit).
