# kdlock Open Tasks

Current work list as of **2026-09-25**. Contracts live in
[DESIGN](DESIGN.md), [execution flow](JIT_EXECUTION.md) and
[register ABI](JIT_REGISTER_ABI.md). Current measurements and the performance
backlog live in [PERFORMANCE_PLAN](PERFORMANCE_PLAN.md); historical evidence
remains separate in [VALIDATION](VALIDATION.md).

## Current Checkpoint

The provider requires kdclobber2 caller-clobber v1. Ordinary spin/mutex requests
capture and restore RIP/RSP/RBP; intermediate exits materialize FULL GPRs.
Spin waiter and combiner share a producer-owned continuation/frame/packet.
Each CPU reserves 20 KiB: twelve records at a bounded CPU-dependent offset in
the low 12 KiB, with an unchanged 8 KiB waiter stack above. Frame pop precedes
completion; native ticket borrows retire before root reclamation and origin unpin.
Single-pass simple batch metadata, one resident C batch loop, shared PT/Stack
backing, hints and normal-root completion are implemented. Explicit KD objects
use one 32-bit word; nondelegating requests use the full pending/MCS queue.
`spin_delegate=0` remains a native control, distinct from actual JIT evidence.

Admission is adaptive only. It uses approximate per-CPU acquisition/MCS totals
at a shared 512-publication sampling/comparison boundary. Native queue heads
can decline future admission when the captured queue prefix lacks five linked
successors. The cold successful CAS is inline. Spin waiter diagnostics use
per-CPU event totals: live aggregation is approximate, final balance is checked
after independent ownership/frame drain. Exact controls and limits live in
[the execution flow](JIT_EXECUTION.md#21-热度与角色) and
[diagnostic lifetime](design/locking.md#spin-diagnostic-identity-lifetime).

The current implementation has a completed [c1 matched matrix and nested/early
JIT checks](../bench/tclock_compare/results/20260924-warmed-peak.md), followed by
the [1/8-cacheline comparison](../bench/tclock_compare/results/20260925-c1-c8-warmed-peak.md).
These scoped results do not establish universal non-regression or a whole-project
PASS. Known unresolved failures remain:

- Concurrent cold promotion stalled with an RCU warning in c16/t4/clobber
  preparation. Single-CPU preparation avoids that phase, not its cause. See
  [the failure record](https://github.com/hailongeric/kdlock/blob/175d73bcc2faaa5ee9f9ab28a20491680d834043/bench/tclock_compare/results/20260918-native-stack.md#失败记录与边界).
- Seven-role/two-CPU mutex mode 4 hit a soft lockup with pinned busy polling.
  Other passes do not replace this case; see
  [the recorded failure](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/tests/README.md#mutex-pinned-mode4-failure).
- Older oversubscribed mode 5 published code but missed actual JIT. Its polling
  strategy differs from today's; see [the evidence](VALIDATION.md#mutex-oversubscription-assessment).

## Delivery Scope

Scope is **x86_64 kernel spin/mutex delegation** with captured guest interfaces.
Current spin integration is explicit; global mutex hook installation is disabled.
Userspace/futex, rwsem and cross-architecture ports are outside the project.
Ordinary spin and mutex use separate clobber identities. IRQ/BH/irqsave/trylock,
explicit nested and special mutex APIs retain their contracts. Preserve two-word
wrapper args and physical owners. Mutex minimal roots borrow the node packet;
FULL exits detach it before control services and native owner ACK.
New protocol code needs purpose and constraint comments.

The user decisions of 2026-09-14 and 2026-09-16 prioritize supported main paths
and basic plus directly affected checks. Extremely uncommon resource/schedule/
alias combinations are optional coverage, not delivery gates. Full suites
require explicit selection. Do not remove valid protocol checks or relax admission to
classify reproduced main-path failures as rare to manufacture a PASS.

Builds, tests and benchmarks run only in the recovery guest. Kernel changes
are not the default; separately authorized spin experiments retain their own
trees, releases and baselines. See [operations](AGENTS.md) and [manual](PROJECT_GUIDE.md).

## Direction And Priority

1. Diagnose known supported-path failures, preserving exact effects, real
   owners, source/request lifetime and final ACKs.
2. Improve measured ordinary-spin costs, including native admission and short
   batches. Report throughput, actual JIT share and observation cost separately.
3. Add useful bounded services and improve reproducibility as separate work.
   Optional generalization is not a prerequisite for these increments.

Immutable code versions, general flags/instruction repair and access-time
checks remain explicitly deferred. These are not pending permission questions;
document cleanup does not reopen them.

### Main-Plan Acceptance Audit

The objective remains actual JIT of existing critical sections, including
nested locks, allowlisted services and forward native continuation. Require
matching generated/published entries, returned-body evidence, correct effects,
owner ACKs and drain. Publication alone is not JIT. Native controls, context
refusals and kernel protocol probes remain separate categories.

The [historical audit](VALIDATION.md#main-plan-acceptance-audit) belongs to its
frozen source. Later scoped passes cannot be joined into a whole-project PASS;
old scheduling-dependent cases do not validate pinned polling. Current test
selection is in [tests](../tests/README.md); scoped native/relay fixtures do not
establish forced live remote-native schedules.

## P0: Correctness Contracts

### C1. Forward Continuation After Partial Execution

Implemented CALL-miss, quota and validated control/resource exits resume the
original waiter with current logical state, never replaying the prefix.
PENDING, post-acquisition spin, checked mutex stack and remote completion have
different ownership requirements; retain their checks and exactly-once effects.

- [ ] Fix reproduced supported-continuation defects as they arise.
- [ ] Optional coverage: broader partial-progress, remote and exhaustion
  combinations. Generic faults, IJ misses and instruction-budget exits remain
  fail-stop, not arbitrary native recovery.

### C2. One Protocol Per Physical Lock

Explicit KD spin objects use one KD word for exclusion and scheduling;
mutex ownership remains with its actual acquirer. Native continuations keep
owner mailboxes/ACKs and source leases until the last use. Spin uses root-ticket
borrows through executor pop; physical ACK, NATIVE_READY, frame retirement and
continuation reclamation are separate boundaries, as is node reuse.

- [ ] Optional generalization: generic hook-reader/drain and nonlocal-exit
  lifetime requires kernel integration; source pins do not supply it. Lock
  allocation/free identity needs subsystem integration. See [the assessment](design/lifetimes.md#31-source-lock-and-hook-lifetimes).
- [ ] Optional coverage: wider native-peer, cancellation and oversubscription
  schedules. Preserve live waiter accounting, release publication, origin/
  ticket identity, no message access after its ACK, and no frame/packet access
  after final handoff. A spin physical ACK does not itself retire the frame.

TCLock target locks use their own queue/unlock protocol. They cannot mix with
unmodified Linux qspinlock solely because both expose spin_lock; see
[compatibility](../tclock_backend/README.md#与-linux-原生-spinlock-的协议兼容边界).

### C3. Immutable JIT Publication And Lifetime

**Deferred by user decision.** RIP-keyed code is still replaced in place.
Independent locks, early release and recompilation can overlap old execution.
Source leases and ABI tags do not make versions immutable. Future work needs
complete-image validation, generations, publication and reclamation after all
executors finish. Source/hook lifetime is separate.

### C4. Instruction, Flags, And Fault Semantics

**Deferred by user decision.** INT-to-NOP, warning-only special instructions,
instrumentation flags clobbers and incomplete processor-state restoration
remain limitations. Software packet flags comparisons do not prove live flags
restoration. Future support needs an explicit instruction subset, liveness/
restoration and checked fault/continuation semantics.

### C5. Origin Context And Nested Boundaries

Current analysis screens the actual emitted JIT scope, tracks CALL/RET and
alias facts, and rejects recognized context/backend violations. Explicit GS
uses origin base; supported current_task loads use logical task. Neither is
a hardware task, scheduling, IRQ or RCU context switch.

- [ ] Optional generalization: hidden calls, arbitrary aliases, context-object
  lifetime and native suffix owner-sensitive behavior need separate analysis.
- [ ] Optional coverage: composed CALL/RET and concurrent pointer changes.
  Static core/module per-CPU screening does not check every runtime address.

#### Deferred Access-Time Guard

**Deferred by user decision on 2026-09-13.** Dynamic/module/context object
ranges and lifetimes, per-access validation, pre-instruction native continuation
and local CF/PF/AF/ZF/SF/OF preservation are unimplemented. Known dynamic-pointer
and concurrent-replacement counterexamples remain in [DESIGN](design/admission.md#721-dynamic-address-gap).
Entry predicates and bounded mutex stack checks do not close that gap. Future
packet requirements remain in [the ABI](JIT_REGISTER_ABI.md#31-访问时续跑的前置契约待实现).

Published delegation waiters remain preemption-disabled and PAUSE-poll;
sleeping/parking them is outside the requested design. Native mutex owner and
service paths retain their own scheduling behavior. Fixing the known mode-4
dependency must not silently restore the obsolete polling contract.

## P1: Evidence And Useful Services

- [ ] Complete fresh-checkout system/build reproducibility. Pinned Python,
  frozen source/environment capture and offline verification are implemented;
  bundled dependency bytes, reproducible kernel builds and immutable loaded-
  image identity are not. Documentation changes do not require a full matrix.
- [ ] Add typed bounded services only with explicit argument, clobber, context,
  sleeping, overflow and side-effect contracts. Clock and int_sqrt already
  exist; generic variadic printk and arbitrary pointer services do not.
- [ ] Optional coverage: randomized schedules and broader production-code
  exactly-once/linearizability fixtures. Missing dependencies are not SKIPs.

## P2: Performance And Broader Scope

The authoritative backlog is [PERFORMANCE_PLAN](PERFORMANCE_PLAN.md). It keeps
implemented work separate from experiments and defines comparison and stopping
criteria; this page does not duplicate its checklists.

### Shared Request Storage

Clobber, shared PT/Stack, hints, normal completion, continuation placement and
single-pass simple batch metadata are implemented. Independent owner state,
source leases, final restore reads and post-pop retirement remain required.
Future representation or sharing changes must preserve them; current layout is
in [frames](design/frames.md#911-reuse-before-copy-contract).

### Hotlock Monitoring And Adaptive Admission

Exact-key tables and CPU/lock windows remain. Approximate per-CPU ratio and
captured-tail admission have matching c1/c8 evidence; phase changes, multiple
lock streams and a general delegation-cost model remain unmeasured.
Admission changes affect future acquisitions, never the permanent safety latch
or existing source/request retirement.

### Instrumented Measurement Foundation

Current comparisons use three rounds and retain min/median/max plus the selected
best session. Cold preparation, short/long measurement behavior and individual
cost attribution remain open. Flat-IP samples and overlapping timers are not
causal cache-transfer measurements or additive CPU costs.

### Comparator Feasibility And Matched Experiments

Linux/TCLock/KD ordinary-spin comparisons exist. Wider NUMA, multi-lock, nested
and mutex measurements remain scoped work; the unresolved failures above and
explicit deferrals are not removed by throughput improvements.
