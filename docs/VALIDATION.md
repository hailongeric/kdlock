# kdlock Validation

Latest complete matrix: **53/53 pass** on the
[mutex task lifecycle](#mutex-task-lifecycle) freeze. Actual-JIT positives,
context refusals, pure-native controls and kernel protocol probes are distinct.
The project is not accepted as complete; older matrices are historical only.

Complete-matrix source identity: **175 runtime/test inputs** in
`/tmp/kdlock-mutex-task-matrix.puvwk1/source.sha256`.
Full source/log/artifact/command archive:
`/tmp/kdlock-mutex-task-matrix.puvwk1.tar.gz`, SHA256:

```text
c7997a0432c15ddb32d9fef5a451ba12dcd243c725bf197aa0e3bb874eed7b14
```

The archive includes frozen source, generated artifacts, per-case commands,
status/dmesg/drain records, units, builds, kernel identities and guest-userspace
generated-predicate checks. /tmp paths are external local evidence, not
files delivered by a fresh Git checkout. The command manifest below keeps
invocations auditable. The two pure-native controls depend on an external
helper; they are not yet a self-contained fresh-checkout test. General evidence
packaging remains TODO P1. Losing an archive never makes recorded results new.

## Mutex Task Lifecycle

This increment against `a3642bb` combines the production mutex resource fixture
with opt-in `test_22`, which calls real task membership, native request/ACK,
mutex ownership and RCU functions. Kernel integration is guarded by
`KDLOCK_SELFTEST`; default runtime, wrapper ABI and guest kernel are unchanged.
Purpose/constraint comments and test flow are maintained in
[the lifecycle guide](JIT_EXECUTION.md#62-task-引用最终-ack-与-rcu).

Preflight closes at **2026-09-08 21:27:22 +08**: all 39 unit programs and 25
admission audit cases pass without skips, including the resource fixture's
15849 checks and eight compiled/detected mutants. Default/selftest+NUMA module,
workload and daemon builds pass; existing objtool/locale warnings remain.

**Complete matrix, 21:27:22-21:46:22 +08:** all 53 selectors pass, comprising
**37 actual-JIT, 12 context refusals, two pure-native controls and two kernel
protocol probes**. Main modes 0-8 report respectively
**4/4/4/554/1/460/4/2/2** returned body witnesses with correct protected states.
Mutex positives explicitly enable `mutex_jit=1`. Mode 5 has 460 matching
hostcall exits/executions/resumes and zero rejected/failed/limited calls.
All eight register gates, four held-B/PENDING selectors, eleven depth/remote
cases and the late-policy/mixed-owner cases pass.

The mixed-mutex test triggers four node overflows and one expected task
allocation failure, with 4331/4331 origin acquisitions/releases and no active
tasks/waiters/nodes. Learned mutex-depth executes the 11778 -> 12512-byte
expanded artifact, reaches three capacity exits retaining seven children each,
and completes four native continuations, 25 owner unlock notifications and
12017 exact state checks. Its `jit_success=0` means partial-JIT/native
completion, not absence of generated-code execution.

`test_22` passes on CPU placements **0,1,2** and **0,20,21**. Each executes
B->A and A->B order, four real owner ACKs and two deferred record frees. An
actual RCU reader keeps the unlinked entry alive across final ACK; after reader
exit, `rcu_barrier()` observes exactly one free per round. Acquisition refs,
allocation refusal, intermediate retention and final routing removal pass.
These probes report **JIT=0**: continuation registers and the outer batch
callback are constructed, with no JIT stack jump or production queue scheduling.
The earlier focused local probe also passes and is archived under `focused/`,
not counted again in the 53-case matrix.

Postflight at **21:48:48 +08** again passes all 39 units and 25 audit cases
without skips. All 175 host/guest inputs match; the 18 kernel source files,
config, nine build files and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` match. Default module `.text` remains
`37362e3c49f513089a6f6bb9647f20d41a07afb69ffef4d34bc3ac808f60a712`;
its symbols and module parameters exclude the task probe. Independent evidence
audit confirms 53 zero exit statuses, empty fault scans and drained callers/
modules. No VM restart or guest-kernel edit/build/install occurs.
This closes this bounded matrix, not C1/C2/C5 or deferred C3/C4.

The two obsolete mutex model sources, unused build outputs and their ignore
entries are removed. Old outputs are retained only as an evidence backup.
Repeated investigation-directory descriptions are replaced by the Git history
index below; active execution and test instructions remain in the usage guide.

## Mutex Resource Coverage

The earlier 173-input freeze against `a3642bb`, **2026-09-08
20:31:07-20:49:46 +08**, passes 51/51: 37 actual-JIT, 12 context refusals and
two native controls. Both pre/post checks pass 39 unit programs, 25 admission
audit cases, default/selftest+NUMA builds and source/kernel identity checks.
Its postflight closes at 20:53:23; the default module `.text` is unchanged.

Two copied mutex models become one production node/shadow/hook fixture:
15849 assertions, eight compiled/detected mutants, real capacities and the
guest's complete 168-byte `pt_regs`. Its slowpath substitute uses actual owner
result `2`, not the earlier unreachable `0`. Scope and substitute primitives
are maintained in [the resource guide](JIT_EXECUTION.md#61-mutex-资源与恢复包).
The real mixed-mutex overflow and learned-depth/owner ACK gates also pass;
these are separate from component fixtures. This does not close C1/C2/C5.

Retained archive: `/tmp/kdlock-mutex-resource-matrix.tpjgUD.tar.gz`, SHA256
`064c7c974477b8829ee945222bd1dbd39cd65d3324ece1ccd4ccc2f773f3bb80`.
Component attempts remain in `/tmp/kdlock-mutex-resources.Ri6xpc/`: a compile
failure, an invalid substitute result and the corrected passing test are not
interchangeable evidence. The initial matrix has 19 passes before a deliberate
stop to correct that substitute; editing its running shell caused status 127
before the next guest launch, not a production JIT failure. Guest drain passed.
Its incomplete archive is `/tmp/kdlock-mutex-resource-matrix.vaVuxc.tar.gz`, SHA256
`acea864615f1544de86e2d38d22ebce9e2f4a44ff1668fb429684d06817ff1f8`.
Current drivers install the stop guard before execution.

## Resource Registry Coverage

Historical checkpoint at `a3642bb`, **2026-09-08 19:17:36-19:36:12 +08**:
the earlier 173-input matrix passes 51/51, with 37 actual-JIT cases, 12 context
refusals and two native controls. All 40 unit programs, 25 audit cases,
build/source/kernel identity checks and drains pass. The 19:50:42 pre-commit
recheck repeats units/audit/default build without another live matrix.

This replaces the execution hash model with production registry functions:
8433 assertions, seven compiled/detected mutants and 24 pthreads registering
six colliding keys. The joined entry fixture has 136 checks, including 14
unavailable spin/mutex roots that do not call the wrapper or mutate the packet.
The full 511-slot lookup test uses synthetic metadata because the 64-block
pool fills first. Allocation, permission and copy APIs are substitutes, not a
live kernel saturation or immutable-publication proof.

The mixed-mutex live case observes four node overflows, one expected task
allocation failure and balanced 4392/4392 origin counters. Learned mutex-depth
executes its expanded helper, reaches three capacity exits and completes
12017 state checks with retained owners and 25 unlock notifications. These
observations are separate from the new component fixture above.

Evidence: `/tmp/kdlock-registry-matrix.RES3zj.tar.gz`, SHA256:

```text
374dd5625799acc6d00bb5ac11cc2355ddba540c5149741227cbfd40421c9b20
```

The first component attempt's mixed-sign compile adaptation is retained in
`/tmp/kdlock-registry.nVHMHh/` and the archive; it is not a passing test.
Pre-commit evidence is in `/tmp/kdlock-registry-review.zshemK/`.
Full details remain available with `git show a3642bb:docs/VALIDATION.md`.

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

The existing 51 selectors plus two kernel task probes ran at
**21:27-21:46 +08, 2026-09-08**. All 53 pass in their respective categories;
per-case exits are in `/tmp/kdlock-mutex-task-matrix.puvwk1/results.tsv`. Older tables remain
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

# kernel-task-local: real RCU/owner ACK, JIT=0
bash tests/test_22_mutex_task_lifecycle.sh

# kernel-task-cross-numa: real RCU/owner ACK, JIT=0
env KD_MUTEX_TASK_CPUS=0,20,21 bash tests/test_22_mutex_task_lifecycle.sh
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

The full directory index for older failed/intermediate experiments remains in
`git show a3642bb:docs/VALIDATION.md`. It is not duplicated in the active guide:
those /tmp paths are local historical evidence, not delivered test commands or
additional passes on the current source. No evidence files are deleted by this
documentation consolidation. The currently relevant archives and command
manifest are retained above.

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
