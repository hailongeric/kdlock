# Translator

The translator reads kernel machine code while holding a source lease, which
keeps the source modules loaded. It selects the code a JIT invocation can reach,
checks whether that code is supported, rewrites uses of the caller's registers,
and emits assembly and a wrapper image.
Use [the daemon](../daemon/README.md) for publication and
[the project guide](../docs/PROJECT_GUIDE.md) for guest dependencies.
JIT means just-in-time compilation; ABI means application binary interface.
The [terminology guide](../docs/TERMINOLOGY.md) explains execution-state terms.

Under the [project roadmap](../docs/ROADMAP.md), stage 1 uses this translator to
establish eligible delegation gains. The current stage 2 mmap adapter executes
MM bodies locally. Broader stage 3 integration must preserve admission and source
lifetime rules; a new benchmark target does not make arbitrary MM code eligible.

| Read first | Responsibility |
| --- | --- |
| [disassem.py](disassem.py) |CLI, input coordination, assembly/link and diagnostics |
| [instruction_policy.py](instruction_policy.py) | Scalar instruction, hardware-register and raw-encoding admission |
| [native_escape.py](native_escape.py) | Reviewed instruction markers, scalar input/output proof, root-only spin scope and terminal generated paths |
| [constant_paths.py](constant_paths.py) | Prove source branches impossible from exact register constants before ordinary admission; no runtime memory assumptions |
| [address_guards.py](address_guards.py) | Restricted spin pointer-load checks against recorded stack writes and immutable source-site records |
| [guard_flags.py](guard_flags.py) | Prove incoming arithmetic flags are overwritten before source code reads them at a checked spin continuation |
| [translation_scope.py](translation_scope.py) | Decode windows, selected blocks and CALL continuations |
| [translation_image.py](translation_image.py) | Dispatch targets and generated assembly |
| [context_policy.py](context_policy.py), `context_symbols.py` | Backend/context screening and static ranges |
| `context_values.py`, `context_registers.py`, `context_memory.py` | Bounded flow, register facts and sequential memory/alias model |
| `context_guards.py`, `entry_abi.py` | Entry predicates and MINIMAL input-dependency proof |
| `conflict.py`, `normal.py`, `special_inst.py`, `hostcall.py` | Virtual register/instruction/control lowering |
| [strcmp_service.py](strcmp_service.py), [strscpy_service.py](strscpy_service.py) | Original kernel API resolution and separate read-only/64-byte writing effects |
| [native_calls.py](native_calls.py) | Direct original string calls, per-invocation allowances and generated relocation directory |
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
(capability versions 5 through 12). Checked mutex instruction markers require
versions 6 through 12 bit 5. Checked spin address exits require versions 7 through
12 bit 6 and image requirement bit 1; mutex instruction markers use image
requirement bit 0. A capability is a provider's advertised execution support;
an image requirement identifies support that its generated code needs.

Original string API services require versions 10 through 12 bit 9, together with bit 7 for
`strcmp` or bit 8 for `strscpy_pad`. Their image requirements remain bit 2 and
bit 3 respectively. A service invokes the original kernel function with its
original arguments while the generated caller retains its analyzed memory
effects. No phase checks helper bytes, helper-specific CALL encodings or string
contents. Runtime does not recheck destination bounds. Native caller guarantees
supply valid, stable strings and output storage. Ordinary register/context
analysis remains active, and the writer still requires a statically known count
of 64 and one local 64-byte destination to model every write. The source CALL's
stack write remains in generated code. Only for these two services in selected
reviewed C callers does analysis record temporary return-address bytes separately
from ordinary object data:
these callers promise not to inspect or overwrite that storage through data
accesses. Explicit known observers are refused. This limited rule does not apply
to arbitrary calls or discard ordinary writes. Decoded `memcpy` keeps ordinary
CALL/RET analysis and all copy effects; it has no separate classification or
special return path. See the
[selected-caller contract](../docs/design/admission.md#original-call-word-aliases).
Both services use immutable images. Only `strcmp` uses the allowance
of 128 calls; writing helpers share the limit of 16 scalar/control continuations.
See the [read-only contract](../docs/design/admission.md#original-strcmp-service)
and [writing contract](../docs/design/admission.md#original-strscpy_pad-writing-service).

Version 11 optionally advertises bit 10 for direct original-helper calls.
The selected image adds requirement bit 4, value 16, alongside its read/write
service bits. It enters only a pristine ABI1 spin root and runs the helper within
one generated invocation, preserving the original arguments and actual virtual
CALL word. Its graph cannot contain address guards, scalar dispatcher services
or nonterminal lock controls. Ordinary decoded callees and the final outer
unlock remain allowed; other eligible string graphs use the dispatcher.

The translator emits a direct x86 CALL with a zero relative-address operand and
a `KDNC0001` directory naming that slot, service and original return. Before
publication the provider fills the relative operand in executable storage near
kernel text and pins helper and return-source residency. No helper or source
CALL bytes are inspected. Uploaded `jit.bin` contains the placeholders; benchmark
evidence also saves loaded generated bytes and a reconstruction receipt outside
timing. The upload hash alone does not identify the executed image.

The wrapper preserves its packet pointer and source register state across the
original C helper, then reads, validates and consumes the actual source return
word. Reserved wrapper slots hold allowances of 128 comparisons and 16 padding
calls. The executor stack is aligned once at direct entry. Quota and return
checks temporarily use RCX, preserve its original value on every path and leave
arithmetic flags unchanged; no per-call alignment or flags scratch is needed.
An excess helper returns FULL exit 10 before effects and leaves its CALL
word for the original waiter; the invocation cannot reenter and reset its limits.
Completed-call counts use private descriptor fields at offsets 96 and 104 in a
112-byte descriptor. The two-word wrapper ABI, body witness and lock protocol
are unchanged. See the
[direct-call contract](../docs/design/admission.md#direct-original-helper-calls)
and [register guide](../docs/JIT_REGISTER_ABI.md) for the complete boundaries.

Linux mutex APIs, their compiler clones and the old kernel mutex bridge are
refused. Ordinary KD return-valued or task-sensitive locking APIs remain local;
explicit clobber entries supply delegation. See the
[object/API contract](../docs/design/kd_only_mutex.md).

Taskname uses the ordinary `KD_SPIN_DIRECT_LOCK` pair. Its `strscpy_pad` service
executes the original helper without translating its prologue, so the call shell
adds no helper-specific register initialization. The optional
`KD_SPIN_DIRECT_HELPER_LOCK` remains available for other callers whose translated
helpers save those incoming registers. The independent source constant proof
also remains: it can exclude `strscpy()`'s impossible size-warning branch when
the actual argument is 64, without changing the helper or permitting a reachable
`UD2`. ABI1 bodies with learned indirect targets are not specialized; unknown
facts and ambiguous joins retain their original branch alternatives.

A restricted ABI1 address guard can check whether a pointer load overlaps earlier
writes on the waiter's stack. A failed guard returns the original waiter to that
exact load and disables future delegation. It requires the original source to
overwrite arithmetic flags before reading them, because ordinary spin recovery
does not restore them. Neither string service supplies that flags proof. Entries
using guards or string services publish immutable images from their first such
version onward. A body needing both constant-branch simplification and address
guards remains refused, because simplifying the graph could hide an incoming
flags read in the native continuation. The generic partial-CALL-alias mask
refinement is an archived experiment, not a maintained admission rule. It tried
to retain the known and unknown byte portions of values overlapping CALL return
words. The maintained revision keeps conservative ordinary-CALL analysis and separate
control storage only for the two string services. It changes no source load or
store and does not make arbitrary pointers safe. Focused unit and live correctness
checks passed, as recorded in the
[version 10 development record](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md);
see the [admission guide](../docs/design/admission.md#original-call-word-aliases)
and [archived candidate 4](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md#archived-alias-experiment-and-next-scope).

Version 10 candidate 6 passed all eight xattr controls and the read-only taskname
checks with matching generated-body entries and completions. The original-string
service, address-guard recovery and mutex instruction-marker probes also passed.
A separate 20% taskname mutation control with preparation disabled passed
correctness on Linux Native, TCLock and KD but recorded zero KD generated bodies;
it does not establish delegation or supersede the earlier strict failure. The
[`88bb5a4` standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/README.md)
completed all 567 sessions with validation and drain. In that historical
dispatcher round, KD was slower than Linux Native and TCLock at 60 workers in
all three measured workloads.
The final version 11 direct bridge passed the affected unit and live checks,
its separate KD screen and all 18 diagnostic profiles. The
[current development record](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-3-checks)
retains the generated-wrapper checks and earlier failures. The separate
[`05876a4` standard-grid comparison](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/README.md)
completed all 567 sessions with validation and drain for the three API
workloads. Archive verification and the separate n129 quota control are complete;
that control verified native waiter completion after quota exhaustion and drain.
Profile timings are unscored, and the completed version 10 results above measure
the dispatcher route.

The preceding
`c79d84f` implementation passed the ordinary taskname shell's 16-worker read-only
check with 3,194,222 returned delegated bodies in 3,200,000 operations. Its 20%
mutation check was correct and drained but measured no returned delegated body,
so the strict delegation requirement failed. All eight xattr front/tail/miss/size
checks at n16/n128 and 16 workers passed with matching entries/completions,
correct results and clean teardown. Earlier address-guard and string-preflight
probes also passed, but the removed string preflight is not current behavior.
These [functional results](../bench/results/10.176.26.71/bench/taskname-xattr-20261018/DEVELOPMENT.md)
remain tied to their source versions; the completed comparison reports the
revised `88bb5a4` implementation separately.

Install [the pinned requirements](requirements.txt) in a guest Python virtual
environment. The translator command uses positional arguments:
`python3 disassem/disassem.py PID ENTRY_HEX [LOCK_KIND] [ABI]`, where PID is the
process identifier, ENTRY_HEX the hexadecimal entry address, and LOCK_KIND the
lock backend. Real-text command-line use acquires its own device lease and does
not by itself upload a published image. Importing helpers
for byte fixtures does not establish actual kernel JIT evidence.

The translator does not check every memory address when it is used or restore all
processor state. Reviewed instructions can end generated execution with a
checked marker; the waiter then executes the instruction and future delegation
of that entry is disabled. Other unsupported state still fails static admission.
See [the exact policy](../docs/design/admission.md#checked-instruction-exits).
Version 12 bit 11 permits ABI1/3 root markers only with exact image requirements
33 and a pristine physical root. Full-source checks reject services, nested and
indirect control before trimming marker successors; generated dispatch admits
only the original root. This does not extend ABI2 nested relay to spin/rwlock.
Mutex images and spin entries that have published a root marker, address-check or typed
string-service image use
separate immutable versions. Other spin/rwlock entries retain
in-place publication. The narrow spin checks do not close the general dynamic
address gap or repair arbitrary processor state. Context checks are not a
security sandbox; see
[known limitations](../docs/TODO.md).
