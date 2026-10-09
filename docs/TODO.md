# Known limitations and deferred work

Current scope: x86_64 kernel spin/mutex delegation. Implementation contracts live
in [DESIGN](DESIGN.md); the optimization phase is closed in
[Performance status](PERFORMANCE.md). These unresolved issues remain documented;
they are not work scheduled by the closed phase. Historical evidence is indexed in
[VALIDATION](VALIDATION.md).

## Current checkpoint

Explicit KD spin and ordinary three-arm mutex workloads exist. KD retains exact
owner/ACK/source lifetime and shared clobber packets; providers do not install
global interception. The final comparison still fails parity across all requested
workloads and counts; use the
[completed report](../bench/tclock_compare/results/20261008-protocol-simplification/README.md).

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
change its kernel. Published KD waiters remain pinned polling.

Userspace/futex, rwsem, other architectures and oversubscription redesign are outside
this phase. Basic plus directly affected checks are the default; full suites need
explicit selection. Extremely uncommon scheduling/resource/alias combinations are
optional coverage, while reproduced supported-path failures must remain visible.

## P0: Correctness contracts

### C1. Forward continuation after partial execution

Supported CALL/PENDING, post-acquisition spin and checked mutex exits preserve
current state and exactly-once effects. Fix reproduced defects without replaying
the prefix. Generic fault, IJ miss and budget errors remain fail-stop, not arbitrary
native recovery. Broader remote/exhaustion combinations are optional coverage.

### C2. One protocol per physical lock

KD spin owns its word; TCLock/Native own theirs. KD mutex keeps the original Linux
mutex plus a scheduling gate. Preserve ledger identity, native-peer exclusion,
frame pop, owner ACK and storage retirement as separate operations.

### C3. Immutable JIT publication and lifetime

Deferred by user decision. Recompilation overwrites a RIP-keyed code block;
source leases and ABI tags do not isolate executable versions. A future change
needs complete-image validation, generations and reclamation after old executors
finish. No current throughput result closes this gap.

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

Actual JIT requires matching generated/published identity, returned-body evidence,
correct data, physical-owner ACKs and drain. Publication/native controls/refusals
are separate. Historical or scoped passes cannot be joined into a whole-project
PASS; see [the historical audit](VALIDATION.md#main-plan-acceptance-audit).
