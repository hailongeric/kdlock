# Translation admission and publication

Production uses `dis_assem(..., trusted_source=True)` for all selected kernel
and module code. This is also the CLI default. Source safety and the compiler
clobber-entry input agreement are caller assumptions, not translator proofs.
[Register ABI](../JIT_REGISTER_ABI.md) defines the unchanged saved state.

## Source trust and backend requirements

Trusted translation skips semantic instruction admission, context metadata
screening, memory/alias and loop-value analysis, constant-path specialization
and minimal-entry input-definedness proofs. ABI1/2/3 import only IP/SP/BP;
trusting the compiler agreement does not capture extra GPRs or processor state.

The following requirements still hold:

| Requirement | Purpose |
| --- | --- |
| Leased source and complete selected text | Keep original module code live while reading, compiling, learning or executing it |
| Supported decoding and faithful lowering | Emit the original operation and selected control flow correctly |
| Actual CALL/RET words and return whitelist | Preserve the source stack protocol and exact continuation routing |
| Matching backend, entry ABI and image requirements | Bind generated code to the provider contract it needs |
| Physical ownership and exact acquisition/frame records | Execute under the required exclusion and retain every unlock/retirement obligation |

Missing text, incomplete decoding, unsupported lowering or invalid image
construction remains a translation failure. It is not a source-safety verdict.
Trust does not supply missing backend support or permit different semantics.
Runtime probes and source/owner/ACK/frame checks must not be removed to hide
failures.

The [October 30 native-section audit](kernel_cs_semantics.md#mandatory-instructions-and-operations)
found a concrete source-level PAUSE fidelity gap in that audited baseline: the
pinned decoder's F3 90 NOP-alias path emitted bare NOP and lost its prefix. The
candidate special handler now emits physical PAUSE for those exact bytes.
Fence mnemonics and LOCK prefixes use separate ordinary emission paths. The
focused decoder/generated-byte fixture is separate from that historical audit;
source trust or a mnemonic allowlist alone is not execution evidence.

Deliberate translation refusal returns exit 2 and the daemon publishes
`KD_EXE_NATIVE_ONLY`; other compiler/environment failures remain distinct retry
errors. Source trust is not universal escape synthesis: only exact reviewed
instruction descriptors receive native markers. The trusted ordinary-callee
fixture even retains `UD2` bytes without executing them. A generic unsupported
operation or post-progress runtime error is not guaranteed recoverable.

## Ordinary callees and strings

`strcmp`, `strnlen`, `sized_strscpy`, `strscpy_pad` and `memcpy` use ordinary
leased-text decoding and generated CALL/RET. Their bodies and loops receive no
named memory model, string service, control-slot exception, string quota or
direct native bridge. Historical provider capability bits cannot select those
routes in current translation.

The selected scalar hostcalls are `ktime_get`, `ktime_get_ns` and `int_sqrt`.
They have explicit result/clobber contracts; they do not switch hardware task
identity to the origin. Their source CALL word remains
part of the ordinary continuation protocol.

Scalar hostcalls are distinct from the retained candidate's provider-registered
returning services. `dis_assem` reads `device_session.service_calls()` for ABI2
and uses those exact targets as declared intervals with their own argument,
continuation, owner and lifetime contracts. The service-control path can return
execution to the executor (E) after that interval. This does not make an
untranslated ordinary callee a returning service, select the retired named string models or authorize
arbitrary native reentry. Ordinary GS operands retain the original saved-origin
lowering; only the precisely declared context operation selects an original-task
service.

The [lock replacement contract](kdlock_lock_replacement_contract.md) selects
bounded original CFG exploration, actual miss learning and subsequent image
replacement. Its current-position handback preserves IP/GPR/SP and completed
CALL pushes/RET pops. Retained-worker wiring and its production component join
are committed, with [source-specific results](kdlock_lock_replacement_contract.md#current-focused-component-results)
and preserved failed attempts. Supplied task/physical primitives limit that
coverage. The later `58af0a53` probe passes cold CALL and indirect-JMP handback;
its exact post-RET observations accompany an overall checker failure. Candidate
`bccf877c` adds untested harness fixes, and further validation is blocked; see
the [partial live record](kdlock_lock_replacement_contract.md#partial-live-probe-and-current-stop).
General flags/SIMD restoration and IRQ/NMI conflict are deferred for this phase.
Existing limited flags and instruction contracts do not establish those broader
features.

### Selected rwsem state queries

The selected ordinary original-JIT bodies are `kd_mmap_assert_held_write`,
`kd_mmap_assert_held` and `kd_mmap_is_locked`. Provider discovery records use
synthetic labels, so classify by operation identity: `KD_RWSEM_OP_ASSERT_HELD`
(14), `KD_RWSEM_OP_ASSERT_HELD_WRITE` (15) and `KD_RWSEM_OP_IS_LOCKED` (16).
Retain those immutable discovery records, but exclude them from runtime-control,
lock-control and callee-exclusion sets. Do not register their public targets as
returning Native services. A snapshot declaring both classifications must fail
translation. `IS_CONTENDED` (17), `IS_WRITE_OWNER` (18), and other existing
services/acquisition/release/downgrade controls stay unchanged.

These helpers still use ordinary bounded CALL/IJ learning. Their downstream
calls keep their individual policies; do not force an entire call chain into
translation or turn it into one Native interval. The necessary narrow
interval is `kd_service_write_owned`, preserving the exact retained custody proof.
Its selected two-argument Boolean service uses `KD_SERVICE_CALL_ATOMIC_ORIGIN`
and a word result. O runs only that runtime query while E is suspended, and E
then resumes the same image with the existing token/module-reference protocol.

The exact task, request generation, phase identity/generation, physical gate
owner and pending-pickup predicates remain required. `ATOMIC_ORIGIN` retains
actual origin pins/RCU; the `BALANCED_ORIGIN` rejection of retained spin/RCU is
not appropriate for this narrow interval. Other context preconditions still
apply. Preparation rejection remains fail-stop and does not automatically
select native handback. The partition and descriptor are committed at
`a6fe0bb2`. Its writer-query component passes with supplied runtime observations.
All six query-image cases pass at `da55414f`, after fixing the legal
return-continuation-label assertion; the failed first receipt remains recorded.
These cases use synthetic source bodies and the actual original image backend.
Separate production service-join coverage uses supplied task/physical primitives;
neither establishes actual public helper execution or a live O/E service/ACK.

An untranslated ordinary callee can transfer the remaining invocation to the
original waiter. Later learning may extend the graph. It does not authorize
resuming JIT after arbitrary native work, replaying the prefix, or consuming a
return token twice. The taskname benchmark learns ordinary callees before its
measured phase; preparation and measured returned-body counts are separate.

## Selected graph and code generation

The translator resolves lock controls, decodes selected roots and learned
targets, and constructs the CALL/RET graph. Intentional native suffixes stay
outside the emitted episode; alternate reachable paths must still be complete.
A reachable empty decoder block is not a successful translation. Decoder-window
extension/reseeding retains its bounded construction limits.

Trusted mode keeps source branches. It does not invoke the optional constant
proof to eliminate a difficult path. Generated entry dispatch, block-budget
checks, indirect/RET target lookup and synthetic LEA lowering preserve arithmetic
flags. Their balanced physical-stack saves are distinct from the virtual source
stack and its real CALL words.

Known lock controls retain their supported physical/virtual acquisition rules.
ABI3 writer admission precedes body execution. Rwsem outer writers reserve their
phase and drain readers before ABI2 publication. Source trust does not make
unsupported nested, signal, try, I/O or non-owner protocols available.

## Build and publication

The daemon retains one device writer session through text reads, compiler
children and uploads. It checks dependency bytes, assembles the image privately
and negotiates the provider's exact header/ABI/requirements. Incomplete uploads,
unknown requirements and mismatched backends cannot become ready images.

Mutex registration may precede executable allocation. Each completed mutex
publication creates an immutable generation; frames retain their bound image
through all continuations. Ordinary spin/rwlock entries can still use in-place
replacement until an immutable transition. See [image lifetimes](lifetimes.md#executable-images-and-guarded-spin-transition).

`NORMAL` records publication. Successful returned JIT execution additionally
requires a completed generated body and matching unlock protocol. Exact business
results and drain remain independent checks. The
[Linux 7 trusted-source evidence](../VALIDATION.md#trusted-ordinary-translation)
does not establish arbitrary-source equivalence or whole-kernel replacement.

## Checked instruction exits

Supported instruction markers stop before a reviewed original instruction. The
origin resumes there with earlier effects retained and the documented arithmetic
flags restored. That invocation finishes its native suffix; the marker leaves
registry status and immutable image identity unchanged, so a later invocation can
delegate a different path or reach the same marker again. It cannot reopen an
independently disabled entry. A generic fault, unsupported lowering or budget failure cannot be
converted into an arbitrary safe native restart.

The pinned decoder's exact F3 90 NOP alias emits physical `PAUSE`; ordinary NOPs
retain their existing lowering. `PAUSE`, fences and supported LOCK instructions
remain generated instructions, without a runtime exit per iteration. Focused
generated-byte and effect checks are required; this is not a claim of arbitrary
opcode support or a completed kernel memory-ordering proof.

Mutex/rwsem use the ABI2 marker contract. Supported pristine root spin/rwlock
ABI1/3 images require immutable requirements 33 and the matching provider bits.
Their physical owner, writer admission where applicable, FULL packet and exact
source target survive native transfer. See the
[register contract](../JIT_REGISTER_ABI.md#checked-instruction-exit) and
[live probes](../../tests/kernel/jit_continuation/README.md).

Linux 7 active call-depth tracking is rejected at provider initialization because
its return thunk changes arithmetic flags after restore. Configured support is
not the same as an active runtime feature. Complete mitigation coverage of
handwritten/generated returns remains separately unvalidated.

## Reached Native CALL boundaries

The candidate adds `include/kd_native_terminals.def`, a shared, finite manifest of exact Native lock and
processor/task-context API symbols. It is a runtime continuation contract, not
a reinstatement of checked source/value admission. The translator and provider
resolve the same names independently. Missing symbols do not match, and unknown
ordinary callees keep the existing learning path. Initial groups cover Native
spin/rwlock, mutex and rwsem operations; scheduling, preemption, migration and
IRQ/BH transitions; and explicit task-mm, user-access and TLB operations whose
effect must remain on the original task. Each manifest group must explain its
context obligation. Compiler clones, inlined instructions and unlisted helpers
are outside an exact-symbol guarantee.

A reached listed CALL retains its actual source return word and saved packet.
The runtime independently checks its exact target, physical/frame scope, pending
CALL stack bounds and source residency before returning it to the original
waiter. That invocation runs the callee and remaining native suffix. The
boundary does not invoke a Native API on a KD object, invalidate a ready image,
request callee learning or return to JIT after arbitrary native work.

Historical callee and indirect-target records must not import a listed body or
keep its otherwise unreachable descendants as independent entry roots. Scope
must follow real entry/CALL/known-indirect edges; alternate reachable branches
remain translated. A previously learned indirect CALL may reach the same native
stub, retaining its real CALL word. Fresh near indirect CALLs can use optional
v12 capability bit 12 and FULL exit 11. The emitter evaluates the target before
the source CALL's virtual push, records the exact source CALL address in
`orig_ax`, and retains the actual target in IP. The provider checks a canonical
optional-REX `FF /2` instruction, its exact next IP against the waiter-stack
return word, FULL packet/frame identity, pending phase and source leases for
the instruction, target and continuation. Only then can the original waiter
execute the callee and native suffix. Unknown ordinary targets still learn that
proved CALL edge; listed terminal targets leave image status unchanged. The
scratch source address is cleared before native restore. This is the ordinary
C-call flags contract, not an arbitrary flags-consuming assembly-call ABI.

Without the optional bit, translation emits the older unresolved-indirect
behavior. Unknown RET/JMP targets remain errors; far or legacy-prefixed CALLs
have no new continuation contract. They must not masquerade as exit 11. Return
routing and complete text for every emitted path remain required.

The selected files/pipe bridges are per-object dispatchers. Their acquire and
non-root unlock calls remain terminal because the object may be Native. Only the
integration's exact outer-object/class unlock predicate may take precedence as
a KD completion endpoint. No symbol-name canonicalization may convert an
arbitrary Native inner lock into a KD control.

The source-derived runtime fixtures and real decoder/wrapper fixtures cover
pending CALL provenance, independent terminal classification, historical-scope
cleanup, alternate branches and old-provider negotiation. Their execution and
the live repeated-path probe remain VM validation gates; no pass or wider Native
API coverage follows from these source changes.

## Checked spin pointer loads

Pointer-load guards are optional checked-regression/historical behavior.
Production trusted translation does not run the address/flags analysis or emit
its retry policy. The retained runtime ABI and fixtures do not establish a
production pointer-validity or object-lifetime check. Its detailed former
contract is in the [fixed pre-cleanup guide](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/admission.md#checked-spin-pointer-loads).

## Explicit checked regression mode

Python callers can select `trusted_source=False` to exercise the retained
context, value/alias, loop and entry-input analyzer in regression fixtures.
Its refusals, widening limits and flags proofs belong to that explicit mode.
They are not production admission failures or implicit requirements to restore.
The finite-edge experiment remains archived and inactive.

Historical string services/direct bridges, control-storage models and their
quotas are documented at the
[fixed pre-cleanup checkpoint](https://github.com/hailongeric/kdlock/blob/cbf0df6fa1acf9fd88a05795644a7b0a6c4c9773/docs/design/admission.md).
Their original numeric outcomes and failures remain in [history](../history/README.md)
and frozen results; they do not validate the current ordinary-callee policy.
