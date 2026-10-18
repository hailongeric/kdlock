# Translator

The translator reads kernel machine code while holding a source lease, which
keeps the source modules loaded. It selects the code a JIT invocation can reach,
checks whether that code is supported, rewrites uses of the caller's registers,
and emits assembly and a wrapper image.
Use [the daemon](../daemon/README.md) for publication and
[the project guide](../docs/PROJECT_GUIDE.md) for guest dependencies.
JIT means just-in-time compilation; ABI means application binary interface.
The [terminology guide](../docs/TERMINOLOGY.md) explains execution-state terms.

| Read first | Responsibility |
| --- | --- |
| [disassem.py](disassem.py) |CLI, input coordination, assembly/link and diagnostics |
| [instruction_policy.py](instruction_policy.py) | Scalar instruction, hardware-register and raw-encoding admission |
| [native_escape.py](native_escape.py) | Reviewed mutex instruction markers, scalar input/output proof and terminal generated paths |
| [translation_scope.py](translation_scope.py) | Decode windows, selected blocks and CALL continuations |
| [translation_image.py](translation_image.py) | Dispatch targets and generated assembly |
| [context_policy.py](context_policy.py), `context_symbols.py` | Backend/context screening and static ranges |
| `context_values.py`, `context_registers.py`, `context_memory.py` | Bounded flow, register facts and sequential memory/alias model |
| `context_guards.py`, `entry_abi.py` | Entry predicates and MINIMAL input-dependency proof |
| `conflict.py`, `normal.py`, `special_inst.py`, `hostcall.py` | Virtual register/instruction/control lowering |
| `device_session.py`, `memread.py` | Same-device lease, capabilities and source pinning |

[Admission](../docs/design/admission.md) defines supported scope and refusal.
[Register ABI](../docs/JIT_REGISTER_ABI.md) defines packet fields, register mapping,
CALL tokens and COMPLETE/FULL. `solve_bug.py` contains narrow, actively called
encoding/assembly corrections; it is not an obsolete standalone driver.

Entry identities are legacy 0, spin clobber 1, mutex clobber 2 and rwlock writer
clobber 3. ABI3 uses the spin backend and IP/SP/BP packet; native code acquires
writer admission before the translated body. The body still passes the existing
memory/context checks and releases its writer byte before spin completion.
This admits the current RCUHT writer without translating reader-drain atomics;
it does not resolve the general dynamic-pointer screening gap.

KD-only mutex translation requires exclusive KD objects and immutable images
(capability v5 or v6). Checked instruction markers additionally require v6 bit 5.
Linux mutex APIs, their compiler clones and the old kernel
mutex bridge are refused. Ordinary KD return-valued or task-sensitive locking
APIs remain local; explicit clobber entries supply delegation. See the
[object/API contract](../docs/design/kd_only_mutex.md).

Install [the pinned requirements](requirements.txt) in a guest Python virtual
environment. The translator command uses positional arguments:
`python3 disassem/disassem.py PID ENTRY_HEX [LOCK_KIND] [ABI]`, where PID is the
process identifier, ENTRY_HEX the hexadecimal entry address, and LOCK_KIND the
lock backend. Real-text command-line use acquires its own device lease and does
not by itself upload a published image. Importing helpers
for byte fixtures does not establish actual kernel JIT evidence.

The translator does not check every memory address when it is used or restore all
processor state. Reviewed mutex instructions can end generated execution with a
checked marker; the waiter then executes the instruction and future delegation
of that entry is disabled. Other unsupported state still fails static admission.
See [the exact policy](../docs/design/admission.md#checked-instruction-exits).
Mutex images use separate immutable versions; spin/rwlock images remain in place.
Access-time guards and general state restoration remain deferred. Its context
checks are not a security sandbox; see
[known limitations](../docs/TODO.md).
