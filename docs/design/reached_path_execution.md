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
`tests/kernel/jit_continuation/fixture/helper_memory.inc:80`. Seven earlier
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


## Correctness module directory naming

Use `fixture/` for maintained correctness module source directories and their
runner/build references. Apply this as a mechanical naming change across the
existing kernel checks; preserve module names, public interfaces, module source
contents and lock behavior. Historical run records retain their captured paths
and hashes. New frozen candidates must use the renamed tree consistently.
Check current references statically, then build the directly affected resident
and MM modules and run the focused VM checks.

Shared benchmark body headers use `body` in their filenames. Update their
include paths and private include markers together. Saved source inventories
and prior baseline lookup paths continue to identify the original artifacts.

## Reached relative branch completion

The `c2ee2298` attempt passed the stack bit updates and reached generation 11
at mmap entry `ffffffff817b6f68`. It stopped on CS-prefixed relative CALL in
`__rb_insert_augmented`, `ffffffff826cd5cb`; another root reached the same
form at `ffffffff826cd699`. Decode the complete reached E8 instruction and
its actual signed displacement. Keep rotation callbacks on E through the
ordinary call/return path; do not add a Native MM-body service.

Admit CS-prefixed near E8/E9/EB CALL/JMP with the existing 15-byte limit,
full-prefix next IP and signed displacement. CALL writes that exact next IP
once; JMP writes no stack word. Preserve flags, source failures and failed
stack-write behavior. Operand-size override, LOCK and REP for this slice stay
unsupported before effects. Validate forward/backward targets, repeated CS,
prefix order, complete CALL/RET, truncation and failure before the next run.

The separate resident log cursor reported an overrun in that attempt. Retain
it as an observation failure as well as retaining the execution stop. The next
frozen diagnostic launcher drains its cursor every 10 ms rather than every
second; it still fails on any lost records. No execution or retirement check
is relaxed, and prior logs are never relabeled as a complete run.

## Page release and locked logical updates

On `e37977dd`, reached execution advanced to munmap entry `ffffffff8181c73b`,
generation87. A CPU-local page-release path stopped inside private
`__free_frozen_pages`; a separate root reached a locked byte AND in
`copy_page_range`. Preserve both failed roots and the log-cursor overrun.

Add exact Native LOCK AND/OR/XOR at widths8/16/32/64 through the existing
one-instruction RMW callback, retaining register and sign-extended immediate
inputs, arithmetic flags, unchanged GPRs and failure-before-commit ordering.
Keep unlocked arithmetic behavior unchanged and validate against Native.

General allocator release APIs run their original Native bodies on O and
return to the same E continuation: `__free_pages`, `free_pages`,
`free_pages_nolock`, `free_pages_exact`, `free_frozen_pages`, and
`free_frozen_pages_nolock` are all two-argument void operations with the
existing atomic-compatible context. Scope5 `include/linux/gfp.h`,
`mm/internal.h:898-916`, and `mm/page_alloc.c:2972-3029,5375-5407,5489-5499`
define these general allocator boundaries. Preserve page/order/address/size,
reference counting, FPI policy and balanced CPU/IRQ intervals. Do not register
the private static three-argument helper or any MM algorithm body.

Shorter polling did not prevent the observer overrun. For the next functional
run, use a separate one-time scope5 boot entry with `log_buf_len=16M`, leaving
the ordinary boot entry and kernel unchanged. Record its exact command line
and boot identity; do not combine its observations with prior runs or timing.
Missing records still fail the diagnostic. The selected thread/process checks
remain separate and unscored, with exact body return and final drain required.

The first log16 check at `73b8da74` passed its four unit drivers, then the
exact kernel identity check stopped before the resident build because the
old bundle correctly requires its original command line. Keep that failed
attempt. Add explicit diagnostic profile `kdscope5-log16-kd`, sharing the
unchanged scope5 source/build but using its own canonical bundle
`linux70-kdscope5-log16-kd-20261103`. Require exactly `log_buf_len=16M` for
this profile. Preserve the original bundle and all existing profile checks.
The new bundle retains identical source/build/installed/configuration records;
only its explicit variant and exact observed runtime policy change. Verify
both identities and retain the derivation before running any module.

## Bounded Native API discovery pages

Candidate `9dc0fbf3` passed four unit drivers and67,608 resident checks, then
its actual provider load returned ENOSPC before activation. The general API
roster exceeded the single-page text discovery limit in
`kd_service_call_configuration_size`, not the128-slot registry or guest disk.
Retain this failed load; neither application model started.

Keep the128 immutable registration slots and exact cookies. Add eight
read-only discovery pages,16 slots per page, plus an exact generation/count
state. Registration and actual deactivation advance the generation under the
existing configuration mutex; inactive slots are never reused. Each bounded
page formats complete rows, including the existing operation context. The
reader accepts a snapshot only when its before/after states match and every
cookie belongs to its declared page with no duplicates. A changed state or
missing page fails; no partial registry is accepted. The legacy single-table
attribute keeps its complete-snapshot behavior and reports overflow rather
than truncating a large roster. Runtime lookup, source references, owner
records, freezing and request retirement are unchanged.

Validate page boundaries, empty pages, duplicate/misplaced cookies, state
changes, legacy overflow and registration/cancellation before another actual
thread/process attempt. Discovery allocations remain outside lock execution.

On `14b00a56`, all seven focused drivers and67,608 resident checks passed,
and the provider loaded successfully. Preparation then found the common
benchmark parameter snapshot still reading the legacy full-table attribute;
it correctly returned EOVERFLOW. Update that known table read to use the same
validated paged reader. Preserve failures from all other attributes and retain
the complete table in the snapshot. No application body was activated by this
attempt. Add a focused old/new provider snapshot check before retrying.


## Returning CPU notification

The `00af410a` run activated the provider and reached munmap generation87,
then stopped at `kick_process+0x18`, `ffffffff8148f9f8`, a GS CPU-number
comparison. Exact scope5 `include/linux/sched.h:2000` and
`kernel/sched/core.c:3404-3424` define the general one-task-pointer void API.
Its Native body disables preemption, compares the caller CPU to the target
task CPU, conditionally sends a reschedule notification, and balances its
preemption state. Execute this declared API once on O, preserving the source
task reference, CPU identity and notification semantics; then resume E.
Use the existing atomic-compatible context and exact CALL/ACK records.
No MM body or private scheduler helper is registered. Preserve the failed
attempt and validate the descriptor/context plus actual thread/process runs.


## Reached caller context for the next IRQ interval

Candidate `06952039` passed its focused checks, then reached
`_raw_spin_lock_irqsave` during `exit_mmap`, entry `ffffffff817f9283`.
Its runtime-patched PUSHFQ at `ffffffff8270235f` is unsupported; no IRQ
transition is claimed. The independent log cursor also overran. Preserve
both failures and the original IRQ compatibility limit. Do not service the
whole MM teardown or turn an IRQ operation into a no-op.

Before choosing the required general API/context work, retain the last eight
actually completed source CALL edges in the preallocated reached state and
print them only on an unsupported event. Reset only their indices at root
entry, and record an edge only after the source CALL word commits. This is
passive reached-path context; it does not rewrite returns, track Native call
depth, analyze an upfront graph, or authorize ownership. Failed calls leave
the history unchanged. Use this to identify the enclosing API/interval and
then implement its exact context requirements.


## Returning folio reference release

The `dc717333` diagnostic identified the actually reached chain:
`free_pages_and_swap_cache` → `folios_put_refs` → private
`__page_cache_release.part.0` → `folio_lruvec_lock_irqsave` →
`_raw_spin_lock_irqsave`. This is a balanced reference-release interval, not
a reason to move the surrounding MM teardown to O. Exact scope5
`mm/swap.c:87-115,937-1045`, `mm/swap_state.c:407-427`,
`include/linux/mm.h:1642,1840-1876` and `include/linux/swap.h:436` define
the general interfaces and the matching IRQ restoration.

Register `__folio_put` (one pointer), `folios_put_refs` (batch/refs pointers),
`release_pages` (array/count) and `free_pages_and_swap_cache` (encoded array/
count), each void with the existing atomic-compatible context. The first
`release_pages` argument is a one-word transparent union of pointer types in
this x86-64 ABI; preserve its source word without conversion. Keep encoded
page bits, per-folio reference counts, NULL-ref semantics, batch compaction/
empty return, swap-cache behavior and internal LRU/IRQ ordering Native on O.
Retain caller-owned arrays and frames through the exact return ACK. E resumes
the MM algorithm afterward. No private LRU-lock helper or MM body is added.
General IRQ-held delegated bodies remain unsupported outside such balanced
returning API intervals; this change does not claim that broader support.


## Executor placement and complete shutdown observations

Continue on `codex/reached-path-translation` from
`02990b62e55f7c2c9b5d6f0d9d6c5b1dd486151e`. Its actual thread application
printed measurement output, but shutdown timed out and both log cursors
lost records. A later status read also timed out. No unsupported reached
instruction was reported in the retained subset; absence from that subset
is not proof that the shutdown protocol completed.

Add a general, load-time-only `service_cpus` list to the sleeping-lock
executor pool. Empty preserves the existing online-CPU policy. A selected
pool is parsed before service initialization, intersects online CPUs and
must contain at least two online CPUs. Every initial placement, repin and
post-root affinity restoration uses this same pool, with the existing
captured-origin exclusion and context recheck retained. It changes execution
placement only: admission, origin signals, ownership, nested nodes,
downgrade and exact return/retirement remain unchanged. Requests never move
their body to O because of this setting. A pool temporarily occupied by
origins waits through the existing scheduling path; oversubscription is
outside this focused diagnostic.

For the next two-worker thread/process check, choose `service_cpus=0-61`,
leaving CPUs62/63 for the ordinary collectors. Record and verify this
parameter in the immutable execution receipt. Expose the selection only
through the diagnostic controller, with the ordinary default unchanged.
Raise the per-log diagnostic allowance explicitly to1024MiB for this run;
retain the existing256MiB default for other callers. Admit disk headroom for
both models' lifecycle and application logs, plus the separate monitor.
Every cursor loss, byte limit or incomplete drain remains a failed check.
Do not drop ownership records, skip probes or change the upstream workload.

Build the provider/resident fixture and run directly affected collector,
MM-proof and source-identity checks in the VM. Then run one ordinary upstream
lifetime per model. Inspect complete shutdown evidence before changing lock
semantics. This is observation work, not a performance claim or a diagnosed
fix for the outstanding shutdown failure.


## Reached task-register instruction and bounded log writes

Continue on `codex/reached-path-translation` with the implementation of
`6f99fa27bb86a844356f59a740ef9ea25ea93945`. That candidate passed its
component checks but the actual thread lifetime and complete log collection
failed. A later ordinary page-fault path reached `0f 01 ee` at
`ffffffff8140cb67`. Exact scope5 source has `__pkru_allows_pkey(u16, bool)`
at `arch/x86/include/asm/pgtable.h:1604-1614`, calling the task-register read
in `asm/pkru.h`/`asm/special_insns.h`. This is an inlined architecture helper,
with possible separate compiler instances. Support the actual instruction
rather than relying on one helper address or registering a private MM body.
The source inventory is retained with the MM attempt.

Extend the existing retained instruction channel with internal operation6,
`KD_ORIGIN_MEMORY_TASK_READ`, for exactly the three reached bytes `0f 01 ee`.
Keep the assembly-consumed prefix and two-word public wrapper ABI unchanged;
append one scalar output field for the second result. Recognize no prefix,
write instruction or adjacent source byte. Require width32, source ECX=0
and the running CPU feature before publishing the service. Invalid inputs
remain an explicit unsupported point before effects; do not pretend to
reproduce a Native instruction exception or its fixups.

O executes that one instruction on its real task stack, under the existing
source-task/CPU, IRQ and preempt-count checks. Retain the packet, exact source
bytes, family artifact, root generation and nested ownership through its ACK.
E then commits zero-extended EAX and EDX, unchanged arithmetic flags and
source SP, and the exact next IP. The ordinary MM branch and remaining body
continue on E. No lock is reacquired, released, downgraded or canceled by this
service; the held writer/read share and all nested records remain live.
Killable acquisition still arbitrates before body entry and never reports a
late cancellation after committed effects. Direct writes to this register,
invalid ECX and unsupported instruction/context combinations stay explicit.

The diagnostic also exposed per-record filesystem writes and a5ms pause
after cursor loss. Use bounded64KiB file buffering and immediately resume
reading after a lost cursor. Flush/close before reporting collection drain;
retain every loss as a failed capture. No probe or record is removed. The
auxiliary monitor can use the same bounded buffering and flush on a reported
execution failure. These changes target collection cost; they are not proof
that the earlier application timeout is fixed.

VM validation: directly exercise the production decoder and Native scalar
outputs/flags, malformed/truncated bytes and invalid descriptor fields; run
the affected collector/MM-proof/source checks and build the provider/resident
fixture. Then run one actual lifetime for each application model after a
fresh explicit diagnostic boot and sufficient log headroom. Retain all
failed, incomplete and unrun outcomes separately.


For one further focused attempt, the temporary log-routing decision is not
needed if the ordinary paths retain the restored headroom: select512MiB per
child log and a1GiB auxiliary limit, keep all cursor-loss gates, and check root
headroom in the already-running monitor. Below1GiB marks the diagnostic failed
and leaves exact process/source state intact for ordinary recovery; it is not
a successful retirement. Retain console records and recover promptly after
an undrained failure. This bounded normal-path attempt makes no routing change
while that separate request is pending. Both successful models still require
normal upstream exit, complete traces, exact ownership and source retirement.
The task-register read remains a synchronous service whenever its source
query is reached; no cached task-state authority or speedup is claimed.


## Reached signed GS load and active request observations

The `b2e96afe229ac43c6ee05f186517615a48103385` application diagnostic still
failed its lifetime and complete-trace gates. Later ordinary console output
reached `get_vma_policy+0x82`, `ffffffff81870a52`, on a background page-fault
path. The runtime reported its first GS byte; the matching scope5 ELF has
`65 48 63 05 66 0d bb 02`, loading the source CPU's signed32 NUMA-node value
into a64-bit register. The reached decoder must validate all actual bytes
before service; the static ELF is identification evidence, not a live-byte
receipt. No private policy helper or MM algorithm body is moved to O.

Add internal operation7, `KD_ORIGIN_MEMORY_LOAD_SIGNED`, for GS opcode63 with
REX.W and the existing supported64-bit memory addressing. Width64 denotes
the destination; the source access is four bytes. O executes one actual
`movslq` with unchanged arithmetic flags. E commits the sign-extended result
only after the existing exact ACK, preserving source SP and the next IP.
Reject word/address-size forms and register SP destinations. Reached-only
publication remains explicit. Classify preempt-count overlap using the
four-byte source width; retain source-task/CPU, IRQ and ownership checks.
This read is normally encountered on the default policy branch, so every
reached occurrence currently costs a synchronous service. No cached CPU-value
proof or performance gain is claimed. Public lock behavior, killable
arbitration, nested records and downgrade/read-tail transitions are unchanged.

Add read-only `service_progress` metadata for at most eight active roots.
The existing dispatch guard protects root/worker lifetimes while formatting;
report total/shown counts explicitly. Read only retained scalar identity,
generation, phase, virtual PC and service-state fields. Never dereference an
unlocked lock object, copy a packet, change request state or add a new global
lock. Concurrent execution fields are diagnostic observations, not an atomic
execution snapshot or ownership authority. The normal execution path does
not update new counters or publish new notifications for this view.

The prestarted monitor may read this view at a bounded rate and retain it
before reporting a failed application. This avoids starting a new inspection
process after failure. It must not turn a timeout into a drain, or use these
observations to grant, cancel, unlock or retire anything. Validate signed
values, addressing, destination and flag behavior through the existing
production decoder/Native fixture, then build and run focused MM checks.


## Distinguish active execution from application termination waits

The `cb5ee7a10591fd2e505a9b029a3bad9e7132b3f3` progress view worked and
recorded continued returned MM roots beyond the nominal sampling interval.
The unchanged upstream printed its complete average, then failed to exit.
Its pinned `main.c` calls asynchronous pthread cancellation followed by joins;
this is a separate Native task-progress obligation from acquisition returning
successfully. Preserve those source hashes and the failed trace. Do not infer
the cause from the average or from one sampled program counter.

Before changing admission/reader ordering or signal handling, capture the
already-owned upstream parent's and workers' ordinary task state on a timeout.
Do this in the existing benchmark controller, before its collectors close;
do not launch another inspection process. Limit the observation to eight
TIDs, report total/shown counts, and retain stat/status/wchan plus a kernel
stack only for an observed sleeping task. File disappearance or an unavailable
stack is diagnostic metadata, not successful drain. The child remains
unreaped/alive exactly as before; no signal, cancellation, unlock or retirement
is initiated by the observation. Preserve the original timeout and every
collection error. Kernel stack snapshots can race with scheduling and are
only evidence for diagnosis, never ownership or readiness authority.

A parent waiting in a reader path, signal setup, a join or another operation
requires different fixes. The new observation is intended to identify that
actual wait. Native cancellation, downgrade, read concurrency, queued writer
ordering and atomic-compatible read unlock remain unchanged in this step.


## Reuse collector input storage and select diagnostic model order

The current collector requests a new1MiB Python bytes object for every kmsg
record. Keep the existing maximum read size and record/error coverage, but
allocate one mutable1MiB input buffer per collector and use `os.readv` into
that same storage. Convert only the returned bytes to a record before the
next read. No caller retains a view of mutable input. Buffer both output
streams in bounded64KiB blocks and close them before reporting drain. Every
cursor loss, file limit, fault and incomplete join remains a failed capture.
This removes repeated large input allocation by construction; its effect on
the observed collection losses and application timing is not yet measured.

The four focused reader fixtures must still retain bytes after a lost cursor,
reject a storage limit, detect split fault text and drain a real nonblocking
pipe. Update their mocked syscall boundary to the real readv contract. Check
readv support on the VM's actual kmsg descriptor before activating a provider.
Keep the normal benchmark workload, its binaries and its output contract
unchanged.

Expose `--model-order` only on the diagnostic controller, preserving the
ordinary thread-first default. The next distinct diagnostic selects processes
first, then threads. This gives the previously unrun process model coverage
without treating an undrained thread run as reusable live state. Each model
still needs its own ordinary application lifetime, complete ledger, exact
retirement and idle boundary. Kernel API code has no application/model branch;
this option only selects the order of independent benchmark checks.


## Bounded collector text scans

The `283b70c24bd664e5c2614723b80d63ffd357ff04` process diagnostic exited
normally, but complete trace capture failed. An idle-VM profile of the exact
retained8MiB prefix measured about2.01seconds for per-record regex scanning
and0.12seconds for batching plus a keyword prefilter. Fix that measured
collector cost before changing queue ordering on an unproved hypothesis.

Keep every raw record and every cursor-loss/error receipt. Decode each record
as before, accumulate at most64KiB plus the last record, then scan the joined
text with the existing256-character boundary tail. Flush the pending scan
on would-block, cursor loss and every exit, including a deadline or write
error. The match expressions are unanchored bounded literals shorter than
the retained tail. Batching must not change fault detection or acceptance.

Provide an optional exact fault-check callback. The shared benchmark helper
first computes lowercase once for ASCII text and checks a superset of the
existing regex alternatives' keywords. If none is present, the regex cannot
match. Otherwise use the unchanged authoritative expression. Non-ASCII text
always uses that expression, preserving Unicode case and word-boundary rules.
Other patterns keep their normal search method. Validate all alternatives,
case variants, Unicode, split records and batch boundaries on the VM, retaining
the real pipe and loss/storage tests. The next application attempt still
requires both models, complete per-request proof and normal retirement.
No kernel/API behavior, trace emission or public lock semantics change here.


## Share one model collector with an exact application window

The `06caaf073543e3923f143014e6a15a4843ec28be` diagnostic captured249,270,496
auxiliary bytes with zero lost ranges after the text-scan change. Its child
controller still failed the application capture. That controller runs two
reader threads in one interpreter on CPU63: a whole-model lifecycle reader
and a second reader for the application interval. They duplicate every active
record and contend for the same interpreter. Treat that as the next measured
collection problem; it is not evidence of an MM lock or signal defect.

Use the already-running lifecycle collector for both obligations. A serialized
checkpoint request is acknowledged only by its owning reader thread after
scanning pending text and flushing raw output. The acknowledgement binds an
exact raw-file offset, record count, errors and fault state. Keep raw offsets
separate from the byte budget, which also includes error receipts. Checkpoint
timeouts or a stopped reader fail; they never imply drain.

Take checkpoints immediately before application launch and after its original
verification interval. Copy exactly that immutable prefix interval to the
application log, retaining source path and both offsets. Bound the copy by the
existing application budget. Preserve all raw bytes and losses. The lifecycle
reader remains active and owns its descriptor; run_point must not finish or
close a borrowed collector. A completed window is not a drained lifecycle
reader. The model still needs the existing final finish, complete full-model
trace, exact source/frame retirement and normal unload; a later loss invalidates
the model even when its earlier window was complete.

The ordinary standalone runner keeps its own collector. No kernel logging,
lock state, API, application, signal ordering or acceptance check is removed.
Validate exact window boundaries, incomplete/lost capture rejection, active
reader retention and the real run_point join on the VM before a fresh attempt.

Checkpoint acknowledgement additionally requires a nonblocking would-block
observation, so all records already available before a completed application's
final boundary have been consumed. A busy stream that prevents that boundary
within the existing two-second limit fails explicitly; acknowledging only a
previously written prefix could omit the application's final returned events.


## Flush observer records before consuming the lifecycle file

The `c373d273797405833aff42b297d4a45d7f3a0ccb` application passed the shared
window and reached observer STOP and per-root/service validation. Its next
gate timed out looking for `kd_mm_pair: event=stop` in the live lifecycle
file. That summary is shorter than the collector's64KiB output buffer; the
reader scans at would-block but does not implicitly flush without a checkpoint.
The polling reader can therefore see an older file prefix even after the
observer emitted the summary. Require the existing reader checkpoint after
STOP and before any lifecycle summary parsing. Keep the same summary checks,
timeouts, per-root proof and final full-model drain. This is a general buffered
observation ordering fix, not a change to MM execution or lock semantics.
Retain the failed attempt; it does not prove final source/provider retirement.


## Drain after application exit and before CPU-intensive proof parsing

The `583a875aef9e8977bfdbc99485df882b1123c9d7` summary checkpoint completed,
but the full-model reader later lost records while proof parsing occupied
the same interpreter. The workload had already returned and its roots had
completed; background MM requests continued producing traces while the
controller parsed hundreds of megabytes. The independent reader retained
385,764,607 bytes without loss. Do not weaken the full-model loss gate.

Move the existing normal factory deactivation and exact bindings/frames drain
to immediately after successful application exit, stable observer STOP and
verification of the still-active execution session. Then parse the retained
application and lifecycle records. Keep the provider loaded and source open
through all proof checks and the later explicit source retirement. Record
DRAINING then VERIFYING states. The actual mmap1 lifetime runs entirely with
the factory active; no application interval is moved to Native execution.
Existing binding/ownership records must drain normally, with the same timeout
and zero-count requirements, before CPU-intensive proof begins. A failed
drain remains a failed run with live state retained.

No kernel protocol, application, trace event or acceptance requirement changes.
This reorders existing post-application lifecycle operations. Native task/MM
identity, every captured service transaction, read-tail execution and later
writer observation are still checked. Final retirement and ordinary unload
remain mandatory after proof.


## Retire after the observing processes release their own MM bindings

The `bfdc35e29d79d3db12dcfb071f2d1ad3438cc71e` application and its complete
trace succeeded, but the controller timed out with two residency bindings
and zero execution frames. A fresh ordinary observation after the controller
and monitor exited found zero bindings, no active requests and the same
completed counters. This is an observing-process lifetime boundary, not a
reason to detach live MM objects. `kernel_integration/mmap_lock/overlay/kernel/
locking/kd_mmap/provider.c` unregisters only future binding; its existing
objects retain the exact provider until ordinary unbind. The source binding
counter includes those object leases. Preserve that contract.

Split observation/proof and final retirement into distinct process lifetimes.
The application runs with delegation active through normal exit. STOP closes
observation; deactivation closes future binding. Both observing processes then
exit, releasing their ordinary address-space bindings. A fresh process, started
only while the factory is inactive, verifies the same boot, committed inputs,
provider bytes/note, complete captures, exact per-root/service and syscall
proofs, and zero bindings/frames/writers. It can then issue the existing source
retirement and ordinary module unload. No live binding is forcibly detached,
no application work changes executor, and no original failure is rewritten.

For the already-retained thirty-second attempt, allow a separately recorded
continuation of validation only for its exact post-application binding-drain
timeout, with normal application exit, complete error-free application and
lifecycle logs, stable balanced STOP, same boot/module, inactive factory and
zero current residency/frame counts. Use the unchanged validators from that
immutable candidate. Preserve the initial failed verdict; report the later
proof and normal retirement as a separate artifact. Do not rerun or score
the application while validating saved records. A thread-model run remains
a distinct application lifetime with independent evidence.
