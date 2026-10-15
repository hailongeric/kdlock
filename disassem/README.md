# Translator

The translator reads kernel machine code while holding a source lease, which
keeps the source modules loaded. It selects the code a JIT invocation can reach,
checks whether that code is supported, rewrites uses of the caller's registers,
and emits assembly and a wrapper image.
Use [the daemon](../daemon/README.md) for publication and
[the project guide](../docs/PROJECT_GUIDE.md) for guest dependencies.

| Read first | Responsibility |
| --- | --- |
| [disassem.py](disassem.py) | CLI, input coordination, assembly/link and diagnostics |
| [translation_scope.py](translation_scope.py) | Decode windows, selected blocks and CALL continuations |
| [translation_image.py](translation_image.py) | Dispatch targets and generated assembly |
| [context_policy.py](context_policy.py), `context_symbols.py` | Backend/context screening and static ranges |
| [instruction_policy.py](instruction_policy.py) | Scalar instruction/operand admission and processor-state encoding refusals |
| `context_values.py`, `context_registers.py`, `context_memory.py` | Bounded flow, register facts and sequential memory/alias model |
| `context_guards.py`, `entry_abi.py` | Entry predicates and MINIMAL input-dependency proof |
| [origin_policy.py](origin_policy.py) | Exact audit, allowed operations and bounded origin-GS body proof for owned mutex images |
| `conflict.py`, `normal.py`, `special_inst.py`, `hostcall.py` | Virtual register/instruction/control lowering |
| `device_session.py`, `memread.py` | Same-device lease, capabilities and source pinning |

[Admission](../docs/design/admission.md) defines supported scope and refusal.
[Register ABI](../docs/JIT_REGISTER_ABI.md) defines packet fields, register mapping,
CALL tokens and COMPLETE/FULL. `solve_bug.py` contains narrow, actively called
encoding/assembly corrections; it is not an obsolete standalone driver.

Entry ABIs are spin full-context 0, spin clobber 1, owned mutex clobber 2, rwlock writer
clobber 3 and owned mutex ordinary C 4. ABI4 uses owned lock kind 3, late capture
of IP/SP/BP and nonvolatile registers, and a distinct completion path that restores
updated values. Caller-saved inputs must be defined before use. It shares the
two-word wrapper input and existing FULL recovery contract; see
[the owned ABI](../docs/JIT_REGISTER_ABI.md#owned-mutex-ordinary-c-entry).

ABI3 uses the spin backend and IP/SP/BP packet; native code acquires
writer admission before the translated body. The body still passes the existing
memory/context checks and releases its writer byte before spin completion.
This admits the current RCUHT writer without translating reader-drain atomics;
it does not resolve the general dynamic-pointer screening gap.

Install [the pinned requirements](requirements.txt) in a guest venv. Inspect CLI
options with `python3 disassem/disassem.py --help`; real-text CLI use acquires its
own device lease and does not by itself upload a published image. Importing helpers
for byte fixtures does not establish actual kernel JIT evidence.

Owned images carry their audited context requirements into immutable publication
descriptors. The provider binds a frame to one version and checks any required
origin-readiness claim at dispatch; see
[publication protocol 2](../docs/JIT_EXECUTION.md#owned-image-publication-protocol-2).
Spin/rwlock image families retain in-place publication.

The translator does not check every memory address when it is used or restore all
processor state. Those features remain deferred. Its context checks are not a
security sandbox; see [known limitations](../docs/TODO.md).
