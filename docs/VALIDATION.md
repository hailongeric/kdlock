# kdlock Validation

Latest complete matrix: **51/51 pass** on the
[scoped learned-callee](#scoped-learned-callees) freeze. An actual-JIT
positive, a context refusal and a pure-native control are different outcomes.
The project is not accepted as complete; older matrices are historical only.

Complete-matrix source identity: **172 inputs** in
`/tmp/kdlock-learned-matrix.uCNLc7/source.sha256`.
Full source/log/artifact/command archive:
`/tmp/kdlock-learned-matrix.uCNLc7.tar.gz`, SHA256:

```text
3c3e892b2c578e95805fdceba4abec4fb2ee47e82716510ca806e02e345e7c73
```

The archive includes frozen source, generated artifacts, per-case commands,
status/dmesg/drain records, units, builds, kernel identities and guest-userspace
generated-predicate checks. /tmp paths are external local evidence, not
files delivered by a fresh Git checkout. The command manifest below keeps
invocations auditable. The two pure-native controls depend on an external
helper; they are not yet a self-contained fresh-checkout test. General evidence
packaging remains TODO P1. Losing an archive never makes recorded results new.

## Scoped Learned Callees

**Complete matrix, 2026-09-08 18:14:38-18:33:14 +08:** all 51 selectors from
the [command manifest](#current-matrix-manifest) pass on the same frozen inputs:
**37 actual-JIT, 12 context refusals and two native controls**. This independently
repeats the focused learned-depth success below; no failed or earlier-source
case is substituted. Per-case commands, artifacts, source hashes, exit statuses,
dmesg and drain records are retained in the current archive.

Main mode 0/1/2/3/4/5/6/7/8 have respectively **4/4/4/674/1/439/4/2/2** returned
body records and passing protected-state oracles. Mutex positives explicitly
use `mutex_jit=1`; mode 5 has 439 executed/resumed hostcalls. All eight marked
register continuation selectors, four held-B/pending-B selectors, late-policy,
mixed-owner and eleven depth/remote fixtures also pass their actual-JIT gates.
Context refusals retain zero JIT and native controls remain a separate category.

`native-mutex-depth` again changes the image from 11778 to 12512 bytes and reaches
three genuine capacity exits inside the translated helper. It reports
`capacity=3 callee=1 native=12`, four native starts/completions, 25 owner-side
unlock notifications and 12017 exact state transitions, matching the focused
contract below. This validates the helper's JIT lock calls, not just its caller
prefix and not every possible original instruction or branch.

At **18:34:42 +08**, postflight repeats all **40 unit programs** (including
**24 guard/CALL methods**) without skips and the independent **25-case admission
audit** with zero failures. All 172 host/guest hashes still match. The 18-file
kernel baseline, config, nine build files and running Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` are unchanged. Default module `.text`
is the hash recorded below; existing manual-stack objtool warnings remain.
All 51 kernel-fault scans are empty and callers/modules drain. This closes the
current matrix, not the broader resource/context/lifetime tasks or deferred C3/C4.

**Focused checkpoint, 2026-09-08 18:10:29-18:11:43 +08:** the formerly failed
`native-mutex-depth` gate now passes with `mutex_jit=1`, as do ordinary mode 4
and its stage-2 register continuation. This three-case run is not a substitute
for a complete matrix. Evidence: `/tmp/kdlock-learned-scope.67p5oR.tar.gz`, SHA256:

```text
2cb1c08bf0980f193d2b6f4242c9af7dee12ceeec75d45c5dbceffd9be7f6521
```

The 172-input freeze changes only `context_policy.py`, `disassem.py` and two
Python test files from `6858c58`. The new conditional path has one actual root;
learned direct callees receive the real post-push CALL packet instead of an
independent seed. CALL fall-through cannot run ahead of RET effects. Every
return target must match the generated whitelist, including nonmatching-caller
targets; no balanced-stack or ordinary callee-saved assumption is added.
IJ history, indirect control, disconnected selected blocks, adjusting RETs,
effect/dispatch mismatch and existing budgets refuse this path. Default
independent-root analysis, GS/context rejection and native/control memory
clobbers remain. Purpose/constraint comments explain the new branches and tests.

Preflight passes all **40 unit programs**, including **24 entry-guard/CALL
methods**, and the **25-case admission audit**, without skips. Eight new methods
cover real generated CALL/RET results, automatic guarded helper execution,
callee memory corruption, GS rejection, disconnected targets, indirect control,
RET dispatch mismatch, IJ-history exclusion and bounded recursion. These are
separate from the live lock/owner observations below.

| Focused observation | Evidence |
| --- | --- |
| Real helper learning | First wave executes the JIT prefix and exits at `kd_resume_depth_mutex`; callers drain before daemon recompilation |
| Expanded image | Entry `0xffffffffc0a69597`, 11778 -> 12512 bytes; helper label and learned target present, image changed |
| Translated helper lock calls | Three real `-E2BIG` exits at `mutex_lock`, return RIP `0xffffffffc0a693b6` inside the helper; no synthetic pending failure injection |
| Retained native owners | Each capacity exit begins with eight held locks: outer A plus seven children; all three report `retained=7 children=8 valid=1` |
| Native completion / owner ACK | `capacity=3 callee=1 native=12`; four starts/four completions, 25 unlock notifications; 2012 native acquires/releases |
| Protected results | 12017 checked transitions; no replay or lost updates; first-wave and capacity outcomes remain separate |
| Ordinary mode 4 / register case | Both pass actual JIT; register case includes one marked JIT sample, 16 GPR/stack checks, flags unchecked |

The depth test has four returned body witnesses but `jit_success=0`: it is
deliberately completed by native CALL/capacity continuation, not entirely by
JIT. Its returned markers plus the helper's staged lock CALL and retained-owner
records prove translated helper execution; the first-wave prefix alone does not.
This does not prove that every helper branch or original instruction executes.
All three fault scans are empty and callers/modules drain.

An earlier static replay first stops because the old module capture lacks the
core-kernel return thunk. After read-only baseline verification, it augments
only core-kernel text, never replacing old relocated module bytes. The replay
then admits the expanded scope with 43 predicates; it does not assemble,
install or execute that captured code. Both attempts and the captured text are
retained separately inside the focused archive. The complete freeze adds the
`scoped_calls` diagnostic field and final test negatives after that replay.

Default and selftest+NUMA module builds pass with existing objtool warnings.
Default `.text` stays
`37362e3c49f513089a6f6bb9647f20d41a07afb69ffef4d34bc3ac808f60a712`;
the read-only source/config/build/live baseline checks pass. No guest-kernel
edit/build/install/restart, owner handoff, third wrapper argument, frame growth,
flags repair or immutable version is introduced. Broader C1/C2/C5 work remains;
C3/C4 are still explicitly deferred.

## Acceptance Contract

Generating `jit.S` or installing `jit.bin` is insufficient. Positive JIT selectors
require nonempty assembly/binary/disassembly artifacts, nonzero structured
kernel-text reads, checked daemon writes, and execution diagnostics matching
an inspected entry. The final chunk log precedes payload copy and cannot alone
prove successful publication. Runtime entry logs also precede the JIT call. Require a matching entry/lock
`JIT body witness: ... body=1` recorded after wrapper return, plus the exact
protected result and the appropriate completion/continuation checks.

The executable artifact must retain branch, rotate, multiply, scaled-index
access and dependent writes. Native replay checks all nine protected state
words, the exact operation count, and the expected number of active states.
Frames, waiters and slots must drain; kernel and protocol failures must be zero.
Modes 2/5 additionally require the named `ktime_get` stub, no service-callee
translation/runtime recompilation, and equal nonzero exit/execute/resume counts.
Mode 5 matches those to JIT completion and waiter resume. Modes 10/11 instead
require native-only publication, no execution/publication for rejected entries,
exact native GS/current probes, and rejection of attempts to reactivate them.

All mutex JIT cases verify `mutex_jit=1`. Ownership/resource accounting requires
`origin_acquires == origin_releases`, `active_tasks=0`, and no leaked waiter
slots. These origin counters count scheduler-owner intervals, not every direct
native API acquisition or nested B. Mode 3's in-CS guard requires
`inside=0 overlaps=0`; that guard does not instrument all nested A/B states.
Task allocation failures are zero except the deliberate one-shot test.

Mode 4 requires one executed A artifact, `nested_queued>0` and `nested_jit>0`:
A's combiner really contends on native B, obtains it, and resumes JIT through B
unlock. B no longer has a remote mutex waiter or a separate required artifact.

Native-continuation cases stop the daemon before execution and require an
ordinary generated CALL miss at the actual `kd_resume_native_probe` RIP. The
original task completes distinct per-request before/call/after records exactly
once; `kd_native started == completed > 0`, with no entry retry or lost state.
A JIT prefix plus native suffix is not counted as an all-JIT completion.
The optional completion-policy variant pauses rather than stops the daemon,
then resumes it to validate subsequent refusal without replay.

## Current Matrix Manifest

These same 51 selectors were rerun at **18:14-18:33 +08, 2026-09-08**.
All pass in their respective categories; per-case exits
are in `/tmp/kdlock-learned-matrix.uCNLc7/results.tsv`. Earlier result tables remain
historical and do not define current acceptance. Body records count returned
positive logs, not retired instructions, unique instructions or immutable
generations.

### Recorded Commands

All commands ran in the recovery guest project with
`KDLOCK_RECOVERY_CONFIRMED=1 LC_ALL=C`. Use the operations guide to confirm
snapshots, freeze/sync inputs, retain evidence and drain between cases.
This is a manifest, not an unattended command to run on the host.
The three cross-NUMA commands use corrected role placements; earlier invalid
CPU placements are excluded from the 51-case total. The external
`/tmp/kdlock-register-native-control.sh` used only by control-0/3 must not be
silently replaced by a JIT test or counted as delivered by this repository.

```sh
# mode-0
bash tests/test_09_jit_execution_modes.sh 0

# mode-1
bash tests/test_09_jit_execution_modes.sh 1

# mode-2
bash tests/test_09_jit_execution_modes.sh 2

# mode-3
bash tests/test_09_jit_execution_modes.sh 3

# mode-4
bash tests/test_09_jit_execution_modes.sh 4

# mode-5
bash tests/test_09_jit_execution_modes.sh 5

# mode-6
bash tests/test_04_spinlock.sh 6

# mode-7
bash tests/test_04_spinlock.sh 7

# mode-8
bash tests/test_04_spinlock.sh 8

# registers-4-2
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 4 2

# registers-1-2
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 1 2

# context-percpu-spill
env KD_CONTEXT_LOCK_API=percpu-spill bash tests/test_12_context_native_only.sh 3

# context-percpu-implicit
env KD_CONTEXT_LOCK_API=percpu-implicit bash tests/test_12_context_native_only.sh 3

# context-percpu-rotate
env KD_CONTEXT_LOCK_API=percpu-rotate bash tests/test_12_context_native_only.sh 3

# context-percpu-cmov
env KD_CONTEXT_LOCK_API=percpu-cmov bash tests/test_12_context_native_only.sh 3

# control-0
bash /tmp/kdlock-register-native-control.sh 0

# control-3
bash /tmp/kdlock-register-native-control.sh 3

# registers-0-1
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 0 1

# registers-3-1
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 3 1

# registers-1-3
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 1 3

# registers-4-3
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 4 3

# registers-8-2
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 8 2

# registers-8-3
env KD_NATIVE_REGISTERS=1 bash tests/test_10_native_resume.sh 8 3

# context-spin
bash tests/test_12_context_native_only.sh 10

# context-mutex
bash tests/test_12_context_native_only.sh 11

# context-mixed
bash tests/test_12_context_native_only.sh 3

# context-irqsave
env KD_CONTEXT_LOCK_API=irqsave bash tests/test_12_context_native_only.sh 3

# context-bh
env KD_CONTEXT_LOCK_API=bh bash tests/test_12_context_native_only.sh 3

# context-percpu
env KD_CONTEXT_LOCK_API=percpu bash tests/test_12_context_native_only.sh 3

# context-percpu-reg
env KD_CONTEXT_LOCK_API=percpu-reg bash tests/test_12_context_native_only.sh 3

# context-percpu-flow
env KD_CONTEXT_LOCK_API=percpu-flow bash tests/test_12_context_native_only.sh 3

# mixed-spin
bash tests/test_17_spin_native_protocol.sh

# mixed-mutex
bash tests/test_11_mutex_native_protocol.sh 1

# native-1-3
bash tests/test_10_native_resume.sh 1 3

# native-4-3
bash tests/test_10_native_resume.sh 4 3

# native-1-4
bash tests/test_10_native_resume.sh 1 4

# native-4-4
bash tests/test_10_native_resume.sh 4 4

# node-physical-1-0
env KD_CHAIN_TRACE_NODES=1 KD_CHAIN_NUMA=0 KD_CHAIN_FORCE_PROMOTION=1 bash tests/test_14_spin_frame_depth.sh 1

# node-physical-1-1
env KD_CHAIN_TRACE_NODES=1 KD_CHAIN_NUMA=1 KD_CHAIN_FORCE_PROMOTION=1 bash tests/test_14_spin_frame_depth.sh 1

# node-physical-2-0
env KD_CHAIN_TRACE_NODES=1 KD_CHAIN_NUMA=0 KD_CHAIN_FORCE_PROMOTION=1 bash tests/test_14_spin_frame_depth.sh 2

# node-physical-2-1
env KD_CHAIN_TRACE_NODES=1 KD_CHAIN_NUMA=1 KD_CHAIN_FORCE_PROMOTION=1 bash tests/test_14_spin_frame_depth.sh 2

# node-physical-8-0
env KD_CHAIN_TRACE_NODES=1 KD_CHAIN_NUMA=0 KD_CHAIN_FORCE_PROMOTION=1 bash tests/test_14_spin_frame_depth.sh 8

# node-physical-8-1
env KD_CHAIN_TRACE_NODES=1 KD_CHAIN_NUMA=1 KD_CHAIN_FORCE_PROMOTION=1 bash tests/test_14_spin_frame_depth.sh 8

# node-remote-plain
env KD_DEEP_TRACE_NODES=1 bash tests/test_21_remote_depth.sh 4 1

# node-multi-b-depth8-stage5-layer6-count3-owner1-reverse1-rename1
env KD_DEEP_TRACE_NODES=1 env KD_DEEP_DEFER_LAYER=6 KD_DEEP_DEFER_COUNT=3 KD_DEEP_CPUS=0,39,20,21,22,23,1,2,3,4,24,25,26,27,5,6,7,8,28,29,30,31,9,10,11,12,32,33,34,17,13,14,15,16,18,19,35 KD_DEEP_CROSS_NUMA=1 KD_DEEP_NATIVE_OWNER=1 KD_DEEP_REVERSE=1 KD_NATIVE_RENAME=1 bash tests/test_21_remote_depth.sh 8 5

# late-spin-policy
env KD_NATIVE_POLICY_COMPLETION=1 bash tests/test_10_native_resume.sh 0 1

# late-mutex-policy
env KD_NATIVE_POLICY_COMPLETION=1 bash tests/test_10_native_resume.sh 3 1

# native-mutex-depth
bash tests/test_10_native_resume.sh 4 5

# remote-late-2-cross-fixed
env KD_DEEP_NATIVE_OWNER=1 KD_DEEP_REVERSE=1 KD_NATIVE_RENAME=1 KD_DEEP_CROSS_NUMA=1 KD_DEEP_CPUS=0,39,20,21,22,23,1,2,3,4,24,25,26,27,5,6,7,8 bash tests/test_21_remote_depth.sh 4 2

# remote-late-3-cross-fixed
env KD_DEEP_NATIVE_OWNER=1 KD_DEEP_REVERSE=1 KD_NATIVE_RENAME=1 KD_DEEP_CROSS_NUMA=1 KD_DEEP_CPUS=0,39,20,21,22,23,1,2,3,4,24,25,26,27,5,6,7,8 bash tests/test_21_remote_depth.sh 4 3

# remote-late-4-cross-fixed
env KD_DEEP_NATIVE_OWNER=1 KD_DEEP_REVERSE=1 KD_NATIVE_RENAME=1 KD_DEEP_CROSS_NUMA=1 KD_DEEP_CPUS=0,39,20,21,22,23,1,2,3,4,24,25,26,27,5,6,7,8 bash tests/test_21_remote_depth.sh 4 4
```

## Commit Verification

**2026-09-08 18:50:39 +08:** a fresh pre-commit guest check passes all
40 unit programs, including 24 guard/CALL methods, and the independent
25-case admission audit, with no skips. The default module incremental build
passes; its `.text` remains
`37362e3c49f513089a6f6bb9647f20d41a07afb69ffef4d34bc3ac808f60a712`.
Evidence: `/tmp/kdlock-release-review.s9K2e0/verify.sh` and `guest.log`.

Both host and guest match all 172 runtime/test inputs of the complete matrix.
The source/config/build/live kernel baseline matches, including Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`; callers/modules are absent before
and after this check. No module is loaded and no guest kernel is rebuilt or
changed in this pre-commit check. This is not another live 51-case run.
The matrix's 51 zero exit statuses and both current evidence-archive SHA256
values are rechecked separately against the recorded results above.

The documentation cleanup keeps the execution flow and commands in
JIT_EXECUTION, ownership in DESIGN, and entry/exit state in JIT_REGISTER_ABI.
It condenses repeated historical validation prose into the index below without
deleting source, test or evidence files. Purpose/constraint comments accompany
the learned-callee implementation and its eight added test methods. Broader
resource/context/lifetime tasks and explicitly deferred version/flags work
remain in TODO, not silently marked complete. All nine local document link
checks, Ruff checks/formatting (59 Python files) and `git diff --check` pass.

## Historical Evidence Index

Older results belong to their own source freezes; none substitutes for the
current matrix. Repeated implementation narratives, obsolete next steps and
old mode-10/11 translated-GS result tables have been removed from active docs.
Current mode 10/11 require native-only refusal. Current contracts live in
[DESIGN](DESIGN.md), [ABI](JIT_REGISTER_ABI.md) and [TODO](TODO.md).

All prior detailed records through cross-window CFG completion remain in Git:

```sh
git show 6858c58:docs/VALIDATION.md
```

The nine-document snapshot immediately before this cleanup is also retained at
`/tmp/kdlock-release-review.s9K2e0/docs-before.tar.gz`, SHA256:

```text
2579b183ac6bf98a6e19378938c9b4c01212013b55b1ec81996195206877269a
```

### Matrix Progression

| Source checkpoint | Observation at that freeze | Evidence archive in /tmp |
| --- | --- | --- |
| `6858c58`, cross-window CFG | 50/51: 36 actual-JIT, 12 refusals, two native controls; learned mutex-depth fails expanded admission | `kdlock-mode8-matrix.HaCWga.tar.gz` |
| `1592e89`, guarded nested admission | 47/51: 33 actual-JIT, 12 refusals, two controls; mode 8, its two register gates and learned mutex-depth fail | `kdlock-guard-matrix.90lmMR.tar.gz` |
| `65e513d`, entry-guard foundation | 39 units/25 audit pass; focused 3 JIT + 1 refusal pass, mode 1/4 fail; predicates not yet enabled in production | `kdlock-guard-foundation.qaCvD5.tar.gz` |
| `7bf7054`, JIT episode scope | Complete matrix 37/51, 14 failures; later eight-case commit check 6/8, mode 1/4 still fail | `kdlock-jit-episode.lQFNLA.tar.gz`, `kdlock-docs-commit.Tm6d9w/` |
| Earlier whole-entry analysis candidates | RMW/identity/CALL facts retain 22 failing JIT gates; diagnostic CALL-phase prototype withdrawn, not an accepted fix | See investigation directories below |

The first four matrix/foundation archives above have these SHA256 values,
in table order; the documentation checkpoint is a directory, not an archive:

```text
8460f9fc2b217c3974db44888efa8a2c8277592f76f612541cc459145b409b74
231c916667b7c1b2e8d6e1ff71f9695d8978441e79d8ece2fa0e0e5dbaa57276
4e41af4531c564323f8751c3e439770a6f10c22a5de4739d0b0073661fea2178
049153a5fd1c185db6531716bd666d09b023a7e58ca3f7caf8dbc32ba0345687
```

Focused failed/intermediate attempts remain separate from those matrix results:

| Attempt | Observation | Archive SHA256 |
| --- | --- | --- |
| `kdlock-mode8-cfg.5HSbXp.tar.gz` | mode 1/4 pass; three mode-8 artifact waits and learned-depth fail | `365ce866d3e97b30b271db33fd9eb26312952095610fed458fc86d4148788b00` |
| `kdlock-mode8-readiness.EeKxsI.tar.gz` | Five JIT passes, learned-depth failure; not a full matrix | `6acc0b405511bede6354cf5e5bc8f13a288d1201b9be8d96af4335148bd10712` |
| `kdlock-guard-runtime.N6l1wz.tar.gz` | Failed cold-read ordering candidate | `4bc964e0f98697f580266767f35b6b3947a6eda20c28f6aace4b3cc4d0a936c3` |
| `kdlock-guard-complete-scope.qwFSxV.tar.gz` | Corrected cold-read ordering candidate, not matrix acceptance | `bf077f89d8edabaa829d31deb2a6417246e1184426f44124d868c8a123b11abf` |

### Investigation Directory Index

Paths below are relative to `/tmp/`. They locate earlier source/log records,
including failures and withdrawn experiments, not additional current passes.
Detailed outcomes and command coverage remain in the Git record above.
Temporary evidence can be lost; a checkout does not recreate these directories.

| Historical topic | Evidence directories |
| --- | --- |
| Entry Premise Investigation | `kdlock-entry-premises.8mGP9Y/` |
| Native Registration Phase Guard | `kdlock-native-phase.2oGMsX/` |
| Alias Origin Diagnostic | `kdlock-alias-origin.yXHEZn/` |
| Decoded CALL Effect Flow | `kdlock-admission-boundary.UQLmRm/` |
| Admission Address Diagnostics | `kdlock-admission-cause.P39W8G/` |
| Native CALL Phase Experiment | `kdlock-call-effects.VjBoN1/` |
| Whole-Word RMW Facts | `kdlock-rmw-words.V4gSiK/` |
| Identity Memory Writes | `kdlock-memory-identity.E8klOz/`, `kdlock-stack-provenance.KwcR2Z/` |
| CALL Return-Slot Facts | `kdlock-call-facts.gjpvhA/` |
| CFG Root Initialization | `kdlock-cfg-roots.LGKcon/` |
| Memory Value Forwarding | `kdlock-memory-masked.JK2xlS/`, `kdlock-memory-verified.3mqGs4/`, `kdlock-memory-values-lea.EqWx7V/` |
| Memory Value Candidate | `kdlock-memory-values-lea.EqWx7V/`, `kdlock-memory-values.0GA9UK/` |
| Memory Forwarding Audit | `kdlock-context-spill-audit.xmexdo/` |
| IR Memory Admission | `kdlock-context-memory.miJshl/` |
| Instruction-Internal IR Admission | `kdlock-context-ir.f26Zqp/` |
| Conditional-Move Admission | `kdlock-context-cmov.Oyghtm/` |
| Generated-Body Execution Witness | `kdlock-jit-body.Fbf8gE/` |
| CALL-Miss Register Witnesses | `kdlock-native-registers.JIwFuQ/` |
| Kernel-Only Execution Entry | `kdlock-kernel-entry-only.XHuRTO/` |
| Captured Kernel Baseline | `kdlock-kernel-baseline-verified.I4n5cI/`, `kdlock-kernel-baseline.SQbmuD/` |
| Context CFG Constants | `kdlock-context-flow-verified.Qb81Nt/`, `kdlock-context-flow-red.9a2MKf/`, `kdlock-context-flow-candidate.IS1I5d/` |
| Middle-Layer Readmission | `kdlock-readmission-middle-verified.qhexWm/`, `kdlock-readmission-middle-red.foBlt6/`, `kdlock-readmission-middle-candidate.cm0GDr/` |
| Live Virtual Readmission | `kdlock-live-readmission-final.EA3eGy/`, `kdlock-live-readmission.tgw4qr/`, `kdlock-live-readmission-candidate.479Crt/` |
| Live Virtual Refusal Continuation | `kdlock-live-refusal-verified.pSTmDB/`, `kdlock-live-refusal.UT1JW6/`, `kdlock-live-refusal-final.zDouQR/` |
| Virtual Preentry Refusal Return | `kdlock-virtual-refusal-final.mpbNe1/`, `kdlock-virtual-refusal.eXNmUN/` |
| Frame Refusal Queue Connection | `kdlock-frame-refusal.jlvfIx/` |
| Live Node Reservation Observer | `kdlock-node-observer-fixed.gttbqI/`, `kdlock-node-observer.0YjV0I/` |
| Node Producer Accounting | `kdlock-node-producers.HBWAxn/` |
| Full Frame Context Refusal | `kdlock-frame-capacity.r3eVYM/` |
| Combined Physical And Deferred Pressure | `kdlock-combined-chain.EOFx47/` |
| Buffered Deferred Observer | `kdlock-buffered-defer.tzUgSd/` |
| Nested Deferred-List Isolation | `kdlock-nested-deferred.CJaUFF/` |
| NUMA Physical Stack | `kdlock-stack-packet.Z7SjlC/`, `kdlock-numa-stack.dJwYA4/` |
| Repeated Admission And Multiple Followers | `kdlock-controller-affinity.cMByFO/`, `kdlock-native-readmission.nxc9Tt/`, `kdlock-multiple-followers.zTagtv/` |
| NUMA Admission Rejection | `kdlock-multi-deferred.djq6Xt/` |
| Deferred Queue Publication | `kdlock-deferred-final.IVjVjO/`, `kdlock-deferred-queue.dDogXz/`, `kdlock-deferred-enabled.CBgXNh/` |
| Deep Logical Chains | `kdlock-remote-depth-verified.aYZKlV/`, `kdlock-remote-depth.KzwWVF/` |
| Remote NUMA Placement | `kdlock-placement-final.sGAJ3o/`, `kdlock-remote-placement.C52xEm/` |
| Three-Executor Remote Progress | `kdlock-remote-chain-verified.EG8v2p/`, `kdlock-remote-chain.gssz7k/`, `kdlock-remote-chain-final.5bgk6K/` |
| Remote Ancestor Progress | `kdlock-remote-outer.xjNrNI/`, `kdlock-remote-outer-final.ra64uh/` |
| Spin Outer Progress | `kdlock-spin-outer-progress.STSvx7/` |
| Mutex Outer Progress | `kdlock-mutex-outer-progress.69mR7e/` |
| Pending After Outer Unlock | `kdlock-pending-after-outer.w8aUex/`, `kdlock-pending-after-outer-final.21j8at/` |
| CALL After Outer Unlock | `kdlock-after-outer-verified.2NcX4K/`, `kdlock-after-outer.qdijFn/`, `kdlock-after-outer-final.togail/` |
| Native OOO Continuation | `kdlock-native-ooo.m4gob6/` |
| Context Register Addresses | `kdlock-context-registers.RGNlPa/` |
| Native Mutex Release Races | `kdlock-mutex-signal-race.lIoQcx/`, `kdlock-mutex-signal-race.lIoQcx/final/` |
| Native Mutex Signals | `kdlock-mutex-signals.ACJNKo/` |
| Context Operand Spans | `kdlock-context-span.N7zrfR/` |
| Live Spin Routing | `kdlock-spin-live-routing.sn99wf/` |
| Context Address Admission | `kdlock-context-address.mDmwlm/` |
| Spin L/S Integration | `kdlock-spin-routing.bnjhgP/` |
| Spin Acquisition Tickets | `kdlock-spin-entry.bl9Q8p/` |
| Native Spin Gate Foundation | `kdlock-spin-gate.ZkhTgh/` |
| Spin Native Compatibility Audit | `kdlock-spin-interop.tBs8nq/` |
| IRQ/BH Lock Admission | `kdlock-context-api.WHliGt/` |
| Natural Combiner Frames | `kdlock-frame-chain.qdyDWa/` |
| Admission Symbol Visibility | `kdlock-context-symbols.3FE9WB/` |
| Independent Pending Spin | `kdlock-pending-spin.MsdJqx/` |
| Translated Shadow Capacity | `kdlock-spin-shadow-jit.URpltM/` |
| Live Spin Shadow Capacity | `kdlock-spin-shadow-live.PY19BU/` |
| Spin Shadow Capacity | `kdlock-spin-shadow.86Z7YN/` |
| Held-Lock Capacity | `kdlock-depth-capacity.zrtPOB/` |
| Independent B Ownership | `kdlock-pending-contention.JlIfcE/` |
| Pending Control Calls | `kdlock-control-call.QRYFZY/` |
| Backend Admission | `kdlock-backend-admission.RQ0Yyd/` |
| Daemon Launch Classification | `kdlock-launch-policy.acBUpR/` |
| Context Admission | `kdlock-context-policy.v7pZtt/` |
| Diagnostic Logging | `kdlock-jit-diagnostics.eiETOc/` |
| Prior Commit Verification | `kdlock-mutex-jit-commit.VzVf2T/` |
| Reproduction And Evidence | `kdlock-mutex-owner-20260905/`, `kdlock-native-final-20260905/`, `kdlock-jit-audit-20260905-1010/` |

## Native Registration Phase Guard

Historical helper gap, fixed before the current matrix:
`kd_exec_native_begin()` used to reject unsupported phases only after outer
unlock. Production-function tests showed that ENTERED/ACQUIRED/non-relay
COMPLETE or invalid phases could otherwise publish borrow state. This was
not a reproduced live misroute. Evidence: `/tmp/kdlock-native-phase.2oGMsX/`.

Current registration validates NONE, eligible PENDING or the supported spin
remote COMPLETE relay before publication/accounting, regardless of outer-lock
state. Later-phase failures are not authorized to replay. See
[the continuation contract](JIT_REGISTER_ABI.md#11-返回原-waiter).

## Captured Kernel Baseline

Historical prerequisite checkpoint, 2026-09-07 20:48:39 +08: 158 frozen inputs,
34 unit programs without skips and 16 integrations (13 actual-JIT, three
native-only) pass. No production lock/JIT change or guest kernel rebuild was
part of that increment. Evidence: `/tmp/kdlock-kernel-baseline-verified.I4n5cI/`
and `/tmp/kdlock-kernel-baseline.SQbmuD/`.

The current matrix repeats the scoped source/config/build/live identity check,
not the original full-archive member scan. Reproduction, captured identities
and limitations are maintained in [kernel_baseline/README](../kernel_baseline/README.md).
