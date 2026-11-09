# JIT register and wrapper ABI

An application binary interface (ABI) defines how lock callers, generated code and recovery code exchange
execution state. They must agree on which registers are valid and how the original
waiter resumes. IP means instruction pointer, SP stack pointer, BP frame pointer,
and GPR general-purpose register. Just-in-time compilation (JIT) translates the
protected body for execution by another task. The [terminology guide](TERMINOLOGY.md)
defines shared lock and lifetime terms. [kd_regs.h](../include/kd_regs.h),
[asm_head.h](../include/asm_head.h), [wrapper.S](../include/wrapper.S) and
[kd_jit_batch.h](../include/kd_jit_batch.h) are the authoritative definitions.
Linux `pt_regs` is unchanged and must never be cast to `kd_regs`.

The selected [kdlock lock replacement contract](design/kdlock_lock_replacement_contract.md)
requires original-JIT current-position handback with exact IP/GPR/SP and source
CALL/RET effects. General flags/SIMD restoration and IRQ/NMI conflict handling
are deferred for that phase. Existing limited flags contracts below do not
establish broader restoration. Candidate details distinguish `ebae17c1`, the
source correction at `10ef078a`, runtime wiring at `a6fe0bb2` and production
checkpoint `da55414f`. Native owner routing, packet acceptance and final ACK have
component coverage with supplied task/physical primitives. Failed attempts and
[fixture limits](design/kdlock_lock_replacement_contract.md#component-fixture-limits)
remain explicit. The later `58af0a53` live probe passes cold CALL and
indirect-JMP handback. Post-RET inspection confirms the actual source return IP
and SP advanced by eight, with useful effects once, but the overall checker
fails. Candidate `bccf877c` has untested harness fixes; further validation is
blocked. See the [partial live record](design/kdlock_lock_replacement_contract.md#partial-live-probe-and-current-stop).

## Entry identities and packet states

| `entry_abi` | Identity | Captured input |
| --- | --- | --- |
| 0 | Legacy entry | Defined native callee-saved state plus IP/SP |
| 1 | Ordinary spin clobber v1 | IP/SP/BP |
| 2 | Ordinary mutex clobber v1 | IP/SP/BP |
| 3 | Rwlock writer clobber v1; writer admission before the body | IP/SP/BP |

A caller-clobber boundary tells the compiler that a call may overwrite registers.
The compiler saves values needed afterward; the provider does not capture every
incoming GPR. Direct calls pass the lock in RDI, RSP before the CALL in RSI, the
resume RIP after the CALL in RDX, and the caller's RBP in RCX. Each named
continuation belongs to one `noipa` workload function.
Registry, daemon, translator, frame and image must agree on backend and ABI.
ABI3 uses the spin backend and completion endpoint, with the rwlock writer
prelude and unstarted-retry ownership described in [rwlocks](design/rwlock_implementation.md).
ABI3 is a provider/translator entry identity, not a new guest-kernel hook. Rebuild
older ABI1 rwlock callers with matching preparation and generated images; retaining
ABI1 support for ordinary spin does not make old rwlock images interchangeable.

| Packet state | C may consume | Meaning |
| --- | --- | --- |
| MINIMAL | IP/SP/BP and declared metadata | Entry, before arbitrary incoming GPRs are captured |
| COMPLETE | Validated IP/SP/BP | Ordinary body finished at its exact terminal unlock |
| FULL | Current logical GPR packet | Materialized before intermediate C/control/native recovery |

A slot may contain bytes written by generated code without being valid captured
input. While a packet is MINIMAL, C cannot treat those slots as a complete entry
snapshot or FULL state. Production trusts all selected kernel/module code and
assumes its compiler clobber-entry contract supplies the needed live inputs.
It does not prove absence of uncaptured initial-bit dependencies or add capture
for those bits. Runtime still distinguishes MINIMAL, COMPLETE and FULL exactly.

Explicit `trusted_source=False` preserves the historical input, alias and bounded
value analyzer for regression fixtures. Its clobber facts and failure limits do
not govern the current production path. See [translation policy](design/admission.md).

The optional `KD_SPIN_DIRECT_HELPER_LOCK` uses this same ABI1 packet. At its
source continuation it defines the already-clobbered `RBX` and `R12`–`R15` with
five zeroing instructions before compiler reloads or helper prologues. Both hot
local returns and delegated entry execute them; the ordinary cold path needs no
added setup. It captures no additional registers and does not change SP/BP or
the ordinary direct entry. Taskname uses the ordinary entry and translates its
compiler-emitted string helper bodies normally. Production assumes the compiler
input contract instead of proving helper-prologue dependencies. The optional
entry remains available to other callers; the two-word ABI is unchanged.

Earlier helper-entry, string-service and mutation controls retain their original
outcomes in [history](history/README.md). Current ordinary-callee validation is
indexed under [trusted translation](VALIDATION.md#trusted-ordinary-translation),
including the separately failed strict mixed-taskname control.

### Mutex clobber and outer cookie

Ordinary direct mutex uses ABI2. The outer paired interface first attempts to
acquire the KD object's physical owner word in the caller. A successful atomic
compare-and-exchange records the exact task owner in an opaque same-task cookie;
its matching unlock calls `kd_mutex_local_unlock`. Linux mutex objects do not
participate in this ownership protocol.
The contended outer entry returns an exact native owner only before taking a KD
reference/gate; entry into the KD queue returns zero. The separate JIT continuation
defines zero before writing the cookie, so MINIMAL never depends on incoming RAX.

The unified `kd_mutex_lock/unlock` macros and ordinary blocking aliases expand
to `KD_MUTEX_DIRECT_LOCK/UNLOCK` with an internal numeric continuation. They use
ABI2 for both outer and supported nested translated operations, without a caller
cookie or named global label. The explicit outer pair remains separate.
Addressable/function-pointer lock calls preserve the ordinary C ABI and acquire
locally because those callers have not declared ABI2 clobbers. Callable public
unlock still uses exact provider routing. These C declarations use the distinct
assembler/export names `kd_mutex_api_lock/unlock`. These are conventional local
APIs; the checked analyzer treats them as native-only boundaries. Trusted source
must obey the object protocol and cannot infer a nested ledger from source trust.
Scope guard/free helpers use these conventional functions.
Interruptible, killable, I/O-related,
trylock and last-reference acquisitions remain local; non-lockdep nested blocking
annotations use the unified direct interface. No Linux mutex object participates.
See [mutex routing](design/locking.md#entry-completion-and-task-routing).

## Source PUSHF and POPF operations

The translator lowers source `PUSHFQ`/`POPFQ` and their 16-bit forms through
the virtual source stack. A flags push decrements virtual SP, captures the
executor's flags on its physical stack, and pops that word into the virtual
stack. A flags pop pushes the virtual word onto the physical stack, executes
the corresponding flags restore, and increments virtual SP. Both transfers
balance physical SP within the one lowered source instruction. Register-map
restoration and virtual-SP adjustments use flag-preserving instructions.

This is the explicitly selected executor-flags behavior. The lowering adds no
incoming-flags capture, waiter/executor flags comparison, context-bit filtering
or runtime instruction service. `POPFQ`/`POPF` apply the processor's ordinary
flag-write behavior on the executor. The opcode family is no longer rejected
as flags access by the optional instruction-policy utility. Other instruction
families retain their existing policy. The backend remains x86-64; the native
encodings have 64-bit or operand-size-prefixed 16-bit stack words; an effective
REX.W keeps the 64-bit form even with a 66 prefix. There is no 32-bit flags-stack
operation in this backend's 64-bit mode.

## Private packet layout

`kd_regs` layout 2 has 21 eight-byte fields, total 168 bytes:

| Offset | Field(s) |
| --- | --- |
| 0, 8, 16 | IP, SP, BP |
| 24, 32, 40, 48, 56 | R15, R14, R13, R12, R11 |
| 64, 72, 80, 88 | BX, R10, R9, R8 |
| 96, 104, 112, 120, 128 | AX, CX, DX, SI, DI |
| 136, 144, 152, 160 | orig_AX, CS, FLAGS, SS |

Under the optional original-task instruction image requirement, SS is private
storage for the remaining branch budget; it is never installed as a hardware
segment selector. Only that contract's FULL marker writes it. The runtime's
`KD_REG_ORIGIN_REENTRY_TAG` authorizes one flags/budget import at an exact
directory-listed successor; ordinary FULL CALL entries clear stale tag bytes.
`KD_REG_ORIGIN_SUFFIX_TAG` instead selects flags-aware native restoration after
an instruction that already executed. Neither tag changes source CALL words.

The packet is shared by waiter and combiner. Virtual R11..R15 use its backing slots;
there is no second wrapper GPR snapshot. The spin frame places its 40-byte core
header immediately before IP/SP/BP, filling one aligned cacheline. Its
`rwlock_admitted` bit shares the queue-tag byte; IP/SP/BP offsets remain 40/48/56.
Mutex has its own node packet layout. [Spin](design/spin_implementation.md) and
[mutex](design/mutex_implementation.md) document those enclosing objects.

## Wrapper inputs and directory

C supplies `kd_regs *` in RDI and a two-word `args` array in RSI. Batch callers also
supply their independent descriptor in RDX. Inputs are:

| Word | On entry | On return |
| --- | --- | --- |
| `args[0]` | Origin kernel GS base | Wrapper exit kind |
| `args[1]` | Logical waiter task | Body witness, 0 or 1 |

The body witness records whether execution entered generated body code. It does
not count instructions, and zero alone does not prove that no effects occurred.
Never use it to justify replaying a body that has made progress. Each continuation
restores its own inputs. The translator may skip loading GS or the task input only
if it proves the body does not use it; otherwise it loads both. The slots and
two-word ABI remain the same.

| Binary offset | Directory item |
| --- | --- |
| 0 | Ordinary C entry |
| 9 | `KDWB002` batch-layout tag |
| 16 | Legacy batch entry |
| 25 | `KDWC002` clobber-layout tag |
| 32 | Clobber entry |
| 41 | `KDAB` identity tag |
| 45 | Generated `entry_abi` byte |
| 46 | Image publication protocol: 2 for ordinary low-byte images; 3 for service-queue or retained-miss requirements at `10ef078a` |
| 47 | Low requirement byte: bits 0-5 retain the contracts described below; bit 6 original-task instruction service; bit 7 budget resumption |
| 48 | Protocol 3 only: full little-endian 32-bit requirement word, with a low byte matching offset 47 |

[`exe_info.h`](../include/exe_info.h) defines the complete requirement mask.
Bits 8-13 select the service queue, returning origin CALL, origin memory service,
origin context read, indirect tail and retained current-position miss contracts
respectively. The fixed directory remains in the first 48 bytes; protocol 3
uses the extended header. This image metadata does not add wrapper arguments.

There is a static discrepancy at `ebae17c1`: a cold ABI2 image can request bit 13
without service-queue bit 8, but `wrapper.S` and `kd_image_protocol()` select the
extended header only for bit 8. Protocol 2 accepts at most an eight-bit mask.
Thus selecting the new requirement in the translator does not establish that
such a cold image can encode and publish it correctly. This was reported to
the implementation owner. Checkpoint `10ef078a` makes both the wrapper and
`kd_image_protocol()` choose protocol 3 for bit 8 or bit 13 and adds a bit-13-only
upload/bind fixture. This corrects the source discrepancy; fresh validation of
the generated/uploaded-header round trip remains pending.

Layout-1 images cannot be published NORMAL. Ordinary offset 0 preserves the C ABI.
Offset 16's adapter preserves physical RBP; offset 32 preserves it in the wrapper.
Both batch entries allow the compiler to protect live combiner values and stay
inside one C batch loop. Neither is callable as an ordinary C function pointer.
Historical direct-string images accept only the clobber entry at offset 32 with a pristine
MINIMAL packet; their ordinary and legacy entries deliberately reject execution.

The separate 16-byte `KD_JIT_CAPS` ioctl reports version 13. Bits 0 and 1 describe
the checked mutex stack bound and static module per-CPU range; bits 3 and 4
advertise immutable mutex images and exclusive KD mutex objects. Bits 5 and 6
support mutex instruction exits and checked spin address exits. Bits 7 and 8
identify the original `strcmp` and `strscpy_pad` APIs. Version 10 adds bit 9:
these APIs use the native caller's argument and memory-lifetime guarantees,
without helper instruction checks, data scans or destination-bound rechecks.
Historical string-service images require bit 9 plus the appropriate API bit.
Current string translation uses ordinary decoded CALL/RET and selects no string
service or direct-call requirement, regardless of these compatibility bits.
Optional bit 10 permits direct original-helper calls within one wrapper
invocation. Such images add requirement bit 4, value 16, to the API requirement:
20 for `strcmp`, 24 for `strscpy_pad`, or 28 for both. The feature is absent if
the provider cannot allocate suitable executable storage or the kernel enables
call-depth tracking, whose additional call accounting this bridge does not
implement. That fallback describes the historical direct-string ABI; current strings
always use ordinary translation instead of either named string route.

Bit 11 separately enables pristine ABI1/3 root instruction exits. These images
require exactly bits 0 and 5 (value 33), immutable storage and the MINIMAL
clobber entry. Their regular and batch directories refuse execution.

Optional bit 12 (`KD_JIT_CAP_INDIRECT_CALL`) extends version 12 with the distinct
FULL near-indirect-CALL exit 11. The translator must negotiate that bit on its
current device lease; version 12 alone does not imply support. Providers without
the bit retain the older unresolved-IJ behavior. No packet field, wrapper word
or image requirement is added; new provider and translator inputs are frozen
and synchronized together for this candidate.

Version 13 bit 13 (`KD_JIT_CAP_ORIGIN_INSTRUCTION`) adds exit 12 for ABI2 mutex images
with exactly requirement bits 0 and 6 (value 65). Their immutable `KDOS0001`
footer has a 32-bit directory offset and count, followed by no other data. Up
to 64 32-byte rows contain source IP, source successor IP, generated successor
offset, one-byte kind and length, two zero reserved bytes and eight padded
opcode bytes. Kinds 1/2/3 mean exact RDTSC/RDTSCP/CPUID. Publication validates
source bytes and pins both source boundaries; runtime matches the current marker
and retained owner before executing. Other instruction/context intervals retain
the suffix path. Prepared rwsem writers retain their reader-excluding reservation
around this same ABI2 gate-mutex transaction; reads never delegate.
The [candidate contract](design/kernel_cs_semantics.md#bounded-original-task-instruction-service-candidate)
states pending correctness and performance gates.

Ordinary images accept compatible versions 5 through 13. Optional image
requirements still need their corresponding capabilities. Bit 9 adds no image
requirement or packet field: image bit 0 alone remains mutex ABI2 only; its
pair with bit 5 is restricted to spin ABI1/3. Image bits 1, 2, 3 and 4 remain
spin ABI1 only. Unknown requirements or mismatched backend/ABI
combinations are refused.

The private `kd_jit_batch_call` descriptor is now 112 bytes. Its original
96-byte prefix is unchanged; two eight-byte result fields at offsets 96 and
104 count completed direct `strcmp` and `strscpy_pad` calls. Only a direct-call
image initializes or exports them. The successful batch or its pending
dispatcher consumes the counts once. They neither extend `args[2]` nor change
the body witness, register packet, lock ownership or mutex protocol.

Historical direct-string images end with a `KDNC0001` relocation directory: a 16-byte footer and
up to 64 16-byte rows naming the generated CALL offset, service and original
return address. The uploaded CALL has a zero displacement. Before immutable
publication the provider fills its signed 32-bit relative displacement to the
resolved original helper and retains helper/return-source residency. These are
generated-image checks, not helper or source-CALL inspection. The uploaded
`jit.bin` hash therefore differs from the loaded executable image. Outside
timing, the runner saves the loaded bytes and receipt and reconstructs the
expected changes using captured symbol addresses. See
[direct-call admission](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/admission.md#direct-original-helper-calls).

## Physical and virtual registers

| Physical resource | Role |
| --- | --- |
| RSP/RBP | Executor's wrapper frame, never the logical waiter stack |
| R11 | Authoritative packet base |
| R12 | Logical BP |
| R13 | Logical SP |
| R14 | Logical RIP/control target scratch |
| R15 | Indirect-jump/exit scratch |
| Other GPRs | Corresponding logical registers while resident |

The physical registers belong to the running executor. The logical registers are
the values the original waiter should see. [conflict.py](../disassem/conflict.py)
rewrites uses of reserved registers through the mapping above and packet storage,
including partial-register accesses. A logical R11..R15 value need not be in the
same-named physical register. CALL/RET translation must also use the logical SP/BP
and save or reload reserved-register values as required.

A physical scratch slot with an empty logical mapping has no value to spill.
In particular, a GS/RIP operand may temporarily borrow the physical SP register:
save logical SP, materialize source next-IP, execute the operand, release IP,
then reload logical SP. Releasing IP empties the mapping; stable recovery must
not emit a store for that empty slot or overwrite the saved SP with temporary
IP. Dirty virtual GPRs still require their ordinary packet stores.

The wrapper keeps its existing 176-byte frame plus the incoming CALL word.
A direct-call entry additionally rounds physical SP down to a 16-byte boundary
once, before generated code. All named slots and restoration stay BP-relative:

| Relative to physical RBP | Slot |
| --- | --- |
| -48, -56 | Packet pointer, args pointer |
| -64 | Per-invocation block budget |
| -72, -80 | Remaining direct `strcmp` and padding-call allowances |
| -88, -96 | Reserved; direct calls need no per-call SP or flags scratch |
| -120, -128 | Origin GS base, logical task |
| -136, -144 | Logical RIP scratch, exit/indirect value |
| -152 | Body witness |
| -160, -168 | Legacy batch descriptor, clobber descriptor |

The direct-call allowances occupy previously reserved slots.
Other words remain reserved to preserve offsets. `Stack_RSP/RBP/R11..R15` macros
refer to packet fields, not another copy on the physical stack. Allocation precedes
stores; kernel code never relies on the red zone.

GS lowering adds the pinned origin base. Supported current_task loads use logical
task input. Hardware GS, current, IRQ, RCU and scheduler context are not switched;
native services still run on the physical executor. Production assumes the
source context contract; [translation policy](design/admission.md) distinguishes
that trust from the optional checked analyzer and supported lowering.

## CALL, completion and exits

A virtual CALL writes its source return token at SP-8. Ordinary misses preserve
that word for the original callee; known controls and typed services advance it
only after successful handling. Registered post-CALL continuations form the JIT
dispatch set. An ordinary CALL miss resumes natively without returning to this
invocation's JIT.

KD can finish directly at the body's final unlock only after checking the exact
backend endpoint, outer lock identity, completion eligibility and resume state.
The two forms of the register proof are:

| Form | Required values |
| --- | --- |
| Ordinary check after CALL | RSI=R13+8, RDX=the return word, RCX=R12 |
| Fused clobber check before CALL | RSI=R13, RDX=the statically known post-CALL address, RCX=R12 |

The fused form checks the same continuation without storing and rereading a
virtual return word. If it fails, KD constructs the original CALL exactly once
and enters FULL handling. Unknown endpoints, nonterminal unlocks and legacy images
keep ordinary CALL handling.

ABI3's body releases its writer byte before this spin endpoint. Pre-body refusal
can cancel native writer admission, but COMPLETE and progressed native handoff
must not issue a second count release. Packet state and writer ownership are
separate obligations; materializing FULL releases neither admission nor the gate.

| Wrapper exit | Meaning |
| --- | --- |
| 1 CALL_MISS | Control, terminal unlock or untranslated ordinary call |
| 2 IJ_MISS | Unresolved indirect target |
| 3 ERROR_INST | Unsupported/faulted execution |
| 4 INST_LIMIT | Block budget exhausted |
| 5 HOSTCALL | Allowlisted typed service |
| 6 ENTRY_REFUSED | Predicate failed before body execution |
| 7 CLOBBER_COMPLETE | Body reached the validated final unlock using the minimal completion packet |
| 8 NATIVE_ESCAPE | Validated instruction marker; resume the waiter at the original instruction for this invocation's native suffix, preserving later eligibility |
| 9 ADDRESS_GUARD | Checked ABI1 spin load would overlap recorded stack writes; resume the waiter before that load and disable future delegation |
| 10 DIRECT_CALL_LIMIT | Direct helper allowance exhausted before that helper executes; preserve its pending CALL word and finish on the original waiter |
| 11 INDIRECT_CALL | Negotiated near indirect CALL miss; IP holds the actual target, `orig_ax` temporarily holds the exact source CALL address, and SP points at its real source return word |
| 12 ORIGIN_INSN | Negotiated exact RDTSC/RDTSCP/CPUID marker; IP is the unexecuted instruction, FLAGS holds arithmetic state, and SS holds remaining block budget |
| 13 ORIGIN_MEMORY | Declared original-task memory-instruction service, with no new source CALL word; the exact retained transaction governs return |
| 14 INDIRECT_TAIL | Negotiated near indirect JMP; FULL IP is the target, `orig_ax` names the source JMP and source SP is unchanged |
| 15 RETAINED_MISS | Negotiated generic IJ/RET/JMP miss; FULL IP/SP describe the already selected target and post-transfer stack, and `orig_ax` is the source next-PC |

Wrapper values in `exe_info.h` differ from C dispatcher results in `exe.h`.
COMPLETE stores only IP/SP/BP; FULL stores current logical GPRs before C reads them.
Entry refusal preserves MINIMAL. Legacy IJ miss dispatch may return the actual
source next-PC in `args[0]`, rather than the registry's literal `KD_EXE_IJ_MISS`
status value. The daemon receives the separate generation-scoped source/target
report. C results include `KD_EXE_RUN_ERROR = 3`, `KD_EXE_RUN_TO_UNLOCK = 4`,
`KD_EXE_RUN_NATIVE = 6` and the candidate `KD_EXE_RUN_HANDOFF = 16`. Numeric
values from these domains are not interchangeable.

Generic fault, legacy untyped IJ and budget errors are not arbitrary recovery
boundaries. The negotiated current-position packet is a separate contract:
CALL pushes and RET pops already performed by generated code remain committed.
Ordinary frames can enter the existing native handback. The retained worker's
consumer was absent at `10ef078a` and is wired at `a6fe0bb2`, with full owner
routing and packet acceptance. Four generated-miss tests pass in its first
frozen receipt; they do not validate central acceptance/final-ACK execution or
loaded-provider custody transfer.

Exit 11 is emitted only after evaluating an actual indirect CALL target before
its virtual push. The provider verifies canonical optional-REX `FF /2` bytes,
the exact next IP/stack word, FULL packet/frame identity, pending phase and
source leases before handing the suffix to the original waiter. `orig_ax` is
cleared before restore. Exact listed Native/context targets do not request
learning or disable the image; an unknown ordinary target records only the
proved CALL edge for a future image. RET/JMP misses are outside this specific
exit-11 contract; candidate exit 15 adds a distinct negotiated post-transfer
packet for them. Noncanonical CALL encodings do not gain support from that
distinction. The existing C-call flags convention is unchanged, and native
suffix execution does not return to JIT in this invocation. Ordinary GS operands
continue to use saved-origin lowering; exit 13 is limited to its declared
instruction transaction, not every GS-prefixed instruction.

Services `ktime_get`, `ktime_get_ns` and `int_sqrt` have typed argument/result,
clobber and no-waiter-memory-write contracts. Their actual virtual return-slot
write remains emitted. Optional checked mode also models it in alias analysis.

The selected narrow `kd_service_write_owned(object, task)` proof uses the existing
two-argument, word-result `KD_SERVICE_CALL_ATOMIC_ORIGIN` service descriptor.
O executes only that runtime proof while E is suspended; E resumes its same
immutable image after the exact service ACK. Task/token/owner and context checks
remain required. `BALANCED_ORIGIN` is not selected for this interval because it
rejects retained spin/RCU state. Preparation rejection is fail-stop rather than
automatic native handback. Other service descriptors stay unchanged; the public
query bodies remain ordinary JIT code under the
[operation-based policy](design/admission.md#selected-rwsem-state-queries).
This selection adds no wrapper argument or packet layout. `a6fe0bb2` commits
the descriptor/registration and passes the writer-query component fixture with
supplied runtime observations. The query-image group passes six cases at
`da55414f`, after repairing the legal continuation-label assertion. It uses
synthetic source bodies with the original image backend; actual public query
bodies and the O/E service/ACK path still require live execution.

Current strings use ordinary decoded CALL/RET and actual virtual return words,
without a named service, memory summary, quota or direct native bridge. The
provider retains historical string capability/image fields for compatibility;
their full former calling and relocation contracts are in the
[fixed ABI checkpoint](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/JIT_REGISTER_ABI.md#call-completion-and-exits).
Those fields do not enable helper-specific handling in current translation.

## Native continuation and final restore

Legacy native entry decodes RBX, R12..R15, RBP and the return IP from the saved
callee-saved/CALL stack; caller-saved incoming values are unspecified. Shared child
frames alias the root packet. Native owner state and continuation/ACK metadata
remain independently live.

Supported PENDING CALLs may resume the original callee without replaying prior
stores. Post-acquisition spin and checked mutex STACK_CHANGED exits have distinct
validated tags and post-CALL packets; they cannot execute the completed control
again. The mutex checkpoint compares 256 live caller-stack bytes and exact token,
IP and SP across one local control. Changed memory remains changed.

The waiter loads COMPLETE's triple or FULL's software packet before releasing node
or continuation storage. Spin reads all fields before reclaiming its root and
unpinning. Mutex FULL keeps an independent restore copy because the node can be
reused after unpin; its ACK/task references must outlive the native suffix.
[Frames](design/frames.md) and [locking](design/locking.md) define the exact order.

For the selected retained-worker handback, O copies the packet and completion
fields before its acceptance ACK and performs no later root/frame access. That
ACK can precede E's recursive unwind. E's selected synchronous home-CPU cleanup
therefore publishes pooled-slot reuse only after its own final references end;
see [retirement ordering](design/lifetimes.md#selected-retained-handback-retirement).
Waiter-side final-use ACK/pinning simplification remains later work. This
sequence is committed. The `da55414f` production service join passes three
modes with supplied task/physical primitives and manually represented recursive
unwind; root storage remains accessible until thread joining. Separate retirement
components pass four positive modes and nine rejections with supplied CPU/work
APIs. Saved-state restore also passes its limited arithmetic-flag/GPR/SP cases,
including a configured-thunk substitute. None closes general flags/SIMD or
IRQ/NMI coverage, real CPU hotplug or loaded-provider execution. The
[current evidence](design/kdlock_lock_replacement_contract.md#current-focused-component-results)
preserves the first query failure and retirement compile failure separately.

### Checked instruction exit

For mutex entry ABI2, an image can replace a reviewed processor instruction with
a marker: generated code that saves current state and returns exit 8 before that
instruction executes. The image declares requirement bit 0, and the provider must
advertise capability version 6 through 13 with `KD_JIT_CAP_NATIVE_ESCAPE` (bit 5).
The [instruction policy](design/admission.md#checked-instruction-exits) lists the
exact eligible instructions, retained protocol restrictions and optional
checked-mode source proofs. Trusted production assumes the source input contract.

The marker captures the original instruction address, logical SP/BP, all current
GPR slots and arithmetic flags. These flags describe carry, parity, auxiliary
carry, zero, sign and overflow; their combined mask is `0x8d5`. Checked mode
proves defined source inputs before the marker; production assumes that contract.
Generated entry dispatch, block-budget checks, indirect-target lookup and
LEA-to-MOV/ADD rewriting preserve arithmetic flags for all images. This does not
make the FLAGS field of ordinary FULL packets generally valid or add captured
entry flags.

The runtime validates the image, packet, source instruction, stack bounds and
ownership state. It tags `orig_AX` with `KD_REG_NATIVE_ESCAPE_TAG`, retains the
existing native-continuation ownership obligations, and leaves registry status
untouched. An older retained image can finish without changing a newer image's
generation or eligibility. The marker never writes `NORMAL`, so an independently
disabled entry stays disabled. Existing immutable-image residency, source leases,
native unlock ACK and frame retirement protect this continuation; persistent
eligibility adds no same-invocation native-to-JIT return bridge.

The original waiter restores current GPRs and merges only the saved arithmetic
flags into its own processor flags after all C cleanup and scheduling helpers.
It keeps its own interrupt-enable, direction and access-control flags. Execution
then resumes at the original instruction, without replaying earlier stores, and
the rest of this invocation remains native. Final unlock acknowledgements and
frame retirement still follow the existing mutex protocol. The two-word wrapper
interface and 168-byte packet do not grow.

ABI1 spin and ABI3 rwlock writers have a separate root-only contract negotiated
by version 12 `KD_JIT_CAP_ROOT_NATIVE_ESCAPE` (bit 11). The exact requirement pair
is 33. Both entry paths check a pristine physical root before execution; the
generated dispatcher admits only that entry. A FULL marker must retain one
unreleased queue owner and, for ABI3, writer admission. Only a published
`NATIVE_READY` result from this image can interpret the instruction tag during
spin restoration. Ordinary images and normal FULL completions may contain
stale `orig_ax` bytes and never select that path. Non-marker native CALL exits
clear the tag.

The flags-aware spin restore requires mode 2 and leaves its acquisition pin and
continuation storage live for final unlock ACK; it neither retires nor unpins
before resuming. The same two-word scratch bound and arithmetic-only merge
apply. Mode-3 or nested marker relay is outside this contract. This does not
change ABI2 nesting or ordinary spin/rwlock packet restoration.

The read-only `native_escape_count` module parameter counts validated markers.
It is diagnostic evidence, not an ownership record. Publication, a marker count,
a returned JIT body and complete drain remain distinct observations.
The conditional live probe keeps one image through cold → taken → cold → taken
phases: both cold phases require returned JIT bodies, and both taken phases
require native markers plus exact final effects and drain. The original sticky
marker-disable results remain evidence for their frozen historical sources.

### Checked spin address exit

This image contract remains available to the optional checked analyzer and
historical images. Production trusted translation does not run address analysis
or select these guards; the runtime compatibility contract below is unchanged.

ABI1 spin images may check a restricted 64-bit `MOV` pointer load for overlap
with recorded source-stack writes. Such images set requirement bit 1 and require
provider version 7 through 12 with `KD_JIT_CAP_ADDRESS_GUARD` (bit 6). This is distinct from
the mutex instruction marker. The [admission guide](design/admission.md#checked-spin-pointer-loads)
defines the address and source flag proofs. The
[historical address-check probe](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
passed successful delegation, exact native resumption after a failed check and
continued local execution after delegation was disabled. That receipt belongs
to the earlier frozen inputs. The v10 dispatcher implementation also passed the
probe in [candidate 6](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/VALIDATION.md#taskname-and-xattr-helper-validation).
An image that required source constant-branch simplification cannot also obtain
address-check admission: the simplified graph could omit a flags read still
present in the original native suffix. Bodies requiring both remain refused.

The image ends with a bounded directory containing at most 64 site records.
Each 32-byte record contains the original eight-byte instruction address, a
one-byte instruction length, proof kind 1, six reserved zero bytes and 16 bytes
holding the opcode followed by zero padding. The final 16-byte footer contains
`KDAG0001`, a four-byte directory offset and a four-byte record count. These are
x86-64 little-endian fields, not pointers to userspace storage. Publication checks
the directory bounds, unique source addresses, supported MOV encoding with the
REX.W prefix that selects a 64-bit operand, source residency and exact source
bytes. The encoding permits one base register
with an optional displacement, including stack-base encoding, but no index,
segment override, RIP-relative address or absolute address.

Publishing an address-check or typed string-service image makes that spin entry use immutable versions from
then on. Later recompilations cannot overwrite an active frame's code or site
directory, even when a later image has no optional checks or services. Old versions remain until
source-session teardown. This does not convert all ordinary spin or ABI3 rwlock
entries to immutable publication.

A failed check occurs before its load. Generated code materializes FULL with
the exact source IP/SP/BP and current logical registers, stores
`0x4b44414700000000 | site_index` in `orig_AX`, and returns exit 9. The runtime
requires a matching immutable ABI1 image, one outer physical lock in a root
frame, no pending nested/native/remote operation, and the exact directory token,
source PC and unchanged opcode. The logical SP must leave four words below it
and one live word at it within the waiter's kernel stack. Invalid state or a
generic execution fault remains an error.

After validation the runtime clears `orig_AX`, saves the continuation and
permanently disables the stable entry for this source session under the image
publication gate. The original waiter restores the full packet and resumes the
same MOV with the same logical SP, without consuming a CALL word or replaying
earlier effects. Existing physical ownership, unlock acknowledgements and frame
retirement remain in force. Arithmetic flags are not restored on this path:
the translator must prove every incoming arithmetic flag is overwritten before
the source reads it. Passing checks preserve flags around their comparisons.
The read-only `address_guard_count` parameter counts validated continuations;
it does not prove body completion or replace an ownership record.

This contract does not admit ABI3 rwlocks, nested spin continuations or arbitrary
memory operations. General address/object validation, processor-flag repair,
floating-point/vector state and hardware segment restoration remain outside it;
see [open contracts](TODO.md).

## Change checklist

- Keep C offsets, wrapper slots and Python lowering synchronized; inspect final JIT bytes.
- Preserve the backend/ABI/layout checks and two-word inputs on every continuation.
- Materialize FULL before generic C consumes GPRs; do not treat backing slots as entry capture.
- Preserve the virtual CALL/token except for an equivalently checked fused completion.
- Keep frame pop, physical ACK, storage reclamation and final pin release separate.
