# Translation admission and publication

Current implementation contract; start with the [design overview](../DESIGN.md).
Validation belongs to its frozen inputs in [tests](../../tests/README.md).

## 7. Translation And Publication

### 7.1 Possible JIT Episode

`context_policy.jit_phase_blocks()` selects reachable decoded blocks using
entry and learned targets as roots. For an ordinary direct CALL to a callee
absent from those blocks, it retains the CALL/exit stub but removes the native
return edge. The waiter will complete that suffix without returning to this
JIT invocation.

Control calls, allowlisted hostcalls, decoded callees and indirect calls retain
their relevant successors. An alternate JIT path to a suffix keeps it in scope;
a deleted native edge must not contaminate that path's dataflow.
Every recompile rechecks the newly learned scope. Admission, lexical lock
boundaries, constant propagation, emitted blocks and entry dispatch share it.
Missing reachable branch text is not an implicitly safe empty block.
For a cross-window placeholder whose bytes are already cached, the translator
seeds the owning decoder window and recomputes the selected graph. Decoder roots
are split into dispatch blocks even when they lie inside an earlier block.
These seeds do not become independent admission roots. Text reads and decoder
reseeding share the 32-expansion bound; genuine undecodable blocks still refuse.

### 7.2 Context And Memory Admission

Production admission accepts explicit GS memory reads, writes and RMW through
the pinned origin base, and supported current_task MOV loads through logical
task input. GS displacements are not linear kernel addresses. FS/base operations,
implicit GS string/XLAT without lowering, known linear per-CPU/current addresses,
scheduling/preemption/IRQ/BH/RCU references and backend mismatches still refuse.
Waiter pinning protects against task replacement, not IRQ/NMI or arbitrary
remote accesses; this is not general per-CPU context equivalence.
These unconditional byte/operand checks run across every selected emitted block
before value propagation or its guarded retry. A rewritten RET may leave a
connected block without a propagated input, but its code and whitelist target
still exist. Such a block cannot bypass unsupported segment, IRQ, known context-symbol or
foreign-backend checks. This pass uses the already selected JIT episode; it
does not reintroduce an ordinary CALL miss's waiter-only suffix.

Analysis covers explicit operands and lifted IR memory effects, including
implicit/internal-IR accesses, decoded CALL arguments/RET results and CALL
return-slot writes. Bounded facts propagate through selected CFG edges; merges
retain sensitive alternatives. Memory values, masks, alias origins and writes
are checked conservatively. It does not read runtime memory or treat source
RBP/RSP as private memory. Analysis limits affecting addresses refuse admission.

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

Scoped flow keeps a bounded disjunction of RSP value/origin facts, preserving
the relation between different CALL depths, saved registers and shared RETs.
It checks the plain 64-bit pop IR, then reads its pre-pop target through the
existing sequential memory model. Only an entirely exact numeric domain
restricts effect propagation to its intersection with the emitted whitelist.
An unknown, partially overwritten or widened slot keeps every target; those
destinations join normally instead of enumerating hypothetical pop-depth cycles.
No CALL/RET balancing, runtime stack read or private-stack assumption is added.
Each block permits at most 64 partitions, and total partitions/visits remain
bounded by the CFG work budget. Exhaustion refuses the entry. A structurally
connected continuation skipped by a proven return-slot rewrite need not gain
a fabricated input state. Unconditional checks still cover its emitted bytes;
register/memory effects use the sequential model, not a proof that another
executor cannot rewrite a return slot or pointer before its later load.

The emitted return-table builder groups direct call sites by callee and walks
each callee iteratively with a visited set. Shared RET tails retain the union
of every caller continuation, including targets reached after return-slot
rewrites; a matching source CALL is not assumed. Location offsets come from
the decoded location database, not formatted label names. A 65536-unit work
budget counts instructions, traversed nodes/edges and return-target additions.
An unresolved location, missing walked successor/database or exhausted budget
raises an explicit refusal without committing a partial table. Both scoped
comparison and final emission handle that error as native-only. This is a
translation graph budget, not a runtime instruction limit, hard memory/time
bound or executable-version publication protocol.

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

The runtime checkpoint for the checked mutex summary is wired into
`handle_known_mutex_call()`. It snapshots 256 bytes above the virtual CALL word,
bounded to the original waiter's live kernel stack, using nofault reads. After
the real local mutex control, it compares those bytes and separately verifies
the captured target/return token and exact post-CALL RIP/RSP. Equal contents
permit the existing JIT continuation. Changed contents set a distinct
`KD_CALL_STACK_CHANGED` phase: the original waiter resumes after the completed
control, with current memory and registers, while the combiner retains native
owners and services unlock ACKs. No writes are restored or acquisition replayed.
An insufficient window exits before the control using a validated PENDING CALL;
an invalid token/read/packet remains fail-stop after progress. Final completion
does not need a preservation check because it never returns to this JIT episode.

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

Unknown entry pointers and addresses loaded from runtime memory are admitted
unless another rule rejects them. `mov rax,[rdi]; mov rax,[rax]` therefore can
reach even a known sensitive interval without embedding its address in text.
A sequentially tracked store does not prevent another thread from changing
that word before a later load. Holding A only excludes users of A; it does not
exclude per-CPU operations or another writer that does not acquire A.

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
   Keep affected complex spin/mutex modes actually executing JIT, including
   `mutex_jit=1`; blanket unknown-pointer refusal is not a passing JIT result.

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

The provider reports this bound using version 2 of the existing 16-byte CAPS
packet on the same device lease. It checks the build constants and the non-NULL
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

Images must be nonempty and fit 640 KiB. Transfers use up to 4000-byte chunks;
the last complete chunk sets NORMAL. The kernel checks entry, offset, payload
size and status, but does not establish complete image continuity/generation
or protect live executors. Recompilation overwrites the existing block.

Independent locks may share the RIP-keyed artifact; early A unlock can also
allow overlapping execution. Lock serialization is not version retirement.
Immutable versions, full publication validation and reclamation are explicitly
deferred under [C3](../TODO.md#c3-immutable-jit-publication-and-lifetime).
See [daemon README](../../daemon/README.md) for CLI and diagnostics.
