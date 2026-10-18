# Known limitations and deferred work

The [KD-only mutex contract](design/kd_only_mutex.md) is the current replacement
assumption. Whole-kernel rebuilding, lockdep/RT/ww_mutex integration and broad
oversubscription remain unvalidated. Removing the Linux mutex bridge does not
resolve historical pinned-producer scheduling failures.

Current scope: x86_64 kernel spin/mutex/rwlock delegation and sleeping rwsem
with local readers and explicit outer writer delegation. Implementation contracts
live in [DESIGN](DESIGN.md); [performance status](PERFORMANCE.md) distinguishes the
accepted KD-only mutex, selected rwsem results, the separate spinning-rwlock
reference and historical comparisons. These unresolved issues remain documented;
this list does not schedule new work. Historical evidence is
indexed in [VALIDATION](VALIDATION.md).

## Current checkpoint

KD has explicit spin, ordinary mutex, rwlock and rwsem APIs. Spin/mutex/rwlock
workloads compare KD, TCLock and Native; sleeping rwsem compares KD with Native
because this port has no TCLock sleeping rwsem. KD tracks real lock owners and
unlock acknowledgements, keeps source modules loaded while needed, and shares
register packets between waiter and combiner. It does not intercept global lock
calls. Historical comparisons retained configuration-specific throughput gaps;
see the [spin/mutex report](../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md)
and [RCUHT rwlock report](../bench/results/380G10/bench/rwlock_compare/20261010-rcuht/README.md).

Rwlock ABI3 moves reader drainage and write admission before the prepared body,
resolving the older hash-writer translation refusal. Native writers have a fast
path, and the count and gate occupy separate cachelines in a 128-byte object.
The historical 40-vCPU RCUHT matrix completed 270 runs correctly and drained,
but met both throughput targets at only 21/30 points. That captured version and
placement had read-heavy cross-NUMA and two-worker writer gaps; those results do
not establish a universal or current KD rwlock limitation. The separate fresh
spinning reference is source- and topology-specific and remains distinct from
sleeping-rwsem performance. All 270 sessions completed correctly and drained.
KD is slower than both comparators at c08/20%/one worker and slower than TCLock
at RCUHT/1%/60 workers; it meets both measured criteria at 29/30 points against
Native and 28/30 against TCLock. These
comparisons retain repetition ranges and do not establish statistical
significance. TCLock's stack-delegation share remains unmeasured.

The selected [rwsem optimization](../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
uses separate admission/drain queues, independent cachelines and finite polling
before publication, while preserving the accepted KD mutex protocol. All 756
sessions completed correctly and drained. KD meets both observed throughput
criteria at 117/126 points against Native, with six misses and three split
execution-status groups. Against the initial KD there are 110 passes, 12 misses
and four split comparisons. Low-count regressions remain substantial: c01/c08
at 20% writes and two workers reach only 0.286×/0.276× the initial KD whole-run
throughput. The six Native misses are the three 20%/one-worker cases,
c08/1%/two workers and c01/c08 at 20%/36 workers. Split comparisons completed
all planned sessions; execution groups and variability remain in the report.
The 16,384-probe choice is platform-specific experimental tuning, not a universal
optimum. The
first-repetition Native variation in both baseline and selected focused screens
remains unexplained; governor-policy equality does not isolate its cause.
Continuous outer-writer arrivals can delay readers or ordinary writers, and no
Linux rwsem fairness or bounded-wait guarantee is provided.

The [initial rwsem report](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
preserves the `485729f` shared-queue baseline: 756 correct, drained sessions,
26/126 observed parity points, seven JIT-positive KD sessions and 371 local
fallback sessions. Its high-count regressions are historical evidence, not
current performance numbers. Neither waiting-path changes nor favorable
measurements resolve the correctness limits below.

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

Keep the two-word wrapper ABI, separate backend identities, exact KD physical owners,
exact acquisition references and final ACKs. Shared storage must survive its final
reader. Builds/tests/benchmarks run in the recovery guest; default work does not
change its kernel. Published KD waiters remain pinned polling.

Userspace/futex, real mmap-lock replacement, other architectures and
oversubscription redesign remain deferred. The [rwsem phase protocol](design/rwsem_implementation.md)
drains readers before writer publication and excludes ordinary downgrade during
an outer-writer cohort. It preserves pinned mutex producers and their existing
oversubscription limits. Outer downgrade, post-publication cancellation, Linux
rwsem fairness and general nested rwsem JIT controls remain unsupported.
Basic plus directly affected checks are the default; full suites need
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

KD spin owns its word; TCLock/Native own theirs. KD mutex owns its physical
owner word, wait list and legacy scheduling gate. Linux mutex objects or calls
cannot be mixed on it. Preserve ledger identity, local/delegated exclusion,
frame pop, owner ACK and storage retirement as separate operations.
KD rwlock owns its count and KD gate. Ungated native writers retain exact
nondelegated references; gate quiescence alone does not establish count or reader
drain. No Linux/TCLock operations may access the same KD rwlock object.

### C3. Immutable JIT publication and lifetime

The current KD mutex implements complete staged publication,
immutable mutex generations, frame binding and stale-miss rejection. Published
versions use the existing bounded pool and remain until session teardown; there
is no in-session generation reclamation. Spin/rwlock images still use in-place
storage. See [the backport comparison](history/legacy_mutex_compatibility.md).

### C4. Instruction, flags, and fault semantics

The current translator refuses unvirtualized processor-state instructions,
unknown mnemonics and equivalent context helpers before emission. INT-to-NOP and
silent special-instruction omission are removed. General flags repair,
instrumentation flag clobbers and SIMD/FPU virtualization remain deferred.
Packet comparisons do not prove live hardware flags restoration.

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
