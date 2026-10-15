# Known limitations and deferred work

Current scope is x86_64 kernel spin/mutex/rwlock/rwsem delegation through explicit APIs.
KD mutexes always support blocking. Legacy mutexes reject delegated origin-CPU GS;
owned mutexes can opt into the bounded audited subset with an exclusive claim.
Legacy mutexes preserve the original Linux owner; experimental owned mutexes
retain their own exact owner/ACK protocol. Rwlock ABI3 acquires write access before the
translated body. Implementation contracts live in [DESIGN](DESIGN.md);
[performance status](PERFORMANCE.md) records measured gaps and
[validation](VALIDATION.md) indexes source-specific receipts. None of those
measurements resolves the correctness limits below.

## Current checkpoint

The experimental owned provider at `585335b` extends `d8d14a1` with the accepted
[ABI4/reuse-32 c01 profile](PERFORMANCE.md#active-c01-18-worker-study), limited to
KD-only object lifetimes and the captured x86-64 configuration. Its
[targeted receipts](VALIDATION.md#current-owned-protocol-verification) do not
establish fairness, general oversubscription or universal Native parity.
The later [c01/post64 full-grid comparison](PERFORMANCE.md#fresh-c01-164-worker-comparison)
measures 1–8 workers in steps of one and 12–64 in steps of four on a separate
66-vCPU boot. All 198 samples are correct and drained; the three-worker warmed
peak misses 97% of Native. Full-grid parity and its two fresh confirmation blocks
remain outstanding. The predominantly SELF results do not establish a benefit
from bulk delegation. Other payloads and post-work settings need separate studies.
The broader native-first experiment remains rejected and archived. None of these
results waives ownership, lifetime, progress or drain requirements, or resolves
the failures below.

Recorded failures and unresolved coverage:

- Concurrent cold promotion stalled with an RCU warning in c16/t4 preparation.
  Single-CPU preparation avoids that phase rather than fixing it. The fixed
  [failure record](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md)
  retains the original inputs.
- The former polling-only mutex soft-locked in seven-role/two-CPU mode4. The
  blocking probes do not rerun that dependency scenario; see the fixed
  [mutex failure](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#mutex-pinned-mode4-failure).
- An older oversubscribed mode5 published code but lacked actual JIT. Current
  blocking checks do not provide a new run of that scenario; see
  [the recorded assessment](VALIDATION.md#mutex-oversubscription-assessment).

## Delivery scope

Keep the two-word wrapper ABI, separate backend identities, exact physical owners,
exact acquisition references and final ACKs. Shared storage must survive its final
reader. Builds/tests/benchmarks run in the recovery guest; default work does not
change its kernel. Mutexes permit sleep with migration pinned; an origin-sensitive
owned image additionally requires a spinning claim. Blocking scheduler/JIT evidence does not
retroactively establish a pass for historical
oversubscription failures.

The [ordinary sleeping rwsem](design/rwsem_implementation.md) supports local
readers and delegated outer writers. Killable waits and real mmap integration,
userspace/futex, other architectures and oversubscription redesign remain outside
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

KD spin owns its word; TCLock/Native own theirs. KD owned mutex uses its own
owner word, OSQ and tagged wait list. Its Linux-compatible object geometry does
not permit Linux or TCLock callers on the same object. The retained legacy mutex
uses the original Linux mutex plus a scheduling gate and excludes native peers
through that original mutex. Preserve ledger identity, physical exclusion, frame
pop, owner ACK and storage retirement as separate operations.
KD rwlock owns its count and KD gate. Ungated native writers retain exact
nondelegated references; gate quiescence alone does not establish count or reader
drain. No Linux/TCLock operations may access the same KD rwlock object.
KD rwsem retains its owned-mutex gate while writers drain the reader count;
ordinary slow readers are noncombining queue boundaries. Neither the gate alone
nor its idle state replaces reader and frame drain.

### C3. Immutable JIT publication and lifetime

Owned mutex publication now binds code, requirements and generation in immutable
descriptors. Complete uploads use separate blocks; every published version survives
until terminal session drain. Pool exhaustion refuses replacements. The remaining
legacy spin/rwlock/mutex scope still overwrites its RIP-indexed block and remains
deferred. Source leases and ABI tags alone do not resolve that lifetime problem.

### C4. Instruction, flags, and fault semantics

Deferred by user decision. INT-to-NOP, warning-only special instructions,
instrumentation flag clobbers and incomplete flags/SIMD/FPU restoration remain
limits. Packet comparisons do not prove live hardware flags restoration.

### C5. Origin context and nested boundaries

Current analysis screens emitted scope, CALL/RET, aliases and static per-CPU ranges;
GS/logical current are not a hardware context switch. Arbitrary hidden calls,
context-object lifetimes, runtime pointers and concurrent replacement remain open.
The [task-name snapshot experiment](../bench/results/10.176.26.71/bench/proc_snapshots/20261015/README.md)
records a concrete spin ABI1 limit: `strscpy_pad()` pushes uncaptured R13, so the
minimal-entry store check refuses its helper scope. The initial partial body
returns natively. Supporting that helper needs an audited register/stack contract;
the experiment does not suppress the check or substitute a different copy body.

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
