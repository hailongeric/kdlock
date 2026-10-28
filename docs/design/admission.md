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

Only the declared scalar services `ktime_get`, `ktime_get_ns` and `int_sqrt`
remain selected hostcalls. They have explicit result/clobber contracts; they do
not switch hardware task identity to the origin. Their source CALL word remains
part of the ordinary continuation protocol.

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
flags restored; future delegation of that entry is disabled for the source
session. A generic fault, unsupported lowering or budget failure cannot be
converted into an arbitrary safe native restart.

Mutex/rwsem use the ABI2 marker contract. Supported pristine root spin/rwlock
ABI1/3 images require immutable requirements 33 and the matching provider bits.
Their physical owner, writer admission where applicable, FULL packet and exact
source target survive native transfer. See the
[register contract](../JIT_REGISTER_ABI.md#checked-instruction-exit) and
[live probes](../../tests/kernel/jit_escape/README.md).

Linux 7 active call-depth tracking is rejected at provider initialization because
its return thunk changes arithmetic flags after restore. Configured support is
not the same as an active runtime feature. Complete mitigation coverage of
handwritten/generated returns remains separately unvalidated.

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
