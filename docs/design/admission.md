# Translation admission and publication

Admission decides which machine code KD may translate and execute. This guide
explains the current checks and their limits. Read the [design overview](../DESIGN.md)
first; [tests](../../tests/README.md) records which source versions were checked.
The [terminology guide](../TERMINOLOGY.md) defines ABI (application binary
interface), JIT (just-in-time compilation) and the lock/lifetime terms used here.

## 7. Translation And Publication

Rwlock writer entries use ABI3 on the spin backend. Native writer admission and
reader drain occur before the prepared JIT body; payload pointer traversal and
writer-byte release still undergo the checks below. This boundary resolves the
historical ABI1 RCUHT alias refusal without relaxing memory/context screening or
closing the [dynamic-address gap](#721-dynamic-address-gap). Admission cancellation
and native retry belong to [the rwlock ownership protocol](rwlock_implementation.md).

### 7.1 Possible JIT Episode

A **JIT episode** is the code that one invocation could execute before finishing
or transferring to native code. `context_policy.jit_phase_blocks()` selects its
reachable decoded blocks, starting from the entry and learned targets.

When an ordinary direct CALL targets an untranslated function, the selected graph
keeps the CALL and exit stub but removes the edge returning from native code to
JIT. The original waiter runs that function and the rest of the invocation natively.
Recognized lock controls, allowed hostcalls, decoded callees and indirect calls
keep the successors that their handling requires.

A block can still belong to the episode if another JIT path reaches it. Analyze
that block using the JIT paths that reach it; do not import facts from the removed
native-return edge. Every recompile rechecks the scope, and admission,
lock-boundary analysis, constant propagation, code emission and entry dispatch
must all use that same scope. Missing reachable code is a refusal, never an empty
block assumed safe.

If a branch points into another decoder window whose bytes are already cached,
the translator seeds that window and recomputes the graph. It splits blocks at
new decoder roots, even when a root lies inside a previously decoded block. Those
roots do not become independent admission entries. Text reads and decoder reseeding
share the 32-expansion limit; code that still cannot be decoded is refused.

#### Source branches with proven constant inputs

For ABI1 spin bodies containing `UD2`, the instruction that deliberately raises
an invalid-instruction exception, `constant_paths.py` can first prove that a
branch cannot reach it. The taskname source passes the constant size 64
through `strscpy_pad()` to `strscpy()`. The latter's warning for a size greater
than `INT_MAX`, the largest signed 32-bit integer, is therefore unreachable if
that fact survives every source path to the comparison. The original helper
call and copy operation remain unchanged; `UD2` itself remains refused. This
proof remains available for ordinary helper translation. The current taskname
path instead uses the separately checked original-helper service below and
does not depend on this branch transformation.

The proof begins with unknown inputs at the registered root. It follows exact
register and flag constants through reviewed instructions and direct calls,
never infers a value from memory, and retains a constant at a merge only when
all incoming paths agree. Each call's continuation forgets all register facts;
returns conservatively reach every recorded call continuation. Indirect control
or previously learned indirect targets, overlapping instruction byte ranges,
and exhausted analysis limits prevent specialization. Uncertain instruction
effects discard the known values instead of preserving stale facts. A proved
conditional branch becomes a jump to its sole possible successor before the
ordinary instruction and context checks. All remaining code still passes those
checks and the same selected graph is emitted. The diagnostic
`CONSTANT_PATH_SPECIALIZATION` records the changed branch addresses.

These source proofs do not establish support for the complete procfs task-name
operation. The current extracted taskname caller uses the checked-helper service;
its read-only functional check completed delegated bodies. Its 20% mutation case
was correct but failed measured delegation, and the full performance comparison
remains pending. See the
[validation record](../../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md).

### 7.2 Context And Memory Admission

Some code depends on the CPU or task that runs it. KD therefore checks context
operations across every block it will emit:

- Explicit GS reads, writes and read-modify-write operations may use the pinned
  origin CPU's GS base. A GS displacement is an offset, not a linear kernel address.
- Supported `current_task` MOV loads may use the original task supplied to JIT.
- FS/base operations, implicit GS string/XLAT operations without lowering, known
  linear per-CPU/current addresses, scheduling/preemption/IRQ/BH/RCU references
  and calls to the wrong lock backend are refused.

Pinning the waiter prevents task replacement. It does not prevent IRQ/NMI activity
or arbitrary remote accesses, and it does not reproduce the waiter's complete
per-CPU context on the combiner.

These byte and operand checks run before value propagation or a guarded retry.
A rewritten RET can leave a connected block with no propagated input, but that
block still has emitted code and a permitted target. It must still pass the segment,
IRQ, context-symbol and backend checks. The scan covers only the selected episode;
it does not add back an ordinary CALL miss's native-only remainder.

The value analysis follows explicit operands and the lifted intermediate
representation (IR), including implicit memory accesses, CALL arguments, RET
results and writes of return addresses. It follows the selected control-flow
graph (CFG), keeps relevant alternatives when paths merge, and checks memory values,
masks, aliases and writes conservatively. It neither reads runtime memory nor
assumes memory addressed through the waiter's RBP/RSP is private. If analysis
runs out of the resources needed to resolve an address, it refuses the entry.

Eligible single-root nested entries can retry address-precision failures with
entry disjointness predicates. Every premise is enforced before generated body
execution; independently enterable callees cannot borrow those root facts.
For learned direct callees, a separate single-entry analysis seeds only the
checked root and propagates real CALL packets and RET effects. It removes the
fabricated immediate CALL fall-through and verifies the complete RET graph
against the generated whitelist. Selected text must be structurally connected
to the checked root before value-based refinement; disconnected targets,
indirect control, IJ history and adjusting RETs are refused. Default
independent-root analysis remains unchanged.
This does not assume callee-saved registers or untouched source memory for an
ordinary function. The predicate/continuation contract is in
[Historical JIT_EXECUTION](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/entry_admission.md#5-%E5%85%A5%E5%8F%A3%E6%9D%A1%E4%BB%B6%E4%B8%8E%E5%B5%8C%E5%A5%97%E7%BB%AD%E7%82%B9).

Stack analysis keeps several possible RSP values and origins when different paths
reach a block. This preserves the relationship between CALL depth, saved registers
and shared RET instructions. For a plain 64-bit pop, it checks the IR and reads
the pre-pop target from the sequential memory model.

Only a completely known set of numeric return targets can narrow propagation to
those also allowed by the emitted target list. An unknown, partly overwritten or
widened slot must keep every target. Those paths merge normally; the analysis does
not invent cycles from hypothetical pop depths. It adds no assumption that CALLs
and RETs balance, that the stack is private, or that runtime stack contents match
the model.

Each block permits at most 64 alternative states. The CFG work budget also bounds
state visits; exhausting either limit refuses the entry. A proven return-slot
rewrite may skip a connected continuation without inventing an input for it. Its
emitted bytes still receive unconditional checks. None of this proves that another
executor cannot change a return slot or pointer before a later load.

The return-table builder groups direct CALL sites by callee and walks each callee
with a visited set. If several callers share a RET tail, that RET keeps all their
continuations, including targets reachable after return-slot rewrites. It does
not assume a RET must match the original CALL. Offsets come from the decoder's
location database, not from text labels.

The builder has a 65536-unit work budget covering instructions, graph nodes and
edges, and additions to the return-target table. An unknown location, missing
successor/database entry or exhausted budget refuses translation without keeping
a partial table. Both scope comparison and final emission report that outcome as
native-only. This budget limits translation graph work; it is not a runtime
instruction limit, a strict memory/time bound or a code-versioning mechanism.

New clobber boundaries retain SP/BP facts only; the compiler spills other live
values. The separate minimal-entry check tracks uncaptured dependencies per bit.
Zero extension preserves source-bit dependencies and defines the added high bits;
sign extension propagates the source sign-bit dependency to those high bits.
A 32-bit CMOV can therefore leave an already-defined low byte usable even when
other source bits remain uncaptured. Observing the undefined bits in a store,
address or branch still refuses admission; this adds no captured registers.

`KD_SPIN_DIRECT_HELPER_LOCK` provides an optional ABI1 source entry for helpers
whose prologue saves registers before assigning them. It sets `RBX` and
`R12`–`R15` to zero immediately at the named continuation, before compiler
reloads and helper calls. These registers were already declared overwritten by
the inline assembly, so this adds no capture or packet fields. Hot local returns
and delegated execution use the same five instructions; ordinary cold execution
already has valid native values. A helper's formerly uncaptured R13 save can
then pass the existing input check; other unsafe helper effects remain refused.
The current taskname payload uses the ordinary `KD_SPIN_DIRECT_LOCK` entry and
the bounded original `strscpy_pad` service instead, without these five setup
instructions. The optional helper entry and the selected KD mutex protocol
are unchanged.

Entry predicates may prove an entire BP-relative spill lies inside the
256-byte SP-relative checkpoint. All prior checkpoint obligations are joined
by intersection of coverage (union of predicates); opaque writes/callees still
block new entry identities. Neither the checkpoint size nor address screening
is relaxed to admit these spills.

Preserving handler GPRs does not prove that saved stack words stayed unchanged.
The two-level mutex helper therefore requires the following runtime checkpoint,
not a private-stack or arbitrary callee-ABI assumption. RET emission, thunk
mitigations and alias checks are unchanged.

`handle_known_mutex_call()` checks whether a supported local mutex call changed
the waiter's stack. Before the call, nofault reads snapshot 256 bytes above the
virtual CALL word, bounded by the waiter's live kernel stack. Afterward, KD compares
those bytes and separately checks the saved target, return token and exact
post-CALL RIP/RSP.

If the bytes match, JIT may continue. If they changed, `KD_CALL_STACK_CHANGED`
resumes the original waiter after the completed control call. It keeps the current
memory and registers; the combiner retains the real locks and handles unlock ACKs.
No writes are rolled back and no acquisition is replayed. If the required window
is unavailable before the call, a validated PENDING exit runs the call natively.
An invalid token, read or packet after progress is still fail-stop. Final completion
needs no preservation check because it does not return to this JIT episode.

The real contention gate now extends the existing seven-role driver. B's native
owner waits for the combiner in Linux's mutex wait_list before writing an
explicitly exposed live waiter-local word. The original waiter observes the new
value after the completed CALL, with A and B still owned by that combiner;
the two unlock ACKs precede suffix completion. The oracle requires the distinct
stack-change warning, actual source CALL successor and unchanged NORMAL root,
not only successful native code. This is one bounded shared-slot history, not
arbitrary concurrent mutation or a stack-privacy assumption; see
[Historical the execution gate](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/entry_admission.md#53-mutex-%E6%8E%A7%E5%88%B6-call-%E7%9A%84%E6%A0%88%E6%A3%80%E6%9F%A5).

The provider now advertises this immutable implementation contract through
the separate 16-byte `KD_JIT_CAPS` ioctl. Translation queries its validated
device description once before text inspection, caches only that lease's bound
and clears it on close. Absent/unknown contracts leave the bound zero; actual I/O
errors abort inspection. Version 1 still describes the old mutex bound but lacks
the module range required by current translation (7.2.2). Source INFO remains
mandatory. This is not a mutable
admission bit or executable generation. Guarded mutex analysis now uses the bound
only at registered local controls whose IR matches the exact eight-byte CALL
push and source return token. It first applies that write, then derives checked
window starts from every possible post-push RSP+8. It never restores pre-CALL
facts. Only identical-base, fully covered byte/word facts survive the clobber;
partial words use the byte model. Unknown bases/packets, spin, hostcall and other
memory retain the existing uncertainty and work limits. Coverage checks cannot
refill the analysis budget or add an alias separation to assume membership.
Spin remote controls can execute later source instructions, so this local mutex
contract must not be generalized to them. The check compares
values across this one control boundary; it is not protection from arbitrary
concurrent writes outside that interval, a private-stack proof, or code-version
isolation.

The real depth gate now learns the local and external helpers in two separate,
joined waves, without inlining either CALL level. The final JIT acquires seven
children in the external helper, executes its RET, and reaches the local
helper's eighth-child capacity exit. The remaining local suffix/RET runs natively
with retained owners and ACKs. Source pins and native importer references are
checked separately through retirement; generated userspace tests also execute
both RETs across substituted control successes. This bounded increment is
complete; broader context/alias work remains in TODO C5.

This remains incomplete for arbitrary pointers, unlifted instructions and
concurrent mutation. Improving precision is not grounds for removing safety
probes. A refusal makes future entries native-only; it does not undo earlier
work or validate owner-sensitive native suffixes.

### 7.2.1 Dynamic Address Gap

The current checks do not validate every address when it is accessed. Unknown
input pointers and pointers loaded from runtime memory are accepted unless another
rule rejects them. For example, `mov rax,[rdi]; mov rax,[rax]` loads a pointer and
then follows it. The second load could reach a sensitive region even though that
region's address never appeared in the instruction bytes.

The sequential memory model also cannot stop another thread from changing a
pointer before a later load. Holding lock A excludes other users of A, but not
per-CPU activity or a writer that never takes A.

The bounded [pointer audit](https://github.com/hailongeric/kdlock/blob/17f146e52f9f52485b8211addb7dab7195e70452/docs/VALIDATION.md#dynamic-pointer-screening-gap) executes
these paths against harmless user allocations labelled by mock symbols.
It confirms a missing check, not actual kernel context corruption or a rate of
failure. The entry predicates, local mutex checkpoint, retained native owner
and unconditional emitted-block scan do not close this gap. Successful code
generation reports `CONTEXT_SCREENING_ONLY`; the narrow stack-alias checks below
do not establish a general runtime address or object policy.

#### Checked spin pointer loads

A source CALL writes its return address on the waiter's stack. A later load
through a dynamically obtained list pointer might refer to those same bytes.
Keeping every possible overlap can make the analysis unable to bound the loaded
pointer, as happened in the xattr linked-list traversal. Treating helper stacks
as private would hide that possibility. `address_guards.py` instead permits a
limited retry that checks the particular overlap immediately before the load.

This retry requires ABI1 spin, complete selected source text, no learned indirect
control and provider capability version 7 bit 6. It handles only an explicit
64-bit `MOV` memory load addressed by one register plus a fixed displacement.
The retry is disabled if source constant-branch proof changed any branch during
this translation. A simplified branch could otherwise hide a flags read in the
original native suffix. A body requiring both kinds of proof remains refused;
the spin flag proof must describe the source that the waiter will actually run.
It can exclude uncertain overlap with recorded source-stack writes whose address
is known relative to the current logical SP or BP; definite overlap retains its
actual stored value. It does not declare arbitrary pointers safe. There are at
most 64 sites, 64 checked ranges per site and a 16,384-byte displacement bound.
The check covers the complete eight-byte load, including address wraparound.
Its address calculations and original load use the same preserved source register
and displacement without reloading a pointer from memory between check and use.

Each site also needs a source flag proof. Arithmetic flags record carry, parity,
auxiliary carry, zero, sign and overflow. Along every possible source path after
the guarded instruction, the proof requires each incoming flag to be overwritten
before a source instruction reads it, or to reach the declared final clobber
unlock. It follows decoded helper instructions and all permitted returns; a CALL
alone does not prove flags are disposable. Missing code, overlapping instruction
streams, unknown flow and cycles that retain incoming flags refuse this proof.

On success, the load executes with its original register state and flags. On a
failed check, generated code saves the current full register packet and returns
exit 9 before the load. The runtime validates the immutable image's site record,
exact source address and instruction bytes, stack bounds and single-root spin
ownership. The original waiter resumes at that same load with the current SP
and registers. Earlier effects remain; no body or CALL is replayed. This path
uses the existing spin native ownership and unlock-acknowledgement rules, and
disables future delegation of the stable entry for the source session. It does
not restore arithmetic flags because the source proof established that their
incoming values are no longer needed. See the
[packet and image contract](../JIT_REGISTER_ABI.md#checked-spin-address-exit).

The candidate 11 live continuation probe passed four phases of 1,600,000
operations. Its cold delegated phase recorded 1,432,107 matching entries and
completed bodies. When a pointer overlapped the waiter's stack, exactly one
entry exited through the address check and completed zero delegated bodies;
later calls made zero generated-code entries. Result, original-task identity,
once-only effects, exclusion and teardown checks passed. These
[functional checks](../../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
do not establish a performance result. The checks do not cover ABI3 rwlock,
nested spin ownership, arbitrary loads/stores, sensitive objects, concurrent
memory changes or generic fault recovery. The existing general processor-flag
limitation also remains.

The following steps describe the remaining general address-policy work,
**not an implemented safety contract**:

1. Define the enforceable address/object policy and its lifetime first. Linked
   kallsyms intervals alone do not enumerate runtime per-CPU allocations, task
   objects or aliases with context-sensitive behavior. A known-range denylist
   would protect only that declared range, not establish context equivalence.
   Core static and boot-reserved module ranges are handled below; object coverage remains
   open. Assess existing kdlock/kernel APIs before considering any guest change.
2. Separate entry-only predicates from use-time validation. Entry GPR checks
   cannot validate a later memory-loaded pointer. An access guard must compute
   and check the effective address once, then use that same address for the
   original load/store/RMW, including width/overflow and implicit accesses.
   Reloading a mutable pointer after checking it leaves a check/use race.
3. Extend either checked exit contract only after proving the new guard's own
   address and state handling. Neither reviewed processor markers nor the
   restricted spin MOV check authorizes recovery at an arbitrary memory
   operation. Preserve completed stores, exact owners and required flags; do
   not reuse entry refusal after progress or treat a generic fault as a validated
   exit. General flag repair remains deferred.
4. Validate memory/RET assumptions at their uses or conservatively join their
   effects. Keep the complete emitted return whitelist; unconditional byte
   bans alone do not check computed addresses in a dataflow-skipped block.
5. Convert the bounded counterexamples into refusal/forward-continuation gates
   in existing test programs, with exactly-once stores and owner ACK checks.
   Keep affected complex spin/mutex modes actually executing JIT; mutex JIT
   is always enabled. Blanket unknown-pointer refusal is not a passing JIT result.

Until an enforceable policy and these exits exist, limit use to audited
experimental workloads. More static examples or successful stress runs cannot
justify a claim that every context-sensitive critical section is refused.

### 7.2.2 Static Per-CPU Ranges

The captured x86-64 kernel's `__per_cpu_start` is zero; `current_task` and other
static per-CPU symbol values are offsets, not each CPU's dereferenceable address.
Translation now reads `nr_cpu_ids`, `__cpu_possible_mask` and `__per_cpu_offset`
through its existing pinned kcore/device lease, before text admission. For every
possible CPU it adds the interval starting at `__per_cpu_start + offset[cpu]`
(modulo 64 bits), with size `__per_cpu_end - __per_cpu_start`. Offline possible
CPUs remain covered. The linked section itself is not added as a low-address
interval, which would incorrectly classify ordinary small immediates.

This uses the captured boot-time initialization contract in
`arch/x86/kernel/setup_percpu.c` and `smpboot.c`: possible CPUs are established
before per-CPU setup and offsets become read-only after init. Each translation
reads the metadata anew and compares a second read. Counts are bounded to 8192,
the static section to 16 MiB, and offset reads to 64 KiB. Missing/ambiguous core
symbols, invalid counts/masks/addresses, short or changed reads, wrapping or
overlapping runtime intervals abort as infrastructure errors, not successful
native-only verdicts.

On the captured x86-64 SMP kernel, both first-chunk allocators reserve
`PERCPU_MODULE_RESERVE` (8192 bytes) after the core section aligned to
`PCPU_MIN_ALLOC_SIZE` (4 bytes). `kernel/module/main.c` uses
`__alloc_reserved_percpu()`; `mm/percpu.c` serves it only from the reserved chunk
when that boot-fixed chunk exists, failing rather than spilling to a dynamic
chunk when full. Normal module unload frees allocations within that arena,
not the arena's address classification. This does not pin or validate an object.

The provider reports this bound using the existing 16-byte CAPS packet on the
same device lease. The module bound was introduced in version 2; the current provider
uses version 9. Translation requires immutable mutex images plus exclusive KD
objects (`KD_JIT_CAP_MUTEX_EXCLUSIVE`, bit 4); ordinary images still accept the
version 5 through 9 contracts. Instruction-marker images require version 6 through 9
with bit 5. Spin address-check images require version 7 through 9 with bit 6;
bounded `strcmp` requires version 8 or 9 bit 7. The bounded `strscpy_pad` writer
requires version 9 bit 8 separately. Version 4 remains readable by observers but
cannot open a translation session for this object contract. It checks the build constants and the non-NULL
`pcpu_reserved_chunk` pointer, which is read-only after init; it never dereferences
the private chunk layout. Translation adds `[base + ALIGN(core_size, 4),
base + ALIGN(core_size, 4) + module_bytes)` for each possible CPU. Version 1,
unavailable or invalid capability cannot silently omit the module check: current
translation reports an infrastructure error before reading source text. Source
inspection/retirement can still query older providers. Neither the ioctl number
nor its size, guest code or wrapper arguments change.

Do not extend coverage to `pcpu_unit_size`: the embedded allocator returns unused
tail pages to ordinary memory. Alignment padding is not claimed as module data,
and ordinary dynamic chunks/objects remain outside this range contract.

Whole-area coverage is separate from named-symbol intervals, so an interior
symbol cannot truncate it. Existing explicit-operand, derived-address and IR
checks then reject statically resolvable accesses, including boundary overlap.
`STATIC_PERCPU_SCREENING` reports possible `cpus`, `core_bytes`, `module_bytes`
and their sum `bytes_per_cpu`, not runtime address enforcement. Core and module
arenas retain separate labels. The optional name-only/core-only parser remains
for byte fixtures; the real translator must supply its leased reader and
negotiated module bound. This is not a runtime memory snapshot
of the protected areas, and it does not establish code-version isolation.

The API audit found that `is_kernel_percpu_address()` only recognizes core
static areas, while `is_module_percpu_address()` recognizes module static areas.
Neither is an arbitrary dynamic-allocation classifier. `per_cpu_ptr_to_phys()`
requires an already valid, live per-CPU pointer; the private allocator lookup
assumes an allocator pointer and cannot safely classify arbitrary JIT addresses.
Module/dynamic allocation lifetimes, other task/context objects, unresolved
runtime pointers and concurrent pointer replacement therefore remain open.
No such helper is called from generated code in this increment.

### 7.3 Build And Publication

The daemon has flat RIP and RIP/tgid workspace modes, independent of benchmark
mode. It maintains callee/indirect-target tables, reads /proc/kcore, combines
generated assembly with the wrapper, assembles/links and transfers jit.bin.
The [device session](../../daemon/README.md#device-session-and-source-residency) remains held across this
flow; opening a new device after an error is not a supported recovery path.
Policy refusal removes stale outputs and exits 2; launch failures/exceptions
are errors/retry conditions, not successful native-only decisions.

Images must include the 48-byte protocol/ABI directory and fit 640 KiB. Transfers
use up to 4000-byte chunks with exact upload identity, contiguous coverage and a
base generation. Mutex uploads publish a complete immutable descriptor; frames
retain it through continuations and old-generation misses cannot change a newer
image's metadata. Published versions remain in the bounded pool until teardown.
Publishing the first address-check image also moves that ABI1 spin entry to
immutable versions; every later image for that entry remains immutable, even
without checks. Its active frames retain their bound image and site directory.
Ordinary spin entries that have not made this transition and ABI3 rwlock images
retain in-place storage. Independent locks sharing an entry address do not
establish image lifetime through lock serialization.

The scalar instruction policy refuses unknown instructions and unreviewed
processor-state operations before emission. Sensitive raw encodings are checked
at instruction boundaries, including selected undecodable roots. The limited
mutex exception below emits an exit marker, never the special operation itself.
See [the compatibility backport](../history/legacy_mutex_compatibility.md) for scope, capability
negotiation and the separate owned-origin/ABI4 interfaces.
See [daemon README](../../daemon/README.md) for CLI and diagnostics.

### Checked instruction exits

An instruction on a rarely taken branch need not reject an otherwise eligible
mutex critical section before it runs. For mutex entry ABI2, the translator can
replace the exact reviewed encodings below with a **marker**, generated code
that returns to the runtime before executing that instruction. The runtime
resumes the original waiter at the instruction and disables future delegation
of that critical-section entry. Earlier protected writes are retained and are
not repeated. Rwsem outer writers use this same ABI2 path.

| Source instructions | Meaning; action at the marker |
| --- | --- |
| `RDTSC`, `RDTSCP` | Read the processor timestamp counter; RDTSCP also returns an operating-system-programmed value called TSC_AUX, commonly used to identify a CPU. The waiter performs the read. |
| `CPUID` | Query processor features using register inputs; the waiter performs the query. |
| `RDPMC` | Read a processor performance counter selected by a register; the waiter performs the read. |
| `RDMSR`, `WRMSR` | Read or write a model-specific processor register; the waiter executes the original operation with its current register inputs. |
| `CLI`, `STI` | Disable or enable maskable interrupts on the current CPU; the original operation runs on the waiter. |
| `CLD`, `STD` | Clear or set the direction flag used by string instructions; the original operation runs on the waiter. |
| `LAHF`, `SAHF` | Copy selected arithmetic flags to or from the high byte of register AX; the original operation runs on the waiter. |

Instruction meanings and encodings follow Intel's
[instruction-set reference](https://cdrdv2-public.intel.com/789581/325383-sdm-vol-2abcd.pdf).
The live probe relies on the documented property that RDTSC leaves arithmetic
flags unchanged, so the native suffix can check flags set before the marker.

Only exact unprefixed encodings without explicit operands qualify. The translator
models their scalar inputs and outputs to check the original code, but never
simulates their processor effects on the executor. An unsafe source instruction
does not become safe by running locally: this change preserves the original
program's behavior and does not authorize new kernel operations. In particular,
the live check uses the harmless timestamp read, not interrupt or register writes.

Before emitting markers, admission still checks the full selected source graph,
including the part that would run natively after a marker. Backend, context,
memory-alias and captured-input checks remain active. The marker needs proven
register inputs and source-defined arithmetic flags. A source path that cannot
satisfy those checks remains refused. Only after proof does generated control
flow end at each marker. Therefore an untaken eligible instruction can cease to
be the reason for rejection, while an unsafe or undecodable suffix can still
reject the entry.

Provider capability versions 6 through 9 advertise this contract on bit 5; the image
requires it on directory bit 0. Earlier providers cannot accept such images.
Spin/rwlock images retain their existing static instruction policy. Unknown
encodings, unreviewed prefixes, control-register moves, flags-stack operations,
interrupt/trap instructions, transactional operations and floating-point/vector
state remain outside this reviewed marker set. Runtime validation failures and
generic JIT faults remain errors, not arbitrary native-continuation points.

The entry becomes `NATIVE_ONLY` under the image-publication gate, including when
an older retained image reaches the marker. Already admitted work may drain;
after quiescence, later calls must have zero JIT entries. The disable persists
for the source session and is cleared only by its normal retirement/reload.
See [register restoration](../JIT_REGISTER_ABI.md#checked-instruction-exit) and
[frame lifetime](frames.md#95-forward-native-continuation) for the exact state
and ownership obligations.

### Bounded original strcmp service

ABI1 spin callers can use a typed native service for the captured `strcmp`
implementation. A typed service is a specific, checked helper call whose input,
output and memory effects are known. This service invokes the original helper
on the executor's stack and resumes the generated caller at its original return
address. It retains the source CALL's write of its return address to the waiter
stack; declaring the helper read-only does not remove that write from analysis.

This is limited to audited ordinary kernel strings that remain allocated and
unchanged while the physical source lock is held. For the xattr workload, that
lock protects stored names, and the pinned waiter owns the syscall's copied
search name. Holding an arbitrary lock does not establish these properties for
unrelated objects. The service is not a general guarantee for every kernel
`strcmp` caller.

Capability version 8 or 9 bit 7 and image requirement bit 2 negotiate the service.
Both bounded string services require one top-level physical lock hold. A
selected source graph containing a nested acquisition or another nonterminal
lock-control call is refused before publication. The terminal outer clobber
unlock remains allowed. Runtime ownership and frame checks stay mandatory;
the translation check prevents an unsupported nested service from reaching
those checks only after protected work has already executed.
Only an exact direct five-byte source CALL is accepted. Both provider and
translator verify the captured 42-byte helper. Each return is either a jump to
the actual return thunk or the captured runtime alternative, RET followed by
four INT3 padding bytes. A return thunk is the kernel's shared return-instruction
sequence; the padding traps if accidentally executed. Different helper text
remains native. The translator also proves
from those original instructions that incoming arithmetic flags cannot affect
the helper's behavior; an ordinary C calling convention is not used as that
proof. Each pointer must be captured, and its possible 256-byte read span passes
the existing context-address checks. Widened address analysis still refuses.

Before invoking the helper, the runtime validates the pending CALL and source
residency, then reads each string through a bounded no-fault check until a NUL
terminator is found. No-fault means an invalid address returns a failure instead
of causing a kernel exception. At most 256 bytes per string are checked, covering
the Linux xattr limit of 255 name bytes plus the terminator. Invalid, overflowing
or unterminated inputs leave the service unexecuted. The original waiter then
continues at that CALL's helper entry, and the critical-section entry is disabled
for later delegation. Earlier work and the CALL word are retained; nothing is
replayed. A successful service changes only saved RAX to the helper's 32-bit
integer result and consumes the validated return continuation once.

Each invocation permits at most 128 `strcmp` calls. All other services and
ordinary continuations share the existing limit of 16; total continuations are
bounded by 144. The bounded `strscpy_pad` service below uses that ordinary
allowance, not the 128-comparison allowance. `strscpy_pad` and `memcpy` write memory
and do not inherit this read-only contract. Helper checks and successful image
publication alone are not evidence that a whole benchmark body completed in JIT.

The candidate 10 bounded-string probe passed all four phases, totaling 6,400,000
operations. Its cold delegated phase recorded 1,292,047 matching entries and
completed bodies. A string longer than the admitted bound caused one entry to
return to the native waiter before calling the helper, with zero delegated
completions; subsequent calls made zero generated-code entries. Candidate 11
also completed all eight xattr front/tail/miss/size checks with 16 or 128
attributes, 64-byte values and 16 workers. Each recorded matching entries and
completions, correct results and clean teardown. These
[functional receipts](../../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
remain separate from the pending full performance matrix.

### Bounded original strscpy_pad writing service

The writing service passed the current ordinary taskname shell's 16-worker
read-only check: 3,194,222 complete delegated bodies in 3,200,000 operations.
Linux Native, TCLock and KD passed data and drain checks with 20% mutations,
but KD's nine preparation completions were followed by zero measured completions. That
strict measured-delegation check remains failed; the full performance matrix
is pending. Exact source identities and earlier failures remain in the
[validation record](../../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md).
The service has a separate capability, version 9 bit 8, and image requirement
bit 3. A provider that supports only the read-only `strcmp` service cannot accept
a writing-service image.

The supported API call is the original `strscpy_pad(destination, source, 64)`.
That helper copies a string and fills the remainder of the 64-byte destination
with zero bytes. The translator requires the exact count 64 and one known
destination in the current caller's local stack frame. It screens both possible
64-byte memory spans for task or processor-sensitive addresses. Unsupported
counts, unknown frame relationships and widened address facts remain refused.
It does not substitute a different copy operation or inspect mutable source
bytes during translation.

Both translator and provider check the complete captured implementation:
70 bytes of `strscpy_pad`, 310 bytes of `strscpy`, the six-byte `__memset` entry
that jumps to the selected 23-byte `memset_erms` implementation, and the actual
single-return-instruction thunk. Every external branch must target the named,
validated helper. The selected `memset_erms` uses a repeated byte-store
instruction to fill the buffer. Other processor alternatives are not admitted
by this contract. The warning trap in `strscpy` remains in the checked bytes;
the exact count 64 cannot reach its oversized-count condition. Ordinary JIT
instruction admission does not gain permission to execute that trap.

Before any destination write, the provider validates the source CALL, its
return continuation, the physical lock owner and the helper source lifetime.
The full destination must lie above the pending CALL word and below the saved
frame pointer, within the logical waiter's task stack. Its source span must be
outside that entire task stack. It then checks the original helper's eight-byte
source reads until a terminating zero byte is found, with a 64-byte maximum.
The check includes the remainder of the final eight-byte word, because the
captured helper reads that word even when the string ends earlier. The audited
caller must keep this ordinary kernel memory allocated and unchanged while the
source lock is held; a no-fault read cannot establish that lifetime itself.

Failed argument bounds or source-read checks leave the helper unexecuted and
return the waiter to its original helper entry with the existing CALL word.
This keeps earlier protected writes and avoids repeating the CALL push.
Malformed ownership, source text or continuation state remains an error.
For the mandatory count 64, the exact `strscpy` prefix cannot take its
zero-count branch. Its following comparison defines all six arithmetic flags
before any incoming flag can affect execution. Both translation and runtime
enforce that argument premise; no source branch is rewritten for this service.
This bounded C API contract does not mark `strscpy_pad` as a generally
flag-independent helper for address checks. The separate source-flag proof
remains conservative when its instruction model leaves a processor-undefined
flag unassigned. An address check that would need such a helper proof remains
refused; constant branch specialization is not used to bypass that condition.

After a successful service, analysis retains the original virtual CALL write,
invalidates every destination byte, drops caller-saved register facts and
preserves the callee-saved registers and returned stack pointer. It makes no
blanket private-stack or read-only-memory assumption: a possible destination
alias still invalidates the overlapping fact. Execution invokes the original
helper with the original arguments and consumes the validated continuation
once. This is a C API contract; observing discarded helper spill storage below
the caller's stack pointer is outside it, because the helper executes on the
executor's stack. The entry uses immutable images. General writing helpers,
including `memcpy`, do not inherit this contract automatically.
Writing services share the existing limit of 16 scalar services and ordinary
continuations. Only `strcmp` uses the separate allowance of 128 comparisons.
