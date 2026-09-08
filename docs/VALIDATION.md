# kdlock Validation

Latest complete matrix: **65/65 pass** on the
[original waiter release races](#original-waiter-release-races) freeze. Actual-JIT positives,
context refusals, pure-native controls and kernel protocol probes are distinct.
The project is not accepted as complete; older matrices are historical only.

Complete-matrix source identity: **179 runtime/test inputs** in
`/tmp/kdlock-waiter-race-matrix.skE2dE/source.sha256`.
Full source/log/artifact/command archive:
`/tmp/kdlock-waiter-race-matrix.skE2dE.tar.gz`, SHA256:

```text
a33d9c1990ceb79cd48d456940f5e370b34d1c85cc17c6ea33ac0f75b0fa710d
```

The archive includes frozen source, generated artifacts, per-case commands,
status/dmesg/drain records, units, builds, kernel identities and guest-userspace
generated-predicate checks. /tmp paths are external local evidence, not
files delivered by a fresh Git checkout. The command manifest below keeps
invocations auditable. The two pure-native controls depend on an external
helper; they are not yet a self-contained fresh-checkout test. General evidence
packaging remains TODO P1. Losing an archive never makes recorded results new.

## Original Waiter Release Races

This increment against `2bdc468` adds a pidfd signal versus B-owner release
race after actual JIT prefix stores and a direct native B API CALL miss.
The observed native return chooses the suffix: 0 acquires/executes/unlocks B
once; -EINTR skips B. Both retain earlier stores, finish the exact record and
borrowed A owner ACK. The client can wait for a late signal in userspace,
without a test-owned task/frame reference. No production lock, wrapper,
translator or guest-kernel change is made. Flow and parameters are in
[usage 6.5](JIT_EXECUTION.md#65-原-waiter-与-b-释放的竞争).

The current freeze is `/tmp/kdlock-waiter-race-matrix.skE2dE/`, with 179
runtime/test inputs. Focused verification closes at **2026-09-09 02:22:07 +08**:
16/16 pass, each with actual JIT and full drain. Six original-waiter race cases
cover both APIs at -50000/0/+50000 us; both APIs have real acquired and cancelled
returns. The two unbiased focus outcomes are interruptible acquired and killable
cancelled. Four retained original-waiter cases and six native-peer regressions
also pass. Peer cancellation races use non-head probes 2/4; acquisition races
use head probes 1/3, with separate forced head-cancellation controls 1/3.
All 27 signal/publication unit methods pass within the 39 unit programs.

**Full matrix: 2026-09-09 02:22:07-02:46:05 +08**, **65/65 pass**:
49 actual-JIT, 12 context refusals, two native controls and two JIT=0 kernel
protocol probes. All modes 0-8 pass, with returned body counts
**4/4/4/632/1/462/4/2/2**. Mutex positives read back `mutex_jit=1`. Mode 3 waits
for the exact published entry before its 632 completions and 12934 transitions.
Mode 5 has 462 matched hostcall exits/executions/resumes and zero rejected,
failed or limited calls. These are execution observations, not version isolation
or proof that every source instruction ran.

The six new matrix cases each have one JIT body, one native continuation and
one final A ACK in a 12069-byte image, plus 12002 exact records:

| API | Offset (us) | Waiter PID | Native result | Protected transitions |
| --- | --- | --- | --- | --- |
| interruptible | -50000 | 1741938 | -EINTR | 12007 |
| interruptible | +50000 | 1743213 | 0 | 12008 |
| interruptible | 0 | 1744474 | -EINTR | 12007 |
| killable | -50000 | 1745735 | -EINTR | 12007 |
| killable | +50000 | 1747001 | 0 | 12008 |
| killable | 0 | 1748281 | -EINTR | 12007 |

The device CALL_MISS targets match the real API addresses, with no PENDING
injection. Acquired cases own B; cancelled cases never enter or unlock B.
Pidfd target/trigger windows, owner-unlock brackets and exact records/ACKs all
match. Both unbiased matrix cases cancel, unlike the interruptible focus case;
these samples do not establish an outcome distribution or all interleavings.
The four retained original-waiter signal paths also pass their separate
held-B/acquisition/PENDING checks.

All eight GPR/return-stack gates, held-B/PENDING, late-policy and depth/remote
cases pass. Mixed mutex has four node overflows, one deliberate task allocation
failure, balanced 4329/4329 origin intervals and no active waiter/task/node.
Learned mutex-depth executes the **12069 -> 12806-byte** image, reaches three
capacity exits retaining seven child locks, and completes four native
continuations, 25 owner unlocks and 12017 transitions. Its zero all-JIT
completion count is not zero generated execution. The separate shadow-capacity
case has two body witnesses, two native continuations, three owner unlocks and
12009 transitions. NUMA depth-8 samples 1784/712 bytes of stack margin/write
watermark; this does not prove arbitrary IRQ/NMI or lifetime safety.

Postflight closes at **2026-09-09 02:47:34 +08**. Pre/post 39 unit programs and
25 admission cases pass without skips; default and SELFTEST/NUMA module builds
and workload/daemon builds pass. All 179 host/guest input hashes, 18 captured
kernel source/interface files, configuration, nine existing build files and
live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5` match. Default
`kdlock_km` `.text` remains
`37362e3c49f513089a6f6bb9647f20d41a07afb69ffef4d34bc3ac808f60a712`, with
task/virtual selftest probes absent. Independent audits verify all 65 matrix
and 16 focus statuses, empty kernel-fault scans and drained callers/modules.
Existing objtool/locale warnings remain; no guest-kernel edit/build/install or
VM restart occurs. General C1/C2/C5 remain open; C3 immutable versions and
C4 flags/special-instruction repairs remain explicitly deferred.

### Failed Bias Expectations

Two earlier attempts remain failures, not additional accepted matrix entries:

| Archive in /tmp | Recorded outcome |
| --- | --- |
| `kdlock-waiter-race-matrix.ysDJPj.tar.gz` | Three focused passes, then original killable waiter acquired B despite SIGKILL being sent about 50ms before unlock; strict `expected=cancelled` fails. B owner used busy polling. |
| `kdlock-waiter-race-matrix.T4nQAI.tar.gz` | Ten original-waiter passes, then a head native-peer race acquired despite early SIGUSR1; its strict cancellation expectation fails. Runtime inputs match the current freeze. |

SHA256, in table order:

```text
e6ccff5871173d3e812f4887ae95cbbdfb6c4cc3dc1ca537573e806041322910
f7b17a50920d38faaff07a708bddf4d6669f98717e637fb955b2d2b94df71d54
```

Both have real JIT/native/ACK records, no kernel faults and drained callers.
The guest's mutex slowpath can trylock or optimistically spin before checking
signals; earlier delivery alone does not require cancellation. This source
ordering explains why the expectation is insufficient, not an instruction
trace of the precise internal branch. The original-waiter fixture now sleeps
between owner gate polls, letting a woken waiter leave optimistic spin; native
return/owner/ACK assertions are unchanged. The native-peer regression selects
the existing non-head cancellation cases instead of modifying its lock flow.
All callers and runners stop before changes; the new run starts independently,
without merging passed subsets or adding any guest-kernel hook.

## Cancellable Native Waiter

Checkpoint `2bdc468`, **2026-09-09 00:46:35-01:08:39 +08**: 178 inputs,
59/59 pass (43 actual-JIT, 12 context refusals, two native controls, two JIT=0
kernel probes). Four focused cases, pre/post 39 unit programs and 25 admission
cases pass; postflight closes at 01:10:08. Default runtime `.text` is unchanged;
source/kernel identity, fault scans and drains pass, with no kernel edit/build
or VM restart. Existing objtool/locale warnings remain.

The direct interruptible/killable B CALL misses each have one JIT prefix and
one native/ACK lifecycle, 12002 records and 12007 transitions. Real `-EINTR`
skips B's CS/unlock; its owner keeps B until after A ACK. No PENDING injection,
API-hiding helper or extra test task reference is used. The two ordinary-B
signals instead retain 128 pending samples and 12008 transitions. These tests
do not cover B release races or arbitrary frame abandonment; the current
execution flow is in [usage 6.4](JIT_EXECUTION.md#64-原-waiter-的信号与退出).

Archive: `/tmp/kdlock-cancellable-waiter-matrix.aLusGN.tar.gz`, SHA256
`9bb03061df82db11f44fb15c5bfade05771f2124c90cc7ff4f536cb541a7686a`.
Detailed mode, register, capacity and remote results remain in
`git show 2bdc468:docs/VALIDATION.md`, not duplicated in the active guide.

## Original Waiter Signals

Checkpoint `37ab8b0`, **2026-09-08 23:50:03 to 09-09 00:11:36 +08**:
178 inputs, 57/57 pass (41 actual-JIT, 12 refusals, two native controls,
two JIT=0 kernel probes). Pre/post 39 units, 25 audit cases, builds, identity
and drains pass; postflight closes at 00:14:01. Default runtime `.text` is
unchanged. Both original-waiter signals finish uninterruptible B and final
A ACK: one body/native/ACK each, 128 pending observations, 12002 records and
12008 protected transitions. They do not test cancellable B or frame abandonment.
Flow and API distinctions live in [usage 6.4](JIT_EXECUTION.md#64-原-waiter-的信号与退出).

Archive: `/tmp/kdlock-waiter-signal-matrix.uB2a4f.tar.gz`, SHA256
`5746f5b23c23591cff76f64811c9d09b5cc12621e0d18542732e13b350c1c099`.
It retains the four earlier focused passes in `focused/` (two original waiters,
two native peers), and the superseded NULL-record-guard preflight separately.
Detailed results remain in `git show 37ab8b0:docs/VALIDATION.md`.

The first matrix `/tmp/kdlock-waiter-signal-matrix.WtywJ2.tar.gz` is incomplete:
ten passes, a mode-3 publication-readiness failure before JIT contention,
then a preinstalled stop marker (93) without launching the next case. There
are no kernel faults/leaked callers. SHA256:
`2ded3e57af001864a372e6b5d5fa85eb7784d5549bf0f4f916a058c838e29b55`.
After the runner closes, `test_07` waits for the exact NORMAL RIP/TGID entry
using existing `wait_ready()`, retaining install/body/exact-state checks.
The corrected full run above is independent, not a merge of passing subsets.
This fixes test readiness, not concurrent code-version isolation.

## Spin Virtual Cancellation

Checkpoint `2171cbf`, **2026-09-08 22:28:39-22:49:31 +08**: 176 inputs,
55/55 pass (39 actual-JIT, 12 refusals, two native controls, two JIT=0 task
probes). Pre/post 39 units, 25 audit cases, builds, source/kernel identity and
drains pass; postflight closes at 22:51:51. Default runtime `.text` is unchanged.

The two added busy-B virtual cancellation probes each have one JIT body,
one native/owner-ACK lifecycle, 12003 records and 12011 protected transitions.
Resource absence/full count is injected; actual tickets, pin cancellation,
CALL packets and retained locks are checked. Flow and limits live in
[usage 6.3](JIT_EXECUTION.md#63-spin-虚拟请求取消与续跑).
The extra shadow-capacity regression also passes. Its sampled NUMA depth-8
stack margin/watermark of 1784/712 bytes is not a general stack-safety proof.

Archive: `/tmp/kdlock-spin-virtual-matrix.bXxA9p.tar.gz`, SHA256
`61cdad52b26512e2529a25e5071541654555976763cb9f5f26d921318a37ee95`.
It retains the focused probes and initial failed compile log/hash separately;
no module was loaded from that failed build. Detailed results remain in
`git show 2171cbf:docs/VALIDATION.md`.

## Mutex Task Lifecycle

Checkpoint `832c44b`, **2026-09-08 21:27:22-21:46:22 +08**, passes 53/53:
37 actual-JIT, 12 context refusals, two native controls and two kernel protocol
probes. All 175 source identities, 39 units, 25 audit cases and postflight pass.
The two JIT=0 probes test actual task/RCU/owner ACK in both unlock orders;
current flow and boundaries are in
[usage 6.2](JIT_EXECUTION.md#62-task-引用最终-ack-与-rcu).
Archive: `/tmp/kdlock-mutex-task-matrix.puvwk1.tar.gz`, SHA256
`c7997a0432c15ddb32d9fef5a451ba12dcd243c725bf197aa0e3bb874eed7b14`.
Detailed records: `git show 832c44b:docs/VALIDATION.md`.

## Mutex Resource Coverage

The earlier 173-input freeze against `a3642bb`, **2026-09-08
20:31:07-20:49:46 +08**, passes 51/51: 37 actual-JIT, 12 context refusals and
two native controls; 39 units, 25 audit cases and postflight pass. The joined
production node/shadow/hook fixture replaces two copied models; its substitutes
and coverage are documented in [usage 6.1](JIT_EXECUTION.md#61-mutex-资源与恢复包).
Archive: `/tmp/kdlock-mutex-resource-matrix.tpjgUD.tar.gz`, SHA256
`064c7c974477b8829ee945222bd1dbd39cd65d3324ece1ccd4ccc2f773f3bb80`.
Component attempts remain in `/tmp/kdlock-mutex-resources.Ri6xpc/`: a compile
failure, an invalid substitute result and the corrected passing test are not
interchangeable evidence. The initial matrix has 19 passes before a deliberate
stop to correct that substitute; editing its running shell caused status 127
before the next guest launch, not a production JIT failure; guest drain passed.
Its incomplete archive is `/tmp/kdlock-mutex-resource-matrix.vaVuxc.tar.gz`, SHA256
`acea864615f1544de86e2d38d22ebce9e2f4a44ff1668fb429684d06817ff1f8`.
Current drivers install the stop guard before execution.

## Resource Registry Coverage

Historical checkpoint at `a3642bb`, **2026-09-08 19:17:36-19:36:12 +08**:
173 inputs, 51/51 (37 JIT, 12 refusals, two controls), 40 units, 25 audit cases
and final identity/drain checks pass. The registry fixture now uses production
functions; substituted allocation/copy APIs do not prove live saturation.
Archive: `/tmp/kdlock-registry-matrix.RES3zj.tar.gz`, SHA256
`374dd5625799acc6d00bb5ac11cc2355ddba540c5149741227cbfd40421c9b20`.
It retains the first failed compile attempt separately. Full details and the
pre-commit recheck are in `git show a3642bb:docs/VALIDATION.md`.

## Scoped Learned Callees

Historical implementation checkpoint at `560e4ec`, **2026-09-08
18:14:38-18:33:14 +08**: the earlier 172-input matrix passes 51/51, comprising
37 actual-JIT, 12 context refusals and two native controls. It closes the
learned mutex-depth failure from `6858c58`. All 40 units, 25 audit cases and
postflight pass. The expanded helper executes real JIT and reaches three
capacity exits, four native completions and 25 owner unlocks. Current scope
and flow live in [usage 5.1](JIT_EXECUTION.md#51-学习后的直接-callee).

| Retained archive | SHA256 |
| --- | --- |
| `/tmp/kdlock-learned-matrix.uCNLc7.tar.gz` | `3c3e892b2c578e95805fdceba4abec4fb2ee47e82716510ca806e02e345e7c73` |
| `/tmp/kdlock-learned-scope.67p5oR.tar.gz` | `2cb1c08bf0980f193d2b6f4242c9af7dee12ceeec75d45c5dbceffd9be7f6521` |

The separate 18:50:39 documentation recheck is not another live matrix.
Detailed records: `git show 560e4ec:docs/VALIDATION.md`.

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

Ordinary CALL-miss cases stop the daemon before measured execution and match
the exit to the expected real callee, such as the native/register probe or
selected cancellable B API. The original task completes distinct per-request
before/call/after records exactly
once; `kd_native started == completed > 0`, with no entry retry or lost state.
A JIT prefix plus native suffix is not counted as an all-JIT completion.
The optional completion-policy variant pauses rather than stops the daemon,
then resumes it to validate subsequent refusal without replay.
PENDING resource cases instead validate the original known lock CALL packet
before B acquisition/publication; they are not ordinary callee-learning misses.
Signal cases correlate signal/task identity, real native queue membership,
suffix completion and final owner ACK. Ordinary B retains its PENDING packet
and acquisition checks; cancellable B requires the actual device CALL_MISS
target and no injection. Held-B cases must cancel without B acquisition/unlock,
with B still held after A ACK. Release-race cases instead follow the real 0 or
-EINTR return, correlating pidfd identity, actual owner-unlock timestamps and
branch-specific ownership/effects. Neither an early signal nor a successful
release-gate write proves cancellation or physical unlock.

## Current Matrix Manifest

The prior 59 selectors plus six original-waiter release races ran from
**2026-09-09 02:22 to 02:46 +08**. All 65 pass in their respective
categories; per-case exits are in
`/tmp/kdlock-waiter-race-matrix.skE2dE/results.tsv`. Mode 3 runs first to
verify publication and actual JIT. Older tables remain historical and do
not define current acceptance. Body records count returned
positive logs, not retired instructions, unique instructions or immutable
generations.

### Recorded Commands

All commands ran in the recovery guest project with
`KDLOCK_RECOVERY_CONFIRMED=1 LC_ALL=C`. Use the operations guide to confirm
snapshots, freeze/sync inputs, retain evidence and drain between cases.
This is a manifest, not an unattended command to run on the host.
The three cross-NUMA commands use corrected role placements; earlier invalid
CPU placements are excluded from the 65-case total. The external
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

# virtual-context-refusal: actual JIT, injected context view, real ticket cancel
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_VIRTUAL_RESOURCE=1 bash tests/test_10_native_resume.sh 8 4

# virtual-node-refusal: actual JIT, injected full count, real ticket cancel
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_VIRTUAL_RESOURCE=2 bash tests/test_10_native_resume.sh 8 4

# waiter-usr1: actual JIT, uninterruptible B, then one userspace handler
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=10 bash tests/test_10_native_resume.sh 4 4

# waiter-kill: actual JIT and final owner ACK must precede fatal userspace exit
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=9 bash tests/test_10_native_resume.sh 4 4

# waiter-interruptible: real API CALL miss, -EINTR skips B, A ACK remains required
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=10 KD_NATIVE_WAITER_API=1 bash tests/test_10_native_resume.sh 4 4

# waiter-killable: no PENDING injection; fatal exit follows the same A ACK
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 bash tests/test_10_native_resume.sh 4 4

# waiter-race-int-cancelled
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=10 KD_NATIVE_WAITER_API=1 KD_NATIVE_WAITER_RACE=1 KD_NATIVE_WAITER_RACE_US=-50000 KD_NATIVE_WAITER_EXPECT=cancelled bash tests/test_10_native_resume.sh 4 4

# waiter-race-int-acquired
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=10 KD_NATIVE_WAITER_API=1 KD_NATIVE_WAITER_RACE=1 KD_NATIVE_WAITER_RACE_US=50000 KD_NATIVE_WAITER_EXPECT=acquired bash tests/test_10_native_resume.sh 4 4

# waiter-race-int-either
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=10 KD_NATIVE_WAITER_API=1 KD_NATIVE_WAITER_RACE=1 bash tests/test_10_native_resume.sh 4 4

# waiter-race-kill-cancelled
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 KD_NATIVE_WAITER_RACE=1 KD_NATIVE_WAITER_RACE_US=-50000 KD_NATIVE_WAITER_EXPECT=cancelled bash tests/test_10_native_resume.sh 4 4

# waiter-race-kill-acquired
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 KD_NATIVE_WAITER_RACE=1 KD_NATIVE_WAITER_RACE_US=50000 KD_NATIVE_WAITER_EXPECT=acquired bash tests/test_10_native_resume.sh 4 4

# waiter-race-kill-either
env KD_NATIVE_PENDING_CONTENDED=1 KD_NATIVE_WAITER_SIGNAL=9 KD_NATIVE_WAITER_API=2 KD_NATIVE_WAITER_RACE=1 bash tests/test_10_native_resume.sh 4 4
```

Separate regression after this matrix and before postflight:

```sh
env KD_NATIVE_SHADOW_CAPACITY=1 bash tests/test_10_native_resume.sh 1 4
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
