# Reached-path execution

## Direction and baseline

The November 3 direction replaces production whole-CFG preparation with
execution-driven supplementation. Decode the current straight-line segment;
when execution selects an edge, resolve only that actual successor. Do not
require a complete callee closure, return graph, both sides of a branch or 55
ready MM images before execution can begin. Decoding instruction boundaries,
faithful lowering, source residency and exact runtime ownership remain required.

The isolated branch is `codex/reached-path-translation`, worktree
`/tmp/kdlock-reached-path-translation`, baseline
`1702a520cbd991f0c9d8fe96f852c2de44b1e8a3`. The previous bounded-CFG candidate
remains reachable on `codex/unified-lock-queue-mm`; master is unchanged. This is
a general execution-layer change, with no mmap1-specific adapter or MM body
change. The public lock acquisition, release, downgrade, cancellation and error
contracts remain unchanged.

The baseline VM build and 11 helper plus 11 killable/nesting phases pass and
drain. Its focused reply is
`/tmp/kdlock-mm-1702-v3-first-20261103/reply.json`, SHA256
`216bb319bd56577bc5ec97fc63cbe94d50581c8d9b0315f0154b880e0ad4ccb8`.
Its actual mmap1 attempt was **not started**. The kernel remains component
`1ab7124abb6140752c1f0bb6e862144d426a3875`, Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, boot
`22c0a1d3-64b3-4de3-867c-e0521c6ba8c3`, with `kd_mmap=on`.
These historical checks do not validate the new engine.

## What is removed from the production requirement

The old path uses `decode_regions`/`dis_multiblock`, repeatedly extends source
windows, discovers direct callees and calls `indirect_jump.find` before image
emission. The last actual attempt stopped at 22 covered-root rebuilds plus ten
source extensions with 215 incomplete blocks. Increasing that allowance is no
longer the chosen approach. Keep the old path as an explicitly selected checked
or historical regression utility; do not silently invoke it for a new miss.

At a reached PC, decode sequentially to the first control transfer, instruction
service boundary or finite local instruction limit. At the local limit, emit an
explicit fall-through event. Never inspect an untaken successor to decide
whether the current segment may execute. An unavailable callee or region is an
execution event, not a permanent rejection of the whole critical section.

## Canonical state and reached events

The continuation keeps one canonical packet and the existing exact ownership
records. An event exports FULL GPRs, source flags, IP, SP, BP and persistent
execution budget before runtime acts. The first entry must honor the existing
MINIMAL clobber contract: do not read absent GPR slots or invent entry proofs.
Defined API results, including successful killable acquisition returning zero,
must be materialized separately from compiler-clobbered values. The two-word
wrapper layout is unchanged. Proving this entry join is a Stage (b) prerequisite.

| Encountered source event | State change and next action |
| --- | --- |
| Straight-line end | Preserve state and resolve the actual next PC. |
| Conditional branch | Evaluate the actual flags, select one target, and resolve that target only. |
| Direct/indirect CALL | Evaluate the operand before changing SP; push the actual source next-PC word once; resolve the actual target. |
| JMP/tail JMP | Resolve the target without a source stack push or pop. |
| RET/RET-with-adjustment | Read and pop the actual source word once, apply the exact adjustment, and resolve that value. |
| Exact KD control | Dispatch by actual API, object, live frame and owner ticket. Preserve existing result and completion rules. |
| Registered Native API | Execute only that declared interval on O, then route its post-CALL state back to E. |
| Supported instruction service | Execute only the reached instruction interval with its declared context contract, then resume E. |

A return word need not correspond to a CALL observed since capture. Native
caller frames already exist; a helper can return while retaining a lock.
Do not replace source stack words with a precomputed return whitelist or make a
new shadow CALL stack the authority. Existing known CALL services consume their
own pending word exactly once; a region transition must not consume it again.

The runtime resolves controls before ordinary code. Ownership and nesting come
from the current exact records, not lexical lock depth inferred from a graph.
A delegated writer can downgrade, retain its read credit while its read tail
runs on E, release that credit and let E freshly acquire for its own pending
writer request. Ordinary read acquisitions remain local. No implicit upgrade or
extra writer acquisition is inserted into a caller's public read release.

## Root family, regions and transactions

Separate stable root identity from the active execution artifact. The current
`root->image`/`frame->image` assumptions cannot stand for both concepts.
`service_memory.inc` currently compares a pending operation to `root->image`;
its source must instead be the exact artifact retained by that transaction.
`kd_exe_resume_retained` and post-service completion must resolve the canonical
next PC through the family rather than demand a label in the old image.

| Record | Required fields and authority |
| --- | --- |
| Family | Source epoch, root entry, ABI/policy, generation, active frame/job references, retirement state and cache index. |
| Immutable region | Source PC/extent and exact bytes identity, source lease, code span, source-event metadata, publication generation and references. |
| Cold instruction artifact | Exact decoded bytes and operands at current PC, source lease, origin/executor context and sequence; retained while a service is pending. |
| Reached-event transaction | Frame identity/generation, parent/nesting identity, event sequence/kind, canonical packet phase, pre/post SP/PC, expected active artifact and exact ACK. |
| Compiler job | Family/frame authority, source epoch and reached PC, job sequence/state, result generation and writer/source references; never owns or copies the packet/stack. |

No region switch occurs while a KD, Native CALL, memory or instruction
transaction is pending. Retain that artifact through O's last stack access and
completion ACK. Then release its transaction reference and resolve the new PC.
Nested requests retain their own generation and parent records; finishing a
child or an early outer unlock does not retire another live artifact.

Current retained ordinary CALL/IJ misses return `KD_EXE_RUN_ERROR`. Introduce a
resumable reached-event state; do not reinterpret that terminal result as a
successful continuation. Final public release still follows existing exact
release/ACK/restoration rules, without an additional source RET.

## Cold progress and compilation

Correctness must not depend on a userspace compiler being scheduled while a
Native spin/preemption pin is held. Waiting or parking in that state is not a
solution. The chosen progress mechanism is a resident kernel cold executor /
lowerer operating on the canonical packet, with preallocated decode/operand
storage and the current source lease. It must execute supported cold source
operations on E without sleeping, allocating an unbounded object or waiting for
another CPU. Cached native regions optimize this same execution; cache capacity
or a delayed optimization job cannot return a new public lock error or force
an original-task suffix after effects have committed.

Stage (b) must first prove a bounded scalar instruction path on E's own Native
runtime stack, including effective addresses, widths, flags and source-stack
operations. Do not introduce an unvalidated foreign-stack raw-byte path merely
to avoid implementing operand semantics. A segment can end before a required
returning instruction service. The cold path and compiled path must implement
the same source effects and transfer into each other only at exact FULL events.
A code-cache miss therefore remains delegated execution; it is not permission
to execute an arbitrary ordinary callee on O.

E's runtime stack is distinct from source RSP and O's retained source-stack
memory. Cold LOCK, XCHG, CMPXCHG and related operations must preserve their
actual atomicity and ordering; decomposing an atomic operation into C loads
and stores is not equivalent.

Optional userspace optimization uses resident workers established before
activation. Current `workspace.inc` uses `system()`, `compiler.inc` forks/execs
Python, and `disassem.py` launches GCC and binutils. Fresh child MMs sample the
active provider even when their parent has an older ordinary backend. Prestarting
only Python does not remove that dependency. Replace workspace operations with
in-process operations and use a resident assembler/encoder, with exact byte,
relocation and wrapper equivalence checks. Miasm's captured
`assemble_block`/`asm_resolve_final` are an available encoding starting point,
not a proven replacement for current GAS/macros. No task-name exception or
mmap1-only compiler exemption is allowed.

An optional compiler job must not be necessary for atomic forward progress.
Worker loss or job failure leaves a correct cold execution path. Keep workers,
FD holders, requests and publications in an exact ledger. Creating unrecorded
postactivation tools is not acceptable progress evidence.

## Cache storage, source leases and retirement

The existing 64 whole-image descriptors cannot represent an arbitrary number
of reached blocks. Add separate preallocated region metadata and suballocate
immutable code spans from ordinary 4 MiB arenas, retaining the existing overall
pool ceiling. Reserve an arena under the existing allocator gate; do not consume
one whole-image descriptor/block per region. Near-text and legacy allocations
keep explicit independent ownership. Published region bytes and source metadata
are immutable. Cache links live in separate data cells.

The first slice retains published cache regions until session teardown; no
approximate eviction or slot reuse is introduced. Cache exhaustion uses the
correct cold path on E. It cannot make a committed acquisition fail or wait
forever for an arena held by that same continuation. Source leases are execution
authority independently of optional cached code. Decoder/source storage must
have a bounded per-frame progress path even when optimization storage is full.

Unavailable source residency and the current 64-module-owner capacity are
separate from code-cache exhaustion. The cold path does not make an unavailable
source lease valid. Live text replacement also needs a proved epoch/invalidation
contract; residency alone is not proof that cached source bytes remain current.

Current source draining closes root pin/publication while frames may remain.
An already admitted frame can still encounter a new target after DRAINING.
Its exact frame/epoch/job authority must permit descendant source retention and
region publication, while unrelated new root admission remains closed. Otherwise
an early retirement request strands a committed critical section. Retirement
must account for active frames, pending events/jobs, Native stack accesses,
artifact references and worker FD holders before freeing anything. Reuse needs
a new generation after all old acknowledgments; an old reply cannot populate a
new slot.

Keep one persistent per-frame instruction/block budget across cold steps,
region switches and services. The existing wrapper resets `Stack_BUDGET` on
entry; that cannot become a reset at every reached block. At a legal scheduling
boundary, unbind first and honor rescheduling with existing ownership rules.
Never sleep while a Native pin remains. No oversubscription or rwsem fairness
redesign is part of this change.

## Context and explicitly unfinished points

Context classification remains necessary runtime semantics, not upfront CFG
analysis. Match saved O/E IRQ and preemption state before proxy execution.
Task-dependent Native operations still execute on O and return. Ordinary
per-CPU accesses must not observe an IRQ-only intermediate state merely because
E can run concurrently with O's IRQ; use the existing exact instruction service
or a separately proved stable-context lowering. PAUSE and ordinary fences must
execute directly on E when encountered, without a per-occurrence O round trip.

RDTSC/RDTSCP/CPUID have a source-backed returning-service design; CPUID also
requires the executor serialization pair. Persistent IRQ/DF changes, privileged
context switches, exception/fixup behavior, task-dependent memory and unavailable
source residency need complete reached-instruction contracts. They are not
silently handled by resuming an ordinary Native body. New opcode/context support
must be enumerated and validated before claiming a caller supported. Whole-kernel
arbitrary replacement, unsupported configurations and existing unvalidated
boundaries remain explicit. In particular, continue refusing CONFIG_PREEMPT_RT,
CONFIG_DEBUG_MUTEXES, CONFIG_DEBUG_LOCK_ALLOC and lockdep.

This design does not claim those unfinished contracts are implemented. The new
mode must remain an isolated candidate until its actual reached instructions
and intervals preserve Native behavior. No unsupported after-effect path may be
reported as an API-equivalent success.

## Activation, proof and stages

Keep the 55-site audit as source/ABI metadata. Replace complete-image readiness
with verified demand-entry, cold-execution, source and lifetime readiness.
First entry may commit acquisition and execute its first reached block without
an application image. Successful acquisition retains priority over signals;
compilation never creates a new cancellation decision after commitment.
Cancellation before commitment observes O's signals and retires the exact node.
The existing downgrade/read-credit/nesting protocol is retained.

Replace the old session rule of no compiler children and an unchanged complete
image registry with an exact worker ledger and append-only family/region event
ledger. Unexpected workers, source epochs, mutations or publications fail the
check. This is a new positive proof, not deletion of an old readiness test.
Unchanged applications still enter through actual mmap/munmap syscalls.

1. Commit this model and its explicit progress/lifetime obligations before code.
2. Implement local decoding/reached events and the allocation-independent cold
   path. Prove selected Jcc, CALL operand-before-push, inherited RET, tail JMP,
   truncated bytes, flags/widths and no untaken-branch decoding.
3. Implement family/region storage, exact packet/service transitions, persistent
   budget, source draining and optional resident optimization publication.
4. Join live controls and general writer/read-tail execution. Preserve the 11
   helper and 11 killable/nesting phases; add simultaneous misses, pinned cold
   progress, stale replies, cache exhaustion and retirement during an active miss.
5. Validate unchanged mmap1 threads/processes once per point. Join source PCs,
   cold/compiled execution, E/O identities, actual syscall return, delegated
   downgraded tails, fresh writer acquisition and final retirement. Then measure
   Nano and application performance separately, preserving all regressions.

## Stage (b) implementation boundary

The next implementation slice is the resident scalar engine and its local
decoder, not MM activation. It exposes exact reached events to the existing
runtime without introducing a second acquisition or cancellation authority.
The initial MINIMAL packet contains only IP/SP/BP. The ordinary clobber wrappers
declare the remaining GPRs and condition codes as outputs/clobbers; initialize
each absent scratch register explicitly instead of reading old slot contents.
`KD_LOCK_DIRECT_RESULT_CALL` captures label 1 before its source `xorl %eax,%eax`;
the conventional failed C return jumps to label 2. A committed cold entry must
execute the success entry, and must never synthesize a post-commit signal error.
FULL events retain all actual source GPRs and arithmetic flags.

Source fetch retains only bytes requested by the current instruction through a
frame-authorized text-range pin. The current frame-scope source pin already
permits descendants during DRAINING; no unrelated root is admitted. Each cold
step uses fixed local storage and returns the actual reached successor. A
bounded segment run preserves its instruction budget across successive calls.
An unsupported instruction is an explicit unexecuted event; it is neither a
public lock result nor authorization to run a suffix on O. LOCK-prefixed or
implicitly atomic operations require an atomic implementation before execution.

The focused validation compares selected scalar effects against Native x86
execution, checks branch-directed fetching, source CALL/RET words, MINIMAL entry,
PAUSE/fences, and unsupported instructions without effects. The kernel fixture
must execute on a distinct E task and keep source stack storage alive. Existing
helper and killable/nesting phases separately verify the unchanged lock protocol;
they do not establish cold MM coverage. The family/artifact, Native service and
MM activation joins remain the following stages. No Stage (b) result alone
establishes returned mmap1 execution, throughput or performance acceptance.

The internal frame adapter accepts only the currently bound packet owner with
no pending KD/Native/memory transaction. It does not reject an early outer
release while another exact owner remains live. Its first memory-store slice
is limited to the retained source task stack: ordinary data stores still need
a complete fault/lifetime contract. Source-width reads use the kernel's typed
nofault primitive. These are explicit candidate coverage limits, not a change
to public API success, error or downgrade behavior. The standalone engine
fixture supplies ordinary private RAM and all-or-none store callbacks; its
checks do not prove the still-unactivated frame adapter or arbitrary MM stores.

Adapter state also records the exact request identity and generation. A reused
frame and packet can have the same addresses; an old scalar state must fail
before fetching or executing in that new request. Focused adapter fixtures
exercise this distinction and committed-prefix preservation separately from
the cold engine's instruction effects.

### First focused validation attempt

The first VM unit attempt used
`d25b210352aea98a1d13b2ab79c5e1baf4c20166`. Reached-path decoding passed all 19
cases, and private-source admission passed all nine cases. The affected source
lifetime fixture failed to compile: its capability assertion still expected
version 16 although the baseline already advertises version 17 and
`KD_JIT_CAP_INDIRECT_TAIL`. Its expected feature set and mutation anchors also
needed that existing capability. Keep every prior probe and add a direct probe
that removing the indirect-tail capability is detected; production capability
values remain unchanged. This is a fixture correction, not a passed rerun.

The exact reply remains at
`/tmp/kdlock-reached-d25b-checks-first-20261102/reply.json`, SHA256
`b02d448f25137b356874b4e3159434820ba6b842c4c6e1bedd33aef7835a482c`.
No provider build or live fixture was launched by that failed attempt.
