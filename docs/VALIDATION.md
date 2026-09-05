# JIT And Native-Owner Mutex Validation

Last validated: 2026-09-05

The latest commit verification ran from 13:36:53 to 13:39:21 Asia/Shanghai.
All **13 mutex integration cases passed with `mutex_jit=1`**: four strict JIT
selectors, one mixed native/delegated protocol case, and eight native-continuation
variants. Guest builds, 11 unit/codegen tests without skips, and module loading
also passed again. Detailed results are in [Commit Verification](#commit-verification).

The preceding full native-owner regression ran from 13:26:27 to 13:31:49.
All **28 integration cases passed**: native mutex
baseline, two mixed-protocol variants, 13 native-continuation variants, eight
strict JIT selectors, and four additional spin selectors. The same sources also
passed 11 unit/codegen tests without skips, guest builds, and a module-load test.
Both runs use the same manifest of 68 source/build/test files implementing the
changes after base `c08368d`. Only documentation changed after this source
manifest was fixed. The broader result tables below retain the earlier run's
counts; spin selectors and `mutex_jit=0` were not rerun during commit verification.

Architecture belongs in `DESIGN.md`, register rules in `JIT_REGISTER_ABI.md`,
operations in `AGENTS.md`, and remaining work in `TODO.md`. Passing this bounded
suite is not a general kernel-correctness or performance guarantee.

## Commit Verification

These are fresh results from the 13-case run, not artifact-generation counts:

| Mode | JIT completions / waiter resumes | Exact operations / states | Additional runtime evidence |
| --- | ---: | ---: | --- |
| 3 | 569 / 569 | 12934 / 1 | Repeated contention and pinned waiters |
| 4 | 1 / 1 | 12008 / 2 | `nested_queued=1`, `nested_jit=1`, B unlock completed |
| 5 | 399 / 399 | 12582 / 1 | 399 matching hostcall exits/executions/resumes |
| 11 | 1 / 1 | 12008 / 2 | Native B contention; 12002 GS/current successes, zero mismatches |

Each strict selector checked `mutex_jit=1`, generated and inspected its artifact,
matched runtime entry diagnostics, and required translated completion plus exact
protected-state replay. JIT/readiness/frame/context failures were zero. Native
scheduler acquisitions/releases matched at 2364/2364, 2006/2006, 2182/2182 and
2006/2006 respectively; all tasks, waiters and slots drained.

The mixed-protocol case performed 18810 operations, completed/resumed 18 JIT
delegations and balanced 4390 native scheduler ownership intervals. Its in-CS
guard reported zero overlap. The deliberate task-allocation failure occurred
once, and four waiter-slot overflow fallbacks were exercised without leaking
resources or breaking replay.

Eight native-continuation cases passed: mode 3 stage 1 and mode 4 stages 2/3,
their three renamed-task variants, CPU-pinned mode 3 and mixed-participant mode 3.
Each completed one native frame with exact per-request records and no replay
failure. Mode 4 stage 3 required two acknowledged unlocks on the retained owner;
the renamed variants recorded 8, 1 and 2 task reroutes. These cases execute a JIT
prefix followed by a native suffix, not a fully translated completion.

Evidence is retained on the host at `/tmp/kdlock-mutex-jit-commit.VzVf2T/`:

- `source.sha256`, `source-kernel-check.log`, `post-test-health.log`: the same 68
  inputs before/after testing and unchanged guest kernel/config hashes.
- `build-unit.log`: repeated guest builds, 11 actual unit/codegen passes and
  module loading. Existing objtool and locale warnings remain as noted below.
- `run.sh`, `cases/started-at`, `cases/completed-at`: serial commands and timing.
- `cases/<case>/`: command, output, zero exit status, dmesg, artifact hashes and
  archive; native/mixed cases also retain detailed guest evidence archives.

All 13 dmesg logs were free of BUG, panic, double fault, soft lockup,
unable-to-handle and WARNING signatures. The guest stayed reachable without a
restart; no benchmark, daemon or test module remained active afterward.

## Acceptance Contract

Generating `jit.S` or installing `jit.bin` is insufficient. Strict selectors
require nonempty assembly/binary/disassembly artifacts, nonzero structured
kernel-text reads, checked daemon writes, and execution diagnostics matching
an inspected entry. The final chunk log precedes payload copy and cannot alone
prove successful publication. Runtime entry logs also precede the JIT call;
they must be followed by translated completion and the exact protected result.

The executable artifact must retain branch, rotate, multiply, scaled-index
access and dependent writes. Native replay checks all nine protected state
words, the exact operation count, and the expected number of active states.
Frames, waiters and slots must drain; kernel and protocol failures must be zero.
Modes 2/5 additionally require the named `ktime_get` stub, no service-callee
translation/runtime recompilation, and equal nonzero exit/execute/resume counts.
Mode 5 matches those to JIT completion and waiter resume. Modes 10/11 execute
GS/current artifacts using `Stack_RGS` and `Stack_RCT`, without live hardware
segment operands, and require zero probe mismatches.

All mutex JIT cases verify `mutex_jit=1`. Ownership/resource accounting requires
`origin_acquires == origin_releases`, `active_tasks=0`, and no leaked waiter
slots. These origin counters count scheduler-owner intervals, not every direct
native API acquisition or nested B. Mode 3's in-CS guard requires
`inside=0 overlaps=0`; that guard does not instrument all nested A/B states.
Task allocation failures are zero except the deliberate one-shot test.

Modes 4/11 require one executed A artifact, `nested_queued>0` and `nested_jit>0`:
A's combiner really contends on native B, obtains it, and resumes JIT through B
unlock. B no longer has a remote mutex waiter or a separate required artifact.

Native-continuation cases stop the daemon before execution and require an
ordinary generated CALL miss at the actual `kd_resume_native_probe` RIP. The
original task completes distinct per-request before/call/after records exactly
once; `kd_native started == completed > 0`, with no entry retry or lost state.
A JIT prefix plus native suffix is not counted as an all-JIT completion.

## Environment And Builds

All builds and execution ran in the recovery guest: patched Linux `6.1.159`,
40 CPUs, 28 GiB RAM, GCC 11.4.0 and miasm 0.1.5. The guest path
`/root/host_fs/kdlock` is on ext4, not a live host share. Only changed individual
files were synchronized after hash comparison; no repository was moved.

**No guest kernel source, config, hook, or export was added or changed.** The
module reuses `is_kd`, mutex hooks, and the existing exported native slowpaths.
The test-only nested-waiter diagnostic is exported by kdlock, not by the kernel.
These kernel hashes matched before and after validation:

```text
3f759de23929a1d32a353aa6b0962fbe31b43cbfc704eca93d998f1ce57cb167  kernel/locking/mutex.c
8a8cce1b35a362abf0fcbdefcacfe0296dd7aa0a7540bbbf29634b3e492bb038  include/linux/mutex.h
caa447885e0429aaaed10b76cc47816aa53c20869e6598b15fce8e6e37eed792  .config
```

Before the final run, QEMU disappeared during an execution-environment change;
its cause was not established. The previous serial log was preserved and
`run_vm.sh recovery` restarted the VM. All 68 source hashes matched afterward,
and the existing `pre_native_resume_20260905_1110` recovery snapshot was confirmed.
The final 28-case run completed without a VM restart.

Guest checks:

```bash
make -C tests/unit clean
make -C tests/unit -j8 run
python3 -m compileall -q disassem tests/unit
make -C kernel_module W=1 -j8
make -C klock_module W=1 -j8
make -C daemon CFLAGS='-O2 -Wall -Wextra -Werror'
gcc -O2 -Wall -Wextra -Werror -Iinclude bench/klock_test.c -o bench/klock_test -lpthread
timeout --kill-after=10s 60 bash tests/test_01_module_load.sh
```

Nine C models and two real-translator Python tests passed with no `SKIP`.
Bash syntax checks, Ruff lint/format (13 Python files), ShellCheck, Markdown
local-link/fence checks and `git diff --check` passed. Existing objtool warnings
about naked returns, stack switching, dynamic calls and UACCESS remain;
no C compiler diagnostic was reported by the final W=1 build. Locale warnings
are separate. These are not warning-free or unwind-validated builds.

## Native Mutex And Fallback

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

| Result | `mutex_jit=0` | `mutex_jit=1` |
| --- | ---: | ---: |
| Protected operations / replay failures | 18810 / 0 | 18810 / 0 |
| In-CS overlaps / final inside | 0 / 0 | 0 / 0 |
| JIT completions / resumes | 0 / 0 | 20 / 20 |
| Scheduler native acquisitions / releases | 0 / 0 | 4388 / 4388 |
| Injected task allocation failures | 0 | 1 |
| Waiter slot overflow fallbacks | 0 | 4 |
| Remaining tasks / waiters / slots | 0 / 0 / 0 | 0 / 0 / 0 |

Promotion is exercised concurrently, but its exact scheduling interleavings
are not exhaustively controlled. Table/code-pool exhaustion and signal-aborted
waits remain untested by this case.

## Native Continuation Results

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

Counts include warmup and promotion; they are not counts of JIT misses. The
renamed mutex variants recorded `task_reroutes=8`, `1`, and `2`, respectively.
Mode 4 stage 3 used one frame and two unlock requests on the same actual owner;
mode 8 stage 3 retained two distinct spin frames. No owner handoff was added.

A first rename test enabled comm changes during warmup: repeated `task_lock`
traffic promoted an unrelated lock first and the target mutex did not enter
JIT. The test correctly failed its execution check. It now arms the test-only
writable `native_resume_rename` parameter only after promotion/translation;
all final rename cases passed without weakening JIT checks. The test helper
changes comm under `task_lock`; it is not a replacement for the full tracing
semantics of the kernel's unexported `__set_task_comm` API.

## Strict JIT Results

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

Additional normal spin selectors 6/7/8/9 passed: respectively 12009/1,
12009/1, 12014/2 and 12006/2 operations/states, all with zero replay failures.
Mode 9 did not enable obsolete synthetic abort injection.

## Reproduction And Evidence

All runtime commands below run in the guest, with bounded outer timeouts as
recorded in each retained `command` file:

```bash
export KDLOCK_RECOVERY_CONFIRMED=1
bash tests/test_05_mutex.sh
bash tests/test_11_mutex_native_protocol.sh 0
bash tests/test_11_mutex_native_protocol.sh 1
for spec in '0 1' '3 1' '1 2' '4 2' '8 2' '1 3' '4 3' '8 3'; do
  read -r mode stage <<< "$spec"
  timeout --kill-after=10s 180 bash tests/test_10_native_resume.sh "$mode" "$stage" || exit
done
for spec in '3 1' '4 2' '4 3'; do
  read -r mode stage <<< "$spec"
  KD_NATIVE_RENAME=1 timeout --kill-after=10s 180 bash tests/test_10_native_resume.sh "$mode" "$stage" || exit
done
KD_NATIVE_PINNED=1 bash tests/test_10_native_resume.sh 3 1
KD_NATIVE_MIXED=1 bash tests/test_10_native_resume.sh 3 1
for mode in 0 1 2 3 4 5 10 11; do
  timeout --kill-after=10s 300 bash tests/test_09_jit_execution_modes.sh "$mode" || exit
done
for mode in 6 7 8 9; do
  timeout --kill-after=10s 180 bash tests/test_04_spinlock.sh "$mode" || exit
done
```

Host evidence: `/tmp/kdlock-mutex-owner-20260905/`:

- `source.sha256`, `source-check.log`, `post-test-health.log`: 68 matching inputs,
  unchanged kernel hashes, healthy SSH and no residual worker/daemon/modules.
- `final-build-unit.log`: W=1 builds, 11 actual unit/codegen passes, module load.
- `run-final.sh`, `final/started-at`, `final/completed-at`: serial runner and timing.
- `final/<case>/`: command, output, exit status and dmesg for all 28 cases;
  JIT cases also retain artifact hashes and an archive. Native/mixed cases add
  an archive of their own detailed guest evidence directory.
- Earlier standalone logs, `previous-VALIDATION.md` and
  `serial-before-restart.log` distinguish implementation attempts from this run.

All final case statuses were zero; dmesg scans found no BUG, panic, double fault,
soft lockup, unable-to-handle or WARNING signature. QEMU remained available;
no benchmark, translation daemon or test module remained loaded. The evidence
is for this source manifest, not for subsequent source changes.

Historical `/tmp/kdlock-native-final-20260905/` records the earlier 21-case
CALL-continuation revision, not native-owner mutex behavior. Its remote-mutex-B
results must not be applied to this implementation. Earlier
`/tmp/kdlock-jit-audit-20260905-1010/` records a timing-sensitive mode 6 promotion
failure followed by an unchanged successful rerun; that general sampling
policy is still not fixed.

## Remaining Limits

The mutex in-CS guard and native per-request records strengthen the oracle but
do not prove arbitrary kernel linearizability. Signal cancellation, alternate
kernel configs, WW/PI/RT locks, lock-address reuse, owner-sensitive native
suffixes and production subsystems require separate evaluation. Native spin
interoperability is not established by mutex mixed-user tests.

Flags remain deferred by user scope. Ordinary CALL continuation is not a
solution for IJ, budget, fault or failed control calls; unsupported post-entry
errors still fail-stop. Known mixed spin/mutex calls reject before their native
service, not through a complete pre-execution eligibility pass. Live hook/module
unload, per-CPU concurrency and general task/CPU context equivalence remain
open. The two-word GS/task ABI is unchanged; no transactional rollback or
performance speedup is claimed.

Concurrent JIT replacement is an explicitly deferred limitation. The suite did
not exercise independent lock instances sharing the same RIP during in-place
recompilation; fixed-lock serialization is not evidence for that scenario.
No concurrent-overwrite failure or failure rate was established. Treating it
as low probability is a project scope decision, not a statistical test result.
Immutable versions, complete-image publication checks and old-version
reclamation remain future work in
[TODO C3](TODO.md#c3-immutable-jit-publication-and-lifetime). This documentation
update adds no runtime validation and does not change the results above or
the independent source-text lifetime and live-unload limitations.
