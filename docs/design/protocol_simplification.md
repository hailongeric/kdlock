# Simplifying delegated execution

This document records unimplemented alternatives after the spin/mutex optimization
phase closed on 2026-10-09. It does not schedule additional implementation work.
The later [rwlock ABI3](rwlock_implementation.md) adds native writer admission to
the existing JIT engine; it implements neither the outlined API nor the proposed
native-register JIT tier below.

KD's largest simplification opportunity is to give the compiler a more explicit
critical-section boundary. A normal function with an input/result object is much
easier to delegate than an arbitrary interval between two lock calls. The existing
JIT API must also recover progressed instructions, nested locks and native suffixes;
those obligations explain much of its state.

## Why TCLock needs less state

TCLock resumes compiled code on the waiter's real stack. Six saved callee-saved
registers and the stack pointer carry its native continuation. During JIT execution,
KD keeps physical RSP/RBP on the executor's wrapper frame and maps the waiter's
logical registers separately. Virtual SP/BP still address the waiter's original
stack. Register conflicts, translated stack accesses and budget checks add work.
At the time of this 2026-10-09 proposal, KD mutex also preserved the original
Linux mutex owner for native peers. The current [KD-only mutex](kd_only_mutex.md)
removes that bridge and owns its exclusion directly, while retaining the legacy
delegation queue and JIT execution model.

The hot path should prove simple requests once, then keep their execution short.
It still needs each request's publication, source OPEN/readiness, identity,
ownership and completion checks. A batch lease can amortize source references;
it cannot replace those checks. Generic recovery must preserve exactly-once
effects, the physical owner, final ACK and frame retirement.

## Compiler and stack choices

| Approach | Benefit | Required contract |
| --- | --- | --- |
| Local translation proofs | Remove redundant loads/checks without changing callers | Partial registers, alternate entries, flags, finite work and FULL fallback stay correct |
| Explicit outlined body and context/result object | Explicit inputs/results and compiler-managed locals simplify the source contract | New opt-in API; runtime owns the outer lock. Mandatory JIT remains; native stack/register execution needs the separate tier below |
| Native-register/native-stack JIT tier | Could preserve native register allocation and avoid virtual stack rewrites | Prove a restricted region, relocate source references, preserve flags and bounds, restore the executor stack before C, and capture exact progressed state on every exit |

The latter two are design proposals, not implemented performance gains. For the
existing lock/unlock API, an initial native-stack tier should accept only a proved
simple region with no calls except terminal unlock and no task/GS dependency.
Hardware `current`, GS and scheduling identity would still belong to the executor.
Exception handling, unwinding, objtool/hardening and FULL snapshots need explicit
designs before live use.
Existing broad register-residency experiments did not establish a repeatable gain.

For a separately scoped prototype, the outlined operation is the preferred
starting point. An illustrative
`kd_apply(lock, descriptor, &operation)` would submit explicit hash inputs and a
result field. Its body would contain no lock/unlock calls. The waiter would remain
inside an ordinary C call while the physical owner executed the generated body.
Native, TCLock and KD must use the same body and context layout in a comparison.
Calling the original native function and reporting JIT would not satisfy the
current requirement.

Outlining with today's translator is a first compatibility prototype; it still
pays for the packet, virtual stack and traversal budget. Removing those costs
requires the separately validated native-register/executor-stack JIT tier.

Initially restrict this API to checked registered operations: no nested locks,
early unlock, calls, indirect control flow, blocking, task/GS/per-CPU inputs or
escaping local addresses. Require bounded stack use and a proved finite traversal;
a finite node allocation alone does not rule out a cyclic list. The producer must
leave its context untouched until completion. Refuse unsupported code before
execution; never restart a body after it has changed shared data.

This restricted contract could remove arbitrary continuation restoration, FULL
packets, nested ledgers and native-suffix ACK routing from **that API**. It still
needs exact lock/image identity, physical mutex ownership, per-request OPEN and
readiness checks, queue retirement, context lifetime and completion publication.
A waiter must distinguish physical handoff from completed execution. The current
lock/unlock API still needs its existing recovery and final-owner ACK state.

C syntax alone does not provide this continuation contract:

- GCC extended assembly must return with its original stack pointer. A dedicated
  assembly trampoline is preferable to depending on an incidental C prologue.
  [Extended asm](https://gcc.gnu.org/onlinedocs/gcc/Extended-Asm.html)
- Computed goto cannot jump into another function; cloning/inlining can change
  label identity. [Labels as values](https://gcc.gnu.org/onlinedocs/gcc/Labels-as-Values.html)
- Nested functions capture a static chain and may require executable-stack
  trampolines. [Trampolines](https://gcc.gnu.org/onlinedocs/gccint/Trampolines.html)
- `noipa` suppresses interprocedural optimization; it does not make a function a
  coroutine or define stack migration. [Function attributes](https://gcc.gnu.org/onlinedocs/gcc/Common-Function-Attributes.html)

## Memory savings need performance validation

The current implementation eagerly allocates up to 64 JIT blocks: 640 KiB per
block, or 40 MiB at full capacity. The tested lazy-backing candidate kept the same
64 admission credits but allocated each full-capacity block on first upload.
It preserved page alignment and stable addresses until drained unload. One
uploaded image needed 640 KiB of code backing, saving 39.375 MiB; metadata, task
records and waiter stacks were separate. Its owner array added 512 bytes and
maximum code backing remained 40 MiB.

That memory result is valid, but the original and cold-helper variants failed
throughput qualification and were reverted. The
[trial report](../../bench/results/380G10/bench/tclock_compare/20261008-protocol-simplification/README.md)
preserves their screens, full matrices and rechecks. Lazy backing is not a current
implementation feature, and no memory reduction was promoted in these trials.
Exact image-sized allocation is a separate problem: later chunks/recompiles may
grow, and moving live code requires a new executable-version lifetime protocol.
The [compatibility backport](legacy_mutex_compatibility.md) now versions mutex
images within the unchanged fixed-size pool; spin/rwlock and exact image-sized
allocation remain separate work.

The smaller structures already have distinct access patterns. KD's private
`kd_regs` leaves Linux `pt_regs` unchanged; spin request identity/state and IP/SP/BP
share one aligned line. Polling notifications are separated from successor writes.
Moving caller-stack contents into a compact request could invalidate escaped
addresses and native recovery. Alignment and apparently unused padding can also
separate independently active reservations or affect cache-set placement.

Spin reserves a 20 KiB continuation/wait region per CPU. Mutex reserves four
8 KiB waiter stacks per CPU because a sleeping physical owner can retain a stack
while another task runs there. Reducing stack sizes or slot counts needs worst-case
call-chain and high-water evidence for nested/FULL/owner-service paths, not just
the short hash body. See [spin storage](spin_implementation.md) and
[mutex storage](mutex_implementation.md).

## Why hash can benefit from delegation

The benchmark hash performs dependent chain reads and can modify list links and
node values. Holding one physical lock across requests amortizes lock-line handoff
and can retain useful table/node lines on one executor. This remains useful even
when data movement is smaller than in the cacheline payload.

KD pays queue/caller-stack transfer costs too, then adds translated traversal and
request processing. More delegated bodies cannot compensate automatically for a
slower service path. The [historical hash diagnosis](../../bench/results/380G10/bench/tclock_compare/HISTORY.md#hash-diagnosis)
found roughly 99.9% spin JIT coverage and similar total L1 misses to TCLock, but
more instructions. Those aggregate counters do not measure remote-memory latency.
Mutex retention trials increased delegation and batch length while losing
throughput. Measure service cost, route/batch exits and minority-node progress;
keep peak and sustained throughput separate.
