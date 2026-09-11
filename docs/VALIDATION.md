# kdlock Validation

Each result below belongs to its dated, frozen inputs. Documentation edits or
a later Git commit do not re-certify those inputs as a new run. The project is
not accepted as complete; actual-JIT positives, refusals, native controls and
kernel protocol probes are different categories.

| Date (+08) | Evidence | Result and scope |
| --- | --- | --- |
| 2026-09-11 | [Reading handoff](#reading-handoff) | Builds and six focused unit programs; comment-only source changes, no kernel-JIT rerun |
| 2026-09-10 | [Static per-CPU ranges](#static-per-cpu-ranges) | Latest scoped live: 24/24, with 12 JIT positives and 12 native-only refusals; mutex positives use `mutex_jit=1` |
| 2026-09-10 | [Dynamic-pointer and resume-boundary audits](#dynamic-pointer-screening-gap) | Guest-userspace counterexamples and packet review, not a passing access-time guard or kernel-JIT gate |
| 2026-09-09 | [Parallel native frames](#parallel-native-frames) | Latest complete matrix: 67/67, with 51 JIT positives, 12 refusals, two native controls and two kernel probes |

The scoped per-CPU run covers static core and boot-reserved module ranges, not
dynamic pointers or arbitrary context-object lifetimes. The
[offline verifier](#offline-evidence-verifier), [selection review](#covered-diagnostic-selection)
and earlier increments retain separate evidence; their passes are not combined
into the latest live run. Current commands and acceptance interpretation are
in [JIT_EXECUTION](JIT_EXECUTION.md); the
[recorded matrix manifest](#recorded-matrix-manifest) preserves historical commands.

Complete-matrix source identity: **183 runtime/test inputs** in
`/tmp/kdlock-parallel-frames.ThpcFS/source.sha256`.
Full source/log/artifact/command archive:
`/tmp/kdlock-parallel-frames.ThpcFS.tar.gz`, SHA256:

```text
06b75aea377f3e1fe27a5b19dbe14d9dd618eab4e2eb9a390a9cf9fea5acfea9
```

The archive includes frozen source, generated artifacts, per-case commands,
status/dmesg/drain records, units, builds, kernel identities and guest-userspace
generated-predicate checks. /tmp paths are external local evidence, not
files delivered by a fresh Git checkout. The command manifest below keeps
invocations auditable. That historical freeze used an external helper for the
two pure-native controls; the current in-repository replacement is verified below,
not retroactively substituted in its command manifest. Automatic scoped packaging
is implemented; system/build reproducibility gaps remain TODO P1.
Losing an archive never makes recorded results new.

The 2026-09-11 documentation consolidation reorganizes navigation and repeated
progress summaries only. It leaves all 211 runtime/test input hashes identical
to the annotated reading-handoff freeze, with no new build, unit or live run.
Historical evidence and the manual's source-file index remain intact.

## Reading Handoff

**2026-09-11:** the code map and manual commands are maintained in
[PROJECT_GUIDE](PROJECT_GUIDE.md). All **208 code files** have file-purpose
comments or docstrings; **65 files** receive purpose, ownership or exit-boundary
comment changes in this increment. The captured kernel patch/config/manifest
remain byte-for-byte evidence rather than annotation targets.

The before/after source inventory contains the same **211 runtime/test inputs**.
Python AST comparison, C/header/assembly token comparison and shell/Makefile
non-comment line comparison find no executable-statement changes. This is a
comment-only check, not a proof of concurrency correctness or a full bug review.
The previous live source hash is not silently replaced by the annotated source.
No modules are loaded and no kernel-JIT matrix is rerun for this handoff.

At **13:06:57-13:07:26 +08**, guest baseline verification and default provider,
workload, daemon and benchmark builds pass. Six focused programs pass: **80
Python methods**, **146 production entry checks** and **3258 production
native-after-outer checks**. The selected wrapper test executes generated code
in guest userspace only; this is not kernel-JIT acceptance. Reproduce with:

```sh
make -C tests/unit run TESTS= PY_TESTS='test_regression.py test_jit_diagnostics.py test_jit_entry_scope.py test_native_after_outer.py test_kernel_baseline.py test_jit_body_witness.py'
```

`git diff --check`, targeted Ruff and ShellCheck checks pass. All ten maintained
documents have valid local links, the manual indexes all 211 inputs, and its
17 Bash blocks pass syntax checking without execution. A formatting comparison
of the eleven annotated provider C files finds unchanged suggestions in
`kd_mutex.c` (21) and `kd_mutex_tasks.c` (4), and none in the other nine. These
pre-existing layouts are retained; this is not a whole-tree formatting pass.
The successful `W=1` builds still report naked-return/frame objtool warnings,
two redundant-CLD warnings and the guest's locale fallback. They are not hidden
or counted as repaired assembly semantics.

All changed inputs are synced individually by SHA256. Both preflight and
postflight report an idle guest and the same 211-input hash:

```text
f2f6ea91d89bd87ec4ac2be0ee69a18fda66bda70afb08375947ec9c13eecc9d
```

The running baseline remains Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`,
40 CPUs, two NUMA nodes, `nokaslr`, voluntary preemption and recovery ext4.
That reading-handoff run performs no VM restart, guest-kernel build/install or
Git commit. A later documentation cleanup/commit does not add runtime evidence.

Before/after source, comment diff, commands, build/unit logs and static-check
records: `/tmp/kdlock-reading.EtCs7p.tar.gz`, SHA256:

```text
74f78964fd64480643a600ed14ee61fc002868eea866c7e248263ab3849419e9
```

## Static Per-CPU Ranges

**2026-09-10 16:10:27-16:18:47 +08**: **24/24 scoped live cases pass** on
**211 frozen runtime/test inputs**. Ten inputs change from the preceding
selection freeze: the provider's CAPS header/handler, Python session/admission
and their existing unit fixtures. No new daily case, guest-kernel change,
wrapper/owner change or general flags repair is introduced.

| Cases | Returned Bodies / Native Frames / Owner ACKs |
| --- | --- |
| `mode-2`, `mode-7`, `mode-8` | 4/0/0, 2/0/0, 2/0/0 |
| `mode-4`, `mode-5` | 1/0/0, 406/0/0 |
| `parallel-drain-0`, `parallel-drain-1`, `parallel-node-pressure` | 2/2/4, 2/2/4, 1/1/2 |
| `registers-8-3`, `registers-4-3` | 2/2/2, 1/1/2 |
| `native-mutex-depth` | 5/5/26 |
| `native-mutex-stack-change` | 1/1/2 |
| Twelve independent `admission` refusals | Zero bodies, native frames and ACKs |

Totals: **429 bodies / 14 native frames / 42 owner ACKs**. Mutex drivers load
and read back `mutex_jit=1`. Mode 5's **406** JIT completions match its hostcall
exits, executions and resumes with zero failures; this observed scheduling count
is not required to equal an earlier run. The depth gate's three images remain
**12825/13141/13540 bytes**, byte-identical to the prior core-range run, with
the external RET, native capacity suffix, retained owners and retirement checked.
These observations are not complete instruction coverage or immutable versions.

Every positive's retained translator logs show the actual same-lease capability
`mutex_stack_bytes=256 percpu_module_bytes=8192` and **40 possible CPUs**, each
with **221184 core + 8192 module = 229376 bytes** of static range coverage.
Eight numeric module/intersecting-end fixtures for actual CPU 0/39 addresses
are admitted before the change and refused afterward with status 2/no assembly.
Four unit-tail controls remain admitted; none of these dangerous loads is
assembled or executed. The external observer initially read the 4-byte
`pcpu_unit_size` as 8 bytes; that invalid tail-control preparation is retained
separately, then corrected before the accepted comparison.

At **16:08:38-16:09:15 +08**, six unit programs pass: **234 Python methods**,
the production source/CAPS fixture and **13 detected mutations**. The independent
**25-case** admission audit and guest module/daemon/benchmark builds also pass.
Coverage includes alignment, overlap/overflow, sparse possible CPUs, unavailable
or malformed capabilities, version 1 compatibility, per-lease cache reset and
mandatory module capability before real text inspection.

All 24 outcomes pass the standard offline verifier and case-specific source,
artifact, body and capability checks. Postflight confirms idle state, unchanged
runtime/test inputs and Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
Four kernel source files used to establish the reserve contract are retained
and match guest hashes. No VM restart or guest kernel build/install occurs.
Evidence: `/tmp/kdlock-module-percpu.8uYyI4.tar.gz`, SHA256:

```text
c113d0675714052ba26b0fe127465d28581e173659c73744f57e06aa0040d489
```

Coverage and API limits are in [DESIGN 7.2.2](DESIGN.md#722-static-per-cpu-ranges);
commands remain in [usage 5.2](JIT_EXECUTION.md#52-运行时续点). Dynamic allocations,
module-object lifetimes, unresolved pointers, concurrent mutation and broader C5
remain open. Covered basics and the full matrix are not repeated or re-certified.

Historical core-only increment, **2026-09-10 15:04:15-15:10:40 +08**: **20/20**
live gates, **441/8/30** body/frame/ACK observations, five unit programs with
**231 methods**, and the 25-case audit passed on its own 211-input freeze.
Eight actual `current_task`/core-boundary operands changed from admitted to
refused without execution; the module arena was not yet included. Evidence:
`/tmp/kdlock-static-percpu.Et3AR5.tar.gz`, SHA256
`0f84cec3f099c83f9c94b5df97c9a913be4d89fedec9a761155e2b7884461e54`.

## Dynamic Pointer Screening Gap

**2026-09-10 14:33:01-14:33:05 +08**: a bounded guest-userspace audit confirms
that runtime pointers can bypass known-symbol screening. Spin and mutex here
select translator backends; no kernel lock hook, module or `mutex_jit` load is
involved. The mock `current_task` interval is ordinary allocated user memory,
never real kernel context. Both statically embedded addresses are rejected
with status 2 and no image, establishing that the symbol filter is active.

The real wrapper then executes **10 invocations** of generated code: each
backend tests an entry pointer and a memory-loaded pointer against both safe
and mock-sensitive data, plus one concurrent replacement history. In the last
history, JIT stores a safe pointer and announces it; a separate thread observes
that store, replaces the pointer and acknowledges before JIT reloads it.
All return the expected data with `body=1` and the source RET target. **Six**
read the mock-sensitive value, including **two** concurrent histories. These
are counterexamples to a safety claim, not successful context-refusal gates,
actual kernel corruption, failure probabilities or full instruction coverage.

At **14:36:34-14:36:38 +08**, the logging-only change passes **21 methods** in
the existing diagnostic and wrapper programs. The existing unknown-address
method now checks both backend/pointer forms, one contract warning, and
identical muted/unmuted assembly and verdicts. Refusal emits no success-scope
warning; historical assembly hashes and actual wrapper checks remain intact.
No test script, daily case, basic smoke or kernel live rerun is added.

The before/after source freezes each contain **211 runtime/test inputs**; only
`disassem/disassem.py` and `tests/unit/test_jit_diagnostics.py` change. Admission,
generated instructions, wrapper ABI, owners and guest kernel remain unchanged.
Source hashes match guest before/after checks, and it is idle after both runs.
The baseline and live Build ID match the preceding run; no VM restart/build.

Source, probe, retained assembly/diagnostics, observations, commands and unit
logs: `/tmp/kdlock-pointer-scope.16owgw.tar.gz`, SHA256:

```text
3ec749e00f4c82b5e0fef40de991b391a7d8dd6439493f24ad46611be90898a5
```

The external probe is a bounded gap audit, not an addition to the passing daily
suite. Subsequent protection must turn these histories into negative or checked
native-continuation gates, not preserve the gap as an accepted safety property.
Implementation prerequisites are in [DESIGN 7.2.1](DESIGN.md#721-dynamic-address-gap);
affected-only diagnostic commands remain in [usage 5.2](JIT_EXECUTION.md#52-运行时续点).
C5, general flags semantics and immutable code versions remain open/deferred.

At **2026-09-10 16:50:25 +08**, a one-off guest-userspace audit of the unchanged
production restore stubs completes **128 cases**: both entry variants across all
64 CF/PF/AF/ZF/SF/OF combinations. Fifteen GPRs, target RIP and resume SP match;
the input packet is untouched. Each target observes the hardware condition codes
seeded before the stub, not the deliberately different `pt_regs.flags` value.
Two actual-wrapper calls with a test-only body capture body condition codes
`0x44`, but leave packet flags at their entry values `0x203` / `0xa82`.
These expected observations confirm the missing boundary, not a new recovery
capability. No kernel code, lock/ACK path or translated critical section runs.

The audit retains the same **211-input** runtime/test freeze as the static-range
live run; source-map SHA256 is
`393c99367836c66eda6890dc74d55311edfb6412fbdb38fd0476014f905859e4`.
Guest idle/source checks and read-only baseline verification pass. No production
code, wrapper ABI, guest kernel or daily test changes; no basic/live reruns.
Independent offline checks validate the frozen sources, extracted stubs and
128+2 records. Inputs, binaries/disassembly, wrapper image and report are in
`/tmp/kdlock-resume-boundary.QWRqXr.tar.gz`, SHA256:
`d1459da0344ab9e59c9ef722796fc1e75382b09dd8ae36345a8fbb2a604a8d8e`.
The [pending packet contract](JIT_REGISTER_ABI.md#31-访问时续跑的前置契约待实现)
defines prerequisites only; local flags changes still require a scope decision.

## Offline Evidence Verifier

**2026-09-10 14:05:40-14:07:36 +08**: the existing `test_regression.py` passes
**47 methods** with the delivered `tests/verify_evidence.py`. The reader and its
five merged test methods are the only changed/new inputs relative to the prior
210-input freeze; current tooling source contains **211 inputs**. No kernel,
translator, ownership, collector layout or live-workload behavior changes.

The reader checks stored source/boot/archive hashes, exact regular-file
membership, selection/journal order, result/log/status/marker agreement and
file identity across the inspection. Tests reject duplicate JSON/tar members,
links/devices/traversal, missing/extra/changed bytes, false acceptance, unsupported
sizes and cross-file mutation. Fixture commands and payloads are never executed
by the reader. Missing results are not interpreted as terminated processes.

Read-only checks against real, already closed guest output directories:

| Existing Capture | Reader Result |
| --- | --- |
| `kdlock-context-freshness.i4in6H`, 210 archived source inputs | Exit 0; all 20 recorded outcomes accepted |
| `kdlock-acquired-queue.ufJhS6`, 209 archived source inputs | Exit 1; acquired-spin rejection remains failed, early-A case has no result |

These are integrity/record checks, not new JIT execution, authentic provenance,
current-source acceptance or independent reexecution of case-specific oracles.
The current guest remains idle, its kernel baseline/Build ID matches, and all
211 tool/test inputs remain unchanged after verification. No module load,
VM restart, guest-kernel build or live rerun was needed.

The initial fixture put its source tree inside the output directory, causing
three errors and one failure; it was corrected without relaxing the reader.
Failure evidence: `/tmp/kdlock-offline-evidence.lhIxE4.tar.gz`, SHA256
`1713817435721a5df7790707f4f004f6fb8b734709529580314bba6d341e84a5`.
After the successful unit/positive checks, an external SSH command used zsh's
reserved `status` variable. Only the pending failed-archive check was resumed;
units and the successful archive check were not repeated.

Tool source, commands, unit/reader results, baseline and postflight evidence:
`/tmp/kdlock-offline-evidence.CNtIC0.tar.gz`, SHA256:

```text
f709a9f8f9377fea8815bf48a0440901564ec636db71019d6c0bb92ecac2212e
```

CLI behavior and limits are in [evidence usage](JIT_EXECUTION.md#执行与证据).
P1's dependency/build reproducibility and C1/C2/C5 remain open.

## Emitted-Block Context Admission

**2026-09-10 13:34:30-13:40:52 +08**: **20/20 live cases pass** on **210 frozen
runtime/test inputs**. Only `disassem/disassem.py` and the existing
`test_context_guards.py` change from the renamed-frame freeze. No new daily
case, owner/ABI change or guest-kernel modification is added.

The before-fix emission audit reproduces five admitted forbidden successors:
GS, FS, CLI, implicit GS load and direct `current_task` access. A callee rewrites
its return word, leaving the first successor without sequential dataflow input
while its code and RET whitelist target remain emitted. All five originally
return status 0 with assembly; after the fix they return 2 with no assembly.
These are mocked-text, assembly-only refusals, not published/executed dangerous
kernel code. The merged unit method expands this to nine operation classes in
both backends, including STI, implicit FS, SWAPGS and a foreign lock reference.

| Live Cases | Returned Bodies / Native Frames / Owner ACKs |
| --- | --- |
| `mode-2`, `mode-7`, `mode-8` | 4/0/0, 2/0/0, 2/0/0 |
| `mode-4`, `mode-5` | 1/0/0, 438/0/0 |
| `registers-8-3`, `registers-4-3` | 2/2/2, 1/1/2 |
| `native-mutex-depth` | 5/5/26 |
| Twelve `admission` refusals | Zero bodies, native frames and owner ACKs |

The eight positives retain exact workload/hostcall/register/ownership gates.
Mode 5 executes and resumes **438** hostcalls. The depth case's joined waves
match separate **12825 / 13141 / 13540-byte** images, with **1 / 1 / 3** returned
bodies; the external helper's translated RET, local capacity exit, native suffix
and source retirement remain checked. An entry-key image match alone is not an
immutable-generation certificate, and **455** body witnesses are not complete
instruction coverage. All cases drain without kernel or invariant faults.

At **13:32:45-13:33:04 +08**, five focused Python programs pass **225 methods**
and the independent **25-case** admission audit passes. This includes the 18
new refusal combinations and existing real generated CALL/RET positives.
Closed archive checks source/artifact hashes, per-case statuses, environment,
learning-wave images and postflight identity. The unchanged live Build ID is
`6f9f2e9fec382e97f620553793aa90b527a30af5`; final source/idle checks finish at
**13:40:54 +08**. No VM restart or guest-kernel edit/build/install.

Evidence: `/tmp/kdlock-context-freshness.i4in6H.tar.gz`, SHA256:

```text
6b9697bf75a20c8403da2e1a23c3f04bdf93eef4c7c377830e365bb5f421c9ce
```

Flow and affected-only commands are in [usage 5](JIT_EXECUTION.md#5-入口条件与嵌套续点).
This closes the unconditional scan omission, not concurrent pointer/return-word
freshness or C1/C2/C5 as a whole. Flags and code-version semantics stay deferred.

## Renamed Native-Frame Routing

**2026-09-10 13:05:02-13:06:29 +08**: **3/3 complex live cases pass** on **210
frozen runtime/test inputs**. Five test/workload/oracle inputs change from the
preceding peer-cancellation freeze. The existing dual-frame cases now verify
that a renamed borrower can acquire/unlock an unrelated native C without
losing its original A/B routing. Production kdlock source, analyzer, ABI and
guest kernel are unchanged; no new daily case is added.

| Case | Returned bodies / Native frames / Owner ACKs | New or preserved gate |
| --- | --- | --- |
| `parallel-drain-0` | 2 / 2 / 4 | Two renamed borrowers own/unlock C; keep their names through B/A ACKs |
| `parallel-drain-1` | 2 / 2 / 4 | Same routing contract with opposite drain order |
| `parallel-node-pressure` | 1 / 1 / 2 | Existing context/node/task refusal; no rename/C extension |

Each dual-frame case first observes both actual native arrivals. The waiters
have already changed comm from `klock_test` to `kd_renamed`. Each then takes
and releases its independent C as the real physical owner, while A/B remain
owned by the original combiner. C's released owner is zero; acquired/released
counts are 1/1. Both C returns precede pool pressure, with source still OPEN.
Arrival, resume and final record retain `kd_renamed`; both B/A ACKs precede
the final record and restoration to `klock_test`. Four rename logs and two
matched native-C records are mandatory, not inferred from aggregate reroutes.

Original **24008** A/B transitions, six contention records, peer cancellation/
userspace EINTR/requeue, **64-block / 1024-shadow** pressure and six retired
source-reuse records remain checked per order. C adds no JIT/frame/owner ACK
or A/B transition. Origin intervals remain **7095/7095** and task reroutes are
**20** per order. The pressure case retains eight records, **24010** transitions,
**4009/4009** origin intervals and its distinct real-node/injected-task refusals.
All cases drain tasks/frames/nodes without invariant or kernel faults.

All executed roots are **607 bytes**. Each dual case has two matching image/
entry/lock witnesses; the pressure case generates two images but executes only
one. Closed archive audit verifies source and artifact hashes, actual client/
module bytes, ordered routing evidence, command statuses and retirement/reload
records. This is execution within the matched images, not instruction-complete
coverage, generic rename/exit safety or immutable versioning.

Two focused unit programs pass **35 Python methods / 15,872 production C
checks**, detecting all eight resource mutants. Native C's absent-shadow and
idle-shadow paths preserve the existing routing ref; substituted scheduling
is not live ACK evidence. `W=1` test-module build passes with existing objtool/
locale warnings. Baseline and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` match; final source/idle checks finish
at **13:06:32 +08**. No VM restart or guest-kernel edit/build/install.
Frozen source, commands, units/build, environment, logs, artifacts and closed
audit: `/tmp/kdlock-renamed-frames.kgbNDt.tar.gz`, SHA256:

```text
eec8dff390a653b38195ff7cee4d7fa5e4093c69697f75ae06d45975c72431f0
```

Flow and affected-only commands are in
[usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame). C1/C2/C5 remain open;
the preceding standalone signal-client results are historical for this increment.

## Native B Peer Cancellation And Retry

**2026-09-10 12:32:59-12:34:56 +08**: **5/5 complex live cases pass** on **210
frozen runtime/test inputs**. The existing two-frame drain cases now cancel and
explicitly requeue both non-target native B peers before releasing either old
frame. This test/client/oracle increment changes six inputs from the preceding
209-input freeze; production kdlock algorithms, analyzer, ABI and guest kernel
are unchanged. The extended catalog remains 64 cases with 11 covered diagnostics
opt-in; the simpler no-cancellation version is not repeated.

| Case | Returned bodies / Native frames / Owner ACKs | Distinct checks |
| --- | --- | --- |
| `parallel-drain-0` | 2 / 2 / 4 | Two cancelled waits, userspace EINTR returns and explicit retries; first drain order |
| `parallel-drain-1` | 2 / 2 / 4 | Same gates with the opposite drain order |
| `parallel-node-pressure` | 1 / 1 / 2 | Real four-slot pressure, context refusal and injected task-allocation failure |
| `native-peer-1` | 1 / 1 / 1 | Legacy interruptible native peer cancellation and surviving peer acquisition |
| `native-peer-3` | 1 / 1 / 1 | Legacy killable peer ignores nonfatal signal, then cancels on fatal signal |

In each dual-frame case, two real B wait lists are observed before SIGUSR1 is
sent through identity-checked pidfds. Each native wait returns **-EINTR**, has
pending=1/fatal=0, has left its wait list and has acquired/unlocked B zero times.
Both old A/B owners remain unchanged. The real single-process client reports
**ret=-1/errno=4/signals=1**, explicitly issues one second ioctl, requeues as the
same task/PID and eventually returns **ret=0/errno=0/signals=1**. Source snapshots
before signalling and after requeue both show **OPEN/modules=1/frames=2/writers=0**.
The kernel oracle requires five failed trylocks, four actual queue observations,
two cancellations and two own-owner acquisitions/unlocks; userspace evidence
independently requires two pidfd signals, two EINTR returns and two retries.

Both drain orders preserve the original **24008** protected transitions, six
exact contention records, four owner ACKs, real **64-block / 1024-shadow**
pressure, retained-writer retirement and six post-reload native records.
Origin acquisition/release counts balance at **7095/7095** per order. The first
peer cannot obtain the other still-retained B; all original callers and both
peer supervisors join before unload. The shared-pressure case preserves eight
records, **24010** transitions and **4009/4009** origin intervals. Each legacy
signal case checks **12005** requests, **12006** transitions and **2003/2003**
origin intervals; expected SIGKILL exit is not counted as a normal return.

The parallel roots are **607 bytes** each; the pressure case generates two
images but has only one matching returned body. Each legacy signal root is
**2672 bytes**. Archive audit matches all seven entry/lock witnesses to actual
image bytes, source hashes, per-case archives and client binary hashes. This
proves execution within those images, not every emitted instruction or version
isolation. All cases drain tasks/frames/nodes with zero invariant/kernel faults.

Two focused unit programs pass **61 Python methods (32 + 29)**, including the
delivered client's 16 valid/error rounds and invalid-target refusal with
substituted syscalls. Those fixtures are not kernel/signal execution evidence.
`W=1` test-module build passes with existing objtool/locale warnings. Baseline
and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5` match before/after;
final source/drain checks finish at **12:34:59 +08**. No VM restart or guest
kernel edit/build/install. Frozen source, commands, units/build, environment,
logs, artifacts, client identities and closed hash audit:
`/tmp/kdlock-peer-cancel.6OzujR.tar.gz`, SHA256:

```text
c2cae8cb0c90170653cfcdb20afcb4e1ee33d6390794d5ede2e2af53203909b2
```

Flow, phase-specific evidence and affected-only commands are in
[usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame). Only native-peer waits
are cancelled; no delegated frame is abandoned and no owner handoff/task pin
is added. Arbitrary cancellation, fairness, provider-reader lifetime and the
broader C1/C2/C5 requirements remain open.

## Queued Spin Acquisition

**2026-09-10 11:24:15-11:25:09 +08**: **2/2 complex live cases pass** on **209
frozen runtime/test inputs**. `native-spin-acquired` now selects the real private
B queue head plus follower, instead of its simpler FAST schedule. The same case
identity remains in the 64-case extended catalog; 11 covered diagnostics remain
opt-in. Production executor/queues, analyzer limits, wrapper ABI and guest
kernel are unchanged by this increment.

| Case | Returned bodies / Native frames / Owner ACKs | Requests / Protected transitions | Executed root bytes |
| --- | --- | --- | --- |
| `native-spin-acquired` | 1 / 1 / 2 | 12002 / 12008 | 10376 |
| `native-spin-outer-dependency` | 1 / 1 / 7 | 12002 / 12008 | 10376 |

Both roots have SHA256
`90c0099c0743d72b44a92ade7456cda777cf1fedaa9281b67eca9553c60b3187`.
Each case produces two images; only the matching root has a returned body
witness. This proves execution in that image, not every emitted instruction.

In the queued case, B holder **2163587** on CPU **1** observes two real private
waiters and **prefix=1/suffix=0**. Waiter **2163590** resumes on CPU **0**, while
combiner CPU **4** retains both A/B as owner **ffff888134fdc100**. The checkpoint
is explicitly **kind=2 / QUEUE_OWNER**, with post-CALL RIP **ffffffffc0b3e4ec**,
RSP **ffffc9000a7d7c58**, and matching CALL-stack token at RSP-8. Actual module
E8/PLT32 return offsets **0x14493 / 0x144ec** independently match the **0x59**
entry-to-B-return delta. The suffix and completion occur once, B/A ACKs match,
and CPU **2**'s follower then acquires B as its own owner. All seven roles join;
all six observer counts equal 1 and failures equal 0. B acquisition/release
counts are **1/1**, with no remote delegation or PENDING substitution.

The affected early-A case retains its distinct real ledger exhaustion, released
A, native C-owner dependency, matching PENDING packet and seven ordered ACKs.
Both cases preserve the original complex B state and request records, check two
protected states, and drain tasks/frames/nodes without overlaps, context failures
or kernel faults. This is not hardware-GPR/flags, arbitrary EIO or remote
publication recovery evidence; the earlier independent register gates remain
historical for this test-only increment.

Two focused unit programs pass **3,258 production C assertions / 46 Python
methods** before live execution. `W=1` test-module build passes with existing
objtool/locale warnings. The baseline and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` match before/after; final source/drain
checks finish at **11:25:11 +08**. No VM restart or guest-kernel edit/build/install.
Frozen inputs, commands, units/build, environment, logs, artifacts and closed
ELF/hash audit: `/tmp/kdlock-acquired-queue-retry.OvUora.tar.gz`, SHA256:

```text
93a71cbf2fdc61515ac3826b4274d8889be2c2e387f305a82ed2af9ce6a655b5
```

The first **04:10:25-04:11:07 +08** attempt is retained as **failed**, with zero
returned JIT bodies and the second case NOT RUN. Admission rejected the original
register-sample write at **ffffffffc0b3e683**, not an actual context access or
kernel crash. Offline ELF analysis reproduces work-budget exhaustion after the
extra copy of the complex A state machine. That redundant copy was removed;
the committed A counter, original B computation, register probe and admission
limits remain intact. The failed run drained and has its own 209-input freeze,
logs and diagnostic trace: `/tmp/kdlock-acquired-queue.ufJhS6.tar.gz`, SHA256:

```text
01366ae15bb8acae4f6dc6edaec99135bc30cfc81b359dbcb19f35a4df5cf81f
```

Flow, CPU prerequisites and affected-only commands are in
[usage 6.11](JIT_EXECUTION.md#611-spin-获取后的受检续跑). C1/C2/C5 remain open.

## Checked Spin Acquisition

**2026-09-10 03:43:25-03:45:02 +08**: **3/3 complex live cases pass** on **208
frozen runtime/test inputs**. A new checked local spin post-acquisition EIO
boundary hands off the already-consumed CALL packet with B still owned by its
combiner. The existing nested workload is reused, not duplicated as a smoke.

| Case | Returned bodies / Native frames / Owner ACKs | Requests / Protected transitions | Executed root bytes |
| --- | --- | --- | --- |
| `native-spin-acquired` | 2 / 2 / 4 | 12009 / 12009 | 9131 |
| `registers-8-3` | 2 / 2 / 2 | 12003 / 12013 | 16369 |
| `registers-4-3` | 1 / 1 / 2 | 12002 / 12008 | 12825 |

This historical checkpoint covers local FAST; QUEUE_OWNER becomes live-tested
only in the later increment above. Waiter **2152703** resumes at the exact B
return **ffffffffc0b3a46e**, with retained A/B and ordered ACKs; the other frame
takes ordinary CALL miss. Actual source return offsets **0x1043c / 0x1046e**
match the packet. No replay, overlap, remote acquisition or invariant failure.
Each register case retains one 16-GPR/return-stack sample, not flags. Mode 8
uses a real remote child/ancestor relay; mutex balances **2006/2006** native
acquires/releases and checks one equal stack window. Generated counts **2/6/1**
are not executed-image counts. Full bytes/identities are in the archive audit.

Five unit programs pass **38,489 C assertions / 56 phase-error combinations /
44 Python methods**. A missing CPU-diagnostic mock initially caused **4/5**;
the failure is preserved and all five rerun after correction. `W=1` builds,
source/kernel identity and final drain pass, ending **03:45:04 +08**. No restart,
guest-kernel edit/build/install, ABI expansion or owner handoff. Commands,
failed/successful units, source, artifacts, protocol and closed audit:
`/tmp/kdlock-spin-acquired.L5BKki.tar.gz`, SHA256:

```text
9c763b7ffecf6a2343690cafd7297d49d6457c3f25636f7e6032ccbfcc2932dd
```

Flow, limitations and affected-only commands live in
[usage 6.11](JIT_EXECUTION.md#611-spin-获取后的受检续跑). `extended` now has **64**
cases; 11 covered diagnostics stay opt-in. C1/C2/C5 remain open; deferred code
versions and flags semantics are unchanged. Earlier 63-case catalog counts
below describe their own historical freezes.

## Spin Gate Pressure

**2026-09-10 03:02:35-03:04:44 +08**: **2/2 complex cases pass** on **207 frozen
runtime/test inputs**. The existing ticket case now includes real gate-map
pressure; it does not add another daily case. Only SELFTEST gate observations,
the test workload/driver/oracle and selection units change. Production lock
capacity/ownership, translator, two-word ABI and guest kernel remain unchanged.

| Case | Returned bodies / Native frames / Owner ACKs | Pressure and continuation |
| --- | --- | --- |
| `virtual-ticket-refusal` | 1 / 1 / 1 | Real 32-ticket PENDING exit, then full gate map/new native contention while the original frame remains live |
| `virtual-node-refusal` | 1 / 1 / 1 | Existing injected node-count refusal after real virtual-ticket reservation/cancellation; new gate pressure disabled |

Each case executes the matching **16,369-byte** root image, completes **12,003
requests / 12,011 protected transitions**, checks two workload states and drains
without kernel faults or invariant failures. Six generated images per case
do not mean six executed images; only the root has a returned body witness.
Spin waiters are **2141419 / 2144622**, executing on combiners' CPUs **4 / 6**.
The original register/CALL packet, pin balance, retained A and final ACK gates
remain enforced. The node case's injected view is not natural node saturation.

Gate snapshots show **3 prepare / 65 held / 1024 filled / 1024 drained** slots.
The filler really acquires **1,025 distinct locks**, allocating **959 new gates**
and encountering **66 genuine allocation refusals**. A separate target adds the
67th refusal on the final lock, behind non-target holder **2141436** on CPU 10.
Target **2141435** on CPU 11 publishes Linux tail word **0x300001**, whose CPU
encoding is independently checked in the archive audit. Both finish native
records with zero pins before B resumes; the last lock's updates are 1, 2, 3.
This absent-gate site is cold, has no returned JIT witness, and cannot be counted
as another proxy execution.

The original native frame stays live during held/filled/drained snapshots.
A owner `ffff888108fa0000` and B owner `ffff88811dd28000` remain unchanged across
the pressure window. The three new roles join before the original B holder is
released; all seven original roles also join. Gate membership/values, physical
words and final full-array records agree. No table population, reduced capacity,
fabricated frame or owner handoff is used; only promotion/timing are controlled.
This tests **unstarted** new-lock gate fallback alongside a progressed ticket
exit, not a PENDING gate-allocation exit or arbitrary cancellation schedules.

Preflight, three focused unit programs and `W=1` module builds finish during
**03:00:44-03:01:00 +08**. The gate oracle checks 3 methods and 15 corruption
variants; the gate/entry production fixtures check **3131 + 3727** assertions,
and the selector/evidence program checks **41 methods**. Builds retain objtool
stack/RETHUNK/CLD and Perl locale warnings, not a warning-free build. The 18-file
baseline, config, nine existing build files and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` match before/after; final drain/source
checks finish at **03:04:46 +08**. No VM restart or guest-kernel edit/build/install.

The closed-archive audit checks all 207 host/guest/frozen-source hashes, boot
notes, every member of six case archives, actual body/image identity, gate
records, native queue identity and terminal drain. The new automatic environment
manifest is present for this live run; post-case default builds and preserved
SELFTEST bytes remain distinguished. Commands, source, logs, images and audit:
`/tmp/kdlock-spin-gate.wqA39m.tar.gz`, SHA256:

```text
4aabca427c571aeb1cf92ea3ffe6fab2911b4f1bd98bc7e2e8d472ad27d8ff40
```

Execution flow and incremental commands have one home in
[usage 6.3](JIT_EXECUTION.md#63-spin-虚拟请求取消与续跑). Extended remains 63 cases,
with 11 covered diagnostics opt-in. Broader C1/C2/C5 requirements remain open.

## Environment Evidence

**2026-09-10 02:39:52-02:39:55 +08**: the existing evidence/selection unit
program passes **41/41 methods**, **1 program, 0 failures, no SKIP** on **205
frozen runtime/test inputs**. Only `tests/regression.py`,
`tests/regression_evidence.py` and `tests/unit/test_regression.py` change.
The catalog stays unchanged: 63 extended cases and 11 covered opt-in diagnostics.

The real guest capture records PATH-selected Python **3.10.12**, Miasm **0.1.5**,
pyelftools **0.27**, future **1.0.0**, pyparsing **2.4.7**, GCC/cc **11.4.0**,
GNU make **4.3**, binutils **2.38** and bash **5.1.16**. Ten bounded command
observations succeed, including Python metadata and structured `findmnt` output.
The unit checks their resolved binary hashes, selected launch paths, relative
PATH handling and exclusion of unrelated environment values. Failure fixtures
cover missing tools/dependencies, nonzero exit, timeout, malformed output and
unreadable preemption settings, plus stopping before any workload on a capture
error. These fixtures are not live translation failures.

Starting settings are ext4, ASLR/NUMA-balancing sysctls 0 and voluntary preemption.
The independent archived-byte audit verifies all 205 source members against
host/guest/pre/post hashes and boot notes against the preceding early-A run.
Kernel remains **6.1.159 #28**; callers/modules are idle before and after.
No module/daemon/benchmark build, module load, JIT workload, admission audit,
VM restart or guest-kernel edit/build/install is performed. The already verified
18-file kernel/build baseline is not rerun for this read-only change.

Command, frozen source, unit log, real environment manifest and archive audit:
`/tmp/kdlock-environment-evidence.DlIkxq.tar.gz`, SHA256:

```text
966c1360ef112a29812279c6d444d7b50e52a2cbedef02da56d8469f43dea2a5
```

Flow and incremental selection are maintained only in
[evidence handling](JIT_EXECUTION.md#执行与证据). This is a starting observation,
not a package lock, full dependency payload, reproducible build, loaded-image
identity or a success cache. P1's broader reproducibility work remains open.

## Early-Outer Continuation

**2026-09-10 02:17:41-02:18:25 +08**: **2/2 complex live cases pass** on
**205 frozen runtime/test inputs**, both loading `mutex_jit=1`. This closes a
specific execution gap, not a selector-triggered repeat: the earlier mutex
dependency result in [the stack-check run](#mutex-control-stack-check) predates
the current analyzer, checked-window retention and executor changes. Archived
old/current hashes identify those differences. No runtime input changes for
this acceptance; no production fix or relaxed admission rule is needed.

| Case | Returned bodies / Native frames / Owner ACKs | Requests / Protected transitions | Executed image |
| --- | --- | --- | --- |
| `native-spin-outer-dependency` | 1 / 1 / 7 | 12002 / 12008 | 9131 bytes |
| `native-mutex-outer-dependency` | 1 / 1 / 7 | 12002 / 12010 | 12825 bytes |

Both use OOO=3/dependency=2 and reach real eight-record ledger capacity after
JIT releases A. The original waiter resumes the current PENDING C lock CALL;
target and staged/native RIP/RSP agree, with a nonzero CALL return IP. A non-target
C owner acquires the released A while the combiner still owns B, completes its
native work and releases C. The waiter then owns C, unlocks it itself and
receives six child ACKs followed by B's final ACK, without replaying the prefix.
Spin waiter/combiner/native-peer TIDs are **2132410/2132408/2132411**;
mutex TIDs are **2133346/2133345/2133349**. The mutex's first six child owners
remain the combiner, while its seventh child belongs to the waiter.

Each case has one matching entry/outer-lock returned-body witness, two checked
states, one exact OOO record and zero failures. Spin additionally generates a
3714-byte image with no separate body witness; it is not counted as executed.
All six spin roles and eight mutex roles join. Mutex records eight equal
256-byte stack comparisons and **2007/2007** original acquisitions/releases;
spin's final ACK restores its waiter pin count to zero. This is real ledger
exhaustion, not `jit_fail_pending_lock` injection. It does not add a full-GPR or
flags sample, prove C entered a Linux wait list, or establish arbitrary deadlock
recovery; those are different contracts.

A closed-archive audit verifies all 205 host/guest/source-archive hashes,
boot notes, every member of six case archives, PENDING/dependency identities,
per-lock ACK ordering, record values and terminal retirement. Pre/postflight
retain the 18-file kernel baseline, config, nine existing build files and
Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`. Final checks finish at
**02:18:27 +08** with no kernel fault, invariant/drain failure, VM restart or
guest-kernel edit/build/install. Default module/daemon/benchmark build hashes
match the preceding live freeze and remain in `summary.json`.

Commands, old/current source identities, frozen inputs, logs, images and audit:
`/tmp/kdlock-early-outer.knD8La.tar.gz`, SHA256:

```text
c04e45ae127395fc9a5ada91b02fcba9c601d374fa36582d15e8464d0bfadca7
```

The preceding **02:05:00-02:05:04 +08** selection-only increment changed only
the selector and its unit program, passing **38 methods**, with no failure or
SKIP. It included these existing dependency gates, replaced the two ordinary
stage-3 diagnostics with same-stage register cases, previewed 18 unique
native-scope cases and retained explicit diagnostic selection. That earlier
step did not build/load modules or run JIT. Its separate source/unit/preview
archive is `/tmp/kdlock-outer-selection.Or6iBT.tar.gz`, SHA256:

```text
c9ef9574bfbf08d19ea6632ce1a40f07f110bb08b160807b16337ece92fb855d
```

Flow, replacement boundaries and incremental commands have one home in
[usage 6.10](JIT_EXECUTION.md#610-提前释放-a-的原生依赖). Eleven reviewed diagnostics
stay opt-in and `extended` stays 63. No basic sweep, additional unit/admission
run or full matrix is performed; wider C1/C2/C5 requirements remain open.

## Same-CPU Mutex Continuation

**2026-09-10 01:41:22-01:42:23 +08**: **3/3 complex cases pass** on
**205 frozen runtime/test inputs**, all with `mutex_jit=1` and actual mutex JIT.
Six workload/driver/oracle/selection inputs change. Mutex-only test barriers
now allow scheduling, and observations identify actual roles and completion
contexts; production locking, translator, wrapper ABI and guest kernel do not
change. `native-4-4` is upgraded in place, with no new daily case.

| Case | Returned bodies / Native frames / Owner ACKs | Distinct contract |
| --- | --- | --- |
| `native-4-4` | 1 / 1 / 1 | Owner/waiter/trailer share CPU 4; actual B wait list and final ACK |
| `registers-4-3` | 1 / 1 / 2 | One raw 16-GPR/CALL-return sample after JIT; flags not checked |
| `waiter-usr1` | 1 / 1 / 1 | Real SIGUSR1, 128 pending observations, uninterruptible native B |

In the shared case, real A owner TID **2126375** and original waiter
**2126377** execute on CPU 4, as does A's trailer. B holder **2126370** is
distinct and native. The waiter resumes the preserved PENDING CALL on B's
Linux wait list, acquires B under its own identity while A's owner stays
unchanged, then receives A's final owner ACK before completing record 12001.
At B acquisition and post-ACK completion it remains on CPU 4 with preemption
enabled and IRQs on. All before/called/after counts are one and value is `d6ed`.
Three actual queue reservations use multiple CPU-local slots; context refusal,
node overflow, frame failure and final waiter/node counts are zero. Original
mutex acquisition/release counts balance at **2003/2003**. PENDING E2BIG is
still injected, not natural resource saturation or another JIT context.

Each case checks **12002 requests, 12008 protected transitions, two states and
zero failures**, with all seven roles joined. Each generates one **12825-byte**
image and has one matching entry/lock returned-body witness. The independent
register sample and real signal ordering pass; no image is counted merely
because it was generated. The signal case keeps separate role CPUs and must
complete native B, the suffix and A ACK before userspace signal delivery.

Focused guest units pass at **01:40:03-01:40:08 +08**, with no failure or SKIP.
New negative checks reject invalid selectors and missing/duplicate/wrong CPU,
task, packet, order, record and exit evidence. A closed-archive audit verifies
all 205 host/unit/guest/source-archive hashes, boot notes and every member of
nine per-case archives; it also rechecks raw register and signal evidence.
Default build hashes remain in `summary.json`; kdlock's production binary is
unchanged, while the workload module reflects the new barriers/observations.

Pre/postflight retain the 18-file kernel baseline, config, nine existing build
files and Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`; final source,
baseline and idle checks finish at **01:42:26 +08**. No kernel fault,
invariant/drain failure, VM restart or guest-kernel edit/build/install occurs.
Commands, frozen source, units, protocols, images and independent audit:
`/tmp/kdlock-mutex-shared.EOHU7c.tar.gz`, SHA256:

```text
147c1a092a6988d392a6a99d279876b4b1329bf1abfcc8f62e8f4fab3a87b930
```

Execution flow and focused commands are in
[usage 6.1](JIT_EXECUTION.md#61-mutex-资源与恢复包). `extended` stays 63; baseline,
native controls, unrelated units, admission audit and the 67-case matrix are
not rerun. This is distinct from another queue's context refusal and does not
close general oversubscription, fairness, arbitrary exit or C1/C2/C5.

## Remote Relay After Waiter Exit

**2026-09-10 01:13:32-01:14:49 +08**: **2/2 existing remote cases pass** on
**205 frozen runtime/test inputs**. A SELFTEST-only probe strengthens the
all-unlocked case; the existing driver/oracle and selector carry the option.
Default ownership, wrapper ABI, translator and guest-kernel behavior do not
change. Both cases load `mutex_jit=1`, but their actual backend is spin.

| Case | Returned bodies / Native frames / RPCs / Owner ACKs | Lifetime observation |
| --- | --- | --- |
| `remote-late-3` | 4 / 4 / 6 / 1 | Waiter TID detaches before no-lock root completion |
| `remote-late-2` | 4 / 4 / 0 / 4 | Existing retained-ancestor owners; exit probe off |

The first run retains the identity of waiter TID **2120580** while it is still
blocked. Its CPU-22 root has zero remaining locks; the real child's final ACK
precedes the waiter's complete record, TID detachment and root completion, in
that order. Full frame/packet and executor-context comparisons pass. Only a
`struct pid` reference is held, not a test-owned task reference. This proves
the bounded normal-exit interval, not task-memory RCU reclamation, arbitrary
suffix exit, request abandonment or a new owner-handoff protocol.

Both runs cross NUMA at every real logical handoff and retain exact state counts
**12008/12008/12008/12009**, two checked requests and zero failures. Each prepares
five images; its four distinct entry/lock body witnesses all match the same
**7004-byte** root image, not all five images. Eighteen workload roles join before
retirement/unload. The enabled case also archives its SELFTEST image and gate
readback; both post-case default modules exclude the probe's logging marker.

At **01:12:20-01:12:25 +08**, all three focused guest unit programs pass. New
negative evidence checks reject missing/duplicate/mismatched identities, changed
packets, false detachment and early completion; the production-function fixture
still checks cached PID after final ACK. A closed-archive audit verifies all 205
host/unit/guest/source-archive hashes and every member of six case archives.

Pre/postflight retain the 18-file source baseline, config, nine existing build
files and Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`; final idle/source
checks finish at **01:14:51 +08**. No kernel fault, invariant/drain failure,
VM restart or guest-kernel edit/build/install occurs. Default build hashes are
retained separately from the loaded SELFTEST image in `summary.json`.

Commands, source, units, protocols, images and audit:
`/tmp/kdlock-relay-exit.UAmCLe.tar.gz`, SHA256:

```text
0a4f638dd16c227c1ae6887d02e98ab4d4c382eb862a901413d75dad4b5d865c
```

Flow and limits have one entry in [usage 6.9](JIT_EXECUTION.md#69-无锁祖先与-waiter-退出).
No daily case is added; `extended` remains 63. Baseline, native controls,
unrelated units, admission audit and the historical 67-case matrix are not rerun.
The remaining C1/C2/C5 lifecycle and concurrency work stays open.

## Repository Native Controls

**2026-09-10 00:43:19-00:44:38 +08**: **4/4 selected cases pass** on
**204 frozen runtime/test inputs**. Only the existing register driver/oracle,
selector and their two unit programs change. Production kernel modules,
translator, ABI and lock protocols are unchanged; all cases load `mutex_jit=1`.

| Case | Checked requests / Raw register samples | Returned bodies / Native frames / Owner ACKs |
| --- | --- | --- |
| `control-0` | 8 / 8 | 0 / 0 / 0 |
| `control-3` | 8 / 8 | 0 / 0 / 0 |
| `registers-4-3` | 12002 / 1 | 1 / 1 / 2 |
| `registers-8-3` | 12003 / 1 | 2 / 2 / 2 |

Both native controls run the same real assembly probe under non-target Linux
locking, with `target_process=kd_unused` read back from the loaded provider.
They have no daemon or promotion phase, zero registered entries and an OPEN
source state with zero modules/frames/writers. All eight records and protected
transitions are exact; raw 16-GPR, CALL stack/return and returned-value checks
pass. There is no JIT entry/body/install or delegated owner evidence. These are
pure-native reference measurements, not JIT, flags or arbitrary-ABI proof.

The two complex register regressions retain the default target/JIT path. Mutex
executes the matched **12824-byte** image, with 12008 state transitions and two
owner ACKs. Spin has two distinct entry/lock body witnesses for one **16369-byte**
image and 12013 transitions; its six generated images do not mean six executed
images. Its two native frames share one matched callee sample. Both cases check
every request and exactly-once effects; all masks/failures are zero.

At **00:42:16 +08**, the two guest unit programs pass **35 + 7 methods**;
the actual native assembly fixture performs **150 checks**. New cases reject
invalid control selectors before live setup, keep controls out of all other
scopes and reject JIT/ACK contamination even with zero continuation counters.
A closed-archive audit verifies all 204 host/unit/guest/source-archive hashes,
boot notes and every member of all 12 per-case evidence archives. The controls'
captured daemon files exactly match the preceding shadow-capacity run's inherited
artifacts; they are neither newly generated nor counted as executed. Their
original metadata is copied into this archive, alongside the historical helper
for provenance; the new driver never invokes that helper.

Pre/postflight retain the unchanged 18-file kernel baseline, config, nine existing
build files and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
Final source/baseline/idle checks finish at **00:44:40 +08**. No kernel faults,
invariant/drain failures, VM restart or guest-kernel edit/build/install occurs.
Post-case binaries match the previous default builds; hashes remain in
`summary.json`, not a new loaded-image or immutable-generation assertion.

Commands, source, units, protocols, artifacts, historical provenance and audit:
`/tmp/kdlock-native-controls.kuhmqe.tar.gz`, SHA256:

```text
658367fdbbea565dce2d327863293142d5c21bd6c9c7a8681be8c37192e02c9b
```

The current controls use [usage 3.1](JIT_EXECUTION.md#31-纯原生寄存器对照), with no
external helper dependency. `native-controls` is explicit, `extended` stays
63, and no baseline, full unit suite, admission audit or 67-case matrix is rerun.
This closes the native-control packaging gap, not generic environment
reproducibility or the remaining C1/C2/C5 work.

## Mutex Shadow With Live Frames

**2026-09-10 00:19:14-00:20:41 +08**: **3/3 existing `mutex-parallel` cases pass**
on **204 frozen runtime/test inputs**, all with `mutex_jit=1`. The increment adds
an early shadow-refusal diagnostic, a SELFTEST-only read counter and an opt-in
workload/oracle inside the existing dual-frame driver. No allocation capacity,
owner protocol, wrapper ABI, translator or guest-kernel behavior changes.

| Case | Returned bodies / Native frames / Owner ACKs | Shadow capacity / New native queue |
| --- | --- | --- |
| `parallel-drain-0` | 2 / 2 / 4 | 3 old + 1021 new shadows = 1024; three native records |
| `parallel-drain-1` | 2 / 2 / 4 | Same checks with the opposite old-frame drain order |
| `parallel-node-pressure` | 1 / 1 / 2 | Shadow extension off; existing context/node/task refusals retained |

Each dual case has 1025 distinct filler-lock records: the first 1021 allocate
real shadows and the remaining four fall back natively. A non-target holder
then observes two identified target tasks on the final mutex's real Linux
wait list. All three update under their own native ownership without a shadow;
four filler refusals plus two target refusals match the exact loaded CALL entry.
Four snapshots retain source OPEN and frame counts 0/2/2/2, with shadow counts
3/3/1024/1024. The new queue drains before either old frame resumes. These are
native-only records, not additional JIT, PENDING-packet or owner-ACK positives.

The previous 64-block code pool, two B peers, four old ACKs, writer-only EBUSY,
terminal retirement and six same-address native-reload records remain checked
in each dual case. Each of the three cases prepares two **607-byte** images;
all five returned entry/lock body witnesses match them, while the shared-CPU
case's other image is not counted as executed. The five 256-byte mutex stack
checks remain equal. No kernel fault, invariant or drain failure occurs.

At **00:17:53 +08**, focused guest units pass **15,849 production resource
assertions**, eight assertion-detected mutants and **29 observer methods**.
The new observer cases check both drain orders and malformed counts, membership,
owners, queue identities, records, fallback entries and execution intervals.
These are not extra live runs. A closed-archive audit matches all 204 host,
unit, guest and source-archive inputs and every member of all nine case archives.
Each dual protocol archive has 70 payload files plus one metadata-only link;
the shared case has 29. Copied SELFTEST modules and default post-case builds are
separate in `summary.json`, not an immutable-version or loaded-image claim.

Pre/postflight retain the 18-file baseline, configuration, nine existing build
files and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
Final source/baseline/idle checks finish at **00:20:44 +08**; no VM restart,
guest-kernel build/install, baseline sweep or full matrix is performed.
Commands, frozen source, units, images, all protocols and independent audit:
`/tmp/kdlock-mutex-shadow.ECYbfc.tar.gz`, SHA256:

```text
948eb4d69e9b444b9eee2946be3b0b84c02e8d6e3c371d2b524d9fabe71855e1
```

The audit notes retain its initial mistake of mixing later reload arrivals with
old-frame arrivals; the correction separates the already marked native-only
interval, without changing live inputs or rerunning JIT. Execution flow and
incremental selection stay in [usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame)
and [usage 7](JIT_EXECUTION.md#7-分层与增量回归). `mutex-parallel` stays three cases,
`extended` stays 63 with nine reviewed covered diagnostics excluded. This closes
one bounded resource composition, not C1/C2/C5 or independent packet/RCU checks.

## Natural Held-Lock Capacity

**2026-09-09 23:50:13-23:51:17 +08**: **2/2 existing complex cases pass** on
**201 frozen runtime/test inputs**. Both use spin JIT with `mutex_jit=0`, not
mutex JIT. Only SELFTEST observation, its protocol oracle and coverage-review
checks change; no production locking, translation, ABI or guest-kernel change.
No new workload or daily case is added. `extended` remains 63 cases excluding
the same nine reviewed diagnostics; `shadow-capacity` stays independent.

| Case | Returned bodies / Native frames / Owner ACKs | Sampled stack left / Untouched write watermark |
| --- | --- | --- |
| `node-physical-8-0` | 8 / 1 / 1 | 2392 / 1320 bytes |
| `node-physical-8-1` | 8 / 1 / 1 | 1896 / 824 bytes |

Each case verifies eight distinct entry/lock body witnesses against the
**2500-byte** image. A second **1642-byte** generated entry has no separate
body witness and is not counted as another executed image. There are eight
genuine physical frames, 96016 exact request records and 96034 protected-state
transitions per case. At the deepest CALL, `depth=recorded=local=8` and
`error=-7`; full GPR/CALL-word, frame, combiner, physical-owner, untouched-B and
CPU/node/preemption/IRQ checks all pass. The only permitted frame change is
the original CALL's PENDING state. The waiter resumes that CALL and completes
its native suffix with one owner ACK, without entry replay. Stack observations
remain bounded measurements, not arbitrary IRQ/NMI safety proofs.

The two guest unit programs pass **33 + 18 methods** at **23:49 +08**; the frame
program also retains its 160 constructed protocol histories and 20 extracted
watermark checks. These are not additional live JIT runs. The automatic source
archive matches all 201 host/unit/live inputs. A closed-archive audit verifies
each member of all six accepted per-case archives, plus the three archives of
the earlier failed case. Boot notes and pre/postflight retain Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`, the 18-file baseline, configuration
and nine existing build files. Final baseline/source/idle checks finish at
**23:51:19 +08**. No kernel faults, invariants or drain failures occur; no guest
restart, guest-kernel build/install, baseline sweep or full matrix is performed.
Each protocol archive contains its copied SELFTEST module; default rebuild
outputs and their hashes remain separate in `summary.json` and automatic
post-case archives, not claims of loaded-image or immutable-version identity.

Commands, source, units, artifacts, protocol, outcomes and independent audit:
`/tmp/kdlock-held-capacity.EVr8p5.tar.gz`, SHA256:

```text
47768c7108ee39a90f895134973d1d8278571c8bac9aea52e434179680dad4e0
```

The **23:43:52-23:44:23 +08** attempt remains **FAIL, then NOT RUN**. Its new
observer incorrectly assumed each physical frame had only one lock record;
actual frames inherit ancestor records and reach logical capacity before the
later local-shadow check. The body/state/native sequence completed, but the
observer rejected it, and the runner retained drained, source-stable evidence
with `accepted=false`. NUMA=1 was not run. The correction preserves this failure
and restores the independent shadow test instead of claiming false coverage.
The original archive also retains the preparation stop for an unresponsive
monitor: verified agent-owned orphan nc clients were closed and the existing
snapshot confirmed; the healthy QEMU was not restarted.

Failed source, units, script result, original observation and monitor records:
`/tmp/kdlock-shadow-merge.0arPT4.tar.gz`, SHA256:

```text
1f51db0ff9c8cc7be95ed952710bd131e28662ea4471bb57277555c474313387
```

Execution flow, the actual branch distinction and incremental commands live in
[usage 6.8](JIT_EXECUTION.md#68-物理-frame-链与容量检查). This strengthens one real
resource exit; it does not close C1/C2/C5 or supersede independent shadow,
register, frame-push, remote-cancellation and RCU checks.

## Scoped Evidence Capture

**2026-09-09 23:15:08-23:15:42 +08**: **2/2 selected cases pass** on
**201 frozen runtime/test inputs**, both with `mutex_jit=1`. Only runner/evidence
code and the common daemon-log declaration change; no lock, translator, ABI or
guest-kernel implementation changes. The new input inventory also includes
the previously omitted captured guest config and patch.

| Case | Returned bodies / Owner ACKs | Archived payload files: generated / protocol / post-case builds |
| --- | --- | --- |
| `parallel-drain-0` | 2 / 4 | 12 / 61 / 5, plus one link recorded as metadata only |
| `context-mixed` | 0 / 0 | 2 / 12 / 5; generated files are empty tables, no `jit.bin` |

The complex positive executes both **607-byte** images and retains two native
frames, both real B peers, the 64-block code-pool/refusal combination, four
owner ACKs and terminal retirement/reuse. The negative retains identical
before/after refusal metadata and completes 12129 native-only requests with
12257 state transitions, no JIT body and no owner ACK. No fault/invariant/drain
failure occurs. Kernel pre/postflight verifies the unchanged 18-file baseline,
configuration, nine existing build files and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`; no VM restart or guest-kernel edit,
build or install occurs. Default module hashes remain those of the previous
post-live formatting check below.

The corrected focused program passes **33 methods** at **23:13:50 +08**.
Archived source matches all 201 host/guest/unit/live inputs; the boot-note hash
and Build ID match. An independent closed-archive audit verifies all six
per-case archives and each member hash. The compiler-entry symlink is absent
from tar payloads; only its target text remains in `evidence.json`, and its
helper is present in frozen source. Post-case binaries are not claimed as
the loaded-image identities. File layout, failure handling and coverage limits
are maintained in [usage 7](JIT_EXECUTION.md#执行与证据).

Final source, commands, units, automatic evidence, outcome records and audit:
`/tmp/kdlock-evidence-capture.s37kBJ.tar.gz`, SHA256:

```text
ff2335beeeabe6c033c366500d8a239ba057d32525a46b867e1308773d27d0fc
```

The earlier freeze remains **one accepted case, one capture failure, one NOT
RUN**, not a retroactive success. At **23:06**, its **32 methods** pass; at
**23:08-23:09**, mode 2 passes with four returned bodies and four matching
hostcall exit/execute/resume cycles. The subsequent dual-frame script exits 0
after actual JIT and four ACKs, but the new collector rejects its legitimate
`writer/disassem/disassem.py` symlink. It records drained=true,
evidence_complete=false and accepted=false, then stops before context-mixed.
The correction records protocol links without following them; only the rejected
case and the previously unrun negative are then executed. Mode 2 is not repeated.
The original failure, recovered protocol/images and preparation are preserved in
`/tmp/kdlock-evidence-capture.7pjo9W.tar.gz`, SHA256:

```text
63b6c162bcf793b4ce58d93c94a4d25d267b148d7be5ecb0da14102aaec763c6
```

No baseline, full unit suite, admission audit or complete matrix is repeated.
This closes scoped capture, not historical external-control packaging, general
kernel reproducibility, immutable JIT identity or the remaining C1/C2/C5 work.

## Native B Peers With Live Frames

**2026-09-09 22:29:24-22:30:21 +08**: **3/3 existing `mutex-parallel` cases pass**
on **198 frozen runtime/test inputs**, all with `mutex_jit=1`. This extends the
two complex drain cases, not the suite size. No baseline, full matrix, full
unit suite or admission audit is repeated; production algorithms are unchanged.

| Case | Returned bodies / Owner ACKs | Additional evidence |
| --- | --- | --- |
| `parallel-drain-0` | 2 / 4 | Two actual B waiters; three failed trylocks; two own-owner native acquisitions/unlocks |
| `parallel-drain-1` | 2 / 4 | Same checks with the opposite frame/peer drain order |
| `parallel-node-pressure` | 1 / 2 | Existing real node fallback, injected task fallback and pre-body context refusal; no added B peers |

Both non-target peers reach their identified Linux B wait lists before
DRAINING or either original native frame resumes. The first peer acquires B
under its own native ownership and, while holding it, fails trylock on the
other frame's retained B. Only after this peer's real unlock and the first
original waiter's final ACK/done may the other frame resume. Each peer updates
its protected value exactly once; neither emits a kdlock frame or owner ACK.
Both orders join all eight original roles and both peers before unload.
Purpose, scheduling gates, sentinel values and limits are in
[usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame).

Each drain case retains the existing real 64-block exhaustion, three new
native queue records, four owner ACKs, writer-only EBUSY, terminal retirement
of all 64 entries and six native records after same-address source reuse.
Each case prepares two **607-byte** images; the pressure case executes only
one. All five returned body witnesses match those images and entry/lock pairs;
all five 256-byte mutex stack comparisons are equal. No kernel faults,
invariant failures or residual callers/modules occur.

The focused observer passes **25 methods** at **22:27 +08**; W=1 kdlock and
test-module builds pass with existing objtool/locale warnings. Pre/postflight
verifies the unchanged 18 source/interface files, configuration, nine existing
kernel build files and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
No VM restart or guest-kernel edit, build or install occurs. Final module hashes:

```text
kdlock_km.ko    900c167a7491e4b4c6a16437fe012bf3972337f4bf7dd1128cf3d1bbd3e2ddd6
klock_module.ko 81c4b78a8a17ffad7a3712ae4fdff515bf646abd72294d4149c0e36f993f0ab5
```

Commands, frozen source, unit/build output, images, per-peer queue/exit logs,
source/capacity protocols and the hash/ACK audit are in
`/tmp/kdlock-parallel-peers.wteGES.tar.gz`, SHA256:

```text
51ea856d5467ae1ebd5a56cde598d0beb8ea0e105b5f6b73e8dd1ad594324851
```

The live freeze's host/guest/unit/archive hashes match. This bounded composition
does not prove fairness, arbitrary cancellation/task exit, hook-reader lifetime
or concurrent image replacement. C1/C2/C5 remain open; older full-matrix results
are not rerun here.

Post-live formatting at **22:43 +08** reflows one `MODULE_PARM_DESC` in
`mutex_parallel_workload.c`; the other 197 inputs are unchanged. The incremental
guest test-module build passes; no module load or JIT/unit rerun follows.
Initial whole-byte comparison detects 44 changed source-line fields. ELF audit
identifies every field by its filename relocation and verifies the expected
one-line shift. After removing debug/build-ID data and normalizing only those
fields, all remaining bytes, including instructions and relocations, match.
At **22:48**, all 198 final host/guest input hashes match, the kernel baseline
is unchanged and callers/modules are idle. The new test-module SHA256 is
`3e2d74afca0c01373f6be1cf615860696c078116e2a9093d7b59028eb8f4de1d`.
The failed raw comparison and successful bounded audit are both preserved in
`/tmp/kdlock-parallel-format.SrvLkt.tar.gz`, SHA256
`328ddf3e38c636bd92546513ff890c8a4a1a83e66ead9f4ca23abe1604f25798`.
This is a separate format/build check, not a new live acceptance freeze.

## Real Spin Ticket Pressure

**2026-09-09 22:03:32-22:05:27 +08**: **2/2 affected complex cases pass** on
**197 frozen runtime/test inputs**, both loading `mutex_jit=1` but executing
the spin backend. No baseline, full matrix, full unit suite or admission audit
is repeated. `virtual-ticket-refusal` replaces `native-1-4` in routine scopes;
the simpler diagnostic remains explicitly selectable. Extended stays at 63
cases and excludes nine reviewed covered diagnostics.

| Case | Resource evidence | Returned bodies / Final owner ACKs | Records / State transitions |
| --- | --- | --- | --- |
| `virtual-ticket-refusal` | 31 real additional locks plus A fill the combiner's 32-ticket pool; B returns PENDING E2BIG before allocation | 1 / 1 | 12003 / 12011, zero failures |
| `virtual-node-refusal` | Existing injected node count; real B ticket allocation and subsequent cancellation | 1 / 1 | 12003 / 12011, zero failures |

Each case prepares six images and executes the matched **16401-byte** outer
image. The capacity case controls promotion only: both candidates' 31 real
owners/lock words/pins are checked before and after A; all 62 locks finish
released. The actual combiner retains them across the observed native frame
and final A ACK. Full `pt_regs`, CALL word, frame, node/context arrays and
combiner shadow snapshots match across the failed allocation. Original waiter
B queue/acquisition, exactly-once effects, pin balance and drain checks pass.
Flow and observation limits are maintained in [usage 6.3](JIT_EXECUTION.md#63-spin-虚拟请求取消与续跑).

The focused selector program passes **22 methods**, and W=1 kdlock/test-module
builds pass with existing objtool/locale warnings. SELFTEST snapshots do not
change the default allocation algorithm, wrapper ABI or physical owners.
Both cases restore default builds and drain callers/modules; no kernel faults
or invariant failures occur. Pre/postflight verifies the unchanged 18-file
source baseline, config, nine existing build files and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. No VM restart or guest-kernel edit,
build or install occurs. Final default module SHA256 values are:

```text
kdlock_km.ko    28197790c97d26715039ee8ff2cc3e0225f977c26fc3f91b36243aac757d0f48
klock_module.ko 0f322d8a3a70451994d9e92b79c7cf74ec2ebb399c9b0c374aa025df4cd7a9b6
```

Commands, frozen source, unit/build output, generated images, per-role native
logs, SELFTEST modules and hash/ACK audit are in
`/tmp/kdlock-spin-tickets.lSoRUC.tar.gz`, SHA256:

```text
097bff6d588326613778fb6720849dde191dbe712b6ea0ac1457c8cc0af59862
```

Host/guest/unit/live/archive input hashes match. This covers one real ticket
saturation schedule, not live gate-table saturation, arbitrary task exit,
full-register instruction coverage or general post-entry failure recovery.
C1/C2/C5 remain open; older full-matrix results are not rerun here.

## Code Pool With Live Frames

**2026-09-09 21:36:46-21:37:36 +08**: all three existing `mutex-parallel` cases
pass on **196 frozen runtime/test inputs**, each with `mutex_jit=1`. No baseline,
complete matrix, full unit suite or admission audit is repeated. Production
changes are diagnostic identity fields only; the new capacity workload extends
the two drain cases, leaving suite membership unchanged.

| Case | Returned JIT bodies | Native frames / Owner ACKs | Capacity and continuation evidence |
| --- | --- | --- | --- |
| `parallel-drain-0` | 2 | 2 / 4 | 64 unique blocks, 3 absent filler sites, 3 new native queue records, 64 retired entries, 6 post-reload native records |
| `parallel-drain-1` | 2 | 2 / 4 | Same checks, reverse old-frame drain order |
| `parallel-node-pressure` | 1 | 1 / 2 | Existing context refusal, four occupied CPU nodes, one native node fallback and one injected task-allocation fallback |

Both drain cases begin with two published images, stop the daemon, then promote
an independent mutex without compiling its code. While both real native frames
retain A/B, 64 distinct noinline CALL sites exercise ordinary root registration.
Loaded ELF mutex CALL relocations and module SHA256 identify every site. The
registry reaches exactly 64 distinct blocks; existing entries are unchanged,
new entries stay UNINIT and sites 61/62/63 remain absent. The final site then
serves three real clients queued behind a holder on CPU 8-11. One matched
`mutex JIT not ready` event identifies pre-wrapper refusal; each client completes
its record once under its own native mutex ownership, without another body/frame/ACK.

Four snapshots retain OPEN/modules=1/writers=0 and frames=0/2/2/2. The 67 fill/
queue records and 12000 preparation updates total 12067 exact updates, with no
record/owner failures. Both old frames subsequently complete their four ACKs;
the original writer-only EBUSY, source-pin unload refusal, terminal retirement
and same-address source reuse checks still pass. All 64 entries remain terminal
through reuse; the six replacement records are purely native. Cold sites are
not translated instructions, and two live frames do not prove simultaneous
execution of one code image or generic code reclamation.

Each case retains two 607-byte images; the shared-CPU case executes only one.
All five real mutex stack comparisons are equal; no changed/short-window exit
occurs. Fault scans, invariants, caller/module/node/task drains and source hashes
pass. Read-only pre/postflight verifies 18 source/interface files, configuration,
nine kernel build files and unchanged live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. No VM restart or guest-kernel edit,
build or install occurs. Final default module hashes are:

```text
kdlock_km.ko   7dba88a73023556caf87d7620b4cd56a5a94f1f0eff9d70a54e33e29e45ba4ed
klock_module.ko 23292378c223c3e944426e62518cff803be0c845cf863bb30d0282ac698085d8
```

The corrected observer's **21 methods** pass at **21:35:33 +08**. Earlier focused
component results are retained on their own freezes: **146 production entry
checks**, and **8437 production registry checks with seven detected mutants**.
The latter and W=1 module builds pass at **21:29** with existing objtool/locale
warnings. Only the observer and its unit program change after those builds;
unchanged component programs are not rerun or counted as new passes.

Final commands, source, unit output, images, four-phase capacity snapshots,
per-role logs, source protocols and audit are in
`/tmp/kdlock-code-pool.CvZVH8.tar.gz`, SHA256:

```text
fbcd1a17447528b096d4949c51cb1ef172e251154ae7d5d8795675172baf1b3b
```

Two earlier failures remain separate, not retroactively accepted:

- `/tmp/kdlock-code-pool.8Tx8Sr.tar.gz`, SHA256
  `8a5f822273c6d5a6a1ce48a4cbb5333d3f25c9d1625fb9a5db0dcb20a1599607`:
  two unit programs pass (146 entry checks and 20 observer methods), one fails
  compilation because the registry fixture lacks the shared CALL/capability
  headers. No module build/load or live run occurs on that freeze.
- `/tmp/kdlock-code-pool.nlKMp0.tar.gz`, SHA256
  `675b5b9122e5183035f7b016f25b013ba22a253e4cf3772918e4ee140a354da1`:
  corrected registry units/build pass, but the **21:31** first live case fails
  its final oracle after real capacity/queue/ACK/retirement work. The observer
  incorrectly counts replacement-source native arrivals as old JIT frames.
  The other two cases are NOT RUN. The final correction validates and isolates the
  replacement interval first and explicitly rejects hidden capacity events.

This closes the code-pool root-refusal combination, not all C1 resource exits
or C2/C5 lifetimes/context. Full GPRs, 511-slot saturation, arbitrary PENDING
combinations and post-entry replay are not established. Flow and scope are in
[usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame).

## Checked Two-Level Mutex

**2026-09-09 20:43:29-20:47:21 +08**: **10/10 affected complex live cases pass**
on **195 frozen runtime/test inputs**. All nine positives have returned body
witnesses matched to generated images; all mutex positives use `mutex_jit=1`.
The context refusal has no JIT body/image. No baseline, full matrix or full
unit suite is repeated. The existing `native-mutex-depth` case now exercises
two real CALL levels instead of an inlined local adapter; it is not another
case appended to the suite.

Guarded analysis uses the same validated device lease's 256-byte capability
only for recognized mutex controls. It first verifies and applies the decoded
eight-byte CALL push, then retains only post-write facts wholly inside every
possible post-CALL stack window. Unknown capability/addresses, out-of-window
facts, other controls and ordinary calls retain conservative clobbers. Alias
writes and analysis budgets are not reset; RET whitelists are unchanged.

| Case | JIT bodies | Equal / Changed windows | Native frames / Owner ACKs | Hostcall cycles |
| --- | --- | --- | --- | --- |
| `native-mutex-depth` | 5 | 21 / 0 | 5 / 26 | 0 |
| `mode-2` | 4 | 0 / 0 | 0 / 0 | 4 |
| `mode-7` | 2 | 0 / 0 | 0 / 0 | 0 |
| `mode-8` | 2 | 0 / 0 | 0 / 0 | 0 |
| `mode-4` | 1 | 2 / 0 | 0 / 0 | 0 |
| `mode-5` | 453 | 0 / 0 | 0 / 0 | 453 |
| `native-mutex-stack-change` | 1 | 0 / 1 | 1 / 2 | 0 |
| `registers-4-2` | 1 | 2 / 0 | 1 / 1 | 0 |
| `registers-4-3` | 1 | 1 / 0 | 1 / 2 | 0 |
| `context-mixed` (refusal) | 0 | 0 / 0 | 0 / 0 | 0 |

Two joined learning waves miss first to `kd_resume_depth_mutex`, then to
`kd_depth_source_enter`; each waiter finishes that episode natively once.
Publication produces three distinct images, **12824 -> 13088 -> 13539 bytes**.
The final wave executes the external helper's seven translated mutex controls
and its RET, then reaches three real B7 capacity exits inside the local helper.
The local helper's remaining suffix and RET complete natively, not in JIT.
Depth has **12025 exact records, zero failures**, with two learning ACKs plus
three sets of eight capacity ACKs. Source pins, loader references, callee tables
and terminal retirement are checked at all nine joined boundaries.

The stack-change/register cases each retain 12002 exact records, zero failures.
All native frames complete; hostcall exits/executions/resumes match, with no
failed/rejected/limit exits. No short-window handoff occurs. Body witnesses are
execution evidence, not complete instruction coverage or version isolation.

Focused analyzer units at **20:32:02-20:32:21 +08** pass six programs:
memory 51, guards 39, policy 92, text regions 29, body witness 8 and diagnostics
13 methods (**232 total**), plus the independent **25-case admission audit**.
Generated shared/private RET positives execute both CALL/RET levels through a
bounded userspace control bridge and verify RBX/RBP, records and final stack;
this bridge does not prove Linux mutex concurrency. Sensitive-pointer writes,
unknown aliases, window edges/alternatives and exhausted budgets remain negative
checks. That accepted freeze is separately archived in
`/tmp/kdlock-checked-facts.GzkN2r.tar.gz`, SHA256
`9b22c0d3969740163a10179a81dd611b9894c2d53eeb1fb9beb18f8a74b505cc`.

The subsequent real-helper increment changes only the test module, depth shell
driver, source oracle and its unit program. Its **10 oracle methods** pass at
**20:41:41 +08** before live execution. Analyzer/unit inputs are unchanged, so
the six programs and audit are not repeated or counted as fresh runs on this
later freeze. Optional test-module W=1 build and default-build restoration
pass with existing objtool/locale warnings; the final default module depends
only on `kdlock_km` and has SHA256
`ed6dd4bfa5169cc4947e419bc17bab6d59f1016a272848bd85c61e17b1efd9ab`.

Fault scans, invariants, caller/module/node/task drains and all 195 input hashes
pass. Read-only pre/postflight verifies 18 source/interface files, configuration,
nine kernel build files and unchanged live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. No VM restart or guest-kernel edit,
build or install occurs. Commands, frozen source, oracle/build output, all ten
live results, three depth images and protocol workspaces are in
`/tmp/kdlock-two-level.ILcF7n.tar.gz`, SHA256:

```text
1fb3c1d15ebfdd8f1cad68c01b932be03e207dd818c0ea91c210f14f6e4ad5af
```

The **20:27** preparation remains **4 unit programs pass / 2 fail**, with no
admission audit or live run. CALL IR recognition required normalization of a
full-slice memory address and resolution of its location-valued return token;
one alias assertion also incorrectly required WIDE instead of allowing the
retained sensitive candidate. This failed freeze is not retroactively accepted:
`/tmp/kdlock-checked-facts.mRI4N9.tar.gz`, SHA256
`065c40734526d3f36ddd8fdec0a844d495415a4477d64e505a027a7af585c63a`.

This closes the bounded Checked Mutex Stack steps 4/5, not broader C5 context,
alias or arbitrary concurrent-mutation safety. The two-word wrapper and existing
64B/24B packets, physical native owners and deferred flags/version limitations
remain unchanged. Execution flow and incremental selection are maintained in
[usage 5.3](JIT_EXECUTION.md#53-mutex-控制-call-的栈检查) and
[usage 7](JIT_EXECUTION.md#7-分层与增量回归).

## Runtime Capability Negotiation

**2026-09-09 19:51:32-19:54:00 +08**: **8/8 affected complex live cases pass**
on **195 frozen runtime/test inputs**. All seven positives have returned body
witnesses matched to generated images; all mutex positives use `mutex_jit=1`.
The context refusal remains a negative, with no JIT body/image. No baseline or
complete matrix is repeated.

The separate 16-byte `KD_JIT_CAPS` ioctl reports the fixed 256-byte local mutex
stack-check contract. Existing 64B/24B packets and the two-word wrapper ABI stay
unchanged. Each actual translation logs a 256-byte bound on its validated
inherited descriptor before text inspection. Neither invalid nor unavailable
capability warnings occur in these live translations. Both drain-order gates
also check the actual orphan writer's cached bound and a fresh query on the
same descriptor in DRAINING; retirement still refuses new writers/publication.
Readonly capability queries remain valid after terminal retirement. This probe
extends the existing lifecycle test, not the live case count.

| Case | JIT bodies | Equal / Changed windows | Native frames / Owner ACKs | Hostcall cycles |
| --- | --- | --- | --- | --- |
| `native-mutex-stack-change` | 1 | 0 / 1 | 1 / 2 | 0 |
| `mode-2` | 4 | 0 / 0 | 0 / 0 | 4 |
| `mode-5` | 439 | 0 / 0 | 0 / 0 | 439 |
| `native-mutex-depth` | 4 | 21 / 0 | 4 / 25 | 0 |
| `parallel-drain-0` | 2 | 2 / 0 | 2 / 4 | 0 |
| `parallel-drain-1` | 2 | 2 / 0 | 2 / 4 | 0 |
| `parallel-node-pressure` | 1 | 1 / 0 | 1 / 2 | 0 |
| `context-mixed` (refusal) | 0 | 0 / 0 | 0 / 0 | 0 |

Hostcall exits/executions/resumes match, with no rejected/failed/limit exits.
The real stack-change and depth cases retain 12002/12017 exact records, zero
failures; depth retains three real capacity exits. The parallel gates retain
their per-role records, owners, retirement/reuse and node/task-pressure checks.
No short-window handoff occurs. On this freeze the depth gate used an inlined
local adapter and a real external helper; it did not validate two CALL levels.

Focused guest units are recorded without merging freezes. The **19:47:54 +08**
preparation passes `test_source_lifetime.py` (**42796 production checks, 11
detected mutants**) and `test_text_regions.py` (**29 methods**, including
same-FD caching, old/invalid packets and I/O-failure closure), but fails to
compile the continuation fixture because its driver lacks the shared header
include path. That preparation remains **2 programs pass / 1 fail**, with no
module build/load or live run. Only `test_native_after_outer.py` changes next;
its corrected run at **19:50:11 +08** passes **2600 checks**, one program. The
other two programs' inputs are unchanged and are not rerun or recounted.

The kdlock W=1 build passes with existing objtool/locale warnings. Live scripts
restore normal builds; final kdlock module SHA256 is
`320fd8adcc8c65c342bdf117f963289d082de6c6fb351bf2eda8636f5f22b75c`.
The default test module depends only on kdlock. Fault scans, invariants,
caller/module/node/task drains and all 195 input hashes pass. Read-only
postflight verifies 18 source/interface files, configuration, nine kernel build
files and unchanged live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
No VM restart, guest-kernel build/install, full unit run or admission audit
occurs; admission and analyzer memory clobbers are unchanged.

Accepted source, commands, unit/build output, eight live cases and joined
translator/writer protocol workspaces are in
`/tmp/kdlock-jit-capability.9UgYwF.tar.gz`, SHA256:

```text
26f65946d8e14aaee4d268b114424b2acb2ef9d1e3f100b91c9e8ebe13b87dd6
```

The failed preparation is separately retained in
`/tmp/kdlock-jit-capability.eAPzl4.tar.gz`, SHA256
`e1071c90588f4e87f9c3630c66ece197a28d826c5eac3c3bf132d1c7a1174a6b`.
This closed TODO C5's capability-negotiation step only. Checked analyzer facts
and the actual two-level helper were still pending on this freeze; their later
bounded acceptance is recorded [above](#checked-two-level-mutex). No code-version
isolation, private-stack proof or broader concurrency safety is claimed.

## Real Mutex Stack Mutation

**2026-09-09 19:29:10-19:30:40 +08**: **5/5 affected complex live cases pass**
on **195 frozen runtime/test inputs**, all with `mutex_jit=1` and matched returned
JIT bodies/images. The corrected oracle's eight guest unit methods pass at
**19:28:13 +08**. Only the test module, shared driver, oracle and selection change;
kdlock runtime, translator and guest kernel are unchanged in this increment.

The new case observes the distinct physical A owner queued in B's Linux mutex
wait_list before B's native owner changes the live exposed word from
`0x123456789abcdef0` to `0x0fedcba987654321`. It lies at post-CALL RSP+8, inside
the checked window. `MUTEX_STACK_CHANGED` and native begin identify the actual
mutex CALL successor in the loaded module. The waiter reads the new value with
both locks still owned by the original combiner, then completes B/A ACKs and
the suffix once. The executed entry retains identical NORMAL/code/target fields;
other roles' newly registered entries remain cold UNINIT. No PENDING injection,
ordinary observer CALL miss, owner handoff, entry replay or snapshot restore
supplies this pass. Flow, command and boundaries are in
[usage 5.3](JIT_EXECUTION.md#53-mutex-控制-call-的栈检查).

| Case | JIT bodies | Equal / Changed windows | Native frames / Owner ACKs |
| --- | --- | --- | --- |
| `native-mutex-stack-change` | 1 | 0 / 1 | 1 / 2 |
| `mode-4` | 1 | 2 / 0 | 0 / 0 |
| `registers-4-2` | 1 | 2 / 0 | 1 / 1 |
| `registers-4-3` | 1 | 1 / 0 | 1 / 2 |
| `waiter-usr1` | 1 | 0 / 0 | 1 / 1 |

Each native case has 12002 exact records, zero failures; the new case has
12008 CS transitions across two states and 2003 balanced origin intervals.
All five images are 12824 bytes; body matching is execution evidence, not
complete instruction coverage. No short-window handoff occurs. Fault scans,
invariants, module/caller/node/task drains and source hashes pass. Postflight
verifies 18 source/interface files, configuration, nine kernel build files and
unchanged live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`. Final test-module
SHA256 is `53adebc73620e8ce156b2ca8581abe3740c7c38c0485d62a40dfd4dab5904d96`;
its only module dependency is `kdlock_km`. No baseline, full matrix, unrelated
unit programs, admission audit, VM restart or guest-kernel build/install occurs.

Accepted source, commands, hashes, five case outputs/images and four protocol
workspaces are in `/tmp/kdlock-mutex-stack-live.bcrv06.tar.gz`, SHA256:

```text
45c7b9848d5aff3358ed549b7e5fb9efe9e0df2fe4c354ff2a284215fa179ef6
```

The **19:25** preparation is retained as **failed**, not retroactively accepted:
actual JIT/change/ACK/records passed, but the oracle incorrectly required the
whole registry to contain one entry. The corrected check binds the executed
root and rejects any new entry that is not cold UNINIT. That preparation's
eight oracle and 22 selector methods, W=1 test-module build (existing objtool/
locale warnings), failed live output and source are archived separately in
`/tmp/kdlock-mutex-stack-live.xY6p5J.tar.gz`, SHA256
`c4b4c4e9940b1b2357978601651d80ccd056ebba1c040a4f5cd06bbfa3198248`.
The four following live cases were NOT RUN on that freeze.

This closed only the real shared-slot concurrency gate. Capability negotiation,
analyzer retention and the actual two-level helper are validated in their later
runs above. No arbitrary stack publication or general
concurrent-mutation safety is established by this one history.

## Mutex Control Stack Check

**2026-09-09 18:37:24-18:37:30 +08**: five focused guest unit programs pass.
**18:41:26-18:44:30 +08**: seven affected complex live cases pass on the same
**192 frozen runtime/test inputs**. Only kdlock's local mutex control/continuation
code and related fixtures change; the translator still clobbers memory facts.
This is a runtime prerequisite, not acceptance of the two-level learned helper.

Production-function tests cover each of the 256 checked bytes, all eight CALL
token bytes, the immediately following out-of-window byte, unreadable/short
windows, mismatched packets, native-phase rejection and retained-owner ledgers.
They report **2600 checks, zero failures**; the array/nofault/lock primitives
are documented substitutes, not proof of Linux concurrency. The other programs
pass 48 CALL phase/error combinations plus post-CALL bounds, 11 frame tests,
6355 production-capacity checks with five detected mutants, and 146 entry-scope
checks. Frame/context sizes remain 656/5264 bytes; the two-word ABI is unchanged.

| Live case | Returned JIT bodies | Equal stack windows | Additional evidence |
| --- | --- | --- | --- |
| mode 4 | 1 | 2 | Queued nested mutex, exact state and normal JIT completion |
| mode 5 | 419 | 0 | 419/419/419 hostcall exit/execute/resume cycles |
| registers 4 stage 2 | 1 | 2 | GPR/return-stack oracle, one native frame/one ACK, 12002 exact records |
| registers 4 stage 3 | 1 | 1 | GPR/return-stack oracle, one native frame/two ACKs, 12002 exact records |
| two-source learned depth | 4 | 21 | Three real capacity exits, four native frames/25 ACKs, 12017 exact records, source retirement |
| registers 8 stage 2 | 2 | 0 | Spin GPR/native continuation, one frame/one ACK, 12003 exact records |
| mutex early-A dependency | 1 | 8 | Existing OOO=3/dependency=2 oracle, one native frame/seven ACKs, 12002 exact records |

All mutex positives use `mutex_jit=1`. The 34 real comparisons are equal;
**no live changed-stack or short-window handoff occurred on that freeze**.
Mode 5's final unlock
does not resume JIT, and spin is outside this local mutex check. Changed-byte
native registration was then only a fixture result. The later
[real stack-mutation run](#real-mutex-stack-mutation) supplies its separate live
evidence. Capability negotiation and bounded analyzer retention are separately
validated in the later runs above.

The live selection reuses `mutex`, the two mutex register cases,
`native-mutex-depth`, `registers-8-2`, plus the existing direct command
`env KD_NATIVE_OOO=3 KD_NATIVE_OOO_DEPENDENCY=2 bash tests/test_10_native_resume.sh 4 3`.
No baseline, full matrix, full units or admission audit is repeated: translation
and admission do not change. Existing body/image matching, record/register,
capacity, source-pin, ownership and drain oracles are retained without weakening.

The kdlock W=1 build passes with existing objtool/locale warnings. Final normal
module SHA256 is `f97bdbc3cba6c8333df08cd14f4559a4a753c354d6d3ce5fe277d1af58d0f777`;
the optional source dependency is removed from the default test-module build.
All fault scans and drains pass. Read-only postflight at **18:50:34 +08** verifies
18 source/interface files, config, nine kernel build files and unchanged live
Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`. No VM restart or guest-kernel
build/install occurs. Source hashes match host, guest, unit/live freezes and the
archived source; build, command, body/image and five protocol directories are
preserved in `/tmp/kdlock-mutex-stack.MI8SJx.tar.gz`, SHA256:

```text
6970a8cb05e023ee786fb84fde9b5d93f27293d45961eda63c9360c794519eb1
```

## Covered Diagnostic Selection

**2026-09-10, postflight 15:43:09 +08**: the focused guest command
`make -C tests/unit run TESTS= PY_TESTS=test_regression.py` passes **47 methods**
in one program. The existing selection check now protects forced cancellation
separately from release races: only forced cancellation requires native B to
remain held through the final A ACK. No new test program or live case is added.
The catalog remains **64 extended cases**, excluding **eleven covered
diagnostics**. CLI previews retain exactly mode 4/5/2 for overlapping
mutex/hostcall selections; explicit diagnostics, mode deduplication and
failure-stop boundaries remain checked. Policy and execution flow have one home
in [usage 7](JIT_EXECUTION.md#7-分层与增量回归).

All **211 runtime/test input hashes** match host, frozen archive and postflight
guest. Only `tests/regression.py` comments and `test_regression.py` assertions
change from the preceding static-per-CPU freeze. Guest Linux 6.1.159 is idle
before/after. No module load, daemon, live workload, JIT, VM restart or kernel
build occurs; neither the full baseline nor historical live results are reverified.
Evidence: `/tmp/kdlock-test-selection.Ukis1c.tar.gz`, SHA256:

```text
e73c458a416b9ddfde29c78397297314ab4131e28b558829667afe253536e57a
```

Earlier selector-only checks remain historical. All archives below are under
`/tmp/`; none constitutes a current JIT run. The initial consolidation's actual
live checks remain in [Scoped Regression Organization](#scoped-regression-organization).

| Date (+08) | Passed Methods / Scope | Archive | SHA256 |
| --- | --- | --- | --- |
| 2026-09-09 19:11 | 22; real mode dispatcher with substituted live backends, 62-case preview | `kdlock-test-dedup.4y6SEx.tar.gz` | `03be0d118547cd00ebd4f1df8e182373471ddc8d0552d62992413bbf90888cb7` |
| 2026-09-09 18:20 | 16; eight reviewed replacements, extended 70 -> 62 | `kdlock-test-selection.snvU0F.tar.gz` | `251abc11f937801d2a0629440f9f5abfa9b3ff318be6451f85806e22dc9a4139` |
| 2026-09-09 15:58 | 14; coverage-policy review and CLI previews | `kdlock-test-scope-review.Ci7oUm.tar.gz` | `44093cf56a10bac8d461317942e77322157252e1afbc3ec2c84716fe464b0fc3` |
| 2026-09-09 13:25 | 14; selection/inventory policy | `kdlock-test-policy.jxKFqd.tar.gz` | `e6816bafa07eaa6df66fea6e4c8c0aaec5df9eedb2aa2e7881ae8d84835c207c` |

## Shared Return Partitions

**2026-09-09 17:44:20-17:47:01 +08**: **6/6 affected complex live cases**,
**34 guard + 92 policy methods** and the independent **25-case admission audit**
pass on **192 frozen runtime/test inputs**. No baseline or full matrix rerun.
Only the scoped translator analysis and its tests change; wrapper, native
owners, source controls, emitted RET tables and guest kernel are unchanged.

The new bounded guest-user image executes two nested CALLs with real saved
RBX/RBP prologues/epilogues through the same RET. It checks three exact record
writes, restored registers and the final virtual CALL stack. The complete
whitelist remains emitted. Full known, unknown-word and unknown-byte return-slot
rewrites still expose cross-caller context pointers to rejection; disconnected
text and partition/work exhaustion also remain refusals. These are generated
userspace-code and analysis tests, not kernel concurrency or flags proofs.

The live selection is `run_all.sh --suite core --case native-mutex-depth`:

| Case | Returned JIT bodies | Additional execution evidence |
| --- | --- | --- |
| mode 2 | 4 | 4/4/4 hostcall exit/execute/resume, no failures |
| mode 7 | 2 | Existing non-LIFO ownership and exact-state oracle passes |
| mode 8 | 2 | Existing multi-queue nested/complex-state oracle passes |
| mode 4 | 1 | Queued nested mutex and one JIT resume, 2006 balanced origin intervals |
| mode 5 | 395 | 395/395/395 hostcall cycles, multi-slot=3, 2186 balanced origin intervals |
| two-source learned depth | 4 | Three real capacity exits, 25 owner ACKs, 12017 exact records, zero failures |

All mutex positives use `mutex_jit=1`. Depth learning changes the image from
12132 to 12773 bytes; three later requests execute the helper's seven translated
locks and return before reaching B7 capacity. Both source pins survive execution
and retire after invalidation; loader/source reference checks remain intact.
Body witnesses are matched to entries/images, not interpreted as coverage of
every instruction or every generated entry. Final fault scans and drains pass.
Postflight at **17:49:37 +08** verifies the unchanged kernel Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`; default test-module dependency is
restored to `kdlock_km`. No VM restart or kernel build/install occurred.

The earlier minimal corpus separated two causes: shared-RET state joining and
control-call memory clobbers. This freeze resolved the former only; saved-value
reloads after controls still widened even with private RETs. Its local adapter
remained inlined. The later [checked two-level run](#checked-two-level-mutex)
validates bounded mutex fact retention and both real CALL levels. Execution
flow and bounds are in [usage 5.1](JIT_EXECUTION.md#51-学习后的直接-callee).

A failed freeze at **17:38:31-17:38:50 +08** stopped before audit/live execution:
the old unscoped budget diagnostic moved, and a CLI symbol fixture encountered
the newer device-session prerequisite first. The correction limits partition
budgets to scoped flow and supplies only the CLI fixture's successful lease;
real device-identity errors stay independently tested. The three unaffected
memory/text/body unit programs passed that earlier freeze and were not repeated
or counted as fresh passes in the final two-program run.

Closed archives contain commands, source hashes, images, protocols and audits:

- Accepted: `/tmp/kdlock-ret-partitions.MAjTlu.tar.gz`, SHA256
  `4f73844933cb727e9e7d53f382e3623111d017ea94220056f630108350088a7b`.
- Investigation and failed freeze: `/tmp/kdlock-shared-ret.fpFfSb.tar.gz`, SHA256
  `00ea54ecf1eccd83115c54b9895ee3ccbb5ff3a61a5de9e00cb5314ddfe80e6c`.

## Two Source Modules

**2026-09-09 16:46:06-16:47:16 +08**: **8 source-observation oracle methods**
and **2/2 affected live cases** pass on **192 frozen runtime/test inputs**.
Both live cases use `mutex_jit=1`; no baseline or complete matrix is repeated.
Production locks, source controls, translator, wrapper and guest kernel are
unchanged. This increment adds an optional test source module, upgrades the
existing depth gate and checks source/loader references at joined boundaries.

| Case | Returned JIT bodies | Native frames / owner ACKs | Exact records |
| --- | --- | --- | --- |
| `native-mutex-depth` | 4 | 4 / 25 | 12017, zero failures |
| `native-4-4` | 2 | 2 / 3 | 12009, zero failures |

The first depth wave has one ordinary miss to `kd_depth_source_enter`; the
original waiter completes its native suffix. After callers join, the daemon
learns the second module and publishes a changed image, **12132 -> 12773 bytes**,
then exits. Three later JIT requests execute its seven child-lock acquisitions,
return to translated caller stores and reach real `-E2BIG` before B7. Each
retains seven child locks plus A at the physical combiner and completes eight
owner ACKs. The depth counters are capacity=3/callee=1/native=12; generated
body, retained-owner, staged CALL packet and per-record checks all remain in
force. This is execution evidence, not just two source addresses in a table.

Root and helper identity is checked against loaded ELF symbols/text ranges and
captured .ko hashes. Before the miss, source modules=1 and helper refcnt=1 from
its native importer. The miss makes modules=2/helper refcnt=2; repeated reads,
publication and execution retain those two pins without duplicate references.
With frames/writers drained, normal source unload is refused. RETIRE makes the
old entry NATIVE_ONLY and modules=0, dropping the main source refcnt to 0 and
helper refcnt to 1. Unloading its importer removes that last loader reference;
the helper then normally unloads, with the old provider registry still terminal.
All intermediate state/refcnt/holder observations are archived separately.

Default test-module dependency is restored to `kdlock_km` only before the
second case. Both cases drain, fault scans are clean, and final identity/idle
verification at **16:49:50 +08** retains Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`, without VM restart or kernel edits.
Optional/default test-module W=1 builds pass with existing objtool/locale
warnings. Host, guest and archived inputs match. Flow and limitations are in
[usage 5.1](JIT_EXECUTION.md#5-入口条件与嵌套续点).

The earlier two-level CALL arrangement failed admission twice, not execution:
**16:18** with record-pointer arguments and **16:25** with a lock-pointer-only
helper. Both learned targets acquired pins, but register addresses widened at
the caller continuation. The later minimal reproduction above separates shared
RET joining from control-call spill clobbers. Final capacity waves and the
next live case were NOT RUN. The first preparation's 8 oracle/15 selector
methods passed; unchanged selection checks were not rerun for each experiment.
The fixture accepted on this freeze inlined only its local adapter, retaining
the cross-module CALL/RET, eight-lock capacity and all owner/record assertions.
It did not fix multi-depth shared-RET precision, alter mitigations or weaken
admission; the later partition/checked-stack increments above address the bounded two-level
case. Two live dependencies still do not prove 64-module
saturation, arbitrary object lifetimes or generic hook-reader hot unload.

Closed archives include commands, source, module binaries, images, protocols,
diagnostics, hashes and the accepted-run audit:

- Accepted: `/tmp/kdlock-multi-source.jA600j.tar.gz`, SHA256
  `c6f9ea4a9b8b71b801057fdf5e7587f6ccc45a629048a8e2dee53f0370900303`.
- First rejection: `/tmp/kdlock-multi-source.XjVda3.tar.gz`, SHA256
  `075cbcba82b22ad996f81cef2cd5eeb5a1d535bf62a947cd73b9519ab67b7d42`.
- Second rejection: `/tmp/kdlock-multi-source.Btbfx8.tar.gz`, SHA256
  `d9d11919c0a41d510acef867341795107ed01f316f93e0b1628e39ee2edcb8b4`.

## Writer Drain And Source Reuse

**2026-09-09 15:31:13-15:32:09 +08**: test-workload W=1 build, **16 parallel
oracle methods** and **3/3 affected complex gates** pass. New mutations reject
changed code/lock identity, nonterminal registry, missing markers, insufficient
native contention, repeated/incomplete records, extra JIT/ACKs and lost original
ACKs. They are evidence-parser tests, not fabricated live frames. Production
lock/source algorithms and guest kernel are unchanged in this increment.

Both `parallel-drain-0/1` retain two returned JIT bodies, two overlapping native
frames, four matched owner ACKs, 24008 original transitions and balanced 4006
origin intervals. The compiler-child probe uses real daemon fork/exec and Python
device-session validation, with a substituted script rather than code generation:

- Parent exits while the child retains the one writer description. With both
  frames live, RETIRE returns EBUSY at modules=1/frames=2/writers=1.
- Child reads 16 bytes of real pinned callee text in DRAINING; header-only
  publication returns ESHUTDOWN. New writer opens also stay refused.
- After both native suffixes and all workload callers finish, writer=1 alone
  still yields EBUSY with frames=0. Final child close permits retirement;
  source unload is refused until pins are released and old entries invalidated.
- Without unloading kdlock or changing its retired registry, the test normally
  reloads the same source module. Both old outer-lock return RIPs are checked
  against ELF `mutex_lock` CALL relocations; module SHA256 and actual runtime
  function/lock addresses match across reload, not just corresponding symbols
  at a different address. All three retired entries retain their old keys,
  code addresses, TGIDs and NATIVE_ONLY status.
- The identical eight roles then contend on the native mutexes without another
  warmup. Both Linux wait lists reach three waiters. Six fresh records complete
  exactly once; each lane has sequence=3/digest=486 and unlocked A/B. No JIT
  body, native-frame registration or kdlock unlock ACK occurs in this interval.

`parallel-node-pressure` still has one JIT/native frame, two ACKs, real four-node
exhaustion plus a separate injected task-allocation failure, eight records and
24010 transitions. It does not run the reload phase or close admission before
its extra requests. Original and reloaded records are independently validated;
the original provider counters and JIT assertions are not replaced by native
success. The reused module SHA256 is
`69311cdaf42c24db41e75a4d3dc3bde1039ea8d0ea92ed2339489690694fcab3`.

All **188 runtime/test inputs** match host, frozen guest and archived source.
Final idle/kernel-identity observation is **15:34:54 +08**, with unchanged Build
ID `6f9f2e9fec382e97f620553793aa90b527a30af5`, no VM restart and clean fault
scans. Existing objtool/locale warnings remain. Baseline, other modes, full unit
inventory and full matrix were not repeated for these test-specific changes.
This is one source module, a terminally retired session and controlled callers;
it does not establish the later two-module gate, arbitrary object free or generic
hook-reader hot unload. Usage and flow stay in [6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame).

Archive includes exact commands, build/unit logs, all source/role/registry/ELF
identity evidence, images, child records and closed-evidence audit:
`/tmp/kdlock-source-reuse.I01mAY.tar.gz`, SHA256
`28306f3afa5e00e2af0fd76daa4f50b4bd45456dd74c6821e2bf77a46aff1681`.

The immediately preceding writer-only increment, **15:14:24-15:15:14 +08**,
passed the same three complex gates and then-12 oracle methods without reloading
source. It has its own 188-input freeze and is not three additional passes on
the current test version: `/tmp/kdlock-orphan-retire.q6SBNv.tar.gz`, SHA256
`06ad1bd3ca9e044b36058c331de9d405f3bfc2bb25d8d9aa2eb9b9d7d475a8d5`.

## Source Pins And Retirement

**2026-09-09 14:48:14-14:51:49 +08**: ten affected complex cases pass, with
`mutex_jit=1` for all mutex positives. No baseline, single-lock mode 0/3 or
complete matrix rerun. All **186 runtime/test inputs** match host, frozen guest
and archived source. The terminal controls extend the existing two-frame test;
they do not add a duplicate module-load smoke or replace its owner/ACK oracle.

| Selected case | Returned JIT bodies | Additional observations |
| --- | --- | --- |
| parallel-drain-0 / parallel-drain-1 | 2 each | Two actual native frames, four owner ACKs, 24008 exact transitions and 4006 balanced origin intervals per order |
| parallel-node-pressure | 1 | One retained frame, real four-node exhaustion plus separate task-allocation refusal; 4009 balanced origin intervals |
| mode 2 | 4 | Four executed/resumed hostcalls; 1256-byte image |
| mode 4 | 1 | Queued nested B and JIT resume; 12069-byte image |
| mode 5 | 412 | 412 executed/resumed hostcalls; multi-slot 3; 1257-byte image |
| native-mutex-depth | 4 | Root/learned retranslation, four native completions and 25 owner ACKs; final image 12751 bytes |
| native-1-4 | 2 | Spin native continuation, two completions and three owner ACKs |
| remote-multi-b | 8 | Eight-layer cross-NUMA multi-request continuation; existing physical/virtual node and deferred-request oracles pass |
| context-mixed | 0 | Native-only, no generated image/body; 2128 balanced origin intervals |

Both non-shared parallel orders observe modules=1/frames=2/writers=0 with two
real native callee arrivals. RETIRE returns EBUSY and changes only OPEN to
DRAINING; new writer opens are refused. Both original waiters then finish their
suffixes and four task/lock-matched owner ACKs. After every worker and translator
has exited, the source module still refuses ordinary unload. Successful RETIRE
invalidates all three used registry entries, releases its one source pin and
reports RETIRED with zero modules/frames/writers. Write opens stay refused.
The archived log order also places busy retirement between both arrivals and
either native resume; aggregate counters alone are not used as overlap proof.
Every selected case ends with successful retirement, clean fault scans and
drained modules/workers. The shared-CPU pressure branch does not close admission
before its extra requests, preserving independent resource-refusal coverage.

Guest units were run by affected scope, not repeated wholesale:

- **14:40:08-14:40:41 +08**: W=1 out-of-tree builds and daemon build succeed;
  seven selected programs pass. Two new fixtures fail: a mutation's whitespace
  anchor no longer matches after formatting, and the ordinary-call success
  assertion expects RUN_ERROR instead of RUN_NATIVE. No live tests in this
  preparation. It remains a failed 7/9 batch, not a nine-program pass.
- **14:44:29-14:44:32 +08**: only those two corrected programs rerun and pass.
  Production source/device/retire logic passes **42733 assertions and all nine
  assertion-detected mutants**; entry-scope passes **146 checks**. The seven
  earlier successes remain earlier evidence. They include registry 8437 checks,
  frame capacity, spin producer/routing, daemon transport, 25 text/device methods
  and 14 test-selection methods. Kernel primitives/module lookup are explicit
  substitutes in source units, not a live 64-module saturation test.

Final W=1 builds and idle/baseline check complete at **14:55:55 +08**. Existing
objtool/locale warnings remain; no guest-kernel change/build/install, VM restart
or baseline change. Live Build ID remains
`6f9f2e9fec382e97f620553793aa90b527a30af5`. This bounds residency/retirement for
the tested session, not generic hook-reader hot unload, dynamic object lifetime
or immutable executable versions. At that freeze, multiple source dependencies,
source-RIP reuse and orphan-writer retirement remained follow-ups. The writer
and reuse increments above add their own evidence; remaining work is tracked in
[TODO C2](TODO.md#c2-one-protocol-per-physical-lock).

Failed preparation archive: `/tmp/kdlock-source-retire.nGIZPl.tar.gz`, SHA256
`af89f53e41e24742904494f045287576cf7f4fcd262789022b539d0ca0a51543`.
Corrected units, exact live selection/source/images, source-state and protocol
observations, final builds and closed-evidence audit:
`/tmp/kdlock-source-retire.FelJoL.tar.gz`, SHA256
`fdcecc24d3a78b1c873741c392c3003fdcc9b742b426ce0ef526ff228837f228`.

## Device Session Binding

**2026-09-09 13:40:40-13:40:45 +08**: guest daemon builds with
`-O2 -Wall -Wextra -Werror`; three selected unit programs pass. The production
daemon fixture checks 18 real compiler child invocations, descriptor inheritance,
three exact payload chunks and terminal status, header-only rejection, closed-FD
errors and workspace preservation when the device cannot open. Its transport is
a regular-file substitute, not a module-reference test. The text program passes
**22 methods** (nine new device-session checks and 13 existing CFG/read cases);
the diagnostics program passes **13 methods**. No full unit sweep is run.

**13:45:47-13:47:21 +08**: the real device probe and five selected live cases pass.
With only kdlock loaded and no source workload, the normal daemon retains the
device provider. A separate driver uses production `compile_entry()` to launch
a Python lease holder; that child does not read kernel text or generate JIT.
Normal `rmmod kdlock_km` is refused at all three observations: daemon alive,
parent plus translator alive, and translator alive after parent exit. Each
observes refcount 2 on this kernel. After releasing and observing the child exit
via pidfd, the count reaches zero and normal unload succeeds. There is no forced
unload, live source-module replacement or generic hook-reader safety claim.

| Selected Case | Returned JIT Bodies | Additional Evidence |
| --- | --- | --- |
| mode 2 | 4 | Four hostcall exits/executions/resumes; 1256-byte image |
| mode 4 | 1 | Contended B acquired through the queue and resumed JIT; origin 2006/2006 |
| mode 5 | 406 | 406 hostcall exits/executions/resumes; same-CPU multi-slot 3; origin 2175/2175 |
| learned mutex depth | 4 | Root translation, initial miss and learned-callee retranslation; two inherited sessions; image 12069 -> 12751 bytes; four native frames, 25 owner ACKs, 12017 exact transitions |
| mixed-backend refusal | 0 | No JIT image/body; native-only publication and 12257 exact transitions |

All mutex positives use `mutex_jit=1`. Each case's daemon log records the inherited
device session; learned depth records both translations. The existing body,
hostcall, ownership and workload oracles remain required, not replaced by the
descriptor observation. **180 runtime/test inputs** match host, frozen guest and
archive. Kernel source/config/build/running identity remains Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`; fault scans and module/caller/frame/node
drains pass. No guest-kernel changes, VM restart, baseline or full-matrix rerun.

That increment completed the device-session prerequisite, not source pinning or
terminal retirement. Source modules, lock allocations and hook readers retained
the documented lifetime limitations. Execution flow and remaining stages are in
[daemon usage](../daemon/README.md#device-session) and [TODO C2](TODO.md#c2-one-protocol-per-physical-lock).
Archive contains commands, fixture source, unit logs, provider observations,
per-case images, daemon/protocol evidence and the hash audit:
`/tmp/kdlock-device-session.taaat6.tar.gz`, SHA256:

```text
1d63fcd3f0fbb3a306758a4222b52074c1b3759d79c93a4a29a4f344853c5527
```

## Combined Task And Node Pressure

**2026-09-09 12:47:05-12:48:33 +08**, `/tmp/kdlock-task-pressure.fgpZs8/`:
five explicitly selected complex cases pass with `mutex_jit=1`. The existing
node-pressure case now also exercises an independent task-allocation refusal
while the older JIT/native frame remains live. Production changes only add the
task-refusal diagnostic in `__kd_mutex_lock`; ownership/routing/ACK logic is
unchanged. No new basic script or catalog entry is added. Flow, ten roles and
injection boundaries are centralized in [usage 6.7](JIT_EXECUTION.md#67-同-cpu-的-mutex-jit-拒绝).

| Case | Returned JIT bodies | Additional observations |
| --- | --- | --- |
| `parallel-node-pressure` | 1 | 1 native frame, 2 ACKs, one each context/node/task refusal; 4009 balanced origin intervals |
| `parallel-drain-0` | 2 | overlapping frames, 4 ACKs, 4006 balanced intervals |
| `parallel-drain-1` | 2 | opposite completion order, 4 ACKs, 4006 balanced intervals |
| `mode-4` | 1 | queued B/JIT continuation; 12008 transitions, 2006 balanced intervals |
| `mode-5` | 403 | 403/403/403 hostcalls; 12582 transitions, 2178 balanced intervals |

In the actual combined schedule, lane 0 reaches its native callee, role 5
fails reservation with real `slots=f`, then role 6 hits the armed task-allocation
failure before joining A1's queue. Role 6 completes under its own A1/B1 owner
before lane 1's context refusal and native completion. Role 5 finishes later,
still before lane 0 resumes and receives both retained-owner ACKs. Its old task
record is not removed by either new request's failure. Both distinct extra
records have exact stores; the total is **eight records, 24010 transitions**,
lane 1 digest `e4e9136d4ef4125`, claimed=111 and pressure_done=3 (two bits).
Both 607-byte images remain unchanged; only lane 0 has a body/CALL_MISS and
lane 1 remains NORMAL. Task allocation failure is injected, not evidence of
real memory exhaustion; no renamed waiter, arbitrary task exit or RCU reader
is added to this case.

Two focused unit programs pass: 12 parallel-oracle methods and the production
mutex-resource fixture's 15849 checks/eight assertion-detected mutants. All
**179 runtime/test inputs** match frozen guest and archived host source.
Postflight `W=1` builds finish at **12:56:12 +08**, retaining the tested default
modules' `.text`; existing objtool/locale warnings remain. Kernel identity is
still Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`. Fault scans/invariants
are clean and all frames, task records, nodes, callers and modules drain.
No guest-kernel change or VM restart. Baseline, full units/admission, spin,
register/RCU gates and the historical full matrix are not repeated.

Archive includes commands, source, per-case images, role/publication/protocol
records, diagnostics, unit/build logs and independent hash/count audits:
`/tmp/kdlock-task-pressure.fgpZs8.tar.gz`, SHA256:

```text
a31a89ff231b1f40f49931c6c880227c4ccbfcf5a100af3cf038a0eb9f90797e
```

Failed preparation **12:44:21-12:44:25 +08** retains status 2: the 12 oracle
methods pass, but the resource fixture lacks substitutes for the new logging
macro/CPU query and fails compilation. No live case/module is started. The
correction adds type-checked diagnostic substitutes, not weaker assertions;
the successful run above is an independent freeze. Failed source/log/command
archive `/tmp/kdlock-task-pressure.m8J28C.tar.gz`, SHA256:

```text
22ffff82942e05507a7c88359a432d0e133f353ae4c9ea2dfabf7201ad8bbd74
```

## Bounded Return Graph

**2026-09-09 12:02:43-12:02:45 +08**: the pre-change return builder fails on
1200 actual decoded callee branches with `RecursionError`. Of three selected
methods, the multi-site/shared-tail/redirected-return generated-code method and
cross-caller sensitive-pointer refusal already pass. This is a reproduced
graph-construction defect, not a reproduced context-policy bypass. The failed
log, status 1 and then-current source remain in the archive.

**12:10:38-12:13:16 +08**, `/tmp/kdlock-call-scope.TttQDI/`: the corrected
callee-grouped iterative builder and explicit failure handling pass five
focused unit programs, the independent 25-case admission audit and six complex
live cases. No baseline, full-unit, full-matrix or unrelated pressure sweep is
repeated. Commands are captured in `verify.sh`; the selected live command is
`run_all.sh --case native-mutex-depth --suite core --timeout 180` with recovery
confirmed. Selection orders suite cases before the explicit depth case.

| Case | Returned JIT bodies | Other checked observations |
| --- | --- | --- |
| `mode-2` | 4 | 4/4/4 hostcall exits/executions/resumes; 12009 transitions |
| `mode-7` | 2 | A-before-B unlock; 12009 transitions |
| `mode-8` | 2 | nested remote path; 12014 transitions over two states |
| `mode-4` | 1 | mutex_jit=1, queued B and JIT continuation; 12008 transitions |
| `mode-5` | 446 | mutex_jit=1, 446/446/446 hostcalls; 12582 transitions |
| `native-mutex-depth` | 4 | mutex_jit=1, 4 native frames, 25 matched owner ACKs; 12017 records |

Depth first has a real helper miss with only A retained. After drain/learning,
the image changes from 12069 to 12751 bytes. Three later JIT invocations reach
real `-E2BIG` before acquiring B7, each retaining A+B0-B6 (`held=remaining=8`).
Their original/staged CALL packets match and all children/records are valid.
`capacity=3 callee=1 native=12`, with 2012/2012 original-mutex intervals. This
proves translated helper execution through nested lock calls, not execution of
that helper's RET, since each request completes its suffix natively.

The five unit programs are `test_context_guards.py` (30 methods),
`test_context_policy.py` (92), `test_context_memory.py` (48),
`test_text_regions.py` (13) and `test_jit_body_witness.py` (8): 191 methods total.
Six added methods are in the existing guard program, not a new basic suite.
Three short multi-site/shared-tail/return-slot variants execute actual wrapper
and generated RET instructions in guest userspace, with exact record values
`[2,17,42]`, `[2,17,42]`, `[1,0,42]`. The 1200-branch corpus only checks table
construction. Unsafe context-pointer code is never executed. The independent
audit remains concrete-input IR/assembly evidence with mocked text/build, not
native execution or a complete alias proof. Flow and budget limits are in
[usage 5.1](JIT_EXECUTION.md#51-学习后的直接-callee).

All **179 runtime/test inputs** match frozen guest and archived host source.
Returned body entries/locks match retained artifacts; counts and partial-image
histories are not immutable-generation proofs. Pre/post kernel identity remains
Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`. Fault scans and execution
invariants are clean; native frames, tasks, nodes, callers and modules drain.
Existing build/decoder warnings remain. No guest-kernel change or VM restart.
Archive contains commands, before/after source, units/audit, per-case artifacts,
daemon logs, depth packets/records and independent hash/count checks:
`/tmp/kdlock-call-scope.TttQDI.tar.gz`, SHA256:

```text
d3feb18da767524d92bb6e42ae25590e7f0bb1393efc8a65d1c51385280bcf2a
```

## Source And Hook Lifetime Review

**2026-09-09 11:45:00-11:45:03 +08**,
`/tmp/kdlock-lifetime-review.A1pUx4/`: inspect current source and actual guest
interfaces without loading modules, rebuilding, running tests or modifying
the guest kernel. Nine inspected project files match host/guest SHA256.
The baseline verifier still matches 18 source/interface files, config, nine
build files and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
Additional `kernel/module/main.c` and `include/linux/module.h` are separately
captured and hashed, not silently added to the original baseline manifest.

The audit verifies four plain lock dispatch sites and the `exc_int3` predicate
reader, export availability, source module exit-before-GOING notification,
`klock_module -> kdlock_km` dependency and kdlock's nonlocal continuation paths.
These establish missing lifetime capabilities, not a reproduced use-after-free
or a passing unload race. Findings, implementation boundaries and the reason
not to add a blind source-module pin are centralized in
[DESIGN 3.1](DESIGN.md#31-source-lock-and-hook-lifetimes). Source pinning and
metadata retirement were unimplemented at that review; the later bounded
implementation is recorded above. Generic provider hot unload remains open.

QEMU/SSH remain healthy with no restart; kdlock/test modules are absent.
That increment changes documentation only, so it does not repeat the
accepted baseline/JIT cases. Archive contains commands, source hashes,
inspected project/kernel source and guest output:
`/tmp/kdlock-lifetime-review.A1pUx4.tar.gz`, SHA256:

```text
24a74bf6464281f5e70317f7877b2e0dec6e775f0f821ebc8dd677b391e18ab1
```

## Real Mutex Node Pressure

**2026-09-09 11:28:26-11:29:29 +08**, `/tmp/kdlock-node-pressure.oqh6E1/`:
three selected complex cases pass with `mutex_jit=1`. This increment extends
`test_23` and its oracle, with only an added production no-node diagnostic.
Daily scopes replace the simpler same-CPU case with the combined pressure
case; no baseline, mode 4/5, full unit/admission or extended sweep is repeated.
Flow and limits are maintained in [usage 6.7](JIT_EXECUTION.md#67-同-cpu-的-mutex-jit-拒绝).

| Selected case | Returned JIT bodies | Native frames / owner ACKs | Additional observation |
| --- | --- | --- | --- |
| `parallel-node-pressure` | 1 | 1 / 2 | slots=f, node_overflow=1, context_busy=1, multi_slot=3; 4008/4008 origin intervals |
| `parallel-drain-0` | 2 | 2 / 4 | both frames overlap; 4006/4006 origin intervals |
| `parallel-drain-1` | 2 | 2 / 4 | opposite completion order; 4006/4006 origin intervals |

Each case has two published 607-byte images that remain unchanged. In the
pressure case, lane 0 reaches its real native callee before the extra request
fails reservation on CPU 1 with all four slots occupied. The extra request
then acquires original A1/B1 on its own stack and completes once, before the
second combiner's context refusal in this actual schedule. Lane 1's waiter
also completes natively before lane 0 resumes with its retained A0/B0 owners.
Only lane 0's entry has a body and becomes CALL_MISS; lane 1 stays NORMAL.
The seven contention records and 24009 protected transitions are exact; lane
1's extra transition yields digest `ff2dd9cd026465f`. No capacity/context
injection, constructed frame or test-owned task reference is used. This is
one live native frame under real node pressure, not two overlapping frames
or a fairness proof.

Three targeted unit programs pass: 11 parallel-oracle methods, production
mutex resources (15849 checks and eight assertion-detected mutants), and 13
runner methods. Default module/test-module W=1 builds pass with existing
objtool/locale warnings. All **179 runner-manifest inputs** match host source.
Kernel source/config/build/live identity remains verified Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. Fault scans are empty, all callers
and modules drain, and no guest-kernel modification or VM restart occurs.

Archive `/tmp/kdlock-node-pressure.oqh6E1.tar.gz` contains frozen source,
commands, unit/build logs, returned-body artifacts, per-case acceptance/drain,
role placement/status, publication and protocol records. SHA256:

```text
983ba28cd901674f0711721ea5b074e88300b1abf544f3bc8456b480f9f31a1b
```

## Same-CPU Mutex Refusal

Earlier scoped freeze, **2026-09-09 10:55:39-10:57:19 +08**,
`/tmp/kdlock-shared-context.opby6X/`: five cases pass with `mutex_jit=1`.
`parallel-shared-cpu` has one body/frame, two ACKs, one context refusal and
4007 balanced origin intervals. Both original drain orders have two bodies,
two overlapping frames and four ACKs. Mode 4 has one completed JIT body;
mode 5 has 459 bodies and 459/459/459 hostcall exits/executions/resumes.
The then-four focused unit programs pass (11 frame tests, eight oracle methods,
15849 resource checks/eight mutants, 13 runner methods). All 179 frozen inputs
match, W=1 builds pass with existing warnings, the kernel Build ID is unchanged,
and fault scans/drains are clean without a VM restart. This is historical
evidence for the simpler placement, not a new run of the pressure extension.
Full commands/source/logs/artifacts are in `/tmp/kdlock-shared-context.opby6X.tar.gz`:

```text
fbe2f78e53d1a0878032833ccae6c5056e7cc1b617b63fe2d1146f67e70bf66b
```

## Scoped Regression Organization

The subsequent test-only increment removes three duplicated smoke scripts,
merges pipeline diagnostics, and adds explicit scope/case selection with
deduplication, guest/recovery guards and fail-stop boundaries. Selection rules,
coverage and execution flow are maintained in
[usage 7](JIT_EXECUTION.md#7-分层与增量回归). The then-68-case `extended` catalog is
not run for that increment. No production or guest-kernel changes were needed.

- **10:18 +08**, `/tmp/kdlock-test-selection.Wfd294/`: 12 runner unit methods
  and five parallel-oracle methods pass. The merged pipeline then fails its
  inherited instantaneous upload-log check; artifacts preceded publication.
  Later live cases are NOT RUN, with no JIT body, kernel fault or leftover
  module/caller. The correction reuses `wait_ready(..., lock_kind=1)` for the
  exact RIP/TGID, rather than relaxing acceptance or adding an arbitrary sleep.
- **10:23:58-10:24:35 +08**, `/tmp/kdlock-test-selection.cxh5ig/`: corrected
  pipeline and both parallel drain orders pass, three selected cases only.
  A duplicate `parallel-drain-0` argument runs once. Pipeline has no JIT body;
  each parallel case has two 607-byte images, two actual JIT bodies, two
  overlapping native frames, four owner ACKs and balanced 4006/4006 ownership.
- **10:30:42-10:30:58 +08**, `/tmp/kdlock-test-selection.gzIf5y/`: final runner
  excludes generated Kbuild `*.mod.c` from source hashes. All **13 runner unit
  methods** and one selected `parallel-drain-1` JIT case pass; pipeline and the
  other order are not repeated. Its oracle reports two JIT bodies, two live
  native frames, four ACKs, six exact records and 24008 transitions. All **179
  entries of this runner's input manifest** match the final host files; this
  filtered manifest is not the earlier matrix's 183-input manifest. Captured
  source, images, publication/role/protocol evidence and logs are archived.

Final guest identity remains Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`
(18 source/interface files, config and nine build files verified). Modules and
callers drain, fault scans are empty, no VM restart occurs. Ruff checks and
format checks for 75 Python files, changed-shell ShellCheck, documentation links
and `git diff --check` pass. These scoped results do not claim all 41 currently
registered unit programs or the historical complete matrix were rerun.

Archives are the three directories above with `.tar.gz` appended; SHA256 in
the same order:

```text
7f0bde2ab8387ce3a4a33ea1577f9948cb5f067be348b0e326e296a63084a136
fa13c82503fbc451aab82187a47c01782c2eb46ea80a5dd9dc08c0e542922c66
9d5b82d940ac937391e945f6d6f763c92ffa6b1c2859de5e17ab2be2a4b2b957
```

Later selection-only results and their separate evidence are consolidated in
[Covered Diagnostic Selection](#covered-diagnostic-selection), not added to
the above live acceptance.

## Parallel Native Frames

The increment against `480a12b` adds an opt-in two-queue mutex workload,
post-unlock/owner assertions, a structured log oracle and five unit methods
covering both orders and corrupted/missing/serial-only evidence. It changes
the test module and tests, not the production executor, wrapper, translator or
guest kernel. Flow and parameters are maintained in
[usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame).

Accepted freeze: `/tmp/kdlock-parallel-frames.ThpcFS/`, **183 runtime/test
inputs**. Focused cases run **2026-09-09 03:30:21-03:30:54 +08**, 2/2 pass.
Each has two distinct 607-byte images, two returned JIT body witnesses, two
overlapping real native frames and four task/lock-matched owner ACKs. Both
waiters arrive before either suffix resumes; the first finishes both ACKs before
the second rechecks its retained A/B owner and record. Each lane has 12004
protected executions and digest `6554ef715ba4103a`; all six contention records
finish exactly once. Native/task/node counts drain, with 4006/4006 origin owner
intervals, no allocation failures and no kernel faults. Zero all-JIT completion
counts are expected here because both translated requests continue natively.

Both entries are observed NORMAL using their real registering TGID before
arming, and CALL_MISS to `kd_parallel_native` afterward. The daemon is stopped
and image hashes stay fixed; this does not test concurrent replacement.
No test-owned task reference or constructed frame extends the production
lifetime. This is not the RCU-reader probe, an arbitrary task-exit test, or a
replacement for the eight full GPR/return-stack gates.

The complete matrix runs **2026-09-09 03:32:21-03:56:40 +08**, 67/67 pass:
51 actual-JIT positives, 12 context refusals, two native controls and two JIT=0
kernel protocol probes. Both parallel drain orders pass again with the same
per-case counts above. Main modes 0-8 have returned body counts
`4/4/4/627/1/448/4/2/2`; mode 2/5 hostcall exit/execute/resume counts are
`4/4/4` and `448/448/448`, with no hostcall errors. Eight register gates pass.

The separate shadow-capacity regression and pre/post 40 unit programs, 25
admission cases, builds and identity checks pass without skips. Postflight
finishes at **03:58:08 +08**; all per-case fault scans/drains are empty and
default module `.text` retains SHA256
`37362e3c49f513089a6f6bb9647f20d41a07afb69ffef4d34bc3ac808f60a712`.
No production runtime or guest-kernel modification or VM restart occurs.
The later test-organization change is a separate increment; this matrix is
not claimed as a rerun of that changed test harness.

### Failed Preparations

Both attempts below stop before arming contention. They have no JIT body or
native frame, no kernel fault, balanced ownership and drained modules/callers.
They are failed preparations, not native-only acceptance or passing JIT cases.
Each runner finishes before changes and an independent freeze starts anew.

| Archive in /tmp | Failure and correction |
| --- | --- |
| `kdlock-parallel-frames.WoflRS.tar.gz` | A per-lane one-second sleep expires lane 1's tightened sampling window, so only lane 0 publishes. Use two initial warmups and one module-wide sleep before consecutive sampling; do not modify hotlock policy. |
| `kdlock-parallel-frames.6K0Cxx.tar.gz` | Both images publish, but the new observer incorrectly requires TGID 0. Reuse existing `wait_ready()` with the artifact's real TGID; registry `pid=0` is not TGID. |

SHA256, in table order:

```text
478908b65655dd2a6cdb73e20daceba38394dd47f4e07c59c897bbaa6a6b99cb
0de11330221210256dd4d7cdcbbdbc5ebd2ab679a0395cc9975c05407d180b69
```

## Original Waiter Release Races

Checkpoint `480a12b`, **2026-09-09 02:22:07-02:46:05 +08**: 179 inputs,
65/65 pass (49 actual-JIT, 12 context refusals, two native controls, two JIT=0
kernel probes). Sixteen focused actual-JIT cases also pass; pre/post 39 unit
programs, 25 admission cases, builds and identity/drain audits pass, with
postflight at 02:47:34. Default runtime `.text` remains unchanged; no guest
kernel edit/build/install or VM restart occurs. Existing objtool/locale warnings
remain. Detailed mode/register/depth results are in `git show 480a12b:docs/VALIDATION.md`.

The six original-waiter races cover both direct B APIs at -50000/0/+50000 us.
Both APIs have real acquired and cancelled outcomes; each has one body/native/A
ACK and 12002 records. Both unbiased matrix cases cancel, while interruptible
focus acquires. These are not an outcome distribution or arbitrary cancellation
proof. Four original-waiter signal cases and six native-peer focus regressions
retain their separate ownership/return obligations. Flow is maintained in
[usage 6.5](JIT_EXECUTION.md#65-原-waiter-与-b-释放的竞争), not duplicated here.

Archive: `/tmp/kdlock-waiter-race-matrix.skE2dE.tar.gz`, SHA256
`a33d9c1990ceb79cd48d456940f5e370b34d1c85cc17c6ea33ac0f75b0fa710d`.

### Failed Bias Expectations

Two earlier attempts remain failures, not additional accepted matrix entries:

| Archive in /tmp | Recorded outcome |
| --- | --- |
| `kdlock-waiter-race-matrix.ysDJPj.tar.gz` | Three focused passes, then original killable waiter acquired B despite SIGKILL being sent about 50ms before unlock; strict `expected=cancelled` fails. B owner used busy polling. |
| `kdlock-waiter-race-matrix.T4nQAI.tar.gz` | Ten original-waiter passes, then a head native-peer race acquired despite early SIGUSR1; its strict cancellation expectation fails. Runtime inputs match checkpoint `480a12b`. |

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

Main-mode workload artifacts must retain branch, rotate, multiply, scaled-index
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

The opt-in dual-queue fixture uses its own A-protected sequence/digest and
per-request records, not the main-mode state table. It requires two real JIT
prefixes with nested B acquisition, two simultaneously live native frames and
four task/lock-matched ACKs in each selected drain order. It does not replace
the complex main-mode or full GPR/return-stack gates. Its code stays fixed while
the daemon is stopped; see [usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame).

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

## Recorded Matrix Manifest

The prior 65 selectors plus two parallel-native drain orders ran from
**2026-09-09 03:32 to 03:56 +08**. All 67 pass in their respective
categories; per-case exits are in
`/tmp/kdlock-parallel-frames.ThpcFS/results.tsv`. Mode 3 runs first to
verify publication and actual JIT. This and older matrices are historical;
current selection is defined by the usage guide and regression catalog, not
this command record. Body records count returned
positive logs, not retired instructions, unique instructions or immutable
generations.

### Recorded Commands

All commands ran in the recovery guest project with
`KDLOCK_RECOVERY_CONFIRMED=1 LC_ALL=C`. Use the operations guide to confirm
snapshots, freeze/sync inputs, retain evidence and drain between cases.
This is a manifest, not an unattended command to run on the host.
The three cross-NUMA commands use corrected role placements; earlier invalid
CPU placements are excluded from the 67-case total. The external
`/tmp/kdlock-register-native-control.sh` was used only by that freeze's control-0/3.
Current controls have a separately validated repository driver above; do not
silently replace these recorded commands or relabel the controls as JIT tests.

This is the completed freeze's evidence manifest, not a requirement to repeat
67 cases after each edit. Current daily selection and removed duplicate smoke
tests are documented in [usage 7](JIT_EXECUTION.md#7-分层与增量回归).

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

# parallel-drain-0
env KD_MUTEX_PARALLEL_FIRST=0 bash tests/test_23_mutex_parallel_native.sh

# parallel-drain-1
env KD_MUTEX_PARALLEL_FIRST=1 bash tests/test_23_mutex_parallel_native.sh
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
