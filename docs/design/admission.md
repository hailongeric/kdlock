# Translation admission and publication

Admission decides which machine code KD may translate and execute. This guide
explains the current checks and their limits. Read the [design overview](../DESIGN.md)
first; [tests](../../tests/README.md) records which source versions were checked.

Delegation admission and translation admission are separate. Owned mutex ABI4
normally offers a request after local acquisition fails. The opt-in adaptive
policy can offer one earlier after observing at least eight contenders. Both
routes then check
source/task eligibility and resources without heat sampling. The translator still
checks owned lock kind 3, ABI4's defined register inputs, the fixed caller stub,
terminal unlock and all applicable context/memory rules below. A local SELF
success executes no JIT body. See the [owned register contract](../JIT_REGISTER_ABI.md#owned-mutex-ordinary-c-entry).

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

### 7.2 Context And Memory Admission

Some code depends on the CPU or task that runs it. KD therefore checks context
operations across every block it will emit:

- Spin and rwlock images may lower explicit GS reads, writes and read-modify-write
  operations through the pinned origin CPU's GS base. Owned mutexes admit only
  the audited subset below, with an exclusive origin claim. A GS displacement is an offset,
  not a linear kernel address.
- Supported `current_task` MOV loads may use the original task supplied to JIT.
- Instructions outside the supported scalar CPU-state contract are refused,
  including interrupt/uaccess state, MSRs, hardware control registers and SIMD/FPU
  operations. Ordinary GPR writes remain eligible; see the instruction rules below.
- FS/base operations, implicit GS string/XLAT operations without lowering, known
  linear per-CPU/current addresses, scheduling/preemption/IRQ/BH/RCU references
  and calls to the wrong lock backend are refused.

Disabling preemption for a spin waiter prevents task replacement. Mutex waiters
retain only migration pinning while asleep, so another task may run on their CPU.
Neither pin prevents IRQ/NMI activity or arbitrary remote accesses, or reproduces
the waiter's complete per-CPU context on the combiner.

These byte and operand checks run before value propagation or a guarded retry.
A rewritten RET can leave a connected block with no propagated input, but that
block still has emitted code and a permitted target. It must still pass the segment,
processor-state, context-symbol and backend checks. The scan covers only the selected episode;
it does not add back an ordinary CALL miss's native-only remainder.

#### Processor-state instructions

`instruction_policy.py` permits supported scalar instruction families with GPR
operands, then applies the existing segment, memory and entry-value checks.
An unknown mnemonic or a hardware register without a lowering contract refuses
the entry. This applies equally to spin ABI0, clobber, rwlock and owned-mutex ABIs.

| Native-only operations | Examples |
| --- | --- |
| Interrupt, access-permission and flags state | CLI/STI, STAC/CLAC, RDPKRU/WRPKRU, PUSHF/POPF aliases, IRET, CLD/STD, LAHF/SAHF |
| CPU context reads and writes | RDMSR/WRMSR, control/debug registers, CPUID, RDTSC/RDTSCP/RDPMC, XGETBV/XSETBV |
| Hardware segmentation and descriptors | SWAPGS, FSGSBASE, direct segment registers, descriptor/task-register operations |
| System effects and transitions | Interrupts, system calls/returns, HLT, TLB invalidation, port I/O, virtualization and transactional instructions |
| Unmanaged extended state | x87, MMX/SIMD/vector registers, MXCSR, FXSAVE/FXRSTOR and XSAVE/XRSTOR families |

Balanced enable/disable pairs are still refused: their intermediate effects and
observations belong to the physical executor. Known uaccess, MSR and FPU helper
symbols are screened too. Typed hostcalls retain their separate audited contracts.
Scalar arithmetic, ordinary memory operations, fences, PAUSE and supported GS or
logical-current lowering remain eligible for the other admission checks.

Raw checks strip prefixes only at decoded instruction boundaries or selected
undecodable CFG roots. They catch sensitive encodings despite Miasm misidentifying
SWAPGS/FSGSBASE or lacking STAC/CLAC/PKRU decoding; immediate/displacement bytes
are not searched. Missing/unknown instructions still fail closed once text is
complete. Every emitted branch, decoded callee and learned target is rechecked,
including blocks skipped by value propagation. Code after the outer unlock or
an ordinary native CALL exit remains outside this episode. This is not a proof
of every callee in the entire lexical critical section before any delegation.

Refusal happens before emission/assembly, deletes stale generated artifacts and
returns translator status 2. The daemon publishes `KD_EXE_NATIVE_ONLY` instead
of uploading an image. INT is no longer replaced by NOP, flags instructions are
not silently omitted, and unsupported instructions do not get runtime error stubs.
This admission policy does not repair arithmetic condition-flag clobbers or add
general processor-state restoration or a pre-instruction native exit.

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

The historical real-contention check extended a seven-role driver. In that
recorded Linux-mutex implementation, B's native owner waited for the combiner
in Linux's mutex wait_list before writing an explicitly exposed live waiter-local
word. The original waiter observed the new
value after the completed CALL, with A and B still owned by that combiner;
the two unlock ACKs preceded suffix completion. The oracle required the distinct
stack-change warning, actual source CALL successor and unchanged NORMAL root,
not only successful native code. This is one bounded shared-slot history, not
arbitrary concurrent mutation or a stack-privacy assumption. It is not a fresh
owned-mutex execution check; see
[historical execution check](https://github.com/hailongeric/kdlock/blob/1b9191256f64785f8e844ada914356a69d4f70f0/docs/testing/entry_admission.md#53-mutex-%E6%8E%A7%E5%88%B6-call-%E7%9A%84%E6%A0%88%E6%A3%80%E6%9F%A5).

The provider now advertises this immutable implementation contract through
the separate 16-byte `KD_JIT_CAPS` ioctl. Translation queries its validated
device description once before text inspection, caches only that lease's bound
and clears it on close. Absent/unknown contracts leave the bound zero; actual I/O
errors abort inspection. Version 1 describes the old mutex bound; version 2
adds the module range below. Current translation requires version 3 and the
immutable owned-image capability before inspecting text. Source INFO remains
mandatory. The stack bound is not a mutable
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

The bounded [pointer audit](../VALIDATION.md#dynamic-pointer-screening-gap) executes
these paths against harmless user allocations labelled by mock symbols.
It confirms a missing check, not actual kernel context corruption or a rate of
failure. The entry predicates, local mutex checkpoint, retained native owner
and unconditional emitted-block scan do not close this gap. Successful code
generation now reports `CONTEXT_SCREENING_ONLY`; no runtime guard is added.

**2026-09-13 user decision:** the access-time guard, pre-instruction waiter
continuation and their local condition-code preservation remain deferred and
unimplemented. This is a retained limitation, not a pending scope decision.
The following order is for a future explicit reopening of this feature,
**not an implemented safety contract or the current implementation agenda**:

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
3. Define a pre-instruction native exit with unchanged current GPRs, virtual
   stack and required flags. Preserve completed stores and retained owners;
   the original waiter continues at that instruction and unlocks through ACKs.
   Do not reuse entry refusal after progress or treat a generic fault as a
   validated escape. Necessary local guard flags preservation belongs to this
   deferred feature; general flags repair is also still deferred. The
   [future packet contract](../JIT_REGISTER_ABI.md#deferred-access-time-continuation)
   separates pass-path preservation from native-target restoration; neither
   reading the stale packet flags nor relying on the existing MOV/RET stubs
   implements it.
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

The module bound was introduced in version 2 of the 16-byte CAPS packet and is
retained in version 3 on the same device lease. The provider checks the build
constants and the non-NULL `pcpu_reserved_chunk` pointer, which is read-only
after init; it never dereferences the private chunk layout. Translation adds
`[base + ALIGN(core_size, 4),
base + ALIGN(core_size, 4) + module_bytes)` for each possible CPU. Missing or
invalid module bounds cannot silently omit the check. Current translation also
requires the version-3 image capability; an older provider fails before text
inspection. Raw source/capability observers can still query older providers.
The ioctl number and size, guest kernel and wrapper arguments are unchanged.

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

Images must include the 48-byte wrapper directory and fit 640 KiB. Version 2
transfers use contiguous chunks with an upload identity, declared length, entry
ABI, requirements and base generation. Incompatible or incomplete metadata is
refused. The final chunk publishes NORMAL only after header validation.

Independent locks may share the RIP-keyed artifact; early A unlock can also
allow overlapping execution. Lock serialization is not version retirement.
Owned mutex frames bind immutable descriptors; every published version consumes
one of the bounded 64 blocks until terminal session teardown. Spin/rwlock image
families still overwrite their existing block; that remaining scope is tracked
under [C3](../TODO.md#c3-immutable-jit-publication-and-lifetime).
See [daemon README](../../daemon/README.md) for CLI and diagnostics.

## Audited owned-mutex GS subset

The origin-sensitive subset is opt-in and fail-closed. `origin_policy.py` accepts
only explicit, statically resolved scalar GS operands with exact symbol bounds,
width and operation permission. `cpu_number` is a read-only four-byte object in
the captured kernel Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`; the live
kernel notes, vmlinux symbol size and running address must all match.

The only mutable seed is `kd_origin_test_counter` in the private `kd_origin_gs`
test module. Its audit binds the reviewed source SHA256, exact module ELF SHA256,
ELF/live Build ID, relocated symbol address and eight-byte object width. It has
its own cacheline, no export or interrupt/NMI callback, and no remote writer.
Only task ioctls under its mutex update it; summation follows worker drain.
`KD_GS_AUDIT` selects that exact build manifest and cannot add arbitrary names.

Every newly admitted GS image must contain at most 256 decoded instructions,
with an acyclic, fully resolved graph ending at the terminal outer unlock. Other
calls, nested locks, services, indirect control and blocking instructions are
rejected. Unknown symbols, wrong widths, dynamic or implicit GS operations and
context-management storage remain rejected. The logical `current_task` rewrite
is unchanged and does not require an origin claim. Admitted GS operands use the
saved origin base; the executor's hardware GS register is unchanged.
