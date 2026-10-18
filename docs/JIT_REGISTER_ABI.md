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
snapshot or FULL state. Admission rejects code that uses uncaptured initial bits
in a value, address, store or branch.

At clobber controls, analysis discards old register facts except SP/BP. It retains
facts about saved stack values only when alias analysis or entry guards prove
them. If the analysis budget runs out, the entry is refused before execution.

### Mutex clobber and outer cookie

Ordinary direct mutex uses ABI2. The outer paired interface first attempts to
acquire the KD object's physical owner word in the caller. A successful atomic
compare-and-exchange records the exact task owner in an opaque same-task cookie;
its matching unlock calls `kd_mutex_local_unlock`. Linux mutex objects do not
participate in this ownership protocol.
The contended outer entry returns an exact native owner only before taking a KD
reference/gate; entry into the KD queue returns zero. The separate JIT continuation
defines zero before writing the cookie, so MINIMAL never depends on incoming RAX.

Nested translated operations keep `KD_MUTEX_DIRECT_LOCK/UNLOCK`. Ordinary aliases
use local KD physical locking; they do not restore a Linux-mutex backing object.
Interruptible, killable, I/O-related, trylock and explicit nested interfaces keep
their documented contracts. See
[mutex routing](design/locking.md#mutex-outer-direct).

## Private packet layout

`kd_regs` layout 2 has 21 eight-byte fields, total 168 bytes:

| Offset | Field(s) |
| --- | --- |
| 0, 8, 16 | IP, SP, BP |
| 24, 32, 40, 48, 56 | R15, R14, R13, R12, R11 |
| 64, 72, 80, 88 | BX, R10, R9, R8 |
| 96, 104, 112, 120, 128 | AX, CX, DX, SI, DI |
| 136, 144, 152, 160 | orig_AX, CS, FLAGS, SS |

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
| 46 | Image publication protocol version, currently 2 |
| 47 | Required runtime features; bit 0 means instruction-exit support |

Layout-1 images cannot be published NORMAL. Ordinary offset 0 preserves the C ABI.
Offset 16's adapter preserves physical RBP; offset 32 preserves it in the wrapper.
Both batch entries allow the compiler to protect live combiner values and stay
inside one C batch loop. Neither is callable as an ordinary C function pointer.

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

The wrapper reserves the same 176-byte frame plus its CALL word across entries:

| Relative to physical RBP | Slot |
| --- | --- |
| -48, -56 | Packet pointer, args pointer |
| -64 | Per-invocation block budget |
| -120, -128 | Origin GS base, logical task |
| -136, -144 | Logical RIP scratch, exit/indirect value |
| -152 | Body witness |
| -160, -168 | Legacy batch descriptor, clobber descriptor |

Other words remain reserved to preserve offsets. `Stack_RSP/RBP/R11..R15` macros
refer to packet fields, not another copy on the physical stack. Allocation precedes
stores; kernel code never relies on the red zone.

GS lowering adds the pinned origin base. Supported current_task loads use logical
task input. Hardware GS, current, IRQ, RCU and scheduler context are not switched;
native services still run on the physical executor. [Admission](design/admission.md)
sets the permitted context boundary.

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
| 8 NATIVE_ESCAPE | Checked mutex instruction marker; resume the waiter at the original instruction and disable future delegation |

Wrapper values in `exe_info.h` differ from C dispatcher results in `exe.h`.
COMPLETE stores only IP/SP/BP; FULL stores current logical GPRs before C reads them.
Entry refusal preserves MINIMAL. Generic fault, IJ-miss and budget errors are not
arbitrary native-recovery boundaries.

Services `ktime_get`, `ktime_get_ns` and `int_sqrt` have typed argument/result,
clobber and no-waiter-memory-write contracts. Their virtual return-slot write still
participates in alias analysis; future services do not inherit that summary.

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

### Checked instruction exit

For mutex entry ABI2, an image can replace a reviewed processor instruction with
a marker: generated code that saves current state and returns exit 8 before that
instruction executes. The image declares requirement bit 0, and the provider must
advertise capability version 6 with `KD_JIT_CAP_NATIVE_ESCAPE` (bit 5).
The [instruction policy](design/admission.md#checked-instruction-exits) lists the
exact eligible instructions and the static checks that still apply.

The marker captures the original instruction address, logical SP/BP, all current
GPR slots and arithmetic flags. These flags describe carry, parity, auxiliary
carry, zero, sign and overflow; their combined mask is `0x8d5`. Source analysis
requires their values to be defined before the marker. For images with markers,
entry dispatch, block-budget checks, indirect-target lookup and address-generation
rewrites preserve these flags. This is a separate contract from ordinary FULL
packets, whose FLAGS field is not generally valid.

The runtime validates the image, packet, source instruction, stack bounds and
ownership state. It tags `orig_AX` with `KD_REG_NATIVE_ESCAPE_TAG`, retains the
existing native-continuation ownership obligations, and marks the entry
`NATIVE_ONLY` under the same serialization gate used by image publication.
Even an older retained image disables the stable entry. Already admitted work
may finish; no new delegation is admitted after the disable takes effect.
The disable lasts until the source session is retired, not across source reloads.

The original waiter restores current GPRs and merges only the saved arithmetic
flags into its own processor flags after all C cleanup and scheduling helpers.
It keeps its own interrupt-enable, direction and access-control flags. Execution
then resumes at the original instruction, without replaying earlier stores, and
the rest of this invocation remains native. Final unlock acknowledgements and
frame retirement still follow the existing mutex protocol. The two-word wrapper
interface and 168-byte packet do not grow.

The read-only `native_escape_count` module parameter counts validated markers.
It is diagnostic evidence, not an ownership record. Publication, a marker count,
a returned JIT body and complete drain remain distinct observations.

### Deferred access-time continuation

Checking arbitrary memory addresses immediately before each access remains
unimplemented. The instruction marker does not add those checks or make generic
faults resumable. General processor-flag repair, floating-point/vector state and
hardware segment restoration remain outside this contract; see
[open contracts](TODO.md).

## Change checklist

- Keep C offsets, wrapper slots and Python lowering synchronized; inspect final JIT bytes.
- Preserve the backend/ABI/layout checks and two-word inputs on every continuation.
- Materialize FULL before generic C consumes GPRs; do not treat backing slots as entry capture.
- Preserve the virtual CALL/token except for an equivalently checked fused completion.
- Keep frame pop, physical ACK, storage reclamation and final pin release separate.
