# kdlock Validation

Latest complete-matrix evidence is the JIT Episode Scope freeze below. The full matrix
has **14 failed gates** and is not accepted as complete. An actual-JIT positive,
a context refusal and a pure-native control are different outcomes. The later
[entry-guard foundation](#entry-guard-foundation) has a separate source freeze
and narrow regression; it does not replace that complete matrix.

Complete-matrix source identity: 168 inputs in
`/tmp/kdlock-jit-episode.lQFNLA/source.sha256`.
Full source/log/artifact/command archive:
`/tmp/kdlock-jit-episode.lQFNLA.tar.gz`, SHA256:

```text
049153a5fd1c185db6531716bd666d09b023a7e58ca3f7caf8dbc32ba0345687
```

The archive includes frozen source, generated artifacts, per-case commands,
status/dmesg/drain records, units, builds, kernel identities and a separate
guest-userspace wrapper check. /tmp paths are external local evidence, not
files delivered by a fresh Git checkout. The command manifest below keeps
invocations auditable. The two pure-native controls depend on an external
helper; they are not yet a self-contained fresh-checkout test. General evidence
packaging remains TODO P1. Losing an archive never makes recorded results new.

## Entry Guard Foundation

**Status: analysis/test foundation only; not enabled in production.** Evidence:
`/tmp/kdlock-guard-foundation.qaCvD5/`, with **170 frozen inputs** in
`source.sha256`. Archive `/tmp/kdlock-guard-foundation.qaCvD5.tar.gz`, SHA256:

```text
4e41af4531c564323f8751c3e439770a6f10c22a5de4739d0b0073661fea2178
```

At **2026-09-08 15:28:18 +08**, all **39 unit programs** pass without skips,
including **14 entry-predicate methods**. These execute bounded generated
MOV/RET fixtures in the guest-userspace wrapper and check overlap, adjacency,
modular wrap, complete store width, register/stack/memory preservation,
single-root admission, sensitive-code rejection and budget refusal before
emission. The expanded real CALL-helper fixture passes **432 checks**. It
tests saved packets, not arbitrary callee effects or remote lock concurrency.
The independent **25-case admission audit** also passes. The default W=1
module build passes with existing objtool warnings and unchanged `.text` hash
`2ab4297b6f3b7656cfa8fa32deff3735a52b9afc7661803d49af13b08eac696c`.

Captured-text replay at **15:28:18-15:28:28 +08** uses the final single-root and
guard-budget checks, preserves memory clobbers and models saved GPR effects
only for registered lock controls:

| Captured entry | Collected ranges | Final conditions | Analysis work | Result |
| --- | ---: | ---: | ---: | --- |
| mode 1 | 487 | 42 | 516076 / 1000000 | Conditional analysis passes |
| mode 4 | 500 | 43 | 787978 / 1000000 | Conditional analysis passes |

The replay does **not** enforce predicates, install an image or execute kernel
text. Its assembly sizes/status are feasibility observations only. Earlier
unconditional separation experiments in `/tmp/kdlock-guard-feasibility.FpSXTS/`
are not safe candidates. Production `dis_assem` still supplies no collector;
the experimental `ENTRY_REFUSED=6` and non-root bypass have no runtime contract.
Integration prerequisites and usage are maintained in
[JIT_EXECUTION](JIT_EXECUTION.md#5-入口条件分析尚未接入生产), not inferred from this table.

Six fresh production regressions run on the final freeze from
**15:28:28 to 15:30:46 +08**; the candidate predicates remain disabled:

| Case | Result | Returned JIT body witnesses / other evidence |
| --- | --- | --- |
| mode 0 | Pass | 4; protected-state oracle passes |
| mode 3, `mutex_jit=1` | Pass | 663; protected-state oracle passes |
| mode 5, `mutex_jit=1` | Pass | 431; 431 hostcalls executed and resumed |
| context mode 11, `mutex_jit=1` | Pass, native-only | 0; 12129 checked native transitions |
| mode 1 | Fail | 0; refusal at `MOV [RAX+0xD0],RDX` |
| mode 4, `mutex_jit=1` | Fail | 0; refusal at `MOV [RBX+0xD0],R13` |

Per-case commands, status, source checks, artifacts, dmesg and drain records
are retained; failed daemon logs preserve the address-widening diagnostics.
All fault scans are empty and callers/modules drain. At **15:30:49 +08**, both
source copies still match and the read-only baseline check passes: 18 source
files, config, nine build files and running Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. No guest-kernel edit or image build,
owner/argument ABI change, flags repair or immutable-code change is made.
This is **3 actual-JIT passes + 1 refusal pass + 2 failures**, not a full-matrix
rerun and not guarded nested-JIT acceptance. The fourteen main gates stay open.

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


## JIT Episode Scope

**Status: episode scope implemented; 37/51 live gates pass, 14 remain failing.**
Evidence: `/tmp/kdlock-jit-episode.lQFNLA/`. Usage, execution flow and test
commands are in [JIT_EXECUTION.md](JIT_EXECUTION.md).

The user approved checking the actual possible JIT episode rather than a
waiter-only native suffix. The new 168-input freeze changes six files from the
native-phase baseline: `context_policy.py`, `disassem.py`, three Python unit
files, and comments only in `kernel_module/exe.c`. It does not copy the earlier
withdrawn prototype or alter decoded CALL/RET effect flow, memory clobbers,
alias assumptions, analysis budgets, workload probes, wrapper ABI or locks.

`jit_phase_blocks()` removes the return edge only for an ordinary direct CALL
whose callee is absent from the current decoded blocks. It preserves the CALL
instruction and its memory checks. Admission, lexical-boundary selection,
constant propagation and emission use that same scope. Alternative live paths
retain their successors, without receiving native-only edge state. Controls,
allowlisted hostcalls, decoded callees and indirect calls keep conservative
continuations; each compile reconsiders the current learned targets.

The seven added policy methods cover a GS-bearing native suffix, alternate
JIT reachability, native-edge state isolation, control/hostcall return paths,
learned-callee retranslation, indirect CALL and CALL's stack write. Three
existing test methods that assumed whole-entry scope now use returning lock
controls for their sensitive suffixes; the ordinary-miss positive is separate.
These changes do not permit sensitive instructions on a retained JIT path.
All **38 unit programs** pass without skips before integration, including
**92 policy, 48 memory and 13 diagnostic methods**. The independent 25-case
admission audit passes with zero failures. NUMA+selftest and default module
profiles build; preflight finishes at **13:00:48 +08** on 2026-09-08.

Captured-text replays initially restore mode-0 assembly but still refuse mode
1/4 at the register-sample address store before the terminal CALL. A separate
temporary experiment preserving control-service GPRs still refuses mode 1;
it is **not adopted**. These are static observations, not JIT execution proof.

The fresh live matrix starts at **13:02:16 +08**, using the corrected three
cross-NUMA commands and excluding the previous invalid-placement commands.
Every command checks the frozen host/guest inputs, retains output/dmesg/JIT
artifacts, scans for kernel faults, and checks caller/module drain. A failed
positive gate remains a failure even if native execution completes.

All **51** valid cases finish at **13:23:13 +08**: **37 pass (23 actual-JIT,
twelve context refusals, two native controls), 14 fail**. All fourteen failures
have zero returned body records. Every fault scan is empty and each case drains;
no prior-source pass or invalid CPU-placement attempt is substituted.
Eight former failures recover: mode 0/3, their two register-CALL cases, both
mixed-owner cases and both late-policy cases. Full acceptance remains open.

The remaining failures are:

```text
mode-1 mode-4 mode-8
registers-1-2 registers-4-2 registers-1-3 registers-4-3
registers-8-2 registers-8-3
native-1-3 native-4-3 native-1-4 native-4-4 native-mutex-depth
```

Confirmed main-path evidence:

- mode 0: 2467-byte JIT image, matching returned body witness, 12009 complex
  state transitions; mode 3 (`mutex_jit=1`): 2663-byte image, 12934 transitions
  and 635 JIT completions.
- mode 5 (`mutex_jit=1`): 1257-byte image, 12582 transitions and **436 hostcall
  exits executed and resumed**; mode 2/6/7 also pass actual-JIT gates.
- mode 0/3 register-CALL continuation: each has eight samples, including one
  marked actual-JIT sample and one native frame. All sixteen GPRs/stack and
  exactly-once checks pass over 12009 requests. Mutex logs record native begin,
  complete and physical-owner unlock ACK. Flags remain explicitly unchecked.
- twelve context-refusal cases retain zero JIT, and both pure-native register
  controls pass separately. Mixed spin/mutex owner cases pass actual-JIT gates.
- complex mode 1/4/8 and their marked register cases still fail admission.
  They are not accepted; this change does not solve all loaded-pointer/alias
  imprecision inside a reachable JIT prefix.
- all eleven selected depth/remote cases pass with actual JIT, including the
  corrected three cross-NUMA native continuations. Eight physical frames retain
  sampled/written stack margins of 2504/1440 bytes (NUMA off) and 2008/944
  (NUMA on). These bounded fixtures do not validate the failed ordinary mode-8
  workload or establish arbitrary-depth safety.

Default module `.text` remains
`2ab4297b6f3b7656cfa8fa32deff3735a52b9afc7661803d49af13b08eac696c`.
The existing guest Linux 6.1.159 source/config/build/live identities are checked;
no guest kernel edit, rebuild, install, restart or owner handoff is introduced.
General context/concurrency guarantees and the explicitly deferred C3/C4
version/flags/instruction issues remain open.

Post-test checks pass at **2026-09-08 13:25:15 +08**: all 38 unit programs
again pass without skips, the 25-case audit reports zero failures, and both
copies of all 168 inputs match the frozen archive. Default module `.text`,
656/5264/184/280-byte layouts, 7904-byte static per-CPU allocation and guest
source/config/build/live identities remain unchanged. Callers/modules are
drained; Ruff, formatting and diff checks pass. Existing manual-stack objtool
warnings remain; no guest kernel compilation is performed.

An additional guest-userspace check uses the real assembler and wrapper with
`MOV RAX,42; CALL 0x5000; GS load; RET`. It checks that the GS suffix is absent
before executing anything. The generated prefix returns RAX=42, callee
RIP=0x5000 and `[exit,body]=[1,1]`; dispatch directly to the excluded suffix
returns `[2,0]`. This verifies both actual generated instructions and the
missing suffix entry, but is deliberately recorded separately from in-kernel
JIT evidence. The retained `wrapper_scope.py` and `post-guest.log` reproduce
and record that check. That runtime increment did not create a Git commit; the later documentation
and version checkpoint is recorded separately below.


## Current Matrix Manifest

These are the **13:02-13:23 +08, 2026-09-08** results, not the later focused
commit checks. Body records count returned positive log records, not retired
instructions, unique source instructions or immutable generations.

| Case | Exit | Class | Returned body records |
| --- | --- | --- | --- |
| `mode-0` | `0` | `actual-jit` | `4` |
| `mode-1` | `1` | `failed` | `0` |
| `mode-2` | `0` | `actual-jit` | `4` |
| `mode-3` | `0` | `actual-jit` | `635` |
| `mode-4` | `1` | `failed` | `0` |
| `mode-5` | `0` | `actual-jit` | `436` |
| `mode-6` | `0` | `actual-jit` | `4` |
| `mode-7` | `0` | `actual-jit` | `2` |
| `mode-8` | `1` | `failed` | `0` |
| `registers-4-2` | `1` | `failed` | `0` |
| `registers-1-2` | `1` | `failed` | `0` |
| `context-percpu-spill` | `0` | `context-native` | `0` |
| `context-percpu-implicit` | `0` | `context-native` | `0` |
| `context-percpu-rotate` | `0` | `context-native` | `0` |
| `context-percpu-cmov` | `0` | `context-native` | `0` |
| `control-0` | `0` | `native-control` | `0` |
| `control-3` | `0` | `native-control` | `0` |
| `registers-0-1` | `0` | `actual-jit` | `1` |
| `registers-3-1` | `0` | `actual-jit` | `1` |
| `registers-1-3` | `1` | `failed` | `0` |
| `registers-4-3` | `1` | `failed` | `0` |
| `registers-8-2` | `1` | `failed` | `0` |
| `registers-8-3` | `1` | `failed` | `0` |
| `context-spin` | `0` | `context-native` | `0` |
| `context-mutex` | `0` | `context-native` | `0` |
| `context-mixed` | `0` | `context-native` | `0` |
| `context-irqsave` | `0` | `context-native` | `0` |
| `context-bh` | `0` | `context-native` | `0` |
| `context-percpu` | `0` | `context-native` | `0` |
| `context-percpu-reg` | `0` | `context-native` | `0` |
| `context-percpu-flow` | `0` | `context-native` | `0` |
| `mixed-spin` | `0` | `actual-jit` | `913` |
| `mixed-mutex` | `0` | `actual-jit` | `26` |
| `native-1-3` | `1` | `failed` | `0` |
| `native-4-3` | `1` | `failed` | `0` |
| `native-1-4` | `1` | `failed` | `0` |
| `native-4-4` | `1` | `failed` | `0` |
| `node-physical-1-0` | `0` | `actual-jit` | `1` |
| `node-physical-1-1` | `0` | `actual-jit` | `1` |
| `node-physical-2-0` | `0` | `actual-jit` | `2` |
| `node-physical-2-1` | `0` | `actual-jit` | `2` |
| `node-physical-8-0` | `0` | `actual-jit` | `8` |
| `node-physical-8-1` | `0` | `actual-jit` | `8` |
| `node-remote-plain` | `0` | `actual-jit` | `4` |
| `node-multi-b-depth8-stage5-layer6-count3-owner1-reverse1-rename1` | `0` | `actual-jit` | `8` |
| `late-spin-policy` | `0` | `actual-jit` | `1` |
| `late-mutex-policy` | `0` | `actual-jit` | `1` |
| `native-mutex-depth` | `1` | `failed` | `0` |
| `remote-late-2-cross-fixed` | `0` | `actual-jit` | `4` |
| `remote-late-3-cross-fixed` | `0` | `actual-jit` | `4` |
| `remote-late-4-cross-fixed` | `0` | `actual-jit` | `4` |

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

The documentation cleanup preserves the above 168 runtime/test inputs unchanged.
At **2026-09-08 14:03:16 +08**, a fresh guest check passed all 38 unit programs
without skips, the 25-case admission audit, default module build and captured
source/config/build/live kernel verification. Module .text remains the hash in
JIT Episode Scope. New evidence: `/tmp/kdlock-docs-commit.Tm6d9w/`.

This checkpoint consolidates README, operations, design, register ABI, daemon,
tasks and validation; execution/test instructions remain in JIT_EXECUTION.
It removes duplicated chronological prose, obsolete whole-entry requirements
and checked historical microtasks. It does not weaken tests or repair the
remaining mode 1/4/8 failures. Purpose/constraint comments in the runtime changes
are retained, and the developer rules now explicitly require them.

The fresh eight-case live check ran **14:10:12-14:13:03 +08**. Six pass:
mode 0/3/5 and register-CALL mode 0/3 have actual JIT evidence; mode 11 is a
native-only context-refusal pass. Mode 1/4 still fail their positive JIT gates,
with no returned body records. This is not a rerun of the complete matrix.

| Focused case | Result | Returned body records | Additional evidence |
| --- | --- | --- | --- |
| mode 0 | Pass, actual JIT | 4 | Complex state oracle passes |
| mode 3 | Pass, actual JIT | 716 | mutex_jit=1 |
| mode 5 | Pass, actual JIT | 432 | mutex_jit=1; hostcall exits/executed/resumed=432, no rejects/failures/limits |
| registers 0/3 stage 1 | Both pass, actual JIT | 1 each | Eight samples each; 16 GPR/stack checks and 12009 exactly-once records |
| context mode 11 | Pass, native-only | 0 | 12129 native transitions, no JIT |
| mode 1/4 | Both fail admission/JIT gate | 0 | No fallback result counted as JIT |

All eight fault scans are empty and all cases drain modules/callers. No guest
kernel changes or restart were needed. Ruff check/format (56 Python files),
ShellCheck with the actual source search path, document links and diff checks
pass. A broad strict C-format scan still reports manual line wrapping in
kd_hotlock.c and kd_mutex.c; those runtime inputs are deliberately unchanged,
not claimed fully reformatted. Existing manual-stack objtool warnings remain.

The retained failed daemon logs identify the same pre-CALL register-sample
stores: mode 1 widens RAX at +0xD0, mode 4 widens RBX at +0xD0. Neither hits
the total analysis budget. Post-live checks pass again at **14:18:54 +08**:
38 unit programs without skips, 25-case audit, unchanged host/guest inputs,
default module .text and kernel identity. No runtime source changed during
this documentation checkpoint.

## Historical Evidence Index

The entries below are **historical summaries only**, tied to their own source
snapshots. "Accepted" or "passes" here never overrides the current 14 failures.
Detailed old test transcripts and repeated investigation narratives were removed
from active docs; headings, key findings and evidence locations are retained.
Current implementation contracts are in DESIGN/ABI, not these old summaries.

The complete pre-cleanup nine-document snapshot is preserved locally as
`/tmp/kdlock-docs-commit.Tm6d9w/docs-before.tar.gz`, SHA256:

```text
ea5e232ddce5a33c57f38e3840df576a2270d6d655d726f1f1e7e03c2960d60a
```

The withdrawn ordinary-CALL prototype below used the earlier whole-entry policy.
The user's subsequent JIT-episode approval supersedes that policy; no old
prototype was copied over the current CALL/RET or memory analysis.

## Entry Premise Investigation

Historical source snapshot, not current acceptance.

**Status: candidate premises tested; no production precision fix.** Evidence:
`/tmp/kdlock-entry-premises.8mGP9Y/`. All 168 inputs remain identical to the
11:27:49 native-phase freeze, including the two-word ABI and guest kernel.
This investigation does not rerun the 51 valid live cases or turn any of
their 22 functional failures into passes.

The external experiment changes only in-process analysis functions and reads
the retained relocated module text. It compares four variants under the same
1M budget and whole selected-block scan:

Retained historical evidence: `/tmp/kdlock-entry-premises.8mGP9Y/`.

## Native Registration Phase Guard

Historical source snapshot, not current acceptance.

**Status: phase-guard checks pass; broader JIT admission remains unaccepted.** Evidence:
`/tmp/kdlock-native-phase.2oGMsX/`. The **2026-09-08 11:27:49 +08** freeze
changes two of 168 inputs: `kernel_module/kd_exec.c` and
`tests/unit/native_after_outer_fixture.c`. Translator/admission policy,
register layout, ownership protocol and guest kernel are unchanged.

Previously `kd_exec_native_begin()` rejected unsupported control phases only
when `outer_unlock_seen` was set. With A still held, a syntactically valid
ENTERED/ACQUIRED/non-relay-COMPLETE or invalid phase could publish a native
frame and increment borrow/start counts. The upstream executor already routes
later-phase errors to fail-stop. This is a helper validation gap demonstrated
in isolated production-function tests, not a reproduced live misroute or crash.

Retained historical evidence: `/tmp/kdlock-native-phase.2oGMsX/`.

## Alias Origin Diagnostic

Historical source snapshot, not current acceptance.

**Status: precision prerequisites isolated; no production fix or new live run.**
Evidence: `/tmp/kdlock-alias-origin.yXHEZn/`. All 168 inputs remain identical to
the decoded-CALL freeze. The external observer records up to 24 events per
category: discarded CALL word facts, widened loads/registers and stores that
widen the memory default. Snapshots are observations, not analysis overrides.
The event sequence is CFG worklist processing order, **not an executed path**.

All three captured-code replays retain the exact baseline status, work,
assembly size and rejection diagnostic text: mode 0 **2 / 102302 / 0**, mode 1
**2 / 11087 / 0**, mode 4 **2 / 45163 / 0**. The following intermediate states
localize where additional alias/effect premises would be needed:

Retained historical evidence: `/tmp/kdlock-alias-origin.yXHEZn/`.

## Decoded CALL Effect Flow

Historical source snapshot, not current acceptance.

**Status: two demonstrated omissions fixed; full regression not accepted.** Evidence:
`/tmp/kdlock-admission-boundary.UQLmRm/`. The 168-input freeze at
**2026-09-08 10:15:21 +08** changes `disassem/context_policy.py`,
`tests/audit_context_spills.py`, `tests/unit/test_context_policy.py`, and
`tests/unit/test_context_spill_audit.py` relative to the address-diagnostic
snapshot. Runtime lock/executor/ABI code and the guest kernel are unchanged.

The old independent audit exits **1**, with two genuine assertion gaps and no
fixture/tool errors: a decoded callee uses caller RDI=0x2ff8 at **0x1044**, and
a decoded callee returns RAX=0x2ff8 used by caller LODSQ at **0x1009**. Both
concrete-input miasm IR witnesses access **0x3008**, but the old translator
returns status 0 and assembly. The reference does not reuse the production
value tracker; no unsafe native or JIT machine code is run. Four added cases
include argument-clearing and return-overwrite safe controls.

Retained historical evidence: `/tmp/kdlock-admission-boundary.UQLmRm/`.

## Admission Address Diagnostics

Historical source snapshot, not current acceptance.

**Status: diagnostic increment verified; ordinary/nested JIT regression open.**
Evidence: `/tmp/kdlock-admission-cause.P39W8G/`. The 168-input freeze at
**2026-09-08 09:32:12 +08** changes only `disassem/context_policy.py`,
`disassem/disassem.py`, and `tests/unit/test_jit_diagnostics.py` relative to the
whole-word RMW snapshot. The withdrawn CALL-phase prototype is not restored.

`CONTEXT_ADDRESS_WIDENED` supplements the existing native-only refusal. It
reports the failed expression/candidate, register inputs, widened registers,
memory cell/word counts and total-work use/limit. Expression text is bounded
to 240 characters. The reporter neither evaluates IR again nor changes the
analysis snapshot/work count; it does not make unknown addresses safe.
The original rejection reason/RIP and status 2/no-image behavior remain.

Retained historical evidence: `/tmp/kdlock-admission-cause.P39W8G/`.

## Native CALL Phase Experiment

Historical source snapshot, not current acceptance.

**Status: diagnostic prototype withdrawn; whole-entry policy unchanged.**
Evidence: `/tmp/kdlock-call-effects.VjBoN1/`. This work starts from the
whole-word RMW candidate and does not claim completion of its 22 failed JIT
gates. No guest kernel edit/build/install or live module/JIT execution occurs.

The generated CALL pushes the source return address through virtual RSP into
the waiter stack (`special_inst.py: process_push`). At an ordinary CALL miss,
`execute_cs_hl` publishes the missing target and exits with `KD_EXE_RUN_NATIVE`;
the current invocation does not return from that native callee into this JIT
version. Known lock controls and hostcalls can resume JIT. None of these facts
justifies omitting the CALL write or assuming arbitrary callee memory/GPR
preservation.

Retained historical evidence: `/tmp/kdlock-call-effects.VjBoN1/`.

## Whole-Word RMW Facts

Historical source snapshot, not current acceptance.

**Status: not accepted; all 48 integrations attempted, 22 positive gates fail.**
Evidence: `/tmp/kdlock-rmw-words.V4gSiK/`. Production changes are confined to
`disassem/context_memory.py` and `disassem/context_policy.py`; three test files
extend the independent audit and focused coverage. No emitter, lock/executor,
two-word args ABI or guest kernel changes.

**168 inputs** are frozen at **2026-09-08 08:02:57 +08**; five differ from the
identity-write freeze. The changed tests are `tests/audit_context_spills.py`,
`tests/unit/test_context_memory.py` and `tests/unit/test_context_spill_audit.py`.
All 38 unit programs pass without skips before integration. Both external
module profiles build; the default profile and its text hash are restored.

Retained historical evidence: `/tmp/kdlock-rmw-words.V4gSiK/`.

## Identity Memory Writes

Historical source snapshot, not current acceptance.

**Historical unaccepted candidate; all 48 integrations attempted, 22 positive gates fail.**
Superseded by the [whole-word RMW follow-up](#whole-word-rmw-facts).
Source: `/tmp/kdlock-memory-identity.E8klOz/`, **168 inputs** frozen at
**2026-09-08 06:52:55 +08**. Four files differ from the preceding CALL-write
freeze: `disassem/context_policy.py`, `tests/audit_context_spills.py`,
`tests/unit/test_context_memory.py` and `tests/unit/test_context_spill_audit.py`.
No emitter, executor, two-word ABI, lock protocol or guest kernel changes.

The earlier diagnostic-only `/tmp/kdlock-stack-provenance.KwcR2Z/` replays
captured mode-0/1/4 text with concrete entry RSP/RBP assumptions, with/without
plain-control-call register preservation. All six still refuse and emit zero
assembly. No generated code is executed. These unenforced assumptions are not
adopted and provide no evidence of a private/disjoint source-stack contract.

Retained historical evidence: `/tmp/kdlock-memory-identity.E8klOz/`, `/tmp/kdlock-stack-provenance.KwcR2Z/`.

## CALL Return-Slot Facts

Historical source snapshot, not current acceptance.

**Historical unaccepted candidate; 22 positive JIT gates fail.**
Superseded by the [identity-write follow-up](#identity-memory-writes).
`/tmp/kdlock-call-facts.gjpvhA/` contains **168 inputs** frozen at
**2026-09-08 06:07:06 +08**. Four files differ from the preceding CFG-root
freeze: `disassem/context_policy.py`, `tests/audit_context_spills.py`,
`tests/unit/test_context_memory.py` and `tests/unit/test_context_spill_audit.py`.
No emitter, execution ABI, lock protocol or guest kernel is changed.

An isolated experiment first tested retaining register facts only at the four
plain control calls, with and without recording their stack write. All four
mode-1/4 captured-text replays still refuse. That diagnostic-only summary is
not implemented in production: no C ABI preservation or private-stack
assumption is introduced to bypass the alias regression.

Retained historical evidence: `/tmp/kdlock-call-facts.gjpvhA/`.

## CFG Root Initialization

Historical source snapshot, not current acceptance.

**Historical incomplete candidate; fourteen complex nested JIT gates fail.**
Superseded by the [CALL-write follow-up](#call-return-slot-facts). Source:
`/tmp/kdlock-cfg-roots.LGKcon/`, **168 inputs** frozen at
**2026-09-08 05:09:01 +08**. Three files differ from the preceding mask freeze:
`disassem/context_policy.py`, `disassem/disassem.py` and
`tests/unit/test_context_policy.py`. No instruction emitter, wrapper, lock
protocol or guest kernel change is included.

Production analysis no longer seeds every selected block as an independent
unknown entry. Actual entry/learned roots seed the worklist; normal successors
are initialized by real incoming state. Joins/backedges remain conservative.
Selected direct callees have independent inputs, and selected CALL fallthroughs
remain covered when decoder endpoint edges are absent. Missing/invalid roots,
missing location databases and unreached selected blocks refuse before image
generation. No source path is pruned, CALL facts are still clobbered, and the
1M memory-work limit is unchanged.

Retained historical evidence: `/tmp/kdlock-cfg-roots.LGKcon/`.

## Memory Value Forwarding

Historical source snapshot, not current acceptance.

**Historical incomplete candidate; mode-4 positive JIT fails.** Superseded by
the [CFG-root follow-up](#cfg-root-initialization), not accepted. Mask candidate:
`/tmp/kdlock-memory-masked.JK2xlS/`, **168 inputs** frozen at
**2026-09-08 03:47:20 +08**. Seven differ from the 166-input audit-only freeze.
It adds finite bit-mask bounds after the
preceding 168-input freeze at `/tmp/kdlock-memory-verified.3mqGs4/` fails its
mode-1 nested positive gate. The latter was frozen at
**2026-09-08 03:34:20 +08** and is retained separately, not accepted by retrying
only the failed command. Production lock/executor, instruction emitters,
two-word wrapper ABI and guest kernel are unchanged throughout this work.

The byte-value model is described under the historical candidate below. Its
normalization/accounting follow-up preserves all value alternatives and the
**1M** work limit:

Retained historical evidence: `/tmp/kdlock-memory-masked.JK2xlS/`, `/tmp/kdlock-memory-verified.3mqGs4/`, `/tmp/kdlock-memory-values-lea.EqWx7V/`.

## Memory Value Candidate

Historical source snapshot, not current acceptance.

**Historical failed candidate; not current acceptance.** Evidence:
`/tmp/kdlock-memory-values-lea.EqWx7V/`, **168 inputs** frozen at
**2026-09-08 02:38:42 +08**. Seven differ from the audit-only snapshot: the new
`context_memory.py` and memory unit program, `context_policy.py`, the unit
Makefile, context workload, workload dispatcher and test 12. Production
lock/executor, instruction emitters, two-word ABI and guest kernel are unchanged.

The candidate models static IR-store byte values, not live memory contents.
Exact unchanged entry-register bases plus offsets identify cells; distinct
bases may alias. Proven covering writes replace old bytes, uncertain writes
join old/new alternatives, and partial writes compose by width. Memory facts
join with register facts across both CFG and instruction-internal IR. Calls and
unliftable instructions clear register constants/identities but retain possible
old memory values plus unknown clobbers. Unknown stores also affect a fallback
domain. Limits are 256 bytes, 64 alternatives, 256 evaluation forks, 16-byte
accesses and 1M estimated work per tracker. Restoring a branch cannot reset work.
This is sequential bounded analysis, not complete alias/concurrency safety.

Retained historical evidence: `/tmp/kdlock-memory-values-lea.EqWx7V/`, `/tmp/kdlock-memory-values.0GA9UK/`.

## Memory Forwarding Audit

Historical source snapshot, not current acceptance.

This is the historical failing audit-only snapshot. The later
[memory-value candidate](#memory-value-candidate) passes this bounded corpus
but is not accepted because its positive JIT regression fails.

Evidence: `/tmp/kdlock-context-spill-audit.xmexdo/`, **166 inputs** frozen at
**2026-09-08 01:43:27 +08**. Only three inputs differ from the preceding
IR-memory freeze: `tests/audit_context_spills.py`, its unit program and the
unit Makefile. Production translator, daemon, lock/executor, test workload,
two-word ABI and guest kernel are unchanged. This is a failing audit with an
implementation backlog, not an accepted production fix.

Retained historical evidence: `/tmp/kdlock-context-spill-audit.xmexdo/`.

## IR Memory Admission

Historical source snapshot, not current acceptance.

Accepted candidate: `/tmp/kdlock-context-memory.miJshl/`, **164 inputs**
frozen at **2026-09-08 00:51:43 +08**, six changed from the internal-IR snapshot.
Only `context_policy.py`, `disassem.py`, the policy unit program, context workload,
workload dispatcher and test 12 change. No instruction emitter, production
lock/executor, wrapper ABI or guest kernel code changes.

`before-unit.log` retains **21 old-implementation assertion failures** across
six real-translator methods. LODS/STOS/MOVS/CMPS/SCAS and XLAT have no explicit
decoded memory operands; POP/PUSH/RET/CALL also have implicit stack effects.
The old policy therefore admits constructed sensitive addresses, crossing
access spans, successive/repeated accesses and widened memory pointers. All
test bytes are decoded/generated in a userspace fixture, not executed in kernel.

Retained historical evidence: `/tmp/kdlock-context-memory.miJshl/`.

## Instruction-Internal IR Admission

Historical source snapshot, not current acceptance.

Accepted candidate: `/tmp/kdlock-context-ir.f26Zqp/`, **164 inputs**
frozen at **2026-09-08 00:17:07 +08**, six changed from the CMOV snapshot.
Changes are limited to context admission, its diagnostic label, the unit program,
the context workload/dispatcher and test 12. Production lock/executor code,
instruction emitters, two-word ABI and guest kernel are unchanged.

`before-unit.log` records **33 assertion failures** in three real-translator
test methods on the old implementation. SHL/SHR/SAR, ROL/ROR/RCL/RCR, SHLD/SHRD,
CMPXCHG, BSF/BSR and REP lifts can erase a known address or an unaffected GPR
because they have internal IR blocks. Counts may be zero, so discarding the
old destination loses a valid sensitive-address alternative. Known nonzero
SHL/ROL counts can also construct the sensitive address in a taken block.

Retained historical evidence: `/tmp/kdlock-context-ir.f26Zqp/`.

## Conditional-Move Admission

Historical source snapshot, not current acceptance.

Accepted candidate: `/tmp/kdlock-context-cmov.Oyghtm/`, **164 inputs** frozen at
**2026-09-07 23:34:34 +08**. Five inputs differ from the preceding body-witness
format checkpoint: `context_policy.py`, its unit program, the context workload,
workload dispatcher and test 12. No production lock/executor, emitted instruction
implementation, two-word ABI or guest kernel code changes.

The old tracker discards all facts when miasm represents an instruction using
extra IR blocks. `before-probe.log` shows three real translator false negatives
after CMOV: the untaken destination, taken source and an unaffected register
can each carry an address that reaches a sensitive interval at the later read.
All three wrongly return success and emit 537 bytes of assembly. The subsequent
`before-unit.log` records **24 assertion failures**, without fixture crashes:
eight operand/CFG forms and all sixteen CMOV condition encodings. A former
"unknown conditional write" admission control is moved into the rejection
cases because the old destination remains a possible sensitive base.

Retained historical evidence: `/tmp/kdlock-context-cmov.Oyghtm/`.

## Generated-Body Execution Witness

Historical source snapshot, not current acceptance.

Accepted runtime batch: `/tmp/kdlock-jit-body.Fbf8gE/`, **164 inputs** frozen at
**2026-09-07 22:39:51 +08**. Nine inputs differ from the preceding register
freeze: translator, wrapper/header, executor logging, common shell assertions,
unit Makefile, two existing unit helpers and one new unit program. Guest kernel
code/configuration and lock/continuation decisions are unchanged. The two-word
input ABI and stack layout are retained; the previously reserved second output
now carries an optional zero/one execution witness, not an instruction count.

The old common assertion accepts a lone pre-call `execute_cs` log as execution
evidence. The retained `before-fix.log` reproduces that false positive and the
absent return witness: all seven initial methods fail assertions, without a
fixture crash. The final default-off control independently verifies that a
real guest-userspace wrapper can execute a MOV of 42 to RAX while returning
zero in that slot, just as a dispatcher-only invocation does.
This establishes an observation gap, not that previous successful workloads
failed to execute JIT.

Retained historical evidence: `/tmp/kdlock-jit-body.Fbf8gE/`.

## CALL-Miss Register Witnesses

Historical source snapshot, not current acceptance.

Accepted candidate: `/tmp/kdlock-native-registers.JIwFuQ/`, **163 inputs** frozen at
**2026-09-07 21:52:25 +08**.
Eight inputs differ from the preceding entry-only freeze: the workload,
`test_10_native_resume.sh`, unit Makefile, and five new probe/oracle/fixture
files. No production executor, translator, wrapper or guest kernel is changed.
The workload does change even with the probe disabled; unchanged production
module text must not be confused with unchanged workload text.

The default-off `native_resume_registers` probe records 13 seed-dependent GPR
stamps plus valid RDI/RBP/RSP at an assembly callee entry, before a C prologue.
It also records the original CALL return, two stack tags, returned RAX and
capture count. A separate 216-byte-per-request array is allocated only when
enabled (65536 slots, 13.5 MiB); existing request records are unchanged.
The caller uses 64 extra virtual/native stack bytes, plus the CALL return word;
this is not a new combiner shadow-stack allocation or wrapper argument.

Retained historical evidence: `/tmp/kdlock-native-registers.JIwFuQ/`.

## Kernel-Only Execution Entry

Historical source snapshot, not current acceptance.

Accepted candidate: `/tmp/kdlock-kernel-entry-only.XHuRTO/`, **158 inputs** frozen at
**2026-09-07 21:03:22 +08**. Only `kernel_module/exe.c`, `include/exe.h` and
`include/kd_segment.h` differ from the preceding kernel-baseline freeze.
The unused `kd_exe_on_call()` function, its `kd_exe_ret` structure, unpinned
task-CPU GS sampler and private diagnostics are removed. Repository source
inspection found no caller, hook registration or export. This removes a dead
userspace-oriented API, not a demonstrated active spin/mutex execution defect.

The frame-backed `kd_exe_on_call_hl_entry()` body, shared unlock endpoints,
status values, daemon packets and two-word wrapper ABI are unchanged. The
translator, lock backends, workload and tests are unchanged. Guest source/config/
build/live identity checks pass; the historical guest futex hooks remain in
the captured kernel and are not registered by kdlock. No kernel source/config
change, build/install, VM restart or Git commit is part of this increment.

Retained historical evidence: `/tmp/kdlock-kernel-entry-only.XHuRTO/`.

## Captured Kernel Baseline

Historical source snapshot, not current acceptance.

Candidate: `/tmp/kdlock-kernel-baseline-verified.I4n5cI/`, **158 inputs** frozen
at **2026-09-07 20:38:15 +08**. Six inputs are new: `.gitattributes`, the four
baseline data/checker files and its unit program. The existing unit Makefile
registers that program. Every preceding 152-input file except that Makefile
is unchanged; no module, daemon, translator or workload implementation changes.
This is prerequisite reproducibility work, not new lock semantics or permission
to alter the guest kernel.

### Source And Identity

Retained historical evidence: `/tmp/kdlock-kernel-baseline-verified.I4n5cI/`, `/tmp/kdlock-kernel-baseline.SQbmuD/`.

## Context CFG Constants

Historical source snapshot, not current acceptance.

Accepted candidate: `/tmp/kdlock-context-flow-verified.Qb81Nt/`, 152 inputs frozen at
**2026-09-07 19:21:51 +08**. Six inputs differ from the preceding middle-layer
snapshot: `context_policy.py`, `disassem.py`, the policy unit test, the context
workload, its module selector and `test_12_context_native_only.sh`. No production
lock protocol, wrapper ABI or guest kernel change is involved. The 73 distinct
fresh commands consist of the new `percpu-flow` refusal and all preceding 72
regressions, each rerun on this freeze from **19:25:41 to 20:03:13 +08**.
All pass: **63 actual-JIT / ten native-only**. All **33 unit programs** pass
without skips before/after; final audits pass at **20:04:44 +08**. This is the
focused matrix, not the historical 341-invocation suite or a whole-context proof.

The preceding block-local tracker drops the computed base at control transfers.
Three real miasm/codegen negatives reproduce admission of a sensitive `[RAX]`
read: a straight JMP between base and adjustment; a conditional join with one
safe and one sensitive predecessor; and a backward edge whose producer is
decoded later. The same three now return native-only exit 2 before codegen.
The bytes are only decoded/generated in guest userspace, never executed as
unsafe kernel JIT:

Retained historical evidence: `/tmp/kdlock-context-flow-verified.Qb81Nt/`, `/tmp/kdlock-context-flow-red.9a2MKf/`, `/tmp/kdlock-context-flow-candidate.IS1I5d/`.

## Middle-Layer Readmission

Historical source snapshot, not current acceptance.

Accepted candidate: `/tmp/kdlock-readmission-middle-verified.qhexWm/`,
152 inputs frozen at **2026-09-07 18:12:57 +08**. Seven test-only inputs differ
from the accepted last-layer snapshot below. All **72 distinct fresh focused
invocations** pass from **18:14:24 to 18:52:45 +08**: **63 actual-JIT / nine
native-only**. This includes all 16 new B/C cases and the previous 56 commands,
each executed on this freeze, not reused receipts. All **33 unit programs**
pass without skips before/after. Final audits pass at
**2026-09-07 18:54:23 +08**. This is not the historical 341-invocation suite.

`KD_DEEP_READMIT_LAYER=1/2/3` selects B/C/D, default D. Sixteen new B/C cases
combine one/two refusals, target/native independent observer and both release
orders. Two refusals at B/C locally acquire that lock in the preceding physical
frame, then continue its existing JIT and delegate a deeper child. The follow
observer checks actual parent/child identity, both original locks' owner,
ledger depth, GS/task and continuation. Expected RPC totals are 5/4/3 for local
B/C/D, not always three; successful second-child execution always uses six.
Native frames/ACKs must remain zero and selected-lock completions exactly 2/1.

Retained historical evidence: `/tmp/kdlock-readmission-middle-verified.qhexWm/`, `/tmp/kdlock-readmission-middle-red.foBlt6/`, `/tmp/kdlock-readmission-middle-candidate.cm0GDr/`.

## Live Virtual Readmission

Historical source snapshot, not current acceptance.

Preceding accepted candidate: `/tmp/kdlock-live-readmission-final.EA3eGy/`, **152 inputs**
frozen at **2026-09-07 17:11:36 +08**. Nine inputs differ from the preceding
label checkpoint: spin SELFTEST inclusion/dispatch, a new readmission observer,
the opt-in workload coordination, test-21 driver, protocol/oracle and unit
fixtures. The parent critical-section macros and direct-caller translated body
are unchanged; new waits and roles run outside those critical sections. The
guest kernel, production lock protocol, wrapper ABI and capacities are unchanged.

All **56 distinct focused invocations** run from **17:13:02 to 17:39:16 +08**
and pass on this same freeze. Final audits pass at **2026-09-07 17:41:06 +08**.
The eight new invocations and the previous 48 commands are all freshly run;
neither the development pilot nor older receipts are reused. This is not the
historical full 341-invocation suite.

Retained historical evidence: `/tmp/kdlock-live-readmission-final.EA3eGy/`, `/tmp/kdlock-live-readmission.tgw4qr/`, `/tmp/kdlock-live-readmission-candidate.479Crt/`.

## Live Virtual Refusal Continuation

Historical source snapshot, not current acceptance.

Evidence for this follow-up is collected separately under
`/tmp/kdlock-live-refusal-verified.pSTmDB/`: **150 inputs**, frozen at
**2026-09-07 16:06:49 +08**. Six inputs differ from the preceding virtual-
refusal fix: SELFTEST call sites in spin C, a new buffered observer, test-21's
driver/oracle, and its unit test plus new observer fixture. No translated
workload, guest kernel, production ABI, capacity or stack gate changes.

`KD_DEEP_REFUSAL=1/2` selects one NO_RUN/RUN_ERROR return after child allocation
and parent attachment but before `kd_exe_on_call_hl_entry()`. The driver waits
for all artifacts to be published, stops the daemon, then arms the last lock
of the existing four-lock stage-1 workload. Only an unexecuted virtual child
with an already-executed parent is eligible. The atomic claim cannot be rearmed
by changing the lock parameter. No live artifact is overwritten or revoked.

Retained historical evidence: `/tmp/kdlock-live-refusal-verified.pSTmDB/`, `/tmp/kdlock-live-refusal.UT1JW6/`, `/tmp/kdlock-live-refusal-final.zDouQR/`.

## Virtual Preentry Refusal Return

Historical source snapshot, not current acceptance.

Final evidence: `/tmp/kdlock-virtual-refusal-final.mpbNe1/`, **148 inputs**
frozen at **2026-09-07 15:14:41 +08**. Seven inputs differ from the preceding
147-input test-only freeze: two production C files, one header comment, three
existing unit-test files and the new `spin_queue_return_fixture.c`.
No guest kernel edit, new hook, owner handoff, ABI/layout or capacity change
is included. Production changes are the native-only `jit_retry` assignment
and removal of the premature parent-IDLE store during child cancellation.

The old code distinguishes these cases incorrectly:

Retained historical evidence: `/tmp/kdlock-virtual-refusal-final.mpbNe1/`, `/tmp/kdlock-virtual-refusal.eXNmUN/`.

## Frame Refusal Queue Connection

Historical source snapshot, not current acceptance.

Evidence: `/tmp/kdlock-frame-refusal.jlvfIx/`, **147 inputs** frozen at
**2026-09-07 14:15:23 +08**. Only `tests/unit/test_spin_outer_progress.py` and
`tests/unit/spin_outer_progress_fixture.c` differ from the preceding observer
freeze. The complete source archive, individual hashes and changed-input list
are retained. Production translator, daemon, modules and integration drivers
are byte-identical inputs; no guest kernel changes were made.

The fixture used to substitute an unconditional NULL for frame allocation.
Its capacity branch now calls the extracted production allocator. A valid
same-owner context is filled through eight API calls, not by assigning its
depth. Production spin `execute_cs()` then attempts the ninth allocation and
returns through the real combiner's rejection/splice path. Two deterministic
CPU identities, native/virtual requests, zero through eight scanned followers,
and NUMA-on zero through two committed prefix nodes are covered.

Retained historical evidence: `/tmp/kdlock-frame-refusal.jlvfIx/`.

## Live Node Reservation Observer

Historical source snapshot, not current acceptance.

Candidate evidence: `/tmp/kdlock-node-observer-fixed.gttbqI/`, **147 inputs**
frozen at **2026-09-07 13:29:05 +08**. Relative to the 144-input producer
increment, this adds `tests/kernel/spin_node_trace.c`,
`tests/spin_node_protocol.py` and `tests/unit/test_spin_node_protocol.py`.
The runtime changes are conditional SELFTEST observation and initialization/
cleanup only; default production `.text` remains
`02f620e4f96caca4ac19a35ad32cea93dc1103b023d51d71216e5d977e41935a`.
No guest-kernel, capacity, stack-gate, translation-policy or two-word ABI changes.

The observer distinguishes both successful producers, rolled-back full-pool
attempts, absent contexts, preparation cancellation, four queue-release classes
and remote polling. It records the first invalid count/context without repair
or later overwrite. Records are allocated once with `alloc_percpu()` only
when the read-only SELFTEST parameter is enabled, before hooks are published;
initialization rollback and drained unload free them. Per-CPU record size is
128 bytes (5120 bytes requested payload on 40 CPUs, not measured RSS).
Static per-CPU sections remain 7904/7968 bytes for NUMA off/on. Reporting is
outside live producers and reads scalar state only.

Retained historical evidence: `/tmp/kdlock-node-observer-fixed.gttbqI/`, `/tmp/kdlock-node-observer.0YjV0I/`.

## Node Producer Accounting

Historical source snapshot, not current acceptance.

Evidence: `/tmp/kdlock-node-producers.HBWAxn/`, **144 inputs** frozen at
**2026-09-07 12:53:03 +08**. Three existing unit-test files change and one
included fixture is added. No production function, hook, capacity, ABI,
integration workload or oracle changes. All 143 prior inputs remain listed;
the extra input is `tests/unit/spin_node_pool_fixture.c`.

`test_spin_shadow.py` now compiles both actual node producers, preparation,
completion adapters, queue-head and queued-waiter exits. Per NUMA configuration:

Retained historical evidence: `/tmp/kdlock-node-producers.HBWAxn/`.

## Full Frame Context Refusal

Historical source snapshot, not current acceptance.

Evidence: `/tmp/kdlock-frame-capacity.r3eVYM/`, **143 inputs** frozen at
**2026-09-07 09:18:22 +08**. The default-off
`spin_selftest_probe_frames=1` requires frame tracing in a SELFTEST build.
Test 14 enables it with `KD_CHAIN_PROBE_FRAMES=1`. Existing limits, guest
kernel hooks, the two-word ABI and default production text are unchanged.

At the entry observation for a real eighth physical frame, the probe verifies
that current owns the full, valid context and is pinned. One atomic claimant
per module load copies all **5264 context bytes** into static BSS, calls the
actual `kd_exec_frame_push()` with otherwise valid arguments, and verifies
NULL, byte-for-byte unchanged context and valid current-frame/parent state.
It never changes a capacity/count or injects a NULL return. Shallow frames
must produce a zero-attempt record; the default profile produces no capacity
record. Reporting occurs only after frame users drain, not at the printed
timestamp of the actual attempt.

Retained historical evidence: `/tmp/kdlock-frame-capacity.r3eVYM/`.

## Combined Physical And Deferred Pressure

Historical source snapshot, not current acceptance.

Evidence: `/tmp/kdlock-combined-chain.EOFx47/`, **140 inputs** frozen at
**2026-09-07 05:36:10 +08**. Four test inputs differ from the preceding observer
freeze: the chain workload, driver, protocol oracle and its unit tests.
Production kdlock, the two-word JIT ABI and guest kernel are unchanged.

`KD_CHAIN_DEFER_LEVELS` selects sorted unique zero-based chain levels and
`KD_CHAIN_DEFER_COUNT=1..3` adds real remote followers at each. Buffering and
NUMA-on compilation are mandatory. Captured online/allowed topology determines
distinct remote CPUs outside the fixed worker set, retaining a spare controller;
insufficient resources are rejected before module loading. New follower roles
use `30+3*level+extra`. Their lock site is not warmed and the daemon is stopped
before arming, so they must run natively on their original tasks.

Retained historical evidence: `/tmp/kdlock-combined-chain.EOFx47/`.

## Buffered Deferred Observer

Historical source snapshot, not current acceptance.

Evidence: `/tmp/kdlock-buffered-defer.tzUgSd/`, **140 inputs** frozen at
**2026-09-07 04:58:19 +08**. Eight inputs differ from the preceding freeze,
including a new standalone C trace fixture. Guest kernel and the two-word JIT
ABI are untouched. Only SELFTEST instrumentation and test workload/oracle
code change; default production `.text` still hashes to
`02f620e4f96caca4ac19a35ad32cea93dc1103b023d51d71216e5d977e41935a`.

`spin_selftest_deferred_buffered=1` is default-off and load-time-only, available
with NUMA+selftest. Existing single-lock selection remains, while an additional
eight-address array can observe multiple levels. Configure it only before
arming. Buffered append/splice/restore snapshot scalar values while their
nodes/tasks are valid; save/resume use the combiner's local lock stack and
head/tail values without dereferencing saved nodes. A 256-slot static array
has saturating atomic reservation and release/acquire-ready publication.
Teardown reports complete records after callers drain, plus sticky overflow
and incomplete counts. These records have a separate tag; they must not be
ordered against ordinary dmesg lines by their eventual print positions.
Predecessor link logs remain live, including cached identities after publication.

Retained historical evidence: `/tmp/kdlock-buffered-defer.tzUgSd/`.

## Nested Deferred-List Isolation

Historical source snapshot, not current acceptance.

This test-only prerequisite changes `test_spin_shadow.py` and its C fixture,
not production code or the guest kernel. Evidence:
`/tmp/kdlock-nested-deferred.CJaUFF/`, 139 inputs frozen at
**2026-09-07 04:14:56 +08**. Exactly those two input hashes differ from the
preceding 309-invocation freeze. That full matrix remains a separate receipt;
it is not a new full-matrix pass for the changed unit inputs.

The fixture now compiles the actual queue-head entry, NUMA scan, append helper
and combiner loop together. At each recursive level, the first request commits
a remote group, and the second selects another group before entering a child.
The child starts with an empty deferred list and must restore the parent's
head/tail without changing any parent node. Normal completion and NO_RUN/ERROR
pre-entry refusals are checked independently at parent and leaf. A refused
request retains its speculative followers; previously committed groups splice
ahead of that request. Exact next pointers, completion/wakeup states, published
chain membership, saved context and node counts are checked, not only totals.

Retained historical evidence: `/tmp/kdlock-nested-deferred.CJaUFF/`.

## NUMA Physical Stack

Historical source snapshot, not current acceptance.

Status: depth-1..8 measurement and the complete 309-invocation matrix accepted;
general and combined-pressure contracts remain open. Current freeze:
`/tmp/kdlock-stack-packet.Z7SjlC/`, **139 inputs**, frozen
**2026-09-07 00:47:31 +08**. No guest kernel change, stack-capacity increase,
additional JIT argument, flags repair or code-version isolation is included.
NUMA remains disabled in default builds.

The old-production baseline at `/tmp/kdlock-numa-stack.dJwYA4/` passes ten
real depth-1/2/4/6/7 commands with NUMA off/on. Its seven-layer NUMA-on entry
sample leaves 1784 bytes, but only 1008 bottom bytes remain unmodified. The
measured 944-byte per-level entry cost projects an eight-layer sample of
840 bytes, below the existing 1024-byte gate. Extending its 776-byte observed
write tail projects only 64 bytes. These are inferences, **not an executed
eight-layer NUMA-on failure**, and the native-capacity path can use still more
stack. The known-risk old eight-layer case was not run.

Retained historical evidence: `/tmp/kdlock-stack-packet.Z7SjlC/`, `/tmp/kdlock-numa-stack.dJwYA4/`.

## Repeated Admission And Multiple Followers

Historical source snapshot, not current acceptance.

Status: accepted on 137 frozen inputs at
`/tmp/kdlock-controller-affinity.cMByFO/`. The freeze is **2026-09-06 21:09:01 +08**;
all **295 integration commands** finish at **23:50:22**, and final verification
completes at **23:52:58**. All **30 unit programs** pass without skips before
and after integration. The independent NUMA+selftest build is checked before
loading; default production text is restored afterward. Every receipt matches
its planned command and source manifest; the standalone first case is counted
once, not duplicated when the sequential matrix resumes.

The earlier candidate `/tmp/kdlock-native-readmission.nxc9Tt/` retains a
production-function red/green regression: the old repeated native decoder
fails **84 conditions per NUMA profile**, and the fix passes **4070/8243** total
checks off/on. Twelve new sequences per profile exercise one to four refusals,
including not-ready, frame-pool failure and alternation, followed by one JIT
stub execution by distinct mock owners. NUMA-on also publishes committed
prefixes. The fixture has partial registers and deterministic kernel/JIT
primitives; it is not a live repeated-admission or full-register/assembly proof.

Retained historical evidence: `/tmp/kdlock-controller-affinity.cMByFO/`, `/tmp/kdlock-native-readmission.nxc9Tt/`, `/tmp/kdlock-multiple-followers.zTagtv/`.

## NUMA Admission Rejection

Historical source snapshot, not current acceptance.

Evidence: `/tmp/kdlock-multi-deferred.djq6Xt/`. This increment was found while
reviewing longer NUMA deferred lists. In W -> R -> S, selection can defer R
before admitting W. If W cannot run, linking R back to W forms a cycle through
W's unchanged `next`. The fix retains the pre-scan deferred tail and restores
it on `NO_RUN`/pre-entry `RUN_ERROR`, preserving any older committed prefix.
The existing final splice connects that prefix to W and its original suffix.
No guest-kernel change or rollback of executed critical-section writes is involved.

`rejected-selection-red.log` reproduces **608 failed conditions** against the
old production NUMA implementation; NUMA-off passes. The unchanged regression
then passes **2524/6613 checks** off/on in `rejected-selection-green.log`.
Both retain eight original progress scenarios, plus **36/108 rejection
scenarios**: not-ready, pinned-context, disabled JIT and substituted frame
allocation refusal, zero through eight fresh followers, and (NUMA-on) zero
through two existing deferred prefix nodes. Checks include exact bounded
acyclic queue identity/order, sole head wakeup, no false completion, original
owner retention and drain. The test extracts actual selection, admission and
combiner functions, but substitutes JIT, frame pool and CPU/lock primitives;
it is not a concurrent long-list kernel test or real allocation exhaustion.

Retained historical evidence: `/tmp/kdlock-multi-deferred.djq6Xt/`.

## Deferred Queue Publication

Historical source snapshot, not current acceptance.

The preceding increment adds an explicit `KDLOCK_NUMA=1` build switch and
SELFTEST-only observations, plus an optional test-21 remote follower/local
successor. Default NUMA combining remains off. All **248 integration commands**
pass on 137 frozen non-document inputs at `/tmp/kdlock-deferred-final.IVjVjO/`.
The freeze is **2026-09-06 14:54:03 +08**; integration runs from **14:54:32 to
17:02:13**, and final verification completes at **17:03:08**. Every completed
receipt is checked against the planned command and source manifest. Seven
documents are maintained and archived separately from the code freeze.

All 41 new deferred cases now pass on these inputs: 32 depth-four combinations
cover both node orientations, four positions and full-JIT/before/after/between
boundaries; nine selected depth-eight cases add capacity and ordinary CALL
continuation. Eight runs are wholly JIT and 33 cross native boundaries,
with 168 native frames, 86 ACKs and 315 owner-side RPC replies. The detailed
receipts are summarized in `deferred-stats.json`. All 27 previous deep cases
and all 180 baseline commands also pass on these inputs. Every case requires
translated root execution, exact state and owner/ACK/drain checks; the extra
successor adds exactly one state update to the selected lock. Append and
splice records identify the real owner and node pointers, and subsequent
R/S acquisitions and returns establish actual progress. The deepest layer
uses normal batch splice; ancestor layers use early outer release. Actual
records contain 31 early-outer and ten normal-batch splices. Every one of the
41 deferred archives includes `linked.json`, `spin-build.cmd` with
`-DNUMA_AWARE`, the selftest module, captured topology and raw protocol log.
All 182 remote archives in the whole run contain placement/protocol evidence.

Retained historical evidence: `/tmp/kdlock-deferred-final.IVjVjO/`, `/tmp/kdlock-deferred-queue.dDogXz/`, `/tmp/kdlock-deferred-enabled.CBgXNh/`.

## Deep Logical Chains

Historical source snapshot, not current acceptance.

This workload/oracle-only increment adds `test_21_remote_depth.sh` and separate
mode-8 functions for depths 4-8. The production backend and guest kernel are
unchanged. Each depth has statically balanced acquisition sites, independent
holder/head/trailing traffic per lock, and a separate dependency owner. The
driver promotes through ordinary acquisitions, verifies `depth+1` matching
published artifacts, stops daemon, then arms contention with `mutex_jit=1`.
Virtual requests execute the root artifact at distinct continuation RIPs.

The corrected source freezes at **2026-09-06 13:40:07 +08**, with 135 matching
host/guest inputs. All **47 focused integration commands** run from
**13:40:29 to 14:02:43**, and final checks complete at **14:03:39**:

Retained historical evidence: `/tmp/kdlock-remote-depth-verified.aYZKlV/`, `/tmp/kdlock-remote-depth.KzwWVF/`.

## Remote NUMA Placement

Historical source snapshot, not current acceptance.

This workload/evidence-only increment leaves production kdlock, guest hooks,
the two-word `{waiter GS base, logical task}` wrapper and context admission
unchanged. Source is frozen at **2026-09-06 11:33:47 +08:00** in
`/tmp/kdlock-placement-final.sGAJ3o/`: 130 source/build/test inputs match the
guest, with only five files changed relative to the accepted 104-command
snapshot (workload module/helper, driver, log oracle and its unit fixture).
Builds, units and module/JIT execution run only in the recovery guest.

### Placement Contract

Retained historical evidence: `/tmp/kdlock-placement-final.sGAJ3o/`, `/tmp/kdlock-remote-placement.C52xEm/`.

## Three-Executor Remote Progress

Historical source snapshot, not current acceptance.

This follow-up extends the test workload/oracle only; it does not change the
production runtime accepted in the preceding remote-ancestor increment.
At that snapshot, all 104 commands pass on the fresh 130-input snapshot
frozen at 2026-09-06 10:17:35 +08:00 under
`/tmp/kdlock-remote-chain-verified.EG8v2p/`.
Integration runs from **10:18:01 to 10:55:35** Asia/Shanghai; final verification
completes at **10:56:36**. Earlier smoke/partial runs are not included in acceptance.

### Workload And Evidence Contract

Retained historical evidence: `/tmp/kdlock-remote-chain-verified.EG8v2p/`, `/tmp/kdlock-remote-chain.gssz7k/`, `/tmp/kdlock-remote-chain-final.5bgk6K/`.

## Remote Ancestor Progress

Historical source snapshot, not current acceptance.

This section records the preceding 76-command snapshot. Its statement that
real A/B/C was unverified describes that revision, not the follow-up above.

Virtual spin B now carries a logical requester link independent of the physical
CPU's frame stack. While A's executor waits for B's node, it services ancestor
unlock requests on its own CPU, releases physical A/L and private A/S, then
acknowledges B. Copied ancestor ledgers are updated after acknowledgment. A's
frame cannot retire while its logical child is WAITING/NATIVE, even after all
local locks are released. The final unlock CALL word is preserved when the
whole logical request completes remotely; it is consumed only if the parent
must resume its remaining JIT suffix.

Retained historical evidence: `/tmp/kdlock-remote-outer.xjNrNI/`, `/tmp/kdlock-remote-outer-final.ra64uh/`.

## Spin Outer Progress

Historical source snapshot, not current acceptance.

This section records the preceding 66-command source snapshot. Its remaining
remote-ancestor limitations describe that revision, not the increment above.

Local spin frames now release original A/L and private A/S at early outer
unlock while retaining B's physical owner. The batch preserves A's ticket and
CPU pin, publishes the saved successor once, and never touches that published
node again. After the B/frame suffix completes, it waits for the complete S
word (including pending/tail), reclaims S and acquires native A before executing
its own original request. NUMA-deferred nodes are flushed into the published
queue, not retained in a stale saved snapshot. This reuses the existing frame
callback and does not add wrapper arguments, frame fields or a guest kernel hook.

Retained historical evidence: `/tmp/kdlock-spin-outer-progress.STSvx7/`.

## Mutex Outer Progress

Historical source snapshot, not current acceptance.

An early mutex A unlock now releases the original native mutex and private
scheduling gate S while B remains owned by the acquiring executor. A frame
callback wakes the batch's saved successor once. The batch remains live through
the JIT/native B suffix; afterward the old executor reacquires A for its own
original request, without inspecting or waking that successor again.
This is not native owner handoff, transaction rollback or a guest kernel patch.
At this historical snapshot, spin's delayed-A/remote-frame dependency contracts
remained open; the local spin increment above supersedes only its local-A part.

`test_mutex_outer_progress.py` extracts production frame events, `execute_cs`,
`run_combiner`, and native-A gate helpers. Its five scenarios cover ordinary
JIT completion, JIT A-before-B completion, native miss before A, native miss
after A, and pre-entry not-ready handoff. The old production functions fail
12 of 104 checks; the fix passes 122/122, including the additional successor
progress/reuse and reacquisition checks reached only by the corrected path.
The JIT body, physical mutex, scheduling and frame pool are deterministic
substitutes. Its register fixture covers RIP/RSP/RDI and callee-saved registers,
not full `pt_regs`, privileged instructions or a concurrent kernel execution.

Retained historical evidence: `/tmp/kdlock-mutex-outer-progress.69mR7e/`.

## Pending After Outer Unlock

Historical source snapshot, not current acceptance.

This section records the preceding source snapshot, which retained physical
mutex A through B completion. The newer [mutex progress](#mutex-outer-progress)
increment changes that behavior; the historical results below are not evidence
for the new release callback.

This increment extends the remaining-local-lock protocol to a pristine
PENDING resource failure after JIT logically unlocks A. The shared
`kd_exec_frame_can_borrow_locks()` checks live frame state, the released-A
ledger and a remaining local suffix before CALL restoration or native
registration. Only PENDING `-ENOMEM`/`-E2BIG` restores the saved lock target
and CALL RSP. Registration also requires the restored target/RSP and a nonzero
return address; later control phases are not converted to continuation.
No entry replay, memory rollback, owner handoff, guest kernel hook, wrapper
argument or frame field is added.

Retained historical evidence: `/tmp/kdlock-pending-after-outer.w8aUex/`, `/tmp/kdlock-pending-after-outer-final.21j8at/`.

## CALL After Outer Unlock

Historical source snapshot, not current acceptance.

This increment fixes two production limitations, unlike the preceding
workload-only OOO increment. Spin already continued JIT after logically
unlocking A, but native registration rejected every `outer_unlock_seen` frame.
Mutex ended JIT at A unlock even with B still held, so it could not reach the
corresponding late CALL miss. An isolated guest-userland extraction of the
actual frame/known-call/native-admission functions reproduced **11 failed
assertions out of 55** before the fix; no known-bad path was deliberately run
to panic the guest.

Native registration now admits an ordinary CALL miss after A only with a live,
consistent released-A ledger, `KD_CALL_NONE` and an unreleased nested suffix
owned by this frame. The existing registry skips released A and routes B's
unlock to its real executor. Mutex's early-A handler records and consumes A's
CALL, continues JIT, and preserves the final B unlock CALL for the original
waiter's return trampoline. Completion no longer records A twice. This adds
no guest kernel hook, native owner handoff, wrapper argument, frame field,
flags repair or JIT-generation lifecycle mechanism.

Retained historical evidence: `/tmp/kdlock-after-outer-verified.2NcX4K/`, `/tmp/kdlock-after-outer.qdijFn/`, `/tmp/kdlock-after-outer-final.togail/`.

## Native OOO Continuation

Historical source snapshot, not current acceptance.

This follow-up closes a live-test gap, not a newly reproduced production
protocol bug. A stage-3 ordinary CALL miss occurs while A and B are both held;
the original waiter then unlocks A first, performs another B-protected update,
and unlocks B. The existing native rendezvous must retain the frame and borrowed
protection between those two acknowledgments. This is not recovery from a
JIT exit that first occurs after A was already unlocked.

New code is confined to the workload and its verifier: the included
`tests/kernel/native_ooo_workload.c`, mode 1/4 branches and private request
fields, the `KD_NATIVE_OOO=1` option in test 10, and
`tests/native_ooo_protocol.py` with four unit-test methods. The test parameter
is disabled during warmup/translation and armed only after daemon stops.
Three noinline native checkpoints observe before A unlock, after A's waiter
ACK with B still held, and after B's final waiter ACK. The earlier
`kd_resume_native_probe` must be the real CALL-miss target; checkpoint logging
cannot substitute for JIT execution evidence. Exact request-state recurrence
and an extra `kd_cs_step(B)` detect replay, omission or continued work without
the expected ordering. No owner word, pin, frame count or ACK is fabricated.

Retained historical evidence: `/tmp/kdlock-native-ooo.m4gob6/`.

## Context Register Addresses

Historical source snapshot, not current acceptance.

The block-local address follow-up reproduces a gap left by operand-span checks:
loading an ordinary address adjacent to a sensitive symbol, adjusting a GPR,
then dereferencing it could bypass per-instruction checks. Four real miasm/
codegen examples were admitted before the fix; their generated assembly sizes
were 525/561/525/515 bytes for ADD/read, LEA/write, EAX zero-extension and RMW.
All four now return native-only exit 2 with zero assembly bytes. These raw
examples are decoded/generated only, never executed in the kernel.

At that snapshot, production preflight uses miasm x86-64 IR for exact GPR
constants within each decoded block. It preserves alias/zero-extension and
parallel assignment semantics and drops unknown destination values. Substitution is limited to
memory addresses and indirect CALL/JMP targets. It does not read runtime
memory, retain flags, merge predecessor states or carry facts across calls.
The later [CFG increment](#context-cfg-constants) supersedes this cross-block
limit without adding runtime-memory or interprocedural analysis.
Extra IR control flow and unmodelled instructions clear facts, without a new
opcode refusal policy. The lifter works on copied instructions with a private
LocationDB; the existing codegen byte baselines remain unchanged.

Retained historical evidence: `/tmp/kdlock-context-registers.RGNlPa/`.

## Native Mutex Release Races

Historical source snapshot, not current acceptance.

The workload-only race extension keeps the original three-private-node JIT
setup, then lets the borrowed suffix finish before gating the physical owner's
own unlock. Two real userspace threads race signal delivery and gate release.
Native mutex success requires one candidate CS/unlock and 12007 total updates;
`-EINTR` requires zero candidate CS/unlock and 12006 updates. Both retain 12005
request records, one real JIT CALL-miss continuation and one waiter ACK.
Optional HANDOFF stimulation wakes the real native head; Linux sets the request
bit itself, which must still be observed before physical unlock. No queue word,
task signal, API return or owner assignment is fabricated by the fixture.

Two initial test failures are retained under
`/tmp/kdlock-mutex-signal-race.lIoQcx/` rather than counted as accepted runs:

Retained historical evidence: `/tmp/kdlock-mutex-signal-race.lIoQcx/`, `/tmp/kdlock-mutex-signal-race.lIoQcx/final/`.

## Native Mutex Signals

Historical source snapshot, not current acceptance.

`test_19_mutex_signals.sh` adds a workload-only fixture, a single-ioctl C signal
client and a Python process/controller oracle. It changes no production lock,
JIT/register protocol or guest kernel code. The initial holder waits for three
actual private nodes: future combiner, delegated waiter and tail. A single
waiter would only exercise direct handoff. After translation and daemon stop,
the queued combiner executes the middle waiter's JIT prefix; its real CALL
miss resumes the original waiter while the combiner retains the Linux mutex.
Only then do the two native API callers join its real `wait_list`.

All **12 variants** pass: interruptible head/non-head cancellation (1/2),
killable head/non-head cancellation (3/4), repeated with target `klock_test`
instead of `kd_native`, and repeated across NUMA nodes. Default six-CPU layout
is `0,1,2,3,4,5`; cross-NUMA is `0,20,1,21,2,22`. Those positions run initial
holder, combiner, JIT waiter, tail and the two native arrivals respectively.

Retained historical evidence: `/tmp/kdlock-mutex-signals.ACJNKo/`.

## Context Operand Spans

Historical source snapshot, not current acceptance.

`context_policy.py` now checks a memory operand's decoded byte width against
known sensitive intervals. The previous implementation tested only its starting
address: an eight-byte access beginning four bytes before `__per_cpu_offset`
was accepted even though it overlapped that table. Six real miasm/codegen
examples reproduce this in `red.log`: read, write, RMW, widening load, indexed
base and memory-indirect CALL. They return status 0 before the fix and status 2
with no generated image afterward. These bytes are not executed in the kernel.
The old adjacent-address positive fixture at table minus one is corrected to
table minus eight, so its entire eight-byte operand is actually outside.

Three added test methods bring the policy suite to **40 cases**. They check
non-overlapping boundary accesses, memory-source rather than destination width,
point-only LEA/immediate operands and overlap with an exact-only symbol whose
end is unknown. Visible indexed bases inherit the operand width; the index is
not inferred. This adds no register-value propagation or general analysis of
implicit/runtime-indexed memory access. The refusal packet, native handoff,
two-word wrapper ABI, instruction/flags lowering and guest kernel are unchanged.

Retained historical evidence: `/tmp/kdlock-context-span.N7zrfR/`.

## Live Spin Routing

Historical source snapshot, not current acceptance.

`test_18_spin_routing.sh` closes a gap between the production-hook unit fixture
and live timing evidence. It uses the existing SELFTEST-only promotion control,
without changing L/S queue words or counts. Four real ioctl callers are pinned
to distinct CPUs: owner, first private contender, native contender, and second
private contender. The second private contender starts only after the first
has genuinely reached L or S waiting; a thread-start flag is not used as proof
of lock queue publication. The production lock protocol is unchanged.

| Scenario | Controlled boundary | Required waiting witness before owner release |
| --- | --- | --- |
| 1 | Native owner acquires L before metadata promotion | First private owner blocks in L, second waits on S pending; native contender publishes L tail |
| 2 | Private owner changes from target to non-target name | First private contender holds S pending, second publishes S MCS tail; native contender waits in L |
| 3 | Non-target native owner changes to target name after acquisition | Native acquisition still has no private ticket; same L/S witnesses as scenario 1 |
| 4 | Target MCS waiter is remotely renamed after queue publication | Same witnesses as scenario 2; renamed waiter later acquires and unlocks through the retained route |

Retained historical evidence: `/tmp/kdlock-spin-live-routing.sn99wf/`.

## Context Address Admission

Historical source snapshot, not current acceptance.

Exact-start matching missed interior data/function addresses and visible
sensitive bases in indexed expressions. The added real miasm/codegen checks
first produced **10 assertion failures** in a 36-case policy run; no unsafe
kernel instructions were executed for that reproduction. The fixed policy
plus an additional boundary/owner test passes **37 cases**. All **21 unit
programs** pass before and after integration, without skips.

The loader retains sensitive names and conservative address intervals through
the next distinct visible symbol of the same kernel/module owner. Aliases do
not shorten intervals. Without a visible successor it knows only the exact
address. Padding may be refused too: kallsyms boundaries are not verified ELF
object sizes. An unresolved index no longer hides a known constant base term.
Tests cover interior loads/stores/address-taking, function calls/tail calls,
indexed loads/LEA/indirect calls, adjacent ordinary symbols, module boundaries,
late callees and post-outer-unlock exclusion. A separate guest check uses the
actual `__per_cpu_offset=0xffffffff82904b60` with a sign-extended x86-64 indexed
operand and also refuses before codegen. It is a decode/admission check, not
runtime execution of that indexed instruction.

Retained historical evidence: `/tmp/kdlock-context-address.mDmwlm/`.

## Spin L/S Integration

Historical source snapshot, not current acceptance.

The production spin path now stores kdlock pending/tail/OOO bits in private S,
claims original L through Linux before a batch or its own CS, and releases L
before publishing S as available. Native IRQ-save/BH/trylock and non-target
plain callers only operate on L. Completed waiters and native suffixes retain
generation-checked acquisition provenance, not just a recyclable MCS slot.
Virtual B's physical request and its logical-origin HOOK waiter have separate
refs. Each retained native frame contributes a reference before publication;
only the original waiter ends its pin after the final acknowledgment.

Nonlocal spin return first restores a native stack below both the saved hook
RSP and virtual CALL RSP, copies registers/ref locally, then ends or marks its
ticket. Normal owner returns restore the native input even when no queue node
was allocated. Hook routing preserves native acquisition across promotion and
keeps ticket-backed unlock routed after rename. The two-word wrapper ABI and
guest kernel are unchanged. Controlled teardown checks for live entries/gates;
these checks are not automatic hook draining or a source-lifetime protocol.

Retained historical evidence: `/tmp/kdlock-spin-routing.bnjhgP/`.

## Spin Acquisition Tickets

Historical source snapshot, not current acceptance.

Historical component snapshot, before the L/S integration above.

`kd_spin_entry.c` adds generation-checked acquisition refs, a 32-slot pool per
possible CPU, physical owner/gate association, and counted native references.
Only the original task/CPU may release its request pin. Remote executors drop
native references but never unpin that waiter. The actual hook, MCS, frame and
native-request routes remain unchanged; see DESIGN's Acquisition Ticket
Foundation and the still-open C2 integration tasks.

Retained historical evidence: `/tmp/kdlock-spin-entry.bl9Q8p/`.

## Native Spin Gate Foundation

Historical source snapshot, not current acceptance.

Historical component snapshot, before the L/S integration above.

`kd_spin_gate.c` now implements a bounded original-lock/private-word map and a
physical-owner token. The helper acquires original L through the existing native
raw-spin path with no hook reentry or new preemption increment. Release checks
task, CPU and acquisition generation, then releases L without opening the private
word or consuming the caller's pin. No guest kernel source, owner handoff or
wrapper ABI changes are involved. The component does not yet replace legacy
spin scheduling, hooks, nested adapters or native continuation.

Retained historical evidence: `/tmp/kdlock-spin-gate.ZkhTgh/`.

## Spin Native Compatibility Audit

Historical source snapshot, not current acceptance.

Historical shared-word implementation. On current L/S sources this script
intentionally exits 1 at its contract check; it is not a passing current-backend
test and must not be forced to pass by removing its assumptions.

`tests/audit_spin_native.py` and `tests/unit/spin_native_fixture.c` reproduce
specific compatibility defects without risking a live mixed queue. The runner
checks the matching x86-64 kernel tree, extracts real node/pt_regs definitions,
tail masks and encode/decode functions, native wake code, plain kdlock hooks,
native inline spin APIs and explicitly bounded uncontended kdlock prefixes.
Per-CPU storage selection and scheduler/atomic primitives are deterministic
userspace substitutes. It does not execute kernel assembly, acquire a kernel
lock, simulate an entire qspinlock, or validate concurrent memory ordering.

Retained historical evidence: `/tmp/kdlock-spin-interop.tBs8nq/`.

## IRQ/BH Lock Admission

Historical source snapshot, not current acceptance.

The context-symbol policy now includes raw IRQ/BH wrapper families and compiler
clones. `_raw_spin_lock_irqsave`, `_raw_spin_unlock_irqrestore`, spin/read/write
BH variants and double-underscore raw helpers cannot bypass admission simply
because their caller has no GS operand. Calls, tail calls and resolved address-
taking are refused before codegen. This is not new IRQ/BH delegation support,
an instruction/flags repair, or a change to ordinary unknown-CALL completion.
No production kernel-module code or guest-kernel hooks changed in this increment.

The pre-fix loader ignores these symbols. In a fixture with a visible `schedule`
symbol, all six direct-CALL/tail-CALL/address-taking checks incorrectly return
admitted status 0 instead of native-only status 2. `red-refined.log` preserves
that result; the first exploratory test log is retained separately. The updated
30-case context suite checks raw spin/read/write families, compiler clones,
actual loader-to-codegen refusal, and preservation of the post-outer-unlock
boundary. All 18 unit/codegen programs pass without skips.
An actual guest symbol-table comparison with the archived loader increases
the resolved context-address count from 304 to 326, including both tested APIs;
`actual-symbols.json` records the 22 newly classified addresses.

Retained historical evidence: `/tmp/kdlock-context-api.WHliGt/`.

## Natural Combiner Frames

Historical source snapshot, not current acceptance.

`test_14_spin_frame_depth.sh` adds a recovery-only fixture to existing spin
mode 8. Each participating lock has a real independent owner, requester and
trailing node. CPU 0 is the real queue head/combiner at every level; requesters
run on CPUs 1 through N, owners on 20 through 19+N, trailers on 10 through
9+N, and CPU 19 occupies A0's pending bit. For N=8 this is 26 target tasks.
The guest has 40 CPUs, with runtime `none (voluntary) full`; full preemption
is deliberately rejected by the test-only frame tracing. No guest-kernel
code, hooks, wrapper parameters, stack size or resource capacities change.

Before arming, each requester primes and warms its lock through the same
entry, and both complex JIT images must be ready. The daemon stops before the
contended phase. Every deeper acquisition makes CPU 0 combine another actual
waiter while retaining its parent frame. The fixture reads real queue/tail
state and never fabricates frame/node/held-lock counts or error results.
Per-request stack records validate original task identity and exactly one
before/call/after update; separate per-lock state oracles check completion.

Retained historical evidence: `/tmp/kdlock-frame-chain.qdyDWa/`.

## Admission Symbol Visibility

Historical source snapshot, not current acceptance.

This follow-up changes only translator admission and its Python tests; it adds
no guest-kernel or kdlock kernel-module behavior. Required plain lock/unlock
symbols must resolve to distinct nonzero addresses, without hardcoded fallback.
Context-symbol loading rejects an empty table or a zero address on any matching
name. Failures occur before kernel-text reading/codegen and remain retryable
errors (`CONTEXT_SYMBOLS_UNAVAILABLE`, CLI exit 1), not permanent native-only
verdicts. Previously published/in-flight code is not revoked by this check.

The 27 context-policy cases include missing/ambiguous lock addresses, empty and
partially hidden context tables, invalid addresses, and actual CLI error
classification. CLI fixtures prevent kernel-text access and emit no image.
Both production daemon launch layouts still pass their error/refusal tests.
The existing instruction/flags codegen baselines are unchanged. Running the
previous archived loader against empty/hidden-address fixtures reproduces the
empty-table result; the updated loader raises a retryable error for both.
The actual guest resolves 304 distinct context addresses.

Retained historical evidence: `/tmp/kdlock-context-symbols.3FE9WB/`.

## Independent Pending Spin

Historical source snapshot, not current acceptance.

`KD_NATIVE_PENDING_CONTENDED=1 bash tests/test_10_native_resume.sh 8 4`
extends the existing fixture, without a new mode or production lock/recovery
change. The test workload's stage-4 record spans the actual B lock CALL in
the independent-contention path. The daemon stops before the workload;
`jit_fail_pending_lock=1` exercises the supported pre-publication resource
failure after spin has staged its post-CALL RIP/RSP. The native continuation
restores the original callee RIP/CALL RSP rather than replaying A.

The final 26 commands cover module loading, three pending-spin repetitions,
strict modes 0-5/10/11, spin 6/7/8, ordinary PENDING and held-B spin continuation,
remote held-B spin continuation, independent pending mutex with/without rename,
mutex held-lock capacity, JIT shadow capacity, the eight-round kernel shadow
queue fixture, two completion-then-rejection cases and mixed-backend admission.

Retained historical evidence: `/tmp/kdlock-pending-spin.MsdJqx/`.

## Translated Shadow Capacity

Historical source snapshot, not current acceptance.

`KD_NATIVE_SHADOW_CAPACITY=1 bash tests/test_10_native_resume.sh 1 4` builds
the external module with `KDLOCK_SELFTEST=1` and the read-only, one-shot
`spin_selftest_fill_shadow=1` parameter. The normal build excludes these
helpers and parameters. No guest kernel change, new exported hook, wrapper
argument, flags repair or JIT publication mechanism is added.

The final 27-command batch includes module loading, three JIT-pressure cases,
three eight-round kernel queue fixtures, strict modes 0-5/10/11, spin 6/7/8,
ordinary PENDING and held-B spin continuation, three remote nested spin
continuations, mutex held-lock capacity, two completion-then-rejection cases,
and mixed-backend native-only admission. All pass.

Retained historical evidence: `/tmp/kdlock-spin-shadow-jit.URpltM/`.

## Live Spin Shadow Capacity

Historical source snapshot, not current acceptance.

This increment adds `tests/kernel/spin_shadow_selftest.c`, included only with
`KDLOCK_SELFTEST=1`, and `test_13_spin_shadow_capacity.sh`. The selftest runs
after spin per-CPU initialization but before hook installation. No guest
kernel patch, new hook/export, default lock policy change or wrapper ABI
change is needed. The script unloads the test module and rebuilds the default
module before returning; final symbol/parameter checks confirm the test code
is absent from that default artifact.

The queue head physically holds eight private native spinlocks and uses the
production shadow-push API for each. It first invokes the actual JIT known-
lock handler with a valid frame containing only one logical lock. The handler
returns PENDING `-E2BIG`; registers and CALL return words are unchanged, and
the probe lock remains unowned. This separates CPU-local capacity from frame
capacity without changing a count or allocation result.

Retained historical evidence: `/tmp/kdlock-spin-shadow-live.PY19BU/`.

## Spin Shadow Capacity

Historical source snapshot, not current acceptance.

This increment changes only kdlock spin handling, its internal capacity query,
tests and documentation. No guest kernel changes, wrapper argument changes,
flags repairs or JIT-version publication changes were made.

The old full local `lock_addr[8]` path had already released its node and
changed saved RSP/combiner context before jumping to the common release exit.
It released the node twice, returned with combiner lock state, and failed to
notify the successor. The fix checks capacity before those saved-state changes,
retains ordinary physical ownership, release-notifies the successor, and uses
the single release exit. The JIT nested-lock service separately checks local
capacity before staging the CALL or acquiring/publishing B, preserving PENDING
on failure even when the logical frame's lock table is not full.

Retained historical evidence: `/tmp/kdlock-spin-shadow.86Z7YN/`.

## Held-Lock Capacity

Historical source snapshot, not current acceptance.

This increment changes the test workload, `test_10_native_resume.sh`, the
translator's production-code tests and documentation. Production lock/recovery
code, guest kernel and two-word wrapper ABI are unchanged.

Mode 4 stage 5 warms only A, then arms an ordinary eight-child-mutex callee.
The first workload produces a real CALL miss at `kd_resume_depth_mutex` and
finishes natively. All first-wave callers exit before the same daemon resumes
and publishes the expanded image; the daemon then stops before the second
wave. No callee table is manually seeded, and `jit_fail_pending_lock` stays 0.
This controlled publication schedule does not fix general JIT version races.

Retained historical evidence: `/tmp/kdlock-depth-capacity.zrtPOB/`.

## Independent B Ownership

Historical source snapshot, not current acceptance.

Only the test module, its Kbuild include path, the continuation test script and
documentation changed in this increment. The production ownership protocol,
guest kernel and two-word wrapper ABI did not change. The test module uses the
matching kernel source's private `struct mutex_waiter` under B's `wait_lock`;
this non-RT oracle requires the full matching source tree, not just public
headers. It reads the queue without editing it. Observation timeout fails the
oracle and releases B; the outer workload timeout remains necessary.

`KD_NATIVE_PENDING_CONTENDED=1 bash tests/test_10_native_resume.sh 4 4` uses
seven pinned roles. A has a delegation queue; B's holder/direct/trailing workers
use non-target comm `kd_native`. After the injected pre-acquisition resource
failure, the B holder finds the original request's task in its real wait queue.
At that point the prefix record is written but the post-B probe has not run,
and A owner, B owner and original waiter are three distinct tasks. After B
release, the native probe verifies that B belongs to the waiter and A retains
the same owner. The script checks the ordered pending/begin/blocked/acquired/
complete events and exactly one retained-A unlock notification.

Retained historical evidence: `/tmp/kdlock-pending-contention.JlIfcE/`.

## Pending Control Calls

Historical source snapshot, not current acceptance.

`kd_call_state` records NONE/PENDING/ENTERED/ACQUIRED/COMPLETE and the original
callee RIP, CALL RSP and return address. Only a valid, still-locked frame with
PENDING `-ENOMEM`/`-E2BIG` can resume the original lock CALL. Spin's pre-queue
post-CALL staging is undone without restoring entry GPRs or memory; mutex has
not consumed its CALL at this point. Queued/acquired/completed/error states
remain excluded. The two-word wrapper ABI and guest kernel are unchanged.

The shared production policy is tested directly by `test_control_call.c`:
40 phase/error combinations verify both accepted resource errors, rejected
deadlock/invalid/unsupported errors, exact RIP/RSP restoration and an unchanged
return word. Invalid captures clear the phase. The other tests also passed:
15 programs total, including 20 context-policy and nine diagnostics cases,
without skips. W=1 module builds and strict daemon builds passed; existing
objtool and locale warnings remain.

Retained historical evidence: `/tmp/kdlock-control-call.QRYFZY/`.

## Backend Admission

Historical source snapshot, not current acceptance.

The entry now carries its registered spin/mutex kind in the former padding at
offset 12 of `kd_exe_info`; size 64 and all pre-existing offsets are unchanged.
Daemon launcher tests cover unknown/spin/mutex arguments in both layouts, and
live device tests verify kind values and terminal refusal. The wrapper retains
two words. W=1 module builds and strict daemon builds passed; existing objtool
and locale warnings remain. The guest kernel was not modified or rebuilt.

The production translator regression first failed with `0 != 2`: a known
mixed-backend fixture was admitted. After the change, the context-policy suite
passes **20 cases**, covering both directions, direct/tail/address-taking
references, missing outer unlock, matching kinds, missing kind, late callees
and post-unlock exclusion. The nine diagnostic cases and two admitted-code
assembly hash baselines still pass. All 14 unit/codegen programs passed without
skips. Dangerous spin-to-mutex fixtures are translated for rejection checks,
not executed as kernel workloads.

Retained historical evidence: `/tmp/kdlock-backend-admission.RQ0Yyd/`.

## Daemon Launch Classification

Historical source snapshot, not current acceptance.

A new test of the actual production `compile_entry()` first reproduced a
misclassification: shell `cd` failure exits 2, as does direct Python invocation
of a missing script. Neither is a policy refusal. The daemon now launches a
child directly, reports workspace/exec failures separately, and uses a fixed
`runpy` bootstrap so missing script files raise an ordinary exception. Both
workspace layouts test missing workspace, missing script and translator exits
0/1/2, including preservation of translator arguments. The result cache and
header-only wire checks remain in the same production-daemon test.

All 14 unit/codegen programs passed without skips, including 14 context-policy
cases and nine diagnostic cases. The strict daemon build passed. Modules and
the guest kernel were unchanged from the preceding admission run; the module-
load integration test passed again. This follow-up did not rebuild the modules.

Retained historical evidence: `/tmp/kdlock-launch-policy.acBUpR/`.

## Context Admission

Historical source snapshot, not current acceptance.

The new preflight refuses all GS memory/current accesses, including implicit
string/XLAT source operands, CLI/STI and statically resolved context-sensitive
symbols. Refusal publishes terminal `KD_EXE_NATIVE_ONLY=-3` without entering
an error stub. The two-word wrapper ABI and guest kernel remain unchanged.

Initial testing exposed a false rejection of mode 0's post-unlock GS stack-canary
epilogue. The caller CFG is now bounded at its outer unlock using lexical lock
depth, retaining nested bodies and branches. Learned callees/targets are scanned
in full at unknown depth. This is conservative scope analysis, not full lock
identity/alias analysis. The rejected early attempt is retained separately;
no unsupported instruction was executed to test rejection.

Retained historical evidence: `/tmp/kdlock-context-policy.v7pZtt/`.

## Diagnostic Logging

Historical source snapshot, not current acceptance.

This run validates logging changes after `044dba1`, not instruction/flags
semantic repairs. The fixed manifest contains 70 source/build/test files;
host/guest hashes matched before and after testing. The existing recovery
snapshot was confirmed, and guest kernel/config hashes remained unchanged.

| Mode | JIT completions | Exact operations / states | Evidence |
| --- | ---: | ---: | --- |
| 0 | 4 | 12009 / 1 | Required spin artifact executed |
| 3 | 607 | 12934 / 1 | 607 matching waiter resumes |
| 4 | 1 | 12008 / 2 | `nested_queued=1`, `nested_jit=1`, one waiter resume |
| 5 | 410 | 12582 / 1 | 410 matching hostcall exits/executions/resumes and waiter resumes |

Retained historical evidence: `/tmp/kdlock-jit-diagnostics.eiETOc/`.

## Prior Commit Verification

Historical source snapshot, not current acceptance.

These are fresh results from the 13-case run, not artifact-generation counts:

| Mode | JIT completions / waiter resumes | Exact operations / states | Additional runtime evidence |
| --- | ---: | ---: | --- |
| 3 | 569 / 569 | 12934 / 1 | Repeated contention and pinned waiters |
| 4 | 1 / 1 | 12008 / 2 | `nested_queued=1`, `nested_jit=1`, B unlock completed |
| 5 | 399 / 399 | 12582 / 1 | 399 matching hostcall exits/executions/resumes |
| 11 | 1 / 1 | 12008 / 2 | Native B contention; 12002 GS/current successes, zero mismatches |

Retained historical evidence: `/tmp/kdlock-mutex-jit-commit.VzVf2T/`.

## Environment And Builds

Historical source snapshot, not current acceptance.

All builds and execution ran in the recovery guest: patched Linux `6.1.159`,
40 CPUs, 28 GiB RAM, GCC 11.4.0 and miasm 0.1.5. The guest path
`/root/host_fs/kdlock` is on ext4, not a live host share. Only changed individual
files were synchronized after hash comparison; no repository was moved.

**No guest kernel source, config, hook, or export was added or changed.** The
module reuses `is_kd`, mutex hooks, and the existing exported native slowpaths.
The test-only nested-waiter diagnostic is exported by kdlock, not by the kernel.
These kernel hashes matched before and after validation:

## Native Mutex And Fallback

Historical source snapshot, not current acceptance.

`test_05_mutex.sh` passed mode 3 twice (40001 combined operations), mode 4
(20001) and mode 5 (20001). Each uses `mutex_jit=0`, including after promotion:
no delegation slowpath or JIT completion, exact replay, no task/slot leak.
It is not evidence that JIT executed, nor a run of the entire default suite.

`test_11_mutex_native_protocol.sh` passed with both `0` and `1`. Each performed
18810 operations on one protected state: mixed callers before promotion,
non-target callers active during the promotion phase, mixed callers afterward,
and eight CPU-1 target waiters behind a CPU-0 holder. Odd mixed workers use
native plain lock, trylock, interruptible and killable APIs; even workers remain
eligible for delegation. Signal cancellation was not injected.

## Native Continuation Results

Historical source snapshot, not current acceptance.

Stage 1 misses inside a single lock, stage 2 after B unlock, and stage 3 while B
is still held. All rows load `mutex_jit=1`; spin rows retain their spin backend.
Every row has zero request-record, replay and invariant failures.

| Mode / stage | Variant | Valid request records | Native frames started/completed | Operations / states |
| --- | --- | ---: | ---: | ---: |
| 0 / 1 | Single spin | 12009 | 1 / 1 | 12009 / 1 |
| 3 / 1 | Single mutex | 12009 | 1 / 1 | 12009 / 1 |
| 1 / 2 | Spin A after B | 12009 | 1 / 1 | 12009 / 1 |
| 4 / 2 | Mutex A after B | 12002 | 1 / 1 | 12008 / 2 |
| 8 / 2 | Independent spin A/B, after B | 12003 | 1 / 1 | 12013 / 2 |
| 1 / 3 | Spin B held | 12009 | 1 / 1 | 12009 / 1 |
| 4 / 3 | Native mutex B held by A combiner | 12002 | 1 / 1 | 12008 / 2 |
| 8 / 3 | Remote spin B held | 12003 | 2 / 2 | 12013 / 2 |
| 3 / 1 | Rename during native suffix | 12009 | 1 / 1 | 12009 / 1 |
| 4 / 2 | Rename after B unlock | 12002 | 1 / 1 | 12008 / 2 |
| 4 / 3 | Rename while B held | 12002 | 1 / 1 | 12008 / 2 |
| 3 / 1 | CPU-0 holder / four CPU-1 waiters | 12006 | 1 / 1 | 12006 / 1 |
| 3 / 1 | Mixed native/delegated participants | 12009 | 1 / 1 | 12009 / 1 |

## Strict JIT Results

Historical source snapshot, not current acceptance.

| Mode | Artifact bytes | Exact operations / states | Additional evidence |
| --- | --- | --- | --- |
| 0 | 2121 | 12009 / 1 | Translated spin completion |
| 1 | 2489 + 2489 | 12009 / 1 | A stream crosses B known calls |
| 2 | 1923 | 12009 / 1 | 4 hostcall exits/executions/resumes |
| 3 | 3400 | 12934 / 1 | 600 JIT completions and resumes |
| 4 | 2153 | 12008 / 2 | `nested_queued=1`, `nested_jit=1`, one JIT completion |
| 5 | 1924 | 12582 / 1 | 418 hostcall cycles, JIT completions and resumes |
| 10 | 1053 + 1053 + 3333 + 3239 + 2489 + 2489 | 12014 / 2 | Translated waiter GS/current |
| 11 | 2065 | 12008 / 2 | Native B contention, JIT resume, GS/current |

All replay failures are zero. Modes 3/4/5/11 have zero JIT/readiness/frame/context
failures and drained resources. Mutex scheduler acquisition/release counts
were 2333/2333, 2006/2006, 2163/2163 and 2006/2006 respectively. Mode 11 recorded
12002 GS/current attempts and successes with no mismatch. Generated entries
are not all required to execute in spin modes 1/10; their scripts identify the
required executed artifact. Mutex modes 4/11 now require A's single artifact.

## Reproduction And Evidence

Historical source snapshot, not current acceptance.

This broader command list and the 28-case evidence below belong to the earlier
native-owner sources. With the current sources, selectors 10/11 exercise
native-only refusal, not the historical translated-GS contract. The current
admission run and its separate evidence directory are described above.

All runtime commands below run in the guest, with bounded outer timeouts as
recorded in each retained `command` file:

Retained historical evidence: `/tmp/kdlock-mutex-owner-20260905/`, `/tmp/kdlock-native-final-20260905/`, `/tmp/kdlock-jit-audit-20260905-1010/`.

## Remaining Limits

Historical source snapshot, not current acceptance.

The mutex in-CS guard and native per-request records strengthen the oracle but
do not prove arbitrary kernel linearizability. Uncovered signal histories, alternate
kernel configs, WW/PI/RT locks, lock-address reuse, owner-sensitive native
suffixes and production subsystems require separate evaluation. Native spin
interoperability is not established by mutex mixed-user tests.
Remote ancestor release and zero-local native relay now have bounded real A/B
and A/B/C integration evidence, including both ancestor release orders in C.
These histories do not establish more executors, cross-NUMA placement of this
chain, arbitrary dependency graphs or full-S reclaim fairness.
The eight-frame remaining-stack sample is not a whole-run high-water
or IRQ/NMI safety proof.

Flags remain deferred by user scope. Ordinary CALL and PENDING resource-error
continuation do not solve IJ, budget, faults or later-phase control failures;
unsupported post-entry errors still fail-stop. Known mixed spin/mutex references
are now rejected by preflight, but undiscovered targets can still reach the
runtime backend guard. This is not a complete eligibility proof. Live hook/module
unload, per-CPU concurrency and general task/CPU context equivalence remain
open. Conservative native-only admission excludes recognized GS/context
operations but does not cover unknown callees or arbitrary pointers, and cannot
revoke already-started code. The two-word GS/task ABI is unchanged; no transactional rollback or
performance speedup is claimed.


### In-Flight Hotlock Window

Historical sampling fix: capture the threshold at INIT-to-CHECKING so another
lock's promotion cannot reclassify an in-flight sample. The production fixture
replaced a duplicate C model and checked 131108 assertions. This does not make
natural promotion deterministic for newly sampled locks or prove a speedup.
Full original record is in the pre-cleanup snapshot under Pending After Outer
Unlock; the current algorithm is described in DESIGN.
