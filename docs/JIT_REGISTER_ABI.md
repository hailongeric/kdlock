# JIT register and wrapper ABI

The ABI connects direct callers, the private KD packet, generated code, C recovery
and final waiter restoration. [kd_regs.h](../include/kd_regs.h),
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

Direct clobber calls pass lock in RDI, pre-CALL RSP in RSI, post-CALL RIP in RDX
and caller RBP in RCX. The compiler spills live clobbered values; the provider does
not save all incoming GPRs. Named continuations belong to one noipa workload function.
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

Backing slots written by generated code do not turn a MINIMAL packet into a valid
entry snapshot or FULL state. Admission rejects any observation of uncaptured
initial bits in values, addresses, stores or branches. Clobber controls discard
old non-SP/BP input facts; permitted stack-spill facts require actual alias/guard
proof. Budget exhaustion refuses before execution.

### Mutex clobber and outer cookie

Ordinary direct mutex uses ABI2. The outer paired API first attempts Linux's native
owner CAS in the caller. A native acquisition stores its exact task owner in an
opaque same-task cookie; its matching unlock calls original `mutex_unlock`.
The contended outer entry returns an exact native owner only before taking a KD
reference/gate; entry into the KD queue returns zero. The separate JIT continuation
defines zero before writing the cookie, so MINIMAL never depends on incoming RAX.

Nested translated operations keep `KD_MUTEX_DIRECT_LOCK/UNLOCK`. Retained kernel
bridge aliases use generic FULL control handling. Special interruptible/killable/IO,
trylock and explicit nested APIs keep their original contracts. See
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

The witness means a generated body was entered; it is not an instruction count or
proof that no effects occurred. Never use it to replay a progressed invocation.
Each continuation reinstalls its inputs. Translation may omit a proven-unused GS
or task import; uncertain images retain both. Slots and the two-word ABI stay fixed.

| Binary offset | Directory item |
| --- | --- |
| 0 | Ordinary C entry |
| 9 | `KDWB002` batch-layout tag |
| 16 | Legacy batch entry |
| 25 | `KDWC002` clobber-layout tag |
| 32 | Clobber entry |
| 41 | `KDAB` identity tag |
| 45 | Generated `entry_abi` byte |

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

[conflict.py](../disassem/conflict.py) lowers logical uses of reserved registers
through the map/backing packet, including partial-register semantics. Translated
instructions must not assume logical R11..R15 live in their namesake physical GPRs.
SP/BP substitutions and special-register spill/flush also apply to CALL/RET lowering.

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

Terminal completion requires the exact backend unlock, outer lock identity,
completion eligibility and continuation triple. The ordinary post-CALL proof checks
RSI=R13+8, RDX=the return word and RCX=R12. A fused terminal clobber CALL checks the
equivalent pre-CALL RSI=R13, static post-CALL RDX and RCX=R12. Success skips the
return-word store/read; failure constructs the original CALL exactly once and
enters FULL. Unknown/nonterminal endpoints and legacy images retain ordinary CALLs.

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

### Deferred access-time continuation

Runtime address guards and a pre-instruction native exit are unimplemented.
A future exit must preserve current logical state, completed effects, real owners,
source lifetime and required condition flags, then resume that exact instruction.
Entry refusal or generic fault cannot be repurposed after progress. Current packet
FLAGS do not supply reliable live processor flags; SIMD/FPU and hardware segment
state are also outside complete restoration. See [open contracts](TODO.md).

## Change checklist

- Keep C offsets, wrapper slots and Python lowering synchronized; inspect final JIT bytes.
- Preserve the backend/ABI/layout checks and two-word inputs on every continuation.
- Materialize FULL before generic C consumes GPRs; do not treat backing slots as entry capture.
- Preserve the virtual CALL/token except for an equivalently checked fused completion.
- Keep frame pop, physical ACK, storage reclamation and final pin release separate.
