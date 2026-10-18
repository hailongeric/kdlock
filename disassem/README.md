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
| [constant_paths.py](constant_paths.py) | Prove source branches impossible from exact register constants before ordinary admission; no runtime memory assumptions |
| [address_guards.py](address_guards.py) | Restricted spin pointer-load checks against recorded stack writes and immutable source-site records |
| [guard_flags.py](guard_flags.py) | Prove incoming arithmetic flags are overwritten before source code reads them at a checked spin continuation |
| [translation_scope.py](translation_scope.py) | Decode windows, selected blocks and CALL continuations |
| [translation_image.py](translation_image.py) | Dispatch targets and generated assembly |
| [context_policy.py](context_policy.py), `context_symbols.py` | Backend/context screening and static ranges |
| `context_values.py`, `context_registers.py`, `context_memory.py` | Bounded flow, register facts and sequential memory/alias model |
| `context_guards.py`, `entry_abi.py` | Entry predicates and MINIMAL input-dependency proof |
| `conflict.py`, `normal.py`, `special_inst.py`, `hostcall.py` | Virtual register/instruction/control lowering |
| [strcmp_service.py](strcmp_service.py), [strscpy_service.py](strscpy_service.py) | Exact original string-helper code, arguments and separate read-only/writing contracts |
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
(capability version 5 through 9). Checked mutex instruction markers require version
6 through 9 bit 5. Checked spin address exits require version 7 through 9 bit 6 and image
requirement bit 1; mutex instruction markers use image requirement bit 0.
The exact bounded `strcmp` service requires version 8 or 9 bit 7 and image requirement
bit 2, only for audited ABI1 direct callers with stable ordinary kernel strings.
See [its admission contract](../docs/design/admission.md#bounded-original-strcmp-service).
The separately negotiated `strscpy_pad` service requires version 9 bit 8 and
image requirement bit 3. It models all 64 destination bytes as writes and only
accepts a checked current-frame destination; readonly string capability alone
cannot enable it. Both retain the original CALL-word effect and invoke the
original helper. Only `strcmp` uses the allowance of 128 calls; writing helpers
share the existing limit of 16 scalar/control continuations. See
[writing-helper admission](../docs/design/admission.md#bounded-original-strscpy_pad-writing-service).
Linux mutex APIs, their compiler clones and the old kernel
mutex bridge are refused. Ordinary KD return-valued or task-sensitive locking
APIs remain local; explicit clobber entries supply delegation. See the
[object/API contract](../docs/design/kd_only_mutex.md).

The taskname caller uses the ordinary `KD_SPIN_DIRECT_LOCK` pair. Its bounded
`strscpy_pad` service executes the original helper without translating its
prologue, so the call shell no longer adds five register initializations.
The optional `KD_SPIN_DIRECT_HELPER_LOCK` remains available for other callers
whose translated helpers save those incoming registers. The independent source
constant proof also remains: it can exclude `strscpy()`'s impossible size-warning
branch when the actual argument is 64, without changing the helper or permitting
a reachable `UD2`. ABI1 bodies with learned indirect targets are not specialized;
unknown facts and ambiguous joins keep their original branch alternatives.
The ordinary taskname shell passed its read-only execution check at 16 workers:
3,194,222 complete delegated bodies in 3,200,000 operations. Its 20% mutation
check was correct and drained, but measured no completed delegated bodies and
therefore failed the strict delegation requirement. Earlier call shells remain
separate evidence; the full performance comparison is pending.

For the xattr traversal, a restricted ABI1 retry checks whether a later pointer
load overlaps earlier writes on the waiter's stack. A failed check returns the
original waiter to that exact load and disables future delegation. It requires
the original source to overwrite arithmetic flags before reading them, because
ordinary spin recovery does not restore them. Entries using address checks or
typed string services publish immutable images from their first such version
onward. Neither helper stacks
nor arbitrary pointers are assumed private or safe. A body needing both source
constant-branch simplification and address checks remains refused: simplifying
the graph could hide a flags read in the original native suffix. The bounded
writing service does not supply a generic helper flag proof to those guards.
All eight xattr front/tail/miss/size checks at n16/n128 and 16 workers completed
delegated bodies with correct results and clean teardown. The address-check and
bounded-string probes also passed their successful-delegation and native-return
checks. These are [functional results](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md);
the full performance matrix remains pending. See the
[detailed scope](../docs/design/admission.md#checked-spin-pointer-loads).

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
Mutex images and spin entries that have published an address-check or typed
string-service image use
separate immutable versions. Other spin entries and ABI3 rwlock images retain
in-place publication. The narrow spin checks do not close the general dynamic
address gap or repair arbitrary processor state. Context checks are not a
security sandbox; see
[known limitations](../docs/TODO.md).
