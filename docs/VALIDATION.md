# kdlock Validation

Latest complete matrix: **51/51 pass** on the
[resource registry](#resource-registry-coverage) freeze. An actual-JIT
positive, a context refusal and a pure-native control are different outcomes.
The project is not accepted as complete; older matrices are historical only.

Complete-matrix source identity: **173 inputs** in
`/tmp/kdlock-registry-matrix.RES3zj/source.sha256`.
Full source/log/artifact/command archive:
`/tmp/kdlock-registry-matrix.RES3zj.tar.gz`, SHA256:

```text
374dd5625799acc6d00bb5ac11cc2355ddba540c5149741227cbfd40421c9b20
```

The archive includes frozen source, generated artifacts, per-case commands,
status/dmesg/drain records, units, builds, kernel identities and guest-userspace
generated-predicate checks. /tmp paths are external local evidence, not
files delivered by a fresh Git checkout. The command manifest below keeps
invocations auditable. The two pure-native controls depend on an external
helper; they are not yet a self-contained fresh-checkout test. General evidence
packaging remains TODO P1. Losing an archive never makes recorded results new.

## Resource Registry Coverage

The resource-test increment freezes **173 inputs** against `560e4ec`. It
replaces `test_exe_hash.c` with `test_exe_registry.py` and its C fixture, updates
the unit runner and connects the existing entry-scope fixture to real lookup,
readiness and terminal publication functions. Production module, translator,
daemon, workload, wrapper ABI and guest-kernel inputs are unchanged.

At **2026-09-08 19:15:19 +08**, preflight passes all **40 unit programs** and
the independent **25-case admission audit**, without skips. Default and
selftest+NUMA kdlock builds, workload module and daemon build checks pass;
default module `.text` remains
`37362e3c49f513089a6f6bb9647f20d41a07afb69ffef4d34bc3ac808f60a712`.
Source/config/build/live kernel identity is unchanged. The recovered VM and
existing snapshot are verified before any live load; no restart is needed.

| New component evidence | Scope |
| --- | --- |
| Production registry: 8433 checks, zero failures | Real init/add/lookup/ready/publish/exit and device read/write decisions; 64-block and partial-pool exhaustion, cleanup, stable prior entries, repeated registration and bounded probes |
| Seven detected mutations | Partial publication, duplicate pool consumption, early pool refusal, premature readiness, lost terminal rejection, hidden last slot and out-of-range upload; each compiles then fails assertions |
| Real registration gate contention | 24 guest pthreads issue 2400 registrations across six colliding keys; six entries/blocks, no duplicate allocation; readers run after join |
| High-level entry: 136 checks, zero failures | Existing scope tests plus 14 unavailable spin/mutex root cases using real lookup/ready; no wrapper calls, full frame/GPR/stack/table snapshots unchanged |

Allocator, executable-permission and user-copy APIs are substitutes. The
511-slot full-table case seeds synthetic metadata: ordinary registration runs
out of its 64 code blocks first. The entry fixture substitutes wrapper/lock
primitives; neither fixture proves live pool saturation, native queue behavior,
IRQ/preemption semantics or concurrent executable replacement. The resource
inventory and remaining mutex-model gaps are in
[JIT_EXECUTION](JIT_EXECUTION.md#6-资源拒绝与测试边界) and [TODO](TODO.md).

Initial component evidence is retained in `/tmp/kdlock-registry.nVHMHh/`.
Its first attempt is a compile adaptation failure, not a passing test:
kernel mixed-sign comparisons trigger userspace `-Werror`. Only the unchanged
production include adopts Kbuild's sign-comparison warning policy; fixture
code retains strict warnings. Subsequent registry and joined entry runs pass.

**Complete matrix, 2026-09-08 19:17:36-19:36:12 +08:** all 51 selectors in the
[command manifest](#current-matrix-manifest) pass on this freeze, comprising
**37 actual-JIT, 12 context refusals and two native controls**. All nine main
modes 0/1/2/3/4/5/6/7/8 have matching returned body records, respectively
**4/4/4/669/1/411/4/2/2**, and correct protected states. Mutex positives explicitly
use `mutex_jit=1`; mode 5 records 411 matching hostcall exits/executions/resumes.
All eight register continuation gates, four held-B/PENDING gates, eleven
depth/remote cases, late-policy and mixed-owner cases also pass. Refusal cases
retain zero JIT; no earlier result substitutes for a current failed gate.

The mixed-mutex run observes four node-overflow fallbacks, the expected one-shot
task-allocation failure, 4392/4392 origin acquisitions/releases and zero active
tasks/waiters/reserved nodes. Learned mutex-depth again executes the expanded
11778 -> 12512-byte helper image, reaches three real capacity exits, retains
seven children at each exit and finishes 12017 state transitions. Four native
starts/completions, 25 owner unlock notifications and 2012/2012 origin counters
match; `jit_success=0` is expected for these partial-JIT/native completions.
These are live protocol observations separate from the new registry fixtures.

At **19:38:38 +08**, postflight repeats all 40 units and 25 audit cases without
skips, including 8433 registry checks, seven detected mutants and 136 entry
checks. All 173 host/guest hashes, default module `.text`, 18 kernel source
files, config, nine build files and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` match. All 51 fault scans are empty
and all callers/modules drain. Existing manual-stack objtool warnings remain.
No guest-kernel edit/build/install, VM restart or runtime capacity change is
introduced. The main matrix is closed for this freeze; broader C1/C2/C5 and
the explicitly deferred C3/C4 work are not closed by these results.

**Pre-commit recheck, 2026-09-08 19:50:42 +08:** all 173 host/guest runtime
and test inputs still match this matrix. The 40 unit programs, 25-case admission
audit and default incremental module build pass again, without skips. Registry
and entry checks remain 8433 and 136 respectively; all seven registry mutants
are detected. Kernel identity and module `.text` are unchanged, and no callers
or test modules are present before or after the check. No module is loaded and
no guest kernel is changed; this is not another live matrix. Evidence:
`/tmp/kdlock-registry-review.zshemK/verify.sh` and `guest.log`. Host Ruff/format,
changed C fixture formatting, all nine documents' local links and
`git diff --check` also pass. The matrix archive SHA256 is rechecked above.

## Scoped Learned Callees

Historical implementation checkpoint at `560e4ec`, **2026-09-08
18:14:38-18:33:14 +08**: the earlier 172-input matrix passes 51/51, comprising
37 actual-JIT, 12 context refusals and two native controls. It closes the
learned mutex-depth failure from `6858c58`; it is not the newer resource-test
freeze. Both pre/post units (40 programs, 24 guard/CALL methods), 25-case audit,
kernel identities and drains pass.

The scoped analysis propagates actual post-push CALL packets and RET effects
from the checked root, removes fabricated CALL fall-through, and checks all
generated RET targets. Default independent-root analysis, memory clobbers,
GS/context rejection, bounded work and the two-word ABI remain unchanged.
Execution and retained-owner capacity flow are described in
[JIT_EXECUTION](JIT_EXECUTION.md#51-学习后的直接-callee), not repeated here.

That run observes a 11778 -> 12512-byte learned mutex image, three capacity
exits, four native starts/completions, 25 owner unlock notifications and
12017 exact state transitions. An earlier three-case focused run independently
passes learned depth, ordinary mode 4 and stage-2 register continuation.
A separate static replay only establishes analysis feasibility, not execution.

| Retained archive | SHA256 |
| --- | --- |
| `/tmp/kdlock-learned-matrix.uCNLc7.tar.gz` | `3c3e892b2c578e95805fdceba4abec4fb2ee47e82716510ca806e02e345e7c73` |
| `/tmp/kdlock-learned-scope.67p5oR.tar.gz` | `2cb1c08bf0980f193d2b6f4242c9af7dee12ceeec75d45c5dbceffd9be7f6521` |

The subsequent documentation/version check at **18:50:39 +08** again passes
40 units, 25 audit cases and the default incremental build on the same runtime
inputs, without another live matrix. Evidence: `/tmp/kdlock-release-review.s9K2e0/`.
Full earlier detail is available with `git show 560e4ec:docs/VALIDATION.md`.

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

These same 51 selectors were rerun at **19:17-19:36 +08, 2026-09-08**.
All pass in their respective categories; per-case exits
are in `/tmp/kdlock-registry-matrix.RES3zj/results.tsv`. Earlier result tables remain
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

The nine-document snapshot before the `560e4ec` documentation cleanup is at
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
