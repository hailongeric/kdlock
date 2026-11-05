# kdlock lock replacement contract

This guide records the selected execution contract for kdlock lock replacement.
It applies to the correction on `codex/mmap-reached-jit` in
`/tmp/kdlock-reached-path-translation`; it does not claim that master implements
the correction or that all kernel locks have been replaced. Native critical
section bodies, surrounding algorithms and userspace syscall paths remain
unchanged. This is a general lock replacement task, including its MM consumers.

The runtime implementation checkpoint is
`a6fe0bb269642cf2dd6f07c3430b6933f9c0557a`. It wires retained current-position
handback, Native read custody, the selected original-JIT state queries and
synchronous retirement. Earlier `ebae17c1` adds miss packets; `10ef078a` removes
the separate instruction JIT and corrects image-header selection. Requirements,
committed source and validation have distinct status: the first frozen `a6fe0bb2`
checks fail overall, with seven passing groups and two failures under repair.

Subsequent selected designs are recorded in `ebf0aa4c` for Native read custody,
`898b9d1c` for the three original-JIT state queries and `c0bb9ccd` for synchronous
home-CPU retirement. Those are design/documentation checkpoints. Their runtime
wiring is now committed in `a6fe0bb2`; final validation and central service
acceptance/final-ACK coverage remain pending. No module load, live handback or
new application result follows from the first build/component receipt.

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

Preserve the narrow Native interval at the existing two-argument Boolean
`kd_service_write_owned`. Its selected descriptor uses the existing
`KD_SERVICE_CALL_ATOMIC_ORIGIN` context and word result. O executes that exact
runtime proof while E is suspended, then E resumes the same immutable image.
Keep the exact task, service token, request/phase generation, physical owner and
pickup checks. A reader count, generic locked observation or translated logical
task load cannot replace that proof.

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
The retained worker route is wired at `a6fe0bb2`. Its central packet-acceptance
and final-ACK behavior is not yet covered by the reported component checks.

The selected Native read-custody path transfers the existing downgraded read
credit without decrementing it. O's normal `up_read` or `up_read_non_owner`
consumes that credit. Custody transfer is not physical unlock. A later routed
downgrade transfers its newly created read credit under the same rule. E retains
any other live owners and their exact release/ACK obligations. The decision and
source wiring are established; integrated packet acceptance, routing and lifetime
behavior remain unverified by a loaded-provider run.

Ordinary readers remain local. The previously implemented delegated-writer
downgrade/read-tail transition has its own exact read credit; preserve it
without relabelling all reads as delegatable. Read-tail final release must not
add allocation, scheduling or post-release object access. Cancellation,
successful-ready priority, nested acquisition, queue readiness and retirement
remain governed by their existing protocols.

Current pooled-slot retirement is also a resolved design: E finishes packet
acceptance, all E-owned releases and recursive stack unwind, then performs
synchronous cleanup. Hold CPU-hotplug protection across the online check and
home-CPU callback; an already-offline home CPU uses serialized explicit per-CPU
retirement. The [lifetime guide](lifetimes.md#selected-retained-handback-retirement)
defines the ordering and final-access rules. No new asynchronous cleanup queue
is selected. TCLock-style waiter reclamation is optional later work; waiter-side
final-use ACK/pinning simplification is not required in this phase.

## Source audit and implementation status

The following observations are static inspection of `a6fe0bb2` unless an
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
| [`kd_service.c`](../../kernel_module/kd_service.c), `kd_service_run_scope`/`kd_service_handoff`; [`native.inc`](../../kernel_module/execution/native.inc), `kd_exec_native_accept` and service wait | `a6fe0bb2` wires the retained owner route, Native read-custody transfer, packet acceptance and typed release/ACK handling. Routing is removed before the final request ACK. Central acceptance/final-ACK execution coverage and loaded-provider validation remain pending. |
| [`device_session.py`](../../disassem/device_session.py), `runtime_rwsem_controls`; [`kd_rwsem_provider.c`](../../kernel_module/kd_rwsem_provider.c) | Committed operation-14/15/16 partition and narrow `ATOMIC_ORIGIN` custody proof preserve the original JIT and other service classifications. The first query-image group fails one assertion; the writer-query component fixture passes with supplied runtime observations. |
| [`kd_service.c`](../../kernel_module/kd_service.c), `kd_service_finish_handoff`/`kd_service_retire_handoff` | Synchronous hotplug-protected home-CPU cleanup and serialized offline slot release are committed. The provider builds, but the first retirement fixture fails compilation under signedness `-Werror`; no retirement fixture or live hotplug pass follows. |
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
cleanup. The implementation owner is repairing the first two check failures
and preparing focused central service-acceptance/final-ACK coverage. Those
repairs and new coverage have no rerun result recorded here. Source wiring,
component fixtures and an actual loaded-provider execution remain distinct.
The owner retains all code and `compiled_mm_continuations.md`.

## Documentation consistency audit

| Document | Correction or remaining coordination |
| --- | --- |
| [Reached-path record](reached_path_execution.md) | Updated: separate emitter checkpoints are historical; `ebae17c1` miss handling, `10ef078a` source removal and `a6fe0bb2` runtime/partial-check evidence have distinct status. Failed and successful receipts remain intact. |
| [Lifetimes](lifetimes.md) | Updated: original bounded translation remains selected; source/image/owner rules and dated preparation records are retained. |
| [Design](../DESIGN.md) | Updated: historical local MM controls, retained candidates and the committed original JIT correction with pending validation have separate scope and evidence. |
| [Execution](../JIT_EXECUTION.md) | Updated: ordinary recovery and committed retained-worker handback are distinguished from incomplete validation, services, errors and completion. |
| [Implementation dependency map](compiled_mm_continuations.md) | Owned by the implementation writer. Contains the reuse inventory and selected Native read custody, original-JIT query and synchronous retirement designs; its earlier option discussions are historical, not unresolved choices. |
| [Register ABI](../JIT_REGISTER_ABI.md) | Updated within reserved scope: current service/miss exits, exact status domains, extended header and the historical cold-mask discrepancy/source correction are explicit; the two-word ABI is unchanged. |
| [Code map](../CODE_MAP.md) | Updated within reserved scope: retained service responsibilities, historical reached paths/revision and local versus retained MM execution are distinguished. |
| [README](../../README.md), formerly lines 55-71 | Updated within reserved scope: local-MM and all-count shared-device-MM losses are dated; newer unchanged mmap1 and retained-candidate evidence remain separate, with no promotion claim. |
| [Roadmap](../ROADMAP.md), formerly lines 19, 39-42 and 82-83 | Updated within reserved scope: subsequent actual thread/process application runs are acknowledged; original stage gates, repeated acceptance and new-candidate confirmation remain required. |
| [Admission](admission.md), formerly lines 54-56 | Updated within reserved scope: the three scalar hostcalls are distinguished from provider-registered returning services read by `dis_assem`. |
| [Kernel critical-section semantics](kernel_cs_semantics.md), formerly lines 86-88 | Updated within reserved scope: copied-body/excluded-participant descriptions are historical; later scoped original-body syscall integration and deferred IRQ/NMI scope are explicit. |

## Validation and remaining work

### First frozen runtime checks at a6fe0bb2

The copied receipt is
`/tmp/kdlock-handback-queries-a6fe0bb2-checks/reply.json`, with source
`a6fe0bb269642cf2dd6f07c3430b6933f9c0557a` and frozen root
`/root/kdlock-inputs/handback-queries-a6fe0bb2`. Its manifest SHA256 is
`ba3ad40419eccc67348af2f907a873ee3e564871fda38bd6b71c2001dab5d9d6`;
input-state SHA256 is
`d3138921d8529b9b96dfa0b5f6b36bcb920b12cc42d6518d2400d70088a10c10`.
The provider builds with W=1 against the recorded scope5 build directory while
the guest remains on `7.0.0-38-kdlock1`; no module load or reboot occurs.

| Affected check | First frozen result |
| --- | --- |
| `codegen/test_rwsem_query_images.py` | Fail: six tests, one failure. The test rejects a legal return-continuation label as if it proved Native routing; repair and rerun remain pending. |
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
The first failures remain recorded while repairs are prepared. Final validation
is pending a separately identified frozen rerun; no uncommitted repair is a pass.

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
Run basic plus directly affected checks on the designated VM when authorized by
the implementation owner; full suites require an explicit request. This audit
does not run or authorize new VM work. The first `a6fe0bb2` checks cover the
listed components. Repairs for the two failed groups and the prepared central
service-acceptance/final-ACK checks need a separately identified frozen rerun.
Online/offline retirement fixture execution and loaded-provider validation are
not supplied by the successful provider build or query/custody components.

Flags/SIMD restoration and IRQ/NMI conflict remain deferred. Whole-kernel
coverage, unsupported configurations and general performance acceptance remain
separate from this correction. No full runtime acceptance, promotion or speedup
follows from this contract.
