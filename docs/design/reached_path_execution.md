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

For a successful scalar step or edge, event length is the complete decoded
instruction length. A SOURCE or UNSUPPORTED event can contain only the prefix
bytes encountered so far. Its source PC remains authoritative; do not publish
those partial bytes as a complete immutable instruction artifact. Supplement
and retry that unexecuted instruction while retaining the already committed
prefix and persistent budget.

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

### Stage (b) measured functional endpoint

The bounded scalar implementation and focused checks are recorded at
[`reached-path-stage-b-20261102`](../../bench/results/10.176.26.71/tests/reached-path-stage-b-20261102/README.md).
The tested source is `4122b53ebc590da82679ffcbb23d4719b7db376a`: normal
provider build, 144 adapter assertions, 19 decoder cases, source-lifetime and
private-source checks, 37,700 resident scalar assertions and the existing 11
helper plus 11 killable/nesting phases passed. All live fixtures drained, with
unchanged frozen inputs and a final idle guest. The earlier failed fixture
compilation remains separately recorded.

This validates the bounded Stage (b) component and preserves the existing
protocol fixtures; it does not activate image-free public capture. Family/cache
and cold service-artifact joins are still required before actual MM execution.
No mmap1 run, delegation metric, Nano score or performance claim follows from
these functional results.

## Stage (c): image-free family, cache and service joins

Continue on `codex/reached-path-translation` from
`961550afdc1429cfd86cff138046d3f6eebacdf8`. Add an explicit provider option
`service_reached=1`; selected captures use resident execution without requiring
or allocating a complete application image. The ordinary image option remains
separate for compatibility checks. Reached-mode misses must never select a
local body or an original-task suffix. Public acquisition/cancellation and
owner transfer remain in the existing unified admission engine.

Each captured root embeds a stable family keyed by its exact request identity,
generation, entry ABI and source lease epoch. Its request generation also names
the family generation for this first slice. The family owns exact caller-held
reference records and a bounded, append-only cache of complete reached
instruction bytes. Cache hits revalidate actual source bytes before execution;
cache exhaustion uses the resident cold path. This first cache is decoded-source
storage, not native compiled code. It consumes no whole 4 MiB image descriptor.
No shared global family-capacity wait or per-instruction allocation is added.
Native region compilation remains optional later optimization.

An active service retains a separate exact family reference, source PC, bytes
and event sequence until its completion ACK. No instruction/cache switch or
packet reuse is permitted while that reference is live. Native CALL and GS
instruction services accept either their existing immutable image authority or
this retained cold artifact, never a null image treated as implicit authority.
Their post-service canonical packet returns to the family resolver; it does
not need a successor label in the old image. An ordinary unregistered callee is
decoded on E after the real source CALL word is pushed once. A known control
CALL preserves its current exact retirement and downgrade behavior.

Keep the instruction budget in continuation storage across yielding, nested
admission and returning services. A local segment remains bounded at 64
instructions, with a 16-instruction family cache in this slice. Small later CFG
extensions may optimize the reached neighborhood; neither large transitive
callee expansion nor complete MM prewarming is an admission condition.

The persistent budget is a 16-million-instruction scheduling window, not a
public lock error or a hard lifetime cutoff. Only exhaustion returns to the
runtime for a new window. If Native pins permit it, unbind and honor scheduling
there; held Native pins prohibit scheduling but do not terminate the source
body. The event sequence and total instruction observation do not reset.

The first joined fixtures require real locked RMWs before their first service.
Support ADD/SUB/INC/DEC/XADD/CMPXCHG and implicit memory XCHG with one actual
source-width CPU operation and captured arithmetic flags, including exact
accumulator behavior. No C load/store decomposition or unbounded CAS retry is
used. Source shifts/rotates and signed multiply also use exact Native-width
instruction effects. Ordinary data stores outside the retained task stack stay
within one page and use typed nofault stores. Cross-page data faults and other
context operations still need separate complete contracts.

Qualified scalar data stores use source-width operations on resident ordinary
kernel memory. A potentially partial copy is not a source instruction. Reached
atomic/context operations still require exact support; unsupported operations
remain explicit diagnostic boundaries, not successful lock results. Do not
activate the MM factory until its reached coverage and returning-service
contracts are actually validated. Preserve source text freshness limitations,
ordinary local readers, delegated downgraded tails, killable acquisition
priority, origin-signal arbitration and exact nested/non-LIFO retirement.

Focused validation must positively prove daemon-free roots, family/transaction
identity, same-artifact service ACK/resume, cache hits and full-cache cold
progress, cancellation while a holder remains locked, nested blocking and
executor downgrade followed by fresh writer admission. Retain the image-mode
checks and all earlier failures. Record reached-mode roots/completions and
unsupported events separately; no Nano or mmap1 performance claim follows from
these functional checks.

The first Stage (c) VM unit attempt, `bf3cb1fc`, passed the new 14-case ledger
driver, the 172-assertion GS decoder plus its three negative variants, the
144-assertion adapter and the existing continuation/helper/memory/mapped/Native
write validator drivers. Its family fixture did not compile: the same
`pthread_t` address was supplied as a restrict-qualified output and as the
thread argument. Use separate identity storage for the argument, preserving
`-Werror` and every reference/concurrency check. No provider build or live
capture was launched in that attempt.

The fixture-only correction `a7935391` passed all selected unit drivers, the
ordinary provider build and 47,658 resident engine assertions. Its first
image-free helper run reached opcode prefix `48 0f ba` at
`ffffffffc09edee5` (entry `ffffffffc09ed944`, request generation 15). The
unsupported bit-operation instruction was reported explicitly; the executor
then stopped and its origin remained waiting. No successful completion or
drain is claimed. Preserve the serial trace and failed outputs before recovery.
Add exact register BT/BTS/BTR/BTC semantics and Native differential coverage;
memory bit-string addressing requires its own complete contract. Do not avoid
the reached instruction by running a whole body on O or disabling the fixture.

The frozen ELF identifies the complete instruction as `48 0f ba f2 1f`,
`btr $0x1f,%rdx`, implementing the preemption-count predicate in
`tests/kernel/jit_continuation/payload/helper_memory.inc:80`. Seven earlier
helper phases completed, including sleeping, Native spin/RCU, an indirect
tail and mapped allocation. The failing GS phase had completed three memory
transactions, including a normalized read of `80000001`. Register bit-operation
coverage now includes that exact instruction and 1,728 Native comparisons.
Memory bit strings remain explicitly unsupported before effects.

That partial run also recorded zero instruction-cache hits: its first sixteen
slots filled before later loops, then cold execution continued. Keep the
observed zero-hit/full-cache behavior explicit; the cache is not a demonstrated
performance optimization. The failed VM was reset after serial and disk
evidence preservation, then booted through the existing one-time scope5 KD
entry. Reset is recovery, not successful retirement; no results are pooled
across the old and new boot identities.

The BTR-corrected `96d58adb` passed all 11 image-free helper and all 11 killable
phases. Both sessions still recorded zero cache hits: one-time entry code
occupied all sixteen immutable records before later loops. Correct that bounded
cache policy by admitting an instruction only after its PC is encountered
again within a 32-PC recent window. This mutable recent-PC history is only a
cache hint, never execution/ownership authority. Cached source bytes must still
be retained and freshly compared before the engine can fetch from them. A
cache candidate is an immutable record with a live family reference; no cache
entry is reused or evicted. A failed freshness check or full cache runs cold.
Keep each local run at 64 instructions and retain the exact service artifacts
independently of this optional cache. Validate observed cache hits and uncached
progress separately from throughput; no performance gain is presumed.

### Stage (c) focused functional endpoint

Tested implementation `b75d82ab7cc066763a659d3fe9f2b6811b98f664` joins
image-free capture, exact family/artifact references and returning KD, Native
and GS services. Ten affected unit drivers, 52,854 resident engine assertions,
all 11 reached helper phases and all 11 reached killable/nesting/downgrade
phases passed on the VM. The same source also passed the separate image-mode
11 plus 11 compatibility phases. Every final session drained; all 6,841 frozen
input files were unchanged, and the final guest was idle with no project module
loaded. The earlier compilation and BTR failures remain distinct evidence.

The reached helper session recorded 826 cache hits in 2,360 lookups; the
killable session recorded 426,594 hits in 428,764 lookups. Full-cache cold
progress also passed. These are functional observations, not timing results;
the downgrade fixture's polling duration changes its instruction total.
The report retains exact source, boot, mode, build warnings and remaining
instruction/context limits at
[`reached-family-stage-c-20261102`](../../bench/results/10.176.26.71/tests/reached-family-stage-c-20261102/README.md).
The MM factory has not been activated with reached mode, and no actual mmap1,
Nano or throughput run is claimed. The candidate remains isolated.

## Stage (d): actual MM reached execution

Continue on `codex/reached-path-translation` from
`1fec704bbeb19b3391066c49a5cb1e303528d2e9`. Activate the existing general
rwsem provider with `service_reached=1` and exercise unchanged mmap1 through
its actual mmap/munmap syscalls. No application-specific branch, MM body
rewrite or entry-specific Native helper is permitted. The kernel's existing
writer-site table identifies generic ABI2 capture entries; retain the exact
ELF audit without requiring those entries to have compiled images.
In reached mode, general provider preparation validates each site's operation,
reserved word and entry, then retains its root text without allocating an image
registry slot. Activation retains the existing binding/registration protocol.

Add an explicit reached execution-session contract alongside the existing
image contract. Bind the same frozen module, controller, source manifest,
kernel/boot identity and provider parameters. Require no translator or device
writer and no published image in reached mode. Source modules can grow only
as actual reached text is retained; final source retirement must still prove
modules/frames/writers zero. Do not relax the image contract to achieve this.

First run one diagnostic lifetime with two workers for each of the thread and
process models, keeping their results separate and unscored. Start the bounded
continuous kernel collector before activating the factory. Observe the real
syscall arguments and returns, the actual worker/MM/backing/provider identity,
distinct origin and executor tasks, completed root generations, exact family
and service ACK/resume ledgers, delegated downgrade/read-release events and
later fresh writer admission. Positive entry alone is not a returned body or
an origin-side syscall return. Cache counters are supplementary observations,
not proof of any individual request's completion.

If execution reaches an unsupported instruction or context interval, retain
its exact PC, bytes, source identity and committed prefix. Supplement that
general operation with its complete Native effects and a focused differential
check, then build and retry under a new immutable source identity. Do not skip
the instruction, weaken ownership checks or route a complete suffix to origin.
Keep unsupported operations explicit until implemented. A failed/undrained
attempt remains a failure; preserve logs before recovery and do not combine
its counts with later attempts. Kernel/VM changes and recovery are authorized
by the current user instructions; default build inputs and historical evidence
remain preserved.

The initial validation is bounded functional execution, not the complete
Nano/MM performance gate. After both application models return with exact
retirement, report the delegated critical sections, observed episode counts
and enter-to-return duration definition, plus every remaining unsupported
point. Performance comparisons require separately identified Native and KD
runs; no gain follows from a diagnostic count.

The first actual activation at `c7e10b24` reached
`ffffffff817f66da` in `find_vma_intersection` (`mm/mmap.c:886`) on the verified
scope5 kernel. Its complete bytes are `65 4c 8b 25 26 49 c1 02`: a GS-relative
64-bit load into R12. The general decoder already recognizes that operation;
the runtime rejected it because its read policy allowed only preempt-count
operands. E stopped and O remained live. No application completion or clean
retirement is claimed for that attempt.

Extend the returning instruction service to ordinary resident GS loads/tests,
retaining the same origin CPU/GS base, IRQ, Native ownership, source-frame and
artifact ACK checks. Only actual preempt-count operands receive count
normalization; an ordinary GS read creates no preempt owner. The reached
callee's normal epilogue at `ffffffff817f6708` contains
`65 48 2b 15 f8 48 c1 02`, a GS-source subtraction into RDX. Implement the
general register-destination GS SUB operation with exact source-width result
and arithmetic flags. This is supplementation of the encountered function's
bounded return neighborhood, not a whole-CFG admission step or a named helper
for its canary predicate. Keep faulting or unsupported forms explicit, preserve
the failed attempt, and validate both the instruction effects and returning
service before another actual MM activation.

The GS-corrected `0ac46e80` passed 500 decoder/Native-effect assertions,
64 production read-policy checks and the affected service/MM validators. Its
actual MM retry passed the first GS service and reached `f3 48 ab` at
`ffffffff826bbc0f` in `mt_find`: REP STOSQ emitted for local initialization.
The source root was still exec's `create_init_stack_vma`; no mmap1 worker
completion is claimed. Preserve this second undrained attempt separately.

Supplement general STOS byte/word/dword/qword execution on E, with or without
REP. Each cold step performs at most one source-width store. After a successful
element, advance RDI according to the saved DF and decrement RCX only for REP;
retain the same source PC until the count reaches zero. A zero REP count
performs no memory access. Preserve all source flags and unrelated registers.
If a later element cannot execute, retain the committed elements and current
RDI/RCX/PC without replay. The existing qualified, all-or-none element-store
contract remains required; arbitrary fault/fixup semantics are not invented.

The 64-step local cap and persistent scheduling window count these element
steps, preventing a large REP count from hiding an unbounded internal loop.
The existing `instructions` observation therefore counts resident execution
steps, including repeated string elements, rather than unique retired x86
instructions. This distinction must accompany later metrics. Validate Native
memory effects, count/address updates, zero count, both DF values, all widths
and bounded stop/resume before the next actual MM retry. Do not replace this
source instruction with a caller-specific service or an origin memset model.

The STOS-corrected `afe1ba21` passed 53,553 resident assertions. Its next MM
attempt advanced to generation 3 and stopped on prefix `2e` at
`ffffffff817fd1d7` in `change_protection`. The built ELF contains a CALL to
`__SCT__might_resched` there; it is not the authority for runtime patched bytes.
A read from the recovered scope5 boot with the same full/lazy policy contains
`2e 2e 2e 31 c0`, the return-zero static-call form defined by
`arch/x86/kernel/static_call.c`. This recovered-boot read is separate evidence
from the failing run's one-byte prefix, not a claimed pre-reset full capture.

Support repeated CS prefixes for the narrow ordinary NOP family and
register-register XOR, using the existing exact XOR width/result/flags lowering.
The observed form must clear EAX and set its actual arithmetic flags; treating
it as a NOP would lose effects. Decode and retain the entire current instruction,
including prefixes, under the normal fifteen-byte bound. Do not admit other
CS-prefixed operations through this change. Validate full source fetch, flags,
zero extension, untouched registers, invalid forms and both supported classes
against Native effects, then retry actual MM execution. Record future failed
instructions' complete live bytes before recovery where available.

The padded-instruction candidate `140ca7e5` passed 54,504 resident assertions,
then its MM attempt reached `f3 a4` at `ffffffff826f0568`, `__memcpy+8`.
This is the selected live fast-string path, after setting RCX from RDX. Two
roots in that same failed attempt stopped at this operation; neither is a
separate scored point or a returned mmap1 worker. Preserve both failures and
the full live-byte read before recovery.

Supplement general MOVS byte/word/dword/qword execution on E, with and without
REP. Each bounded step reads one qualified source element and writes one
destination element. Only after successful storage may RSI/RDI move according
to virtual DF and REP's RCX decrease. Zero count accesses neither address;
flags, RAX and unrelated registers stay unchanged. If reading or writing an
element fails, retain earlier elements and exact current RSI/RDI/RCX/PC so
resumption cannot replay the committed prefix. Source reads and destination
stores must retain the existing ordinary-RAM/access-width contracts. Do not
convert the operation into an origin memcpy call. Validate Native overlap
effects in both directions, all widths, zero count, bounded continuation and
read/store failures before the next actual MM retry. Scheduling and step
accounting follow the same element bounds as STOS.

The MOVS candidate `b8b915e9` passed 57,972 resident assertions and reached
`kvfree_call_rcu` at `ffffffff817ca6b7`: `65 39 15 02 71 c5 02`, a comparison
against the origin CPU's NUMA field. The public API is
`void kvfree_call_rcu(struct rcu_head *head, void *ptr)`, not an MM body.
Captured scope5 `mm/slab_common.c:1941-2015` and
`include/linux/rcupdate.h:1089-1132` distinguish non-NULL embedded heads from
NULL-head calls: the former permit atomic callers; the latter require a
sleepable context and can fall back to `synchronize_rcu()` followed by `kvfree()`.
Its CPU-local slab/IRQ internals belong in an origin Native API transaction.

Add a reusable immutable descriptor policy
`KD_SERVICE_CALL_ARG0_BALANCED_OR_ATOMIC`, appended after all existing context
values. Resolve it per transaction from the captured argument zero, before
PREPARED publication: NULL selects `BALANCED_ORIGIN`, non-NULL selects
`ATOMIC_ORIGIN`. Do not mutate the registered descriptor, change existing
fixed-context behavior, admit the policy to mapped descriptors, or relax the
Native spin/RCU/IRQ/stack/ACK checks. Registration requires a real first
argument. Native discovery must recognize the policy value while runtime
execution receives only a resolved context.

Register the unchanged public `kvfree_call_rcu` API with its two arguments,
void result and this policy. The exact source CALL and one Native return remain
on O; E resumes the same retained MM family afterwards. This is the same
general returning-API mechanism as the existing `call_rcu` services, not a
caller-specific helper or a restart of a previously executed API prefix. A new
candidate intercepts the API at its entry before any effects. Preserve the
failed interpreted-prefix attempt independently.

Focused validation must cover NULL/non-NULL selection, descriptor immutability,
arity, unchanged fixed contexts, mapped-descriptor refusal, retained spin/RCU
gates and Native context balance. Actual MM proof must join the public API's
request/enter/done/resume and artifact to the same E body. Ordinary source
strings continue through the backend; no origin memcpy/memset model is added.

The API-service candidate `a8325ab5` passed the selected descriptor, Native
context, discovery/emission and trace checks. Its actual MM retry reached
`_find_first_bit+0x25`, `ffffffff81cc7195`, bytes `f3 48 0f bc c9` (TZCNT
RCX to RCX). This general bitmap operation stays on E; it is not a Native API
service. Preserve the failed prefix and verify the earlier API transaction
separately from whole-workload completion.

Add general BSF/BSR and their F3 TZCNT/LZCNT forms for widths 16/32/64. Use
the actual Native instruction with the source arithmetic flags and full old
destination as inputs; import its full destination GPR and arithmetic flags.
Do not guess zero-input BSF/BSR behavior or erase the CPU's actual undefined
result through a generic width write. Native asm supplies the normal 32-bit
zero extension and 16-bit partial-register effects. Memory sources retain the
qualified source-width read contract and fail before register effects.
Validate zero/boundary inputs, nonzero old destinations, flags, widths, source
failure and exact reached alias bytes before another actual MM attempt.

The scan candidate `6b4a8983` passed 63,165 resident assertions. Actual MM
execution then reached read-only memory BT at `ffffffff817b7c44`,
`48 0f a3 02`, in `__next_zones_zonelist`. Preserve both stopped roots in
that one failed activation. The pure bitmap selection remains on E.

Implement read-only BT memory operands for widths 16/32/64. A register index is
signed at the source operand width: use its arithmetic word quotient to adjust
the base address and its low bits to select within the loaded word. An imm8
index masks within the encoded word without a word-address adjustment. Read
one qualified source-width word; execute a Native memory-form BT on the retained
private word to obtain flags. Do not assume undefined flag effects match a
register-form BT. No source GPR or source data is written, and failure precedes
packet effects. Memory BTS/BTR/BTC and LOCK forms remain explicit unsupported
operations in this slice. Validate signed offsets, immediate masking, flags,
one-read/no-write behavior and source failure against Native before retrying MM.

The memory-BT candidate `07189e3c` passed 64,432 resident assertions, then its
MM retry reached GS ADD of `this_cpu_off` at `ffffffff81828ca9` in private
`get_page_from_freelist`, immediately after source preemption was disabled.
This is CPU-local page-allocation machinery. Audit the enclosing public API;
do not register that private allocator body or restart its failed prefix.

Captured scope5 `include/linux/gfp.h`, `mm/page_alloc.c`, `mm/mempolicy.c` and
`include/linux/sched/mm.h` establish the exact general page/folio allocation
boundaries. Register `__alloc_pages_noprof`/`__folio_alloc_noprof` (four args),
`alloc_pages_noprof`/`folio_alloc_noprof`/`get_free_pages_noprof` (two), and
`get_zeroed_page_noprof` (one), each with its Native word result and unchanged
arguments. Execute the selected exact public API on O, preserving source GFP,
NUMA policy, PF_MEMALLOC/NOIO/NOFS/PIN scope, result/refcount and failure rules.
No mapping to a different allocator, caller flag or MM body adapter is added.

Use the existing atomic-compatible context (2) with the explicit clarification
in `rwsem_delegated_protocol.md`: it permits inherited atomic custody, rather
than forcing every invocation to be non-sleeping. The actual Native API retains
its own argument/task-dependent blocking preconditions. O's sole runtime pin
is removed; if no Native pins remain, O can schedule normally and E can unbind.
Keep IRQ/preempt/RCU/owner/stack/ACK checks unchanged. A bare GFP-bit selector
on E would incorrectly ignore Native task scopes and is not introduced.
Validate the public roster/prototypes and existing context gates, then require
actual API return and continued E execution in the next MM attempt. IRQ-off
entry and arbitrary allocator internals outside these API intervals remain
unvalidated.

The next actual attempt (`9b0da70c`) reached `mod_node_page_state+0x33`,
`ffffffff817b9883`, bytes `65 0f b6 07`. Scope5 `mm/vmstat.c:552-685` and
`include/linux/vmstat.h:281-287` identify the general public node/zone accounting
family. Its byte-sized CPU-local differential update uses GS MOVZX/MOVSX and
CMPXCHG, followed by atomic overflow accounting; the alternative Native body
balances its own local IRQ save/restore. Preserve the entire unchanged public
accounting transaction on O instead of splitting a CPU-local retry loop across
tasks. This is a returning API interval, not an MM-body continuation.

Register the six ordinary public APIs `mod_{node,zone}_page_state` (three
arguments) and `inc_{node,zone}_page_state`/`dec_{node,zone}_page_state` (two),
all void and atomic-compatible. Preserve the original object, enum and long
delta words exactly; in particular, the public node API's long delta is not
replaced by its private helper's int prototype. Existing inherited-pin, IRQ,
origin migration, return and exact ACK checks remain unchanged. No private
`mod_node_state`/`mod_zone_state` or caller-specific function is registered.
After focused roster/context checks, build and retry actual MM under a new
immutable candidate. The stopped attempt is undrained evidence, not success.

Candidate `918cd561` then reached `ffffffff818a863b`, bytes
`65 48 01 5c c2 18`, a GS ADD in private `mod_memcg_lruvec_state`. Captured
scope5 `mm/memcontrol.c:693-835`, `include/linux/memcontrol.h:931-961` and
`include/linux/vmstat.h:519-523` define the public accounting boundaries.
`mod_lruvec_state` updates node, cgroup and lruvec counters; its private helper
uses `get_cpu`/`put_cpu`, per-CPU additions and rstat accounting. Preserve this
complete public transaction on O, then resume E. Do not register its private
helper or repeat the already executed prefix in the stopped activation.

Add four general three-argument void API descriptors: `mod_memcg_state`,
`mod_lruvec_state`, `lruvec_stat_mod_folio` and `mod_lruvec_kmem_state`.
Their public delta is int, passed unchanged as the source argument word and
consumed by Native code. All use the existing atomic-compatible context;
Native API bodies retain their own balanced preemption/RCU intervals and
untracked-object branches. Inherited source RCU/pins, object lifetime and
exact return/ACK records remain required. No MM integration change or private
body service is introduced. Require focused roster/context checks and a new
actual-MM attempt, preserving the preceding failure separately.

The `eb21e334` MM attempt passed that accounting point and reached generation
5, entry `ffffffff817b6f68`. It stopped at `__get_unmapped_area+0x6b`,
`ffffffff817f716b`: live bytes `2e 2e 2e ff d0` are a CS-padded indirect
CALL RAX. The ELF's corresponding branch through an indirect-call thunk is
patched at runtime. Keep address selection delegated; this pure control-flow
encoding is not a reason to service `__get_unmapped_area` on O.

Extend only CS-padded FF /2 and /4 register near CALL/JMP, using the existing
64-bit target capture, exact full-length source return word, one stack push
for CALL, unchanged flags and ordinary reached-edge dispatch. Prefix order
must retain its actual REX meaning. Memory targets, far transfers, PUSH/INC/DEC,
operand-size override, LOCK and REP in this CS branch slice remain refused
before effects. Source truncation must stay a source failure. Validate the
patched byte sequence, extended GPR targets, CALL/RET and JMP behavior, stack
failure with no committed effect, source-length/flags and refused forms; build
the candidate and retry actual mmap1 under a new frozen identity.

Candidate `4fd4d4d5` next reached `vma_link_file+0x4e`, `ffffffff81816e6e`,
bytes `48 0f ba 6d e0 03`: unlocked BTSQ immediate 3 on a retained source
stack flag word. The next source instruction sets bit 5 in that same word.
Keep the VMA linking algorithm on E and implement the missing general memory
bit RMW. Do not service an MM body or split the RMW into source load/store.

Append distinct unlocked and LOCK BTS/BTR/BTC operations to the existing exact
Native RMW callback. Reuse BT's signed register-index containing-word address
and imm8 within-word mask; pass only the masked bit to one actual Native
memory-form instruction at the qualified source word. Preserve source width
16/32/64, actual LOCK presence and captured arithmetic flags. No source GPR is
written. Read-only BT retains its separate one-read path and LOCK BT remains
unsupported. Existing callback RAM/page/owner checks and extable handling stay
required; no callback, address refusal or failed operation commits packet,
flags or budget. No retry/replay loop is added.

Validate against Native memory-form BTS/BTR/BTC for immediate/register indices,
signed containing-word offsets, all widths, existing/set bits and both LOCK
policies. Check exact one-RMW/no separate read or write, source alias/failure,
unchanged unrelated words/registers and explicit unsupported forms. Build and
retry actual MM only after these directly affected checks pass; preserve the
preceding failed activation separately.
