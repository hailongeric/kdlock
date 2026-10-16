# Known limitations and deferred work

Current scope is x86_64 kernel spin/mutex/rwlock delegation through explicit APIs.
KD mutexes support blocking and retain their own exact owner/ACK protocol.
They can opt into the bounded audited origin-CPU GS subset with an exclusive
claim. Rwlock ABI3 acquires write access before the
translated body. Implementation contracts live in [DESIGN](DESIGN.md);
[performance status](PERFORMANCE.md) records measured gaps and
[validation](VALIDATION.md) indexes source-specific receipts. None of those
measurements resolves the correctness limits below.

## Current checkpoint

The recorded owned provider at `585335b` extends `d8d14a1` with the accepted
[ABI4/reuse-32 c01 profile](PERFORMANCE.md#active-c01-18-worker-study), limited to
KD-only object lifetimes and the captured x86-64 configuration. Its
[targeted receipts](VALIDATION.md#current-owned-protocol-verification) do not
establish fairness, general oversubscription or universal Native parity.
The later [c01/post64 full-grid comparison](PERFORMANCE.md#fresh-c01-164-worker-comparison)
measured 1–8 workers in steps of one and 12–64 in steps of four on a historical
66-vCPU boot. All 198 samples are correct and drained; the three-worker warmed
peak misses 97% of Native. Full-grid parity and its two fresh confirmation blocks
remain outstanding. The predominantly SELF results do not establish a benefit
from bulk delegation. Optimization acceptance for other payloads and post-work
settings requires separate studies.
The broader native-first experiment remains rejected and archived. None of these
results waives ownership, lifetime, progress or drain requirements, or resolves
the failures below.

The [2026-10-16 expanded comparison](PERFORMANCE.md#expanded-mutex-workloads)
covers c01/c02/c04/c08/c16, RCUHT and five private pipe/file API variants on the
required 64-vCPU topology through 60 workers. The associated
[support checks](VALIDATION.md#expanded-mutex-workload-verification) establish
the added workload coverage. The descriptive performance results retain
low-worker regressions and do not extend the narrow optimization acceptance,
generalize the private API adapter to arbitrary kernel objects or close the
64-worker collector gap below.

Recorded failures and unresolved coverage:

- New benchmarks use exactly CPUs 0–63: NUMA node 0 has CPUs 0–31 and node 1
  has CPUs 32–63.
  Spin/mutex timed runs support explicit collector sharing on CPU 63 at
  64 workers. Rwlock, real-API and the all-lock driver still need that support;
  through-60 runs leave their full-grid gate open. See the
  [runner support table](../tools/vm/README.md#complete-164-worker-comparison).
- The later immutable owned-image implementation and opt-in origin/NUMA policies
  have [separate source-specific receipts](VALIDATION.md#origin-readiness-and-image-version-verification).
  Keep origin claims and NUMA selection disabled by default until their documented
  [screen and confirmation gates](../bench/tclock_compare/README.md#owned-origin-and-numa-comparison)
  are met; the recorded origin/NUMA comparison missed those gates, and the older
  c01 acceptance does not cover these additions.
- Concurrent cold promotion stalled with an RCU warning in c16/t4 preparation.
  Single-CPU preparation avoids that phase rather than fixing it. The fixed
  [failure record](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md)
  retains the original inputs.
- The [owned-only checks](VALIDATION.md#owned-only-mutex-verification) cover
  bounded scheduler probes and 16-worker JIT/FULL/ACK cases. They do not establish
  general oversubscription progress or fairness; earlier implementations' failure
  records remain in the [validation history](VALIDATION.md#fixed-records).

## Delivery scope

Keep the two-word wrapper ABI, separate backend identities, exact physical owners,
exact acquisition references and final ACKs. Shared storage must survive its final
reader. Builds/tests/benchmarks run in the recovery guest; default work does not
change its kernel. Mutexes permit sleep with migration pinned; an origin-sensitive
owned image additionally requires a spinning claim. Blocking scheduler/JIT
evidence does not retroactively establish a pass for historical oversubscription
failures.

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

KD spin owns its word; TCLock/Native own theirs. KD owned mutex uses its own
owner word, OSQ and tagged wait list. Its Linux-compatible object geometry does
not permit Linux or TCLock callers on the same object. Preserve ledger identity,
physical exclusion, frame pop, owner ACK and storage retirement as separate
operations.
KD rwlock owns its count and KD gate. Ungated native writers retain exact
nondelegated references; gate quiescence alone does not establish count or reader
drain. No Linux/TCLock operations may access the same KD rwlock object.

### C3. Immutable JIT publication and lifetime

Owned mutex publication now binds code, requirements and generation in immutable
descriptors. Complete uploads use separate blocks; every published version survives
until terminal session drain. Pool exhaustion refuses replacements. The remaining
spin/rwlock scope still overwrites its RIP-indexed block and remains
deferred. Source leases and ABI tags alone do not resolve that lifetime problem.

### C4. Instruction, flags, and fault semantics

Processor-state instruction admission now refuses interrupt/uaccess controls,
MSRs, hardware registers, extended state and unsupported instructions before
emission; INT-to-NOP and silent flags-instruction omission are removed. See
[instruction admission](design/admission.md#processor-state-instructions).
General instruction/flags repair remains deferred: instrumentation flag clobbers
and incomplete flags/SIMD/FPU restoration are still limits. Packet comparisons
do not prove live hardware flags restoration, and the scalar allowlist is not
a proof of every existing lowering's semantics.

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
