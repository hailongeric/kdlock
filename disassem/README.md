# Translator

The production translator trusts all selected kernel and module source code.
It reads machine code under a source residency lease, decodes the reachable
instructions, lowers their registers and control flow, and builds a wrapper
image. It does not run context-symbol screening, memory/alias or loop-value
analysis, constant-path proofs, or the minimal-entry input-definedness proof.
The compiler's clobber-entry agreement is a source assumption: only IP/SP/BP
are guaranteed by a minimal packet, and the source must supply its other live
inputs. Trust does not add register capture or restore unsupported CPU state.

The Python API defaults to `dis_assem(..., trusted_source=True)`. Explicit
`trusted_source=False` retains the earlier checked analyzer for regression and
comparison fixtures; it is not the production command-line path. The abandoned
finite-edge refinement candidate is preserved with the ordinary-translation
experiment receipts and is absent from active code.

Use [the daemon](../daemon/README.md) for publication and
[the project guide](../docs/PROJECT_GUIDE.md) for guest dependencies.
Python 3.14 requires the [pinned Miasm compatibility patch and preflight](compat/README.md).
Startup checks those installed bytes before decoding. The
[terminology guide](../docs/TERMINOLOGY.md) explains JIT, ABI and execution states.

Under the [project roadmap](../docs/ROADMAP.md), stage 1 measures delegation;
the stage 2 mmap adapter executes unchanged MM bodies on their original tasks.
Trusted translation does not extend that MM integration scope.

| Read first | Responsibility |
| --- | --- |
| [disassem.py](disassem.py) | Production trust selection, input coordination, assembly/link and diagnostics |
| [translation_scope.py](translation_scope.py) | Decode windows, selected JIT episode and CALL continuations; optional checked screening |
| [translation_image.py](translation_image.py) | Dispatch targets, flag-preserving instrumentation and generated assembly |
| `conflict.py`, `normal.py`, `special_inst.py`, `hostcall.py` | Register, instruction, virtual-stack and control lowering |
| [native_escape.py](native_escape.py) | Exact instruction-marker lowering and retained runtime protocol scope |
| `device_session.py`, `memread.py` | Same-device lease, capabilities and source pinning |
| [instruction_policy.py](instruction_policy.py), [context_policy.py](context_policy.py), `context_symbols.py` | Optional checked-mode instruction and context screening; shared CFG helpers |
| `context_values.py`, `context_registers.py`, `context_memory.py` | Optional bounded value and memory analysis |
| `context_guards.py`, `entry_abi.py`, [constant_paths.py](constant_paths.py), [address_guards.py](address_guards.py), [guard_flags.py](guard_flags.py) | Optional checked-mode input, branch and address proofs |
| [strcmp_service.py](strcmp_service.py), [strscpy_service.py](strscpy_service.py), [native_calls.py](native_calls.py) | Historical service/direct-call compatibility; not selected by production translation |

[Translation policy](../docs/design/admission.md) separates source assumptions
from construction and runtime checks. [Register ABI](../docs/JIT_REGISTER_ABI.md)
defines packet fields, mapping, actual CALL words and COMPLETE/FULL.
`solve_bug.py` contains active encoding/assembly corrections.

Entry identities remain legacy 0, spin clobber 1, mutex clobber 2 and rwlock
writer clobber 3. ABI3 uses the spin backend and IP/SP/BP packet. Native code
acquires writer admission and drains readers before its translated body; the
paired unlock releases the writer byte before spin completion. The object must
still use one lock protocol. Trust does not create a Linux/KD mutex bridge or
extend the nested ownership ledger.

String routines, including `strcmp`, `strnlen`, `sized_strscpy`, `strscpy_pad`
and `memcpy`, follow ordinary leased-text decoding and generated CALL/RET
handling. A helper's prologue, memory operations, loops and return path remain
ordinary code. No string name selects a memory summary, direct native service,
quota or helper-specific escape. Current images retain only the scalar services
`ktime_get`, `ktime_get_ns` and `int_sqrt`; historical string capability bits
cannot reactivate the removed selection routes. Taskname retains its ordinary
`KD_SPIN_DIRECT_LOCK` pair and source `strscpy_pad` use.

Generated entry dispatch, block budgets, RET target checks and LEA-to-MOV/ADD
lowering always preserve source arithmetic flags. Balanced saves use the
executor's physical stack; source CALL words and source stack accesses use the
waiter's virtual stack. This does not add captured entry flags or enlarge the
native-continuation flags contract.

Text coverage, decoder/lowering support, assembler success, return-target graph,
image layout and provider capabilities still determine whether an image can be
built and published. Missing bytes, unsupported representations or construction
failures are not source-safety verdicts. Known decoder aliases require correct
lowering; trusting their source is not permission to emit different semantics.
Generated control flow retains actual CALL/RET operations and the return
whitelist. Source leases, physical owners, acquisition records, unlock ACKs,
frame retirement and normal drain remain enforced by the existing runtime.
A NORMAL image is publication evidence, not a completed delegated body.

KD-only mutex images remain immutable and require the negotiated exclusive-KD
and immutable-image capabilities. Exact instruction markers keep their existing
image requirements and runtime source/owner/continuation checks. Trusted mode
does not apply the historical semantic proofs to their bodies. Marker images
still obey the restricted root/nested protocol and disable later delegation
when execution transfers to the original waiter. Unsupported marker encodings
are not automatically native fallback points. See
[the protocol details](../docs/design/admission.md#checked-instruction-exits).

Install [the pinned requirements](requirements.txt) in the guest virtual
environment. The production command is
`python3 disassem/disassem.py PID ENTRY_HEX [LOCK_KIND] [ABI]`.
Real-text CLI use acquires its own device lease and does not upload an image.
Byte-fixture imports and successful assembly do not establish live kernel JIT
correctness or performance. New trusted-mode results require their own receipts;
the historical results below retain their original source and policy identities.

## Historical checked-analysis and service evidence

The following descriptions record historical checked-analysis and image/provider
compatibility. The current translator does not select these routes, and their
recorded validation does not validate ordinary helper translation on Linux 7.

Historical original string API services require versions 10 through 12 bit 9,
together with bit 7 for
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

The optional checked analyzer refuses Linux mutex APIs, their compiler clones
and the old kernel mutex bridge. Ordinary KD return-valued or task-sensitive locking APIs remain local;
explicit clobber entries supply delegation. See the
[object/API contract](../docs/design/kd_only_mutex.md).

The former checked path combined source constant proofs, optional pointer-load
guards and bounded memory/alias analysis. These mechanisms remain available to
explicit checked-mode regression callers; production trusted translation does
not invoke them. The generic partial-CALL-alias mask experiment remains archived
in the [version 10 development record](../bench/results/10.176.26.71/bench/taskname-xattr-native-api-20261019/DEVELOPMENT.md#archived-alias-experiment-and-next-scope).
Its results and the historical service-specific control-storage contract do not
establish properties of the current trusted path.

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
[historical development record](../bench/results/10.176.26.71/bench/taskname-xattr-direct-api-20261019/DEVELOPMENT.md#candidate-3-checks)
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
