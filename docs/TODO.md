# kdlock Open Tasks

Current work list as of **2026-09-19**. Implementation contracts live in
[DESIGN](DESIGN.md), state layout in [JIT_REGISTER_ABI](JIT_REGISTER_ABI.md),
and historical evidence in [VALIDATION](VALIDATION.md). Completed step-by-step
logs have been removed from this task list; Git history retains their detail.

## Current Checkpoint

The default provider requires `kdclobber2`'s caller-clobber v1 interface; older
kernel installers have been removed. Ordinary spin/mutex requests capture
and restore RIP/RSP/RBP; intermediate exits materialize FULL logical GPRs.
Waiter and combiner share one preallocated request/frame/register packet.
Both caller ABIs use one resident C batch loop. Shared PT/Stack backing,
producer-prepared hints, diagnostic identity reuse and normal-root admission/
retirement specialization are implemented. The independent TCLock backend
switches waiter stacks to execute native code; it does not replace kdlock JIT.
Spin nodes now separate links/hints from notifications in a 128-byte aligned
stride; 64-byte gate slots isolate independent locks. Exact shared waiter
accounting remains unchanged.
See [current execution paths](../bench/spin_cacheline/EXECUTION_PATHS.md).

[Earlier paired measurements](../bench/spin_cacheline/results/20260919-cacheline-isolation.md)
belong to their frozen source and do not imply a general speedup or a current
full-suite PASS. Known unresolved failures remain:

- Concurrent cold promotion stalled with an RCU warning in c16/t4/clobber
  preparation. Single-CPU preparation avoids this phase in steady-state
  measurements; it does not fix it. See [the failure record](../bench/tclock_compare/results/20260918-native-stack.md#失败记录与边界).
- Seven-role/two-CPU mutex mode 4 hit a soft lockup with pinned busy polling.
  Other mutex passes do not replace this case; see [the failure](../tests/README.md#mutex-pinned-mode4-failure).
- The older oversubscribed mode-5 run published code but missed actual JIT.
  Its polling strategy differs from today's; see [historical evidence](VALIDATION.md#mutex-oversubscription-assessment).

Hotlock discovery now keeps CPU/lock counters and windows per CPU, reads TSC
every 10240 observations and publishes only qualified addresses. Cooling closes
fresh admission; published identities remain until provider teardown. Sparse
monitoring is implemented. Benefit-based native/probe/delegate selection and
shared-identity retirement remain unimplemented. The latest
[component comparison](../bench/hotlock_record/results/20260919-local-discovery.md)
does not establish current complete-operation throughput or JIT share.

## Delivery Scope

Scope is **x86_64 kernel spin/mutex delegation** with existing guest hooks.
Userspace/futex, rwsem and cross-architecture ports are outside the project.
Ordinary spin and mutex use separate clobber identities. IRQ/BH/irqsave/trylock,
explicit nested and special mutex APIs retain their contracts. Preserve two-word
wrapper args and physical owners. Mutex minimal roots borrow the node packet;
FULL exits detach it before control services and native owner ACK.
New protocol code needs purpose and constraint comments.

The user decisions of 2026-09-14 and 2026-09-16 prioritize supported main paths
and basic plus directly affected checks. Extremely uncommon resource/schedule/
alias combinations are optional coverage, not delivery gates. Full suites
require explicit selection. Do not delete existing tests, relax admission or
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
selection is in [JIT_EXECUTION](JIT_EXECUTION.md#7-分层与增量回归).

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

kdlock retains Linux L for native-peer exclusion and private S for scheduling;
mutex ownership remains with its actual acquirer. Native continuations keep
owner mailboxes/ACKs and source/request references until the last use.
Node reuse, waiter wake and frame retirement are separate boundaries.

- [ ] Optional generalization: generic hook-reader/drain and nonlocal-exit
  lifetime requires kernel integration; source pins do not supply it. Lock
  allocation/free identity needs subsystem integration. See [the assessment](DESIGN.md#31-source-lock-and-hook-lifetimes).
- [ ] Optional coverage: wider native-peer, cancellation and oversubscription
  schedules. Preserve live waiter accounting, release publication, origin/
  ticket identity and no-access-after-final-ACK rules in current changes.

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
and concurrent-replacement counterexamples remain in [DESIGN](DESIGN.md#721-dynamic-address-gap).
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

### Shared Request Storage

The [shared spin request contract](DESIGN.md#911-reuse-before-copy-contract),
clobber ABI, common C loop, PT/Stack backing, prepared hints and diagnostic
identity reuse are implemented. Independent owner ledgers and shared-lifetime
references remain necessary; removing every atomic is not the objective.

- [ ] Measure remaining waiter-count RMWs and duplicate entry lookups before
  changing accounting. JIT-disable is a safety latch, not a statistic or
  performance-demotion switch.
- [ ] Measure generated dispatch, address/virtual-stack rewriting, caller spills
  and wrapper service cost separately where feasible.
- [ ] Measure nested contention; single-lock benchmarks cannot evaluate child
  ledger or virtual-waiter optimizations.
- [ ] Further mutex frame/packet sharing must preserve the independent frame
  lifetime after a native waiter releases its node; ordinary minimal roots already borrow it.

### Hotlock Monitoring And Adaptive Admission

Implemented: CPU-local frequency and per-lock discovery before process selection.
One TSC sample per 10240 observations evaluates local candidates. Only qualified
addresses enter the shared positive set; cached positives never read it. There
are no shared warmup counters/windows or negative states. Local expiry retries,
collisions may lose approximate history, and each CPU qualifies independently.
Cooling changes new admission only; unlock and owner ACK remain independent.
See [sampling protocol](DESIGN.md#hotlock-monitoring) and
[component comparison](../bench/hotlock_record/README.md).

Remaining work, **not current behavior**:

- [ ] Evaluate native/probe/delegate selection using contention and actual batch
  amortization, bounded probes, cooldown and hysteresis. Validate complete
  operation throughput and latency against matched native runs; frequency and
  JIT percentage alone cannot decide profitability.
- [ ] Change admission of future roots only. Outstanding tickets, batches,
  native owners and final ACKs finish under their original protocol. Retain
  compiled entries where valid; demotion is not source retirement.
- [ ] Record batch-ending reasons and compare short/long batches. Four-thread
  samples are already promoted and ready; lowering the promotion threshold
  does not explain or fix their roughly two-body batches. The new 8/16-thread
  points show the transition to longer batches; see [log analysis](../bench/tclock_compare/results/20260919-thread-scaling.md#batch-length).

The desired steady state is inexpensive native execution when delegation does
not pay, sustained delegation when it does. Probes and workload transitions
naturally mix paths. Do not accumulate waiters just to report 99% JIT or count
native bodies as JIT. Zero JIT can still cost more than Linux. Cold-promotion
correctness remains a separate open defect.

### Instrumented Measurement Foundation

Complete-operation throughput, actual body counts, translation wall/CPU/RSS
and opt-in jit_timing exist. Ten phases include queue, owner wait and native
handoff; nested inclusive intervals overlap and are not pure CPU cost.
Functional ioctl p50/p99 includes instrumentation and scheduling.

- [ ] Separate acquisition, queueing, body, hostcall, native suffix and
  observation costs with justified boundaries; do not add overlapping timers.
- [ ] Obtain suitable latency distributions and memory/cache-transfer evidence;
  existing flat-IP samples do not measure causal transfers or pure wrapper cost.
- [ ] Evaluate exact waiter accounting independently; its shared RMWs remain
  true sharing. Node notification/gate isolation is implemented and
  [paired measurements](../bench/spin_cacheline/results/20260919-cacheline-isolation.md)
  show a 20-thread gain and a 4-thread regression. Separate the two layout
  contributions and quantify gate isolation with a multi-lock experiment;
  the single-lock comparison does not measure cross-lock interference.

### Comparator Feasibility And Matched Experiments

The ordinary-spin [Linux/TCLock/kdlock comparison](../bench/tclock_compare/README.md)
exists with matching callers, fresh sessions, actual delegation and drain checks.
Earlier upstream mutex incompatibility remains separate; disabling mutex JIT
is not a native-delegation comparator.

- [ ] Expand contention, CS size, input/state, affinity and sockets with balanced
  repeated trials; establish amortization.
- [ ] Evaluate fairness, batching, code-pool sizing and optional NUMA policy.
  Spin NUMA needs broader opt-in evidence before a default change; mutex has
  no NUMA-local delegation policy.

Earlier phases are indexed in [benchmark history](../bench/spin_cacheline/results/HISTORY.md).
Current results do not erase failures or make old source versions current acceptance.
