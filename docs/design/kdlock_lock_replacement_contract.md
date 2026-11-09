# kdlock lock replacement contract

This guide describes the retained execution contract implemented on `master`.
It covers current-position native continuation, exact ownership and source/frame
lifetime; [JIT execution](../JIT_EXECUTION.md) owns current emission boundaries,
including the narrow JIT-consumed proxy downgrade. Native critical-section
bodies and userspace syscall paths remain unchanged.

Merge `6badc60e` includes the proxy-read implementation and its source-specific
evidence. The [latest validation](../VALIDATION.md#retained-original-jit-and-proxy-read)
distinguishes tested `7e3c90b4` from the unexecuted union with master's flags-stack
changes. Historical work orders below apply to their named checkpoints;
separate redesign proposals need their own target decisions and implementation.

The initial production checkpoint `da55414f` followed wiring at `a6fe0bb2`,
miss packets at `ebae17c1` and removal of the separate instruction backend at
`10ef078a`. The [component receipts](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/README.md)
retain every failed and successful source-specific attempt with fixture limits.
The later `58af0a53` probe passed cold CALL and indirect-JMP phases but failed
its overall post-RET checker. Its `bccf877c` harness follow-up remains untested;
that targeted record is separate from later mmap1 campaigns.

## Required execution model

Use exactly one instruction translation backend: the original
[translator](../../disassem/disassem.py), its bounded graph construction,
[ordinary lowering](../../disassem/normal.py),
[CALL/RET lowering](../../disassem/special_inst.py),
[image emission](../../disassem/translation_image.py),
[wrapper](../../include/wrapper.S) and existing
[daemon pipeline](../../daemon/README.md). The separate reached instruction
emitter is a superseded candidate, with its historical results retained.
Checkpoint `10ef078a` removes its production emitter/cache/dispatcher and moves
the C reference engine/adapter into test fixtures. This is confirmed source
removal, not a fresh build or runtime pass. Stale reached-state fields remain.

Bounded exploration constructs a complete selected image, using existing CALL
and indirect-target history. It does not require the entire kernel CFG, eager
ordinary-callee closure or every MM entry to be compiled before progress.
Reaching untranslated code records the actual miss and returns this invocation
to its original task. The daemon can include learned edges in a subsequent
replacement image. The current invocation does not wait for, join or restart
in that replacement image.

An untranslated initial entry is an unstarted case: no source body has run and
no delegated request has been published. At `10ef078a`, capture registers the
entry, releases its pending capture lease and uses ordinary C acquisition so
cancellation and local execution retain their usual results. This is distinct
from handing back a progressed body or reporting that its body completed.

Production retains the selected source-trust policy. Source trust skips the
optional semantic and entry-input proofs; it supplies no missing instruction
lowering, acquisition ownership or lifetime reference. Decoded instructions,
selected text, source leases and actual source return words remain required.
The explicit checked analyzer remains a regression utility.

## Origin, executor and GS

**O** is the origin or waiter. **E** is the executor or combiner physically
running O's generated body. Logical task state and physical execution context
remain separate. The wrapper retains its two context words: O's saved kernel
GS base and logical task pointer. Physical RSP and the wrapper stack belong to E;
source SP/BP and source stack memory belong to O's logical execution.

Preserve the original GS lowering. `normal.py` represents ordinary GS memory
through `RGS`; `current_task` loads use logical `RCT`. `wrapper.S` imports
`PT_GS`/`PT_TASK` into those existing slots when used. A GS prefix alone does not
require an original-task service. Stable GS reads, including the stack guard,
use ordinary lowering. GS mutation and precisely identified task/CPU-context
operations retain their declared instruction or API contracts. No hardware GS,
task identity or complete kernel context switch is implied.

## Current-position handback

On untranslated code, O resumes at the first source instruction E has not
executed, using the current IP, GPRs and source SP/BP. Preserve all completed
memory effects and acquired locks. The entry packet is not a substitute for
current logical state after progress. Neither a body prefix nor a completed
control transfer may run twice.

| Stop boundary | Required source position and stack state |
| --- | --- |
| Ordinary source instruction has not executed | Resume at that instruction, with its current operands and pre-instruction source SP. |
| Direct or indirect CALL already selected its target and pushed its source return word | Resume at the target. Preserve the pushed word and post-push SP; do not execute the CALL again. |
| RET already read/popped its source return word, including any encoded adjustment | Resume at the resulting target with post-RET SP; do not pop or adjust again. |
| JMP or conditional branch already selected an untranslated target | Resume at the selected target with the resulting current packet; do not repeat prior work. |

Actual CALL words and RET values govern source execution. An inherited caller
frame can exist before capture. The required handback therefore cannot depend
on replaying from a lexical lock entry or inventing a new CALL/RET pair.

The required general handback covers untranslated CALL, RET and JMP paths.
It does not turn memory faults, malformed packets, lost source references or
budget failures into arbitrary successful recovery. An unstarted refusal,
a progressed handback, a completed body and an execution error stay distinct.

Flags and SIMD restoration are deferred and unsupported for this phase's
general handback. Existing narrowly defined arithmetic-flags capture or restore
paths do not establish arbitrary flags/SIMD preservation. IRQ/NMI conflict
handling is also deferred. These limits must remain explicit in implementation
and validation reports; this phase does not add their completion requirements.

## Learning and image replacement

Keep CALL and IJ learning distinct. An untranslated direct callee uses the
existing CALL miss record. An actual indirect CALL, indirect JMP or RET miss
uses `KD_EXE_IJ_MISS` with the actual target and existing source-site convention.
The original IJ table keys identify the source instruction's next IP. Do not
invent `CALL_MISS(target, 0)` for an indirect edge or confuse a metadata status
with a C dispatcher return value.

The existing daemon appends direct callees to `callee_table.txt` and actual
source/target pairs to `ij_table.txt`, then recompiles. Reports retain the bound
image identity; an old-generation miss must not overwrite a newer generation's
metadata. Publication checks the expected base generation before replacing the
entry's current image. A bound immutable image and its source lease remain live
through that invocation and its final retirement. Publication is not evidence
that any generated body executed or returned.

## Selected state-query execution

`kd_mmap_assert_held_write`, `kd_mmap_assert_held` and `kd_mmap_is_locked` use the
original JIT as ordinary decoded helpers. Their discovery records remain, but
operation identities 14/15/16 exclude them from runtime controls and returning
Native services. Synthetic display labels do not determine that classification.
The [admission policy](admission.md#selected-rwsem-state-queries) defines the exact
partition. Ordinary cold CALL/IJ learning still applies; this selection does not
force every downstream helper into translation or require eager callee closure.

The implemented narrow Native interval at `15f1c08a` uses the two-argument Boolean
`kd_service_write_owned`. Its descriptor uses the existing
`KD_SERVICE_CALL_ATOMIC_ORIGIN` context and word result. O executes that exact
runtime proof while E is suspended, then E resumes the same immutable image.
Keep the exact task, service token, request/phase generation, physical owner and
pickup checks. A reader count, generic locked observation or translated logical
task load cannot replace that proof.

An earlier follow-on selected pure queries on E and permanent O takeover with
immediate requeue. The [dated work-order record](compiled_mm_continuations.md#approved-follow-on-permanent-takeover-and-executor-local-pure-queries)
preserves that proposal and its original implementation boundary. It is not a
claim of completed queued role exchange or a specification for a later redesign.

`BALANCED_ORIGIN` is not the selected class for this interval: it rejects retained
spin/RCU state. `ATOMIC_ORIGIN` preserves the origin's actual pins/RCU under the
existing context contract; it does not remove preparation preconditions. A
preparation rejection is fail-stop, not automatic native handback. Other query
operations and Native services keep their existing classifications and behavior.

## Owners, services and retirement

Returning instruction/API services and terminal handback serve different roles.
A declared returning service executes only its specified interval and may
resume E at its validated continuation. Encountering ordinary untranslated code
hands the rest of that invocation to O. Native execution after such handback
does not implicitly reenter JIT.

Every physical acquisition, nested owner, reader credit, source/task/stack
reference, pending service and release ACK retains its exact identity. A
completion counter or queue notification cannot replace those records. All
participants in an object keep the same backend protocol.

For a retained worker request, the required handback preserves custody of every
live owner and routes O's later operations on E-owned gates to those records.
Retain source, frame, stack, task and provider lifetimes until the
last required acknowledgment and retirement. E can then return to its service
loop; it has no implicit public writer acquisition of its own. The legacy
single-root native handback cannot substitute for an entire retained owner list.
The retained worker route is wired at `a6fe0bb2`. The `da55414f` Native-service
join exercises production packet acceptance, typed release and final-ACK code
with supplied task/physical primitives; its limits are recorded below.

For genuine reader credits created by local or Native-first downgrade, Native
custody transfers the existing credit without decrementing it. O's matching
`up_read`, or a supported non-owner release of that real credit, consumes it.
That final decrement performs no later object access, allocation or scheduling.
E retains any other exact owners and release/ACK obligations. The historical
partial probe below does not establish arbitrary nested-owner coverage.

A downgrade consumed by the JIT proxy creates no anonymous reader credit. It
retains the exact physical writer and selected phase while the same root runs
its logical read tail. Matching typed `UP_READ` releases that writer once and
completes its physical/phase ACKs. Native handback after this transition retains
the same route. This final proxy release requires the original logical task in
ordinary task context; it can wait for physical release/ACK and does not inherit
the real-reader final-decrement contract. Ordinary readers remain local.
[Rwsem implementation](rwsem_implementation.md#local-writers-cancellation-and-downgrade)
defines the supported context and non-owner boundaries. Cancellation, readiness
and retirement keep their existing exact protocols.

Current pooled-slot retirement is also a resolved design: E finishes packet
acceptance, all E-owned releases and recursive stack unwind, then performs
synchronous cleanup. Hold CPU-hotplug protection across the online check and
home-CPU callback; an already-offline home CPU uses serialized explicit per-CPU
retirement. The [lifetime guide](lifetimes.md#selected-retained-handback-retirement)
defines the ordering and final-access rules. No new asynchronous cleanup queue
is selected. TCLock-style waiter reclamation is optional later work; waiter-side
final-use ACK/pinning simplification is not required in this phase.

## Source audit and implementation status

The following observations are static inspection of `da55414f` unless an
earlier checkpoint is named. The separate validation record below identifies
the build/component checks and their limits.

| Source and symbol | Confirmed observation and limit |
| --- | --- |
| [`disassem.py`](../../disassem/disassem.py), `dis_assem` | Uses `trusted_source=True`; disables eager ordinary-callee closure with `direct_call_closure = False`. Ordinary source-window and graph-work bounds remain. Cold eligible ABI2 images select the current-position miss requirement without needing an encountered returning service. |
| [`normal.py`](../../disassem/normal.py), `is_current_task_operand` and ordinary operand lowering; [`asm_head.h`](../../include/asm_head.h) | Distinguishes saved-origin GS addressing, logical task, virtual SP/BP and physical wrapper state. This is the original lowering, not proof of complete task-context equivalence. |
| [`special_inst.py`](../../disassem/special_inst.py), `special_inst_dispatch`; [`indirect_jump.py`](../../disassem/indirect_jump.py), `make_jump_table` | CALL/RET lowering uses the source stack and exports the post-transfer FULL miss packet. Four retained-miss tests pass at `a6fe0bb2`; packet checks do not validate loaded-provider handback. |
| [`wrapper_entry.inc`](../../kernel_module/execution/wrapper_entry.inc), `kd_jit_retained_miss`; [`exe.c`](../../kernel_module/exe.c), `kd_exe_dispatch` | Validates current packet/source identity and classifies actual CALL versus IJ learning. The retained path produces `KD_EXE_RUN_HANDOFF`, now consumed by `kd_service_run_scope` and `kd_service_handoff`. |
| [`daemon.c`](../../daemon/daemon.c) and [`workspace.inc`](../../daemon/workspace.inc), `make_callee_cmd`/`make_ij_cmd` | Separate actual CALL and IJ metadata drives subsequent compilation. This code is not a synchronous current-invocation image join. |
| [`images.inc`](../../kernel_module/execution/images.inc), `kd_image_report`/`kd_image_publish` | Reports check the currently published image; immutable publication rejects a stale base generation and publishes the replacement separately. Existing frame bindings are not rewritten by learning. |
| [`wrapper.S`](../../include/wrapper.S), image header; [`exe_info.h`](../../include/exe_info.h), `kd_image_protocol` | `ebae17c1` selected cold miss bit 13 without necessarily selecting the full-width header. `10ef078a` makes the wrapper and provider choose protocol 3 for bit 8 or bit 13 and adds a bit-13-only upload/bind fixture. This corrects the inspected source discrepancy; fresh fixture/publication validation remains pending. |
| [`kd_service.c`](../../kernel_module/kd_service.c), `kd_service_run_scope`/`kd_service_handoff`; [`native.inc`](../../kernel_module/execution/native.inc), `kd_exec_native_accept` and service wait | Retained owner routing, Native read-custody transfer, packet acceptance and typed release/ACK handling are committed. Routing is removed before the final request ACK. Three Native-service join modes pass at `da55414f` with supplied task/physical primitives; the separate partial live probe below leaves full retained-owner validation open. |
| [`device_session.py`](../../disassem/device_session.py), `runtime_rwsem_controls`; [`kd_rwsem_provider.c`](../../kernel_module/kd_rwsem_provider.c) | Operation-14/15/16 partition and narrow `ATOMIC_ORIGIN` custody proof preserve the original JIT and other service classifications. All six synthetic query-image cases pass at `da55414f`; the earlier writer-query fixture passes with supplied runtime observations. Actual public helper execution remains a live requirement. |
| [`kd_service.c`](../../kernel_module/kd_service.c), `kd_service_finish_handoff`/`kd_service_retire_handoff` | Synchronous home-CPU cleanup, hotplug protection through the callback, serialized offline slot release and missing-reservation rejection are committed. Four positive retirement modes and nine inconsistent-state rejections pass at `da55414f` with supplied CPU/work APIs; real CPU hotplug remains unverified. |
| [`spin/execute.inc`](../../kernel_module/spin/execute.inc), [`mutex/combiner.inc`](../../kernel_module/mutex/combiner.inc) and [`lock/mutex_calls.inc`](../../kernel_module/lock/mutex_calls.inc) | Executed-error and abort-cleanup checks still reject treating progressed execution as an unstarted retry. The committed negotiated handback path does not turn generic execution errors into native continuation. |

The original ordinary path still has a generic IJ-error branch in `exe.c` that
reports the edge and returns `KD_EXE_RUN_ERROR`. Its existence must not be
described as a general current-position restore implementation. The negotiated
current-position path is separate and has narrower checkpoint coverage.

Historical source `491d3a67` contains a spin waiter `ret_val == 4` branch that
calls `jump_to_saved_regs_in_cs`, labelled for `KD_EXE_IJ_MISS`. The examined
`kd_exe_on_call_hl` IJ branch instead returns `KD_EXE_RUN_ERROR`; no matching
producer for that old waiter notification was verified. The restoration routine
alone is historical mechanism code, not proof of a working end-to-end path.

### Runtime wiring and coverage boundary

The earlier working-tree query, custody and retirement changes are committed
in `a6fe0bb2`. Source inspection confirms the worker handback consumer, origin
packet copy/acceptance, exact Native owner registry routing and synchronous
cleanup. Subsequent frozen checks exercise central acceptance, typed owner
routing, read custody and terminal retirement. Resource and OSQ fixture repairs
also pass in later runs with identical production trees. Source wiring,
component fixtures and an actual loaded-provider execution remain distinct;
the fixture limits below prevent treating the joins as whole-stack execution.
The owner retains all code and `compiled_mm_continuations.md`.

## Documentation consistency audit

| Document | Correction or remaining coordination |
| --- | --- |
| [Reached-path record](../history/documentation-20261109/design/reached_path_execution.md) | Updated: separate emitter checkpoints are historical; miss handling, backend removal, runtime wiring and subsequent component results have distinct source identities. Failed and successful receipts remain intact. |
| [Lifetimes](lifetimes.md) | Updated: original bounded translation remains selected; source/image/owner rules and dated preparation records are retained. |
| [Design](../DESIGN.md) | Updated: historical local MM controls, retained candidates and the original JIT correction have separate scope; focused component results do not establish live validation. |
| [Execution](../JIT_EXECUTION.md) | Updated: ordinary recovery and retained-worker handback are distinguished from services, errors, completion and the remaining live proof. |
| [Implementation dependency map](compiled_mm_continuations.md) | Owned by the implementation writer. Contains the reuse inventory and selected Native read custody, original-JIT query and synchronous retirement designs; its earlier option discussions are historical, not unresolved choices. |
| [Register ABI](../JIT_REGISTER_ABI.md) | Updated within reserved scope: current service/miss exits, exact status domains, extended header and the historical cold-mask discrepancy/source correction are explicit; the two-word ABI is unchanged. |
| [Code map](../CODE_MAP.md) | Updated within reserved scope: retained service responsibilities, historical reached paths/revision and local versus retained MM execution are distinguished. |
| [README](../../README.md), formerly lines 55-71 | Updated within reserved scope: local-MM and all-count shared-device-MM losses are dated; newer unchanged mmap1 and retained-candidate evidence remain separate, with no promotion claim. |
| [Roadmap](../ROADMAP.md), formerly lines 19, 39-42 and 82-83 | Updated within reserved scope: subsequent actual thread/process application runs are acknowledged; original stage gates, repeated acceptance and new-candidate confirmation remain required. |
| [Admission](admission.md), formerly lines 54-56 | Updated within reserved scope: the three scalar hostcalls are distinguished from provider-registered returning services read by `dis_assem`. |
| [Kernel critical-section semantics](kernel_cs_semantics.md), formerly lines 86-88 | Earlier audit update retained unchanged in this refresh: copied-body/excluded-participant descriptions are historical; later scoped original-body syscall integration and deferred IRQ/NMI scope are explicit. |

## Validation and remaining work

### Current focused component results

The [fixed evidence bundle](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/README.md)
contains exact reply/freeze bytes, an [artifact manifest](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/artifacts.json)
and [source identities](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/source-identity.json).
These are the implementation owner's designated-VM results, reviewed offline
here. This documentation audit runs no builds, unit tests or live checks.

| Frozen source | Observed result and subsequent resolution |
| --- | --- |
| `a6fe0bb2` | W=1 build and seven drivers pass; query assertion fails and retirement fixture does not compile. Overall `passed=false`; exact first results remain below. |
| `da55414f` | W=1 build passes with compiler-name and return/frame diagnostics. Query images: six cases pass; retirement: four positive modes and nine inconsistent states rejected; Native-service join: write/downgrade/read modes pass. Segment lowering, final reader access, saved-state restore and 12 CALL-boundary cases pass. Resource/OSQ drivers fail obsolete-helper extraction, so overall `passed=false`. |
| `615cdb0b` | OSQ passes 26 scenarios and detects all 14 mutations. Repaired resource fixture compiles but fails its supplied ordinary-peer outcome. Overall `passed=false`; no new build. |
| `2bfbb8dc` | Only repaired resources rerun: 19,164 checks, zero failures, all 27 mutations detected. Focused receipt `passed=true`; no new build. |

The query repair accepts the legal continuation label and checks the actual
inner target and source CALL words. The retirement fixture fixes its supplied
CPU ID's signedness; production also rejects a missing reservation before
dropping references. Resource/OSQ extraction follows the canonical request
helpers, and the later resource repair supplies the ordinary peer through the
real physical-wait helper without creating a delegation gate for it.

All observed failures in these four attempts now have passing results, but the
earlier overall failures remain failures. `kernel_module`, `include` and `disassem` trees at
`615cdb0b` and `2bfbb8dc` equal `da55414f`; only on that recorded identity basis
are these component results carried together. This is not a new combined run,
full suite, warning-free build or performance result. Every attempt records
final idle and unchanged frozen inputs, with no module load or reboot.

### Component fixture limits

The Native-service join extracts production registry, packet-acceptance, typed
owner matching/release, final ACK and continuation handoff/retirement code.
Its O/E threads use supplied task binding, physical admission/release,
source-reference and preemption/IRQ primitives. Recursive E-stack unwind is
represented manually by removing a child and a synthetic anchor before terminal
handoff. Root storage remains accessible until `pthread_join`; it is not made
inaccessible immediately after the final ACK. Its Native-owner list starts
empty, so it does not exercise custody in a populated Native-owner list. Post-join root
overwrite and ordinary non-owner read release check that transferred credit
survives independently of the retired continuation.

Separate retirement modes make storage inaccessible with `mprotect(PROT_NONE)`
at final reuse and exercise production cleanup without later root access.
The concurrent `offline_pair` uses two supplied threads/dispatch guard and
checks count-before-bitmap reuse, with separate root storage. CPU/hotplug/work
APIs are supplied; these are not real CPU-hotplug results. Query-image cases
use synthetic source bodies with the actual original image backend. The
saved-state restore fixture covers two tags, 64 arithmetic-flag combinations,
GPR/SP and control flags using direct and configured-thunk substitutes; it
does not close general flags/SIMD or IRQ/NMI coverage.

No component group proves a real kernel/JIT stack switch, loaded retained MM
ownership, actual public query bodies, application completion or throughput.

### Installed identity and pending live proof

The pre-live [identity receipt](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/live-identity-2bfbb8dc.json)
verifies installed `kdscope5-kd`: 59 bundle files, 70 named source
files, 12 build files and four installed files, with `kd_mmap=on` and Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`. The unloaded provider has SHA256
`0184c67b4cebcf7a8d0e1a25f12f77e364c593330c4ed66dd35a7542f089de1c`
and targets `7.0.0-38-kdscope5`. The recorded running kernel is instead
`7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`,
boot UUID `0a2b2a34-caf7-4c63-9b38-d4f29a5a2d7d`. Installed verification is
not running-scope5 or loaded-provider validation.

Shared facade, layout and adapter bytes match the installed source. The
provider header and builtin restoration source match the recorded kernel
recipe and differ from this candidate only in comments; the generator's
builtin-local definition is recorded separately in the
[interface diff](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/kernel-interface-comparison.diff).
This interface review does not make all kernel inputs the candidate's revision
or establish general caller compatibility.

That receipt predates the live probe below and records preparation gaps at its
own checkpoint. Existing returned-body/unchanged-registry validators cannot
validate permanent handback followed by later image learning.
The [minimum live sequence](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/README.md#minimum-live-acceptance-preparation)
requires once-only prefix/CALL effects and exact resume position; nested typed
release, downgrade/read custody and cancellation joins; immutable old images
and later learned generations; the three actual public query bodies; then
focused real-syscall `mmap1_threads` and `mmap1_processes` checks. Fully returned
JIT episodes and handed-back prefixes need distinct acceptance and retirement
observations. The partial probe below does not complete that sequence or
establish mmap1 correctness or performance acceptance.

### Partial live probe and current stop

The [implementation record](compiled_mm_continuations.md#opt-in-cold-and-learned-continuation-probe)
retains the stopped attempts and the opt-in generic continuation probe. Its
live source is `58af0a5303052a57925f96b6e973b29d533c70d2`, with frozen
manifest `b97edaaaef98e856219787ccbc2ca8ad242703813ec9efb77ad2d3ce6590706d`.
The saved live reply verifies running scope5 Build ID
`5f2fce72a33480f6e79a79b374b21a0db377ecd1`, `kd_mmap=on`, boot UUID
`b19adc77-b8d9-4060-93ab-e2bb8635a5a8`. It is separate from the earlier
unloaded-provider identity receipt.

| Observation | Evidence status |
| --- | --- |
| Cold direct CALL and actual indirect JMP | Both live phases pass their exact current-position handback checks, with distinct O/E identities and useful effects once. |
| Later RET handback | Inspection finds IP equal to the actual source return word, SP equal to leaf-entry SP plus eight, and useful effects once. The checker did not handle that post-pop continuation; the run exits 1 with `DATA_ERROR` and the learned-return phase incomplete. This is an observation, not a passing overall live result. |
| Failure cleanup | The controller resumes the paused daemon before its no-child stop check, allowing a compiler child to start. Its saved session has `drained=false` and `translator has not exited`; preserve that failed cleanup verdict. |
| Subsequent manual cleanup | After the child completes, the exact retained daemon is stopped, retirement reports zero modules/frames/writers, helper registration is released and both modules unload normally. Final idle is verified without force unload. This later cleanup does not rewrite the failed session. |
| Candidate `bccf877c` | Adds bounded RET-continuation learning waves, exact post-pop checking and termination-before-resume daemon shutdown ordering. These harness fixes have not been tested; freezing their inputs is not a test pass. |

The later recovery receipt verifies the original `7.0.0-38-kdlock1`, Build ID
`b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, boot UUID
`73f3cf44-38b5-4502-936b-882d5c784eef`, idle state and empty `next_entry`.
No test modules or daemon remain active. Saved local replies are under
`/tmp/kdlock-handoff-live-third-58af0a53`,
`/tmp/kdlock-handoff-third-inspect-58af0a53`,
`/tmp/kdlock-handoff-third-cleanup-58af0a53` and
`/tmp/kdlock-normal-return-confirmed`; this audit reads them offline.

At that checkpoint, the implementation turn and one continuation stopped at
the platform's risk flag. The owner reported no supported review interface, so
an execution approval request was not submitted and the targeted probe stopped.
Its nested/read-tail and later returned-image joins remain unaccepted by that
checker. The [later independent mmap1 results](../VALIDATION.md#retained-original-jit-and-proxy-read)
have their own source and evidence scope; they do not rewrite this failure.

### First frozen runtime checks at a6fe0bb2

The [copied receipt](../../bench/results/10.176.26.71/tests/compiled-mm-handback-components-da55414f/a6fe0bb2-checks.json) has source
`a6fe0bb269642cf2dd6f07c3430b6933f9c0557a` and frozen root
`/root/kdlock-inputs/handback-queries-a6fe0bb2`. Its manifest SHA256 is
`ba3ad40419eccc67348af2f907a873ee3e564871fda38bd6b71c2001dab5d9d6`;
input-state SHA256 is
`d3138921d8529b9b96dfa0b5f6b36bcb920b12cc42d6518d2400d70088a10c10`.
The provider builds with W=1 against the recorded scope5 build directory while
the guest remains on `7.0.0-38-kdlock1`; no module load or reboot occurs.

| Affected check | First frozen result |
| --- | --- |
| `codegen/test_rwsem_query_images.py` | Fail: six tests, one failure. The test rejects a legal return-continuation label as if it proved Native routing; its subsequent `da55414f` result is separate. |
| `mutex/test_writer_query.py` | Pass: production query/registration component with supplied O/E runtime observations, not live task execution. |
| `mutex/test_service_retirement.py` | Compile failure: signedness comparison under `-Werror=sign-compare`. No fixture execution pass. |
| `mutex/test_admission.py` | Pass: 15 deterministic component cases for actual queue, phase, PICKUP and cancellation code. |
| `codegen/test_native_rwsem_contract.py` | Pass: 81 Native writer-custody component checks, including non-LIFO objects and ten records. |
| `codegen/test_retained_misses.py` | Pass: four generated-packet tests. |
| `codegen/test_returning_calls.py` | Pass: 21 tests. This does not replace the older checkpoint's eight failures. |
| `execution/test_jit_entry_scope.py` | Pass: 9,342 checks, zero failures. |
| `infrastructure/test_mmap_rwsem_generation.py` | Pass: generated MM retains the builtin core and ordinary provider binding/capture interface. |
| W=1 provider build | Return code 0 with objtool warnings; this is not warning-free or loaded-provider validation. |
| Overall receipt | `passed=false`, `final_idle=true`, `frozen_inputs_unchanged=true`, `no_module_load=true`, `no_reboot=true`. |

These are component/synthetic/generated-packet results. They do not establish
the central service packet-acceptance/final-ACK path, an executed online/offline
retirement fixture, live JIT handback, current mmap1 behavior or performance.
The first failures remain recorded. The subsequent runs above provide their
separate results without changing this receipt's failed overall verdict.

### Earlier miss-handling and backend-removal checkpoints

The implementation owner ran frozen `ebae17c1` in the designated VM. This audit
read the copied receipt at
`/tmp/kdlock-original-miss-checks-20261104/reply.json`; its `source_commit` matches
the inspected checkpoint. The VM record is
`/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/original-miss-checks-20261104/result.json`.

| Affected check | Recorded result |
| --- | --- |
| `codegen/test_retained_misses.py` | 3 tests pass; generated packets cover the post-pop RET target, pushed direct-CALL word and generic-JMP edge. |
| `codegen/test_segment_codegen.py` | Pass, return code 0. |
| `execution/test_jit_entry_scope.py` | Pass: 9,342 checks, zero failures. |
| `codegen/test_returning_calls.py` | Fail: 21 tests run, eight failures. |
| `execution/test_mutex_images.py` | Fixture compilation fails, including missing integer type declarations and `kd_service_calls_pin` declaration; no fixture execution pass. |
| W=1 provider build | Return code 0 with objtool warnings; warning-free coverage is not established. |
| Overall receipt | `passed=false`, `final_idle=true`, `no_module_load=true`, `no_reboot=true`. |

These are the owner's VM checks, not tests run by the documentation audit.
Passing packet/dispatcher fixtures do not establish loaded-provider execution,
the cold uploaded-header round trip, retained-owner custody transfer or actual
application behavior of the corrected backend. No new live handback or timing
result is established for this checkpoint. Final idle state is separate from
per-request ownership and drain proof. The failures remain failures while the
owner investigates them; no later result replaces this receipt.

Checkpoint `10ef078a` subsequently removes the separate instruction backend,
changes extended-header selection to bit 8 or bit 13 and adds header/fixture
repairs. Static inspection confirms matching wrapper/provider selection and no
production references to the removed reached-JIT entry points. No fresh test,
provider-build, loaded execution or application result was supplied for that
checkpoint alone. The later `a6fe0bb2` receipt above has its own source identity;
neither it nor the earlier mixed receipt is a rerun of `10ef078a`.

The [indexed reached JIT record](../../bench/results/10.176.26.71/tests/reached-mm-jit-indexed-20261104/README.md)
belongs to provider `626bd9fb78d1b2876534dce77df8aa213cfabbb9` and the separate
instruction emitter. It records focused execution and actual mmap1 proofs, with
failed performance acceptance and no Nano run. Those receipts do not validate
the restored original JIT pipeline or its new handback path. Earlier interpreter
results, original-image measurements and local-MM comparisons remain separate.

Required follow-up evidence includes current-position CALL/IJ/RET/JMP packets,
one-time CALL push and RET pop, actual miss learning and later replacement,
generation-specific bindings, ordinary and retained-owner handback, completed
effects, exact unlock/ACK routing and final retirement. A newly published image,
an entered body or a restored GPR packet alone cannot establish this chain.
Run basic plus directly affected checks on the designated VM under the existing
execution rules; full suites require an explicit request. This audit
does not run new VM work. Subsequent focused receipts above cover the repaired
groups, central service join and supplied online/offline retirement components.
The partial live probe above supplies two passing cold phases and exact RET
observations with a failed overall result. Remaining joins still need their own
accepted/retired episodes; the untested harness fixes and successful component
joins cannot supply them. Those targeted joins remain unaccepted; this audit
runs no new execution work. Later application and integration evidence is
indexed in [validation](../VALIDATION.md#retained-original-jit-and-proxy-read).

Flags/SIMD restoration and IRQ/NMI conflict remain deferred. Whole-kernel
coverage, unsupported configurations and general performance acceptance remain
separate from these historical checks. Current integration and application
claims require their separately recorded source-specific receipts.
