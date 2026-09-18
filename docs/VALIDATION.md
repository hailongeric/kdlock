# kdlock Validation

Each result below belongs to its dated, frozen inputs. Documentation edits or
a later Git commit do not re-certify those inputs as a new run. The project is
not accepted as complete; actual-JIT positives, refusals, native controls and
kernel protocol probes are different categories.

**Scope decision, 2026-09-13:** the user explicitly continues to defer access-time
checking, its pre-instruction waiter exit and local condition-code preservation.
These remain [unimplemented limitations](TODO.md#deferred-access-time-guard),
not pending authorization. This documentation-only decision changes no runtime
inputs and adds no build, unit or JIT result; earlier pending-decision statements
below describe the state at their respective freezes.

**Scope decision, 2026-09-14:** delivery prioritizes supported x86_64 main paths;
extremely rare scenarios may remain unimplemented and untested under the
[delivery scope](TODO.md#delivery-scope). This does not turn untested limitations
into passes, remove existing guards or require another extended test matrix.

**Documentation handoff, 2026-09-14:** that documentation increment ended after the
native-handoff timing acceptance below. The README now links to one Chinese
[version overview](PROJECT_GUIDE.md#1-当前进展) separating implemented behavior,
unfinished work and explicit deferrals; duplicate chronological summaries were
removed from those two entry documents. This final documentation pass does not
change the 211 runtime/test inputs, add another live result or resolve the earlier
two-CPU missing-JIT failure. No further experiment or Git commit is part of this
handoff. The later user-requested cleanup/commit is recorded separately below;
it does not resume the paused implementation/experiment plan.

| Date (+08) | Evidence | Result and scope |
| --- | --- | --- |
| 2026-09-18 | [Shared-backing/entry commit audit](/tmp/kd-spin-entry-20260918/commit-source-audit.json), [TCLock protocol boundary](../tclock_backend/README.md#与-linux-原生-spinlock-的协议兼容边界) | Documentation/commit pass only: 331 runtime/test inputs match the final checkpoint, including all 23 changed non-document inputs. Both evidence archive hashes match; final 60-session, 20-session and cache-off archive audits pass again, including the recorded eight unit entrypoints and five live cases. No new build, live test, benchmark or TCLock/native mixed-protocol test. API compatibility is distinguished from queue/unlock interoperability; L/S remains required by kdlock's existing native-peer contract. |
| 2026-09-18 | [Spin first-CAS entry validation](../tests/README.md#spin-entry-first-cas), [cache/entry comparison](../bench/spin_cacheline/results/20260918-spin-entry.md) | Eight basic/affected units and five live cases pass and drain. Ticket creation follows the root CAS; physical owner and tail/link publication remain checked. Uncached 60-session trial substantially regressed single-thread throughput, so the final default retains cache and skips duplicate population lookups. Final-default 60-session comparison passes and drains; c1/t4 improves about 12%, other contended points are essentially unchanged. Twenty long native-cost sessions pass with a residual 0.9–1.5 ns regression; cache-off actual JIT also passes. Failed/superseded freezes stay separate on the result page. No kernel rebuild or full suite. |
| 2026-09-18 | [Shared GPR backing validation](../tests/README.md#shared-register-bank), [directed spin comparison](../bench/spin_cacheline/results/20260918-shared-reg-bank.md) | 12 basic/affected unit entrypoints, five actual-JIT live cases and 24 before/after benchmark sessions pass and drain. Wrapper spill copies removed; 16-cacheline throughput essentially unchanged. Three samples per group, sequential versions and differing JIT shares do not establish a general gain. No kernel rebuild or full suite. |
| 2026-09-18 | [TCLock commit input audit](/tmp/kd-tclock-native-20260918/commit-source-audit.json) | Documentation/commit pass only: 300 runtime/test inputs match the final guest freeze, including all 23 changed non-document inputs; exact upstream bytes/port diff, Python syntax, local document links and whitespace checked. The 180-session archive audit was rerun offline; no new build, benchmark or live test. Cost comparison distinguishes measured hotspots from unimplemented optimization candidates. |
| 2026-09-18 | [Complete TCLock native stack backend and three-way comparison](../bench/tclock_compare/results/20260918-native-stack.md) | Three basic/assembly entrypoints, 22 benchmark checks, 180 steady-state sessions, six zero-loss profiles and 20 long native checks pass. Full data/delegation/drain and archived-byte audit retained. Earlier kdlock concurrent-promotion RCU stall remains unresolved; final matrix uses uniform one-CPU preparation. No full suite or general TCLock context claim. |
| 2026-09-18 | [Caller-clobber v1](../tests/README.md#spin-clobber-v1), [same-kernel comparison](../bench/spin_cacheline/results/20260918-clobber-v1.md) | Independent kdclobber1 kernel, scoped unit/assembly checks, six live cases and 120 benchmark sessions; no consistent large throughput gain |
| 2026-09-18 | [TCLock context comparison and unified loop](../tests/README.md#tclock-context-loop) | Subsequent freeze: eight basic/affected unit entrypoints and five live cases pass; old/new/mixed wrappers share one C frame; no new performance matrix |
| 2026-09-18 | [Unified combiner spin benchmark](../bench/spin_cacheline/results/20260918-unified-context.md) | Subsequent measurement on the unified loop: 22 benchmark checks and 120 sessions pass, 100 million correct/drained operations; new ABI at 20 threads is 1.6294/1.6370 Mops/s, essentially unchanged from the previous freeze |
| 2026-09-15 | [Spin static dispatch and profiling](#spin-static-dispatch-profiling) | Two authorized experimental kernels built/booted; final 60-session comparison correct/drained, single-thread NO_JIT 50–57 ns/op versus native 38–45, all five sizes execute measured JIT at four threads; flat hardware samples locate native dispatch and request waiting |
| 2026-09-14 | [Native spin fast path](#native-fast-path-optimization) | Module optimization, scoped units and six complex spin JIT cases pass; final 40-session single-thread scan is correct/drained with zero measured JIT; 102–107 ns/op versus native 37–44 ns/op, so near-native performance is not yet achieved |
| 2026-09-14 | [Spin cacheline microbenchmark](#continuous-lock-contention-scan) | Continuous-loop 35-point/140-session scan completes with 1/4/8/12/16/20/24 threads; 17,000,000 operations, 8,283,218 measured JIT bodies, all five sizes verified; ten single-thread NO_JIT sessions and cross-node 24-thread placement remain explicit |
| 2026-09-14 | [Repository checkpoint](#repository-checkpoint) | Five readability/mapping changes on 211 inputs; five focused unit programs, external W=1 module and strict daemon build pass; no kernel-JIT rerun or expanded matrix |
| 2026-09-14 | [Native handoff timing](#native-handoff-timing) | 211 inputs, nine changed files: six affected units, W=1 build, two off/nested cases, eight paired sessions and three on/native cases pass; 1,252 returned bodies, four owner handoffs; initial CLI rejection retained |
| 2026-09-14 | [Isolated Python runtime](#isolated-python-runtime) | 211 inputs, version recipe plus existing evidence/unit changes: fresh venv, 40 units, 25 admission cases and core 5/5 pass; 484 returned bodies; no JIT execution-code or test-inventory change |
| 2026-09-14 | [Mutex oversubscription assessment](#mutex-oversubscription-assessment) | Same 210 inputs, no runtime edit: 13 sessions accepted, one two-CPU/short-work actual-JIT gate fails, two unrun; six complete pairs have 829 returned bodies; polling/parking decision remains open |
| 2026-09-14 | [Private queue timing](#private-queue-timing) | Executor increment, 210 inputs: nine affected units, W=1 build, eight paired sessions, five off/core and two on/nested cases pass; 1,334 returned bodies; eight timing rows and 915 queue samples match drained slowpath totals |
| 2026-09-14 | [Native owner wait timing](#native-owner-wait-timing) | Earlier 210-input freeze: 40 existing units, W=1 build, eight paired sessions, five off/core and five on/complex cases pass; 1,693 returned bodies; 3 spin + 3 mutex waits match native completion/identity and nine unlocks |
| 2026-09-13 | [JIT boundary timing](#jit-boundary-timing) | Earlier 210-input freeze: 40 existing unit programs, external W=1 build, 16 off/on paired sessions and five default-off core cases pass; 2,083 returned bodies; scalar registry fixture compile regression reproduced and repaired |
| 2026-09-13 | [Context-symbol matching](#context-symbol-matching) | Earlier 210-input freeze: five existing units / 234 methods, 25 audit cases, four JIT positives and 12 refusals pass; 427 returned bodies; byte-identical mode 2/5 images, ordinary translation about 3.3 s to 1.6 s |
| 2026-09-13 | [Translation resource accounting](#translation-resource-accounting) | Earlier 210-input freeze: three existing units, 32/32 sessions / 16 pairs pass; 3,250 measured JIT bodies and 16 matching translation resource records; no native-arm JIT |
| 2026-09-13 | [Mutex routine log severity](#mutex-routine-log-severity) | Earlier 210-input freeze: existing mutex unit, 8/8 mode-5 sessions / four pairs and both mode-4 phases pass; 632 measured plus three nested JIT bodies; INFO traces retained |
| 2026-09-13 | [Paired native/JIT experiments](#paired-native-jit-experiments) | Earlier 210-input freeze: two focused units, 16/16 independent sessions and eight alternating pairs; 1,044 measured JIT bodies, no native-arm JIT; instrumented costs, not three-arm acceptance |
| 2026-09-13 | [TCLock comparator feasibility](#tclock-comparator-feasibility) | External-object audit only: native control compiles, unchanged TCLock mutex lacks nine task fields; no new JIT or performance result |
| 2026-09-13 | [Instrumented benchmark measurements](#instrumented-benchmark-measurements) | Earlier 208-input freeze: two focused units and 5/5 core JIT pass; four measured payloads contain 451 new returned bodies, 481 across all phases; no speedup claim |
| 2026-09-13 | [Hotlock promotion ordering](#hotlock-promotion-ordering) | Earlier final freeze: production sampling unit and 6/6 complex actual-JIT cases pass, 468 returned bodies; independent windows and serialized TSC; both counterexamples retained |
| 2026-09-13 | [Typed scalar service](#typed-scalar-service) | Earlier scoped increment: four affected units and mode 2/5/8 pass; full-width int_sqrt input/result, two-service JIT returns and unchanged clock-quota native suffix; 444 returned bodies |
| 2026-09-13 | [Main-plan acceptance audit](#main-plan-acceptance-audit) | Earlier clock-only freeze: 64/64 on 206 inputs; 50 actual-JIT cases, 12 refusals, two kernel probes; 39 unit programs and 25 independent admission cases |
| 2026-09-13 | [Shared B waiter exit](#shared-b-waiter-exit) | Earlier scoped live: 2/2 complex spin JIT cases, 14 returned-body witnesses; first TID detaches before the next root on the same B combiner, three existing units, no new routine entry |
| 2026-09-13 | [Progressed spin gate refusal](#progressed-spin-gate-refusal) | 2/2 complex spin JIT cases, three returned-body witnesses; real gate ENOMEM after a second root's prefix, two existing units, no new routine entry |
| 2026-09-13 | [Shared native mutex B](#shared-native-mutex-b) | 3/3 complex mutex JIT cases, 413 returned-body witnesses including both mode-4 phases; two focused units, initial artifact-selection failure retained |
| 2026-09-13 | [Shared B mixed completion](#shared-b-mixed-completion) | 4/4 complex spin JIT cases, 20 returned-body witnesses including three mode-8 phases; two focused units, initial fixture failure retained |
| 2026-09-13 | [Shared B combiner](#shared-b-combiner) | 3/3 complex spin JIT cases, 12 returned-body witnesses including both mode-8 phases; two focused units, no new routine entry |
| 2026-09-13 | [CALL quota continuation](#call-quota-continuation) | 6/6 complex JIT cases, 444 returned-body witnesses; four focused units; mode 5 keeps normal JIT returns and adds a checked quota/native suffix |
| 2026-09-13 | [Native frame retirement](#native-frame-retirement) | 8/8 complex JIT cases, 464 returned-body witnesses; two focused units verify native-reference pop refusal |
| 2026-09-13 | [Mutex nested scheduling](#mutex-nested-scheduling) | 3/3 with `mutex_jit=1`, seven-role/two-CPU mode 4 and OOO plus mode 5; 432 returned-body witnesses |
| 2026-09-13 | [Remote packet unit](#remote-packet-unit) | One existing guest unit passes; full software packet, DONE/reuse and eight mutants, no live JIT rerun |
| 2026-09-12 | [Spin waiter publication](#spin-waiter-publication) | 9/9 complex spin JIT cases; 28 returned-body witnesses, no mutex rerun in that increment |
| 2026-09-12 | [Original waiter exit](#original-waiter-exit) | 5/5 actual-JIT cases with `mutex_jit=1`; two-frame signals/exit, node pressure and shared-client regressions |
| 2026-09-12 | [Test inventory review](#test-inventory-review) | 44-entry audit, then five models consolidated into production units; then 39 entries, no live rerun |
| 2026-09-11 | [Reading handoff](#reading-handoff) | Builds and six focused unit programs; comment-only source changes, no kernel-JIT rerun |
| 2026-09-10 | [Static per-CPU ranges](#static-per-cpu-ranges) | 24/24 scoped live, with 12 JIT positives and 12 native-only refusals; mutex positives use `mutex_jit=1` |
| 2026-09-10 | [Dynamic-pointer and resume-boundary audits](#dynamic-pointer-screening-gap) | Guest-userspace counterexamples and packet review, not a passing access-time guard or kernel-JIT gate |
| 2026-09-09 | [Parallel native frames](#parallel-native-frames) | Historical complete selection: 67/67, with 51 JIT positives, 12 refusals, two native controls and two kernel probes |

The scoped per-CPU run covers static core and boot-reserved module ranges, not
dynamic pointers or arbitrary context-object lifetimes. The
[offline verifier](#offline-evidence-verifier), [selection review](#covered-diagnostic-selection)
and earlier increments retain separate evidence; their passes are not combined
into the latest live run. Current commands and acceptance interpretation are
in [JIT_EXECUTION](JIT_EXECUTION.md); the
[recorded matrix manifest](#recorded-matrix-manifest) preserves historical commands.

The historical 2026-09-09 matrix's source identity is **183 runtime/test inputs** in
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

## Demo workload module layout

**2026-09-14, 19:46:57–19:49:28 +08.** Demo critical-section modules are now
grouped under `workload_modules/`: `lock_scenarios/` contains the former
`klock_module/` and 21 workload fragments, while `spin_cacheline/` contains the
cacheline driver, payload and ioctl header. Clients, runners and provider
observations keep their existing bench/test roles. Of 28 moved source/build
inputs, 26 are byte-identical; the scenario driver and Makefile only adjust
includes, the symbol-file path and comments. Module/device names and ioctl
interfaces are preserved. Historical evidence below retains its original paths.

Recovery-guest W=1 builds pass through the aggregate entry, optional source
helper, restoration of the default dependency, and the benchmark's delegated
module target. All **11 cacheline tests** and **10 affected unit programs** pass;
the default cacheline preview still lists 20 configurations/80 sessions, and the
mode-4 regression preview passes. Both workload modules' executable ELF sections
match their pre-move builds byte for byte; whole-file hashes are recorded
separately. Kernel baseline, unchanged ordinary provider artifact, frozen-input
and final idle checks pass. No live kernel or performance matrix was rerun.

Guest evidence: `/tmp/workload-modules-layout-20260914`; host evidence:
`/tmp/workload-modules-layout-evidence-20260914`. The archive
`workload-modules-layout-20260914.tar.gz` retains the migration map, old layout,
271 frozen source/support files, build/test logs, module metadata and binary
comparisons, SHA256
`8797ee18137127a2dbd2b5d4723300c5f8aa541a273ea532202fc74828cbf476`.
The initial verification wrapper misparsed the dry-run's summary following its
JSON; the finishing check validates both parts of that saved successful output,
without rerunning the already-passed builds or tests.

## Spin Cacheline Microbenchmark

### Spin static dispatch profiling

**2026-09-15, recovery guest.** The user's continuation authorizes the scoped
spin-hook kernel experiment prepared in the previous increment. Two independent
source/build trees and releases are built and booted; the original source,
captured baseline, installed kernel and default boot entry are preserved.
Both experiments retain the original configuration except `CONFIG_LOCALVERSION`,
including mitigation/debug settings, `nokaslr` and voluntary preemption.
Each performance pair uses its own running kernel's native control.

| Kernel | Build ID | Role |
| --- | --- | --- |
| `6.1.159` | `6f9f2e9fec382e97f620553793aa90b527a30af5` | Original hook-patched baseline; new diagnostic profiles, previous increment's formal comparison |
| `6.1.159-kdstatic1` | `c377e3f66f35aaab46bc38ebc79803d9a0e0388e` | R1: direct `static_call` selector and callbacks |
| `6.1.159-kdstatic2` | `460d77502af4709a0cca794b322cedc20c2cc478` | R2: combined dispatch, selection and miss-only cleanup outside the cached native path |

The [kernel experiment](../kernel_experiments/spin_static/README.md) preserves
RSP capture, register clobbers, callback arguments, int3 selection and the
two-element wrapper ABI. R2's native hit still checks context, source admission,
the cached site, the entire S word and the real Linux trylock; the owner remains
pinned through unlock and retirement checks. A cache hit cannot authorize JIT.
The cold helpers remove miss-path scheduling calls and extra register saves
from successful acquisition. Both combined callbacks save only RBP in the
compiled prologue. This does not mean that every machine CALL disappears:
PV alternatives and disabled fentry sites remain in the ELF.

The final R2 single-thread scan uses CPU 0, sizes 1/2/4/8/16, **1,000,000
operations per worker's one RUN ioctl**, four alternating native/kdlock pairs
per size. All **40 sessions / 20 pairs / 40,000,000 operations** are correct and
drained. All 20 kdlock sessions have valid, stable NORMAL artifacts but **zero
measured JIT bodies**; they remain NO_JIT. Median wall and worker CPU ns/op:

| Payload lines | Native wall | kdlock wall | Native CPU | kdlock CPU | Median paired kdlock/native throughput |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 38.61 | 50.21 | 36.31 | 48.07 | 0.7673 |
| 2 | 38.35 | 52.46 | 35.94 | 49.28 | 0.7366 |
| 4 | 38.56 | 51.61 | 36.72 | 49.83 | 0.7479 |
| 8 | 41.24 | 54.39 | 40.11 | 52.71 | 0.7600 |
| 16 | 44.71 | 57.05 | 42.06 | 54.56 | 0.7831 |

R1 independently completes the same 40-session selection, all correct/drained
and all single-thread kdlock samples NO_JIT. Across sizes 1/2/4/8/16 its native
wall medians are 37.47/38.84/38.77/42.28/44.07 ns/op, kdlock medians
69.35/70.17/70.78/72.40/75.88, and paired ratios
0.5404/0.5603/0.5500/0.5840/0.5839. The N=1 progression is therefore about
**101.66 → 69.35 → 50.21 ns/op** for kdlock, with native controls
37.14 → 37.47 → 38.61. The first point is explicitly the previous increment;
these are different kernel freezes, not one pooled sample or a statistical
significance claim. R2 still adds roughly 12–14 ns/op and reaches 74–78% of
native throughput; **near-native performance has not yet been achieved**.

Independent bench-only dispatch controls use N=1, CPU 0, 1,000,000 operations
and four repetitions per arm in forward/reverse order. All R1 12 controls and
R2 16 controls are correct and drained; they contain no kdlock/JIT machinery:

| Control | R1 wall ns/op | R2 wall ns/op | R2 CPU ns/op |
| --- | ---: | ---: | ---: |
| Provider absent | 37.52 | 37.00 | 35.49 |
| Selector returns native | 48.63 | 45.70 | 42.98 |
| Selector plus minimal original-L callbacks | 62.35 | 60.27 | 57.21 |
| Combined unconditional original-L callbacks | Not available | 46.58 | 45.45 |

The final native fast path is close to the combined callback control. This
supports the remaining guest hook/callback framework as a substantial cost;
it does not isolate an exact number of nanoseconds per function or establish
a universal hardware lower bound. Further progress needs to address that
framework, rather than treating the retained ownership checks as dispensable.

R2 also completes **20 sessions / 10 pairs / 80,000,000 operations** with four
workers pinned to CPUs 0–3, the same five sizes and 1,000,000 operations per
worker. All data, artifacts and drain checks pass; each size has measured JIT
in both kdlock sessions, totaling **26,782,877 returned bodies**. Medians:

| Payload lines | Native wall ns/op | kdlock wall ns/op | Paired throughput ratio | Measured JIT share |
| --- | ---: | ---: | ---: | ---: |
| 1 | 292.50 | 2922.12 | 0.1001 | 62.57% |
| 2 | 320.05 | 2974.67 | 0.1076 | 64.57% |
| 4 | 353.67 | 2873.30 | 0.1233 | 68.85% |
| 8 | 421.51 | 2609.00 | 0.1617 | 70.31% |
| 16 | 482.53 | 2720.75 | 0.1791 | 68.49% |

Actual JIT therefore remains much slower than native for this short payload.
This is a focused 1/4-thread optimization increment, not another complete
35-point/140-session scan. Wall ns/op is batch time divided by completed
operations, not lock-acquisition or waiter latency. Four-thread CPU ns/op sums
all workers' CPU time, including simultaneous spinning.

Separate diagnostics use `perf record -e cycles:k -F 499`, **flat IP sampling
only**, with ftrace `nop` and function profiling disabled. No clock/probe is
inserted into the lock loop. On each of the three kernels, native T=1 and
kdlock T=1 execute 100,000,000 operations; kdlock T=4 executes 4,000,000 total.
All nine profile sessions are correct/drained with zero lost samples. T=1
kdlock is NO_JIT on all three; the T=4 profiles return 2,696,114 (original),
2,471,967 (R1), and 2,350,312 (R2) measured bodies. These sessions have
`performance_result=false` and are excluded from the performance pairs.

R2 period-weighted hotspots, with 2,154 single-thread and 21,701 four-thread
worker samples:

| Single thread, NO_JIT | Sample weight | Four threads, 58.76% measured JIT | Sample weight |
| --- | ---: | --- | ---: |
| `kd_spin_dispatch_lock` | 38.59% | `__kd_spin_lock_longjmp` | 52.80% |
| PV queued-spin unlock | 17.66% | PV queued-spin lock slowpath | 10.87% |
| Kernel `_raw_spin_lock` | 13.65% | Kernel `_raw_spin_lock_irqsave` | 10.23% |
| `sc_body_1` wrapper | 12.52% | PV queued-spin unlock | 3.48% |
| `sc_ioctl` batch loop | 7.75% | Spin `execute_cs` | 3.28% |
| Kernel `_raw_spin_unlock` | 5.27% | `kd_spin_gate_lookup` | 2.44% |
| `kd_spin_dispatch_unlock` | 4.51% | `kd_exec_frame_validate` | 1.92% |

The single-thread lock callback includes the actual locked CMPXCHG: its hottest
offset, +0x99, is the branch immediately after that instruction. Its entire
38.59% must not be labeled redundant dispatch code. Similarly, `sc_body_1`
includes call setup and return, not just the counter update. The update's
+0x19..+0x32 envelope receives only 24 samples, about 1.12%; that is too sparse
for precise instruction timing. The original profile's separate selector was
24.67% of sample weight, R1's 10.42%; R2 has no sampled separate selector.
Those earlier selector-entry samples may include indirect-call stalls/skid,
not just comm comparison.

Exact saved R2 disassembly resolves **46.06%** of all four-thread sample weight
to `__kd_spin_lock_longjmp` +0xc6..+0xfd, the `curr_node->locked`/PAUSE wait loop;
another **4.26%** lies at +0xfd..+0x108, polling S locked/pending. Both ranges
exclude their upper bound. The generated image has only 20 samples (0.092%).
Thus the observed multicore cost concentrates in request waiting and lock/
executor protocol, not the tiny counter body. The gate map's source also
contains a serialized irqsave lookup, making repeated metadata lookups a
concrete optimization candidate. Flat samples cannot attribute every kernel
spinlock sample to a particular caller or prove how often ownership changes.
They describe sampled execution locations, not exact function times, contention
probability, single-operation latency or an instruction-coverage proof.

Verification and evidence boundaries:

- R1's initial full unit inventory has 39 passes and one compile failure:
  the outer-progress fixture lacked two native-fast state stubs introduced
  previously. Adding the empty fast-state stubs preserves its existing ticket
  assertions; the affected program passes. The independent 25-case admission
  audit also passes. This is not an initial 40/40 pass.
- R2 runs the affected routing, entry and source-lifetime units on the final
  kernel. Routing exercises 14 scenarios / 3,796 checks including combined
  selection, native peers, context/miss pin balance, nesting, rename, closing
  and retirement. W=1 provider and benchmark builds and all 13 benchmark tests
  pass; earlier old-interface compatibility builds also pass. Existing
  assembly/trampoline objtool warnings remain, not a warning-free build claim.
- Each experimental kernel independently passes eight complex actual-JIT
  cases: mode 2/7/8/4/5, mixed-spin, registers-1-3 and native-spin-acquired.
  Mode 4/5 use `mutex_jit=1`; their inclusion checks the retained shared/int3
  behavior. R2's offline live verifier accepts all eight on 236 frozen files,
  with no unrecorded cases. The R2 performance/profile freeze has 127 files.
- Offline checks recompute counter deltas, unused slots, worker affinity,
  completion/CPU aggregation, alternating pair order/ratios, binary/source
  hashes and published image hashes. The final three profiles and both grids
  retain the same source. Single-grid and later provider ELF hashes differ
  only in non-allocated `.BTF`; all other 73 sections are byte-identical.
  The initial cross-run whole-binary postflight assertion is retained as a
  metadata mismatch, then resolved by this full section comparison, without
  repeating a workload or altering a recorded sample.
- Final live Build ID, original captured source/config/build, binaries, idle
  state and dmesg checks pass; no new kernel fault, workload timeout or
  undrained session occurs. The guest remains on R2; default boot stays original.
  The recovery snapshot `pre_static_boot_20260915` is confirmed before kernel
  boot/testing; the monitor save reply timeout is resolved by later snapshot
  queries, without issuing another save. Early boot SSH readiness delay and
  a missing `/tmp` perf preflight are resolved before workload loading. Perf
  is then built at a persistent guest path. Draft unit import-path and archive
  compression-wrapper failures are retained separately from passing runs.

This remains a 40-vCPU recovery VM, 64-byte lines, node-0 measurement placement,
without host physical-core exclusivity. Quiet observation is not zero overhead,
and the generic hook-reader/hot-unload limitation remains. No guards,
mitigations, counters, natural-discovery criteria or workload instructions are
removed to manufacture the speedup. The only host operations are source edits,
VM control and read-only evidence analysis; all builds/tests/profiles run in
the recovery guest.

Host `/tmp` archives (not distributed by a fresh checkout):

| Archive | SHA256 |
| --- | --- |
| `kdlock-profile-old-evidence-20260915.tar.gz` | `43dbf9437b99cd6ad2d3bae09d4905e9154735325633352868941849d284f81f` |
| `kdlock-static-kernel-preboot-final-20260915.tar.gz` | `6fe26435c3f75e507cf747304f13722c43e860b0106be7e5c39d7e267c3f8de1` |
| `kdlock-static-r1-evidence-20260915.tar.gz` | `e318bcb7a001e1d35d9604bf1dd05116874acf9dc1290b5b245b1bce6ffa2eb4` |
| `kdlock-static2-kernel-preboot-20260915.tar.gz` | `b1024d1f4a163146045cf1fff5dd696bbea42c4fdc624c3d619093729051a5d0` |
| `kdlock-static2-runtime-evidence-20260915.tar.gz` | `c6b5fca8ee9109055844784e7d18972baadfbf4554051775192a5a827603dabd` |

Kernel archives include exact named source/config/build files and installation
records, including vmlinux; runtime archives preserve raw CSV/JSON, profiles,
frozen source and ELF files, generated artifacts, units/builds/live logs and
postflight records. R2's runtime archive contains 3,475 regular files. Readable
results and later read-only audits are under
`/tmp/kdlock-static2-runtime-evidence-20260915/`; its
`instruction-attribution.json` resolves the byte intervals above. These later
audit files are separate from the already hashed archive. The final experiment
patch SHA256 is `e621077111e6c2d3483456d4e265f64ab09bf406cd3c328179dda40cfd71e62b`.

### Native fast path optimization

**2026-09-14, recovery guest, after the single-thread investigation.** The
later authorized kernel experiment and its results are recorded
[above](#spin-static-dispatch-profiling); the scope and draft status below
describe this earlier freeze. This
increment changes the production spin path, retaining the captured guest
kernel, original Linux lock L, natural discovery/publication and two-element
wrapper ABI. A per-CPU cache of a normally registered/published root entry
permits native trylock when the entire scheduling word S is idle. A successful
hit avoids registration, gate lookup and ticket machinery; misses and contention
retain the general route. Ownership stays CPU-pinned through native unlock and
participates in retained-owner routing and retirement checks. The final revision
also inlines the unchanged source-state read, prepares bounded comm comparisons
at load time, and separates the general callback stack frame. Contracts are in
[DESIGN](DESIGN.md#41-native-lock-and-private-queue), and the workload/measurement pseudocode remains
in the [bench README](../bench/spin_cacheline/README.md#临界区与测试伪代码).

The final single-thread run uses CPU 0 on node 0, payload sizes 1/2/4/8/16,
**1,000,000 lock operations per RUN ioctl** and four alternating native/kdlock
pairs per size. All **40 sessions / 20 pairs / 40,000,000 operations** complete
with correct counter deltas and normal drain. All 20 kdlock sessions have stable
NORMAL entries and valid generated artifacts, but **zero measured JIT bodies**;
they remain NO_JIT, not actual-JIT acceptance. Medians below include the batch
boundary and framework costs; wall ns/op is not lock-acquisition latency.

| Payload lines | Native wall ns/op | kdlock wall ns/op | Native CPU ns/op | kdlock CPU ns/op | Median paired kdlock/native throughput |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 37.14 | 101.66 | 35.64 | 101.33 | 0.3654 |
| 2 | 38.08 | 102.46 | 36.70 | 102.16 | 0.3714 |
| 4 | 37.92 | 103.28 | 37.48 | 101.12 | 0.3640 |
| 8 | 40.45 | 103.69 | 38.95 | 101.49 | 0.3873 |
| 16 | 44.32 | 107.30 | 40.84 | 106.36 | 0.4120 |

**Near-native single-thread performance is not yet achieved.** A separate
bench-only `dispatch_floor` provider runs the same payload/client on CPU 0,
with 1,000,000 operations and four samples per arm in alternating order. It
has no kdlock discovery, S, tickets, source leases, JIT or per-operation
observation. All 12 controls / 12,000,000 operations are correct and drained:

| Independent dispatch control | Median wall ns/op | Median CPU ns/op |
| --- | ---: | ---: |
| Provider absent, native | 38.00 | 36.16 |
| Selector called, returning native | 65.69 | 63.80 |
| Selector plus minimal original-L callbacks | 96.69 | 95.72 |

This control is close to the optimized kdlock's 101.66 ns/op and supports hook
dispatch as the dominant remaining cost on this guest. It is not a universal
hardware lower bound or a per-function timing breakdown. The captured kernel
uses indirect selector/callback calls with RETPOLINE and RETHUNK enabled;
static-call support is also enabled. A direct-call patch and provider adapter
were prepared only as an **unapplied, unbuilt draft** in
`/tmp/kdlock-static-dispatch-proposal-20260914/`; offline patch applicability
checks pass. No guest-kernel source, configuration, build or boot identity has
been changed. Further kernel work needs the original no-kernel-change scope
to be adjusted; this draft has no performance or JIT acceptance result.

Earlier development runs remain distinct from this final long batch. R1 adds
the native path; R2 also reduces selector/general-frame overhead. Each runs
16 sessions at N=1, T=1/4, I=100,000, four pairs per point, with 4,000,000
operations and correct/drained outcomes:

| Revision | T=1 native wall ns/op | T=1 kdlock wall ns/op | T=1 paired ratio | T=4 paired ratio | T=4 measured JIT bodies |
| --- | ---: | ---: | ---: | ---: | ---: |
| R1 | 81.10 | 220.44 | 0.3791 | 0.1016 | 1,097,776 |
| R2 | 80.75 | 180.44 | 0.4476 | 0.1229 | 1,115,907 |

All four T=1 kdlock sessions in each revision are NO_JIT; all four T=4 sessions
execute actual JIT. The earlier 100,000-operation dispatch diagnostic has
12 passing controls, with native/selector/callback wall medians
84.10/141.80/170.02 ns/op. Absolute times change substantially between those
short batches and the later long batches, including the native arms. The R2
and final provider ELF sections are identical except BTF metadata, and the
workload/client/daemon binaries are byte-identical. The long-batch result is
therefore not another code optimization; no claim isolates batch size from
VM scheduling/frequency effects. Four samples do not establish significance.
Earlier 10,000-operation results are also not controlled speedup comparisons.

Focused recovery-guest checks:

- R1: production spin-entry, spin-routing and source-lifetime units pass.
  R2: spin-routing and source-lifetime units pass again after their affected
  code changes: 14 routing scenarios / 3,724 checks, and 42,820 lifetime checks
  with all 13 mutation checks detected. The routing fixture directly exercises
  the production fast path, native-peer/S-busy fallback, nesting, rename,
  closing and busy retirement, plus exact bounded comm equivalence.
- W=1 external provider builds and the strict daemon build pass. Existing
  assembly/trampoline objtool warnings remain; they are not new clean-build
  claims. All 11 directed benchmark tests pass with unchanged one-ioctl and
  clock-call budgets, counter oracles and NO_JIT/pair classification.
- `tests/run_all.sh --suite spin --case mixed-spin --case registers-1-3
  --case native-spin-acquired` passes all six selected complex cases:
  mode 2, non-LIFO mode 7, multi-queue/nested mode 8, original native peers,
  register continuation and acquired-child continuation. Each retains its
  actual returned-body and data oracle; all are accepted, source-unchanged,
  fault-free and drained. The offline evidence verifier confirms 232 frozen
  files and all six recorded outcomes and artifact/protocol archives.
- The final scan's offline audit checks all phase counter deltas, affinities,
  aggregation, pair order/ratios, 119 frozen source files, four binaries and
  40 generated image/assembly hashes. Final guest idle, matching binaries and
  captured source/config/build/live baseline checks pass. Function profiling
  remains disabled, tracer is `nop`; no new kernel fault was observed. An
  initial read-only postflight wrapper had a tuple/list concatenation error;
  its corrected completion does not rerun any workload.

This scoped increment does not rerun the full 35-point contention scan or
mutex matrix. Sizes 2/4/8/16 have no measured actual-JIT performance acceptance
on this new freeze; the historical full scan is not substituted for it.
The native baseline remains the existing hook-patched kernel in a VM, without
host physical-core exclusivity. The generic hook-reader/hot-unload limitation
also remains; cleanup is the controlled, drained recovery-guest procedure.

Guest output directories use the archive basenames below. Host readable CSVs,
offline audits, postflight/build/unit records and snapshot confirmation are in
`/tmp/kdlock-native-fast-evidence-20260914/`. Archives in host `/tmp`:

| Evidence archive | SHA256 |
| --- | --- |
| `kdlock-native-fast-single-final-20260914.tar.gz` | `177b1cd96246927b48946b39ebc65918109d77fe5983524ab5accb2444ae7951` |
| `kdlock-dispatch-floor-long-20260914.tar.gz` | `e784bb26ec3f258e452815aa0c4ea3fbd00bdc9d9c4943ae9a682fa0f1a600dd` |
| `kdlock-native-fast-protocol-20260914.tar.gz` | `475fd045cdf4e6ade982cc200d8641ce5013be13a453b6cb2c422ef618c40182` |
| `kdlock-native-fast-r1-20260914.tar.gz` | `fa0094028e34cd915ae5f6e875a3f8a92822beca338e9d21329560f10f77db67` |
| `kdlock-native-fast-r2-20260914.tar.gz` | `b89ec10910900578247d914f129d20b67ca6900df7b7cb886b7b4bf1bcd3fa45` |
| `kdlock-dispatch-floor-20260914.tar.gz` | `0b25bb37ead9e636d5199507ea328bfcb2c0a015226b487aa6e24e3af41a767b` |

### Continuous lock contention scan

**2026-09-14, 21:42:57–21:53:24 +08.** The workload now executes a fixed
batch of consecutive lock acquisitions without the former per-256-iteration
`cond_resched()` and signal polling. The critical section remains N unrolled
counter increments under the same shared spinlock. The default thread grid is
**1/4/8/12/16/20/24**, with 10,000 operations per worker in one RUN ioctl,
1/2/4/8/16 payload lines and two alternating native/kdlock pairs per point.
Setup uses the existing atomic start gate; no delay or extra wait is added to
the measured workload loop.

The recovery guest's default CPUs 0–19 belong to node 0; CPUs 20–23 belong
to node 1. Thus the 24-thread point crosses nodes. Plans and sessions retain
the per-worker CPU/node mapping; CSV and terminal summaries identify each
point as single-node or cross-node. The latter includes placement effects and
is not presented as a same-node comparison.

All **140 sessions / 70 pairs** finish with correct data and normal drain:
**17,000,000 measured operations**, **8,283,218 measured JIT bodies**, 70 native
sessions, 60 multi-thread kdlock sessions with actual JIT and 10 single-thread
`NO_JIT` sessions. All five payload sizes have actual-JIT coverage. Single-thread
NO_JIT keeps its ratio without passing JIT acceptance. The new uncontended
reference is visible, for example, in the 1-line native median throughput:
10.724 million op/s at one thread, 2.022 at four and 3.184 at 24. These short VM
trials do not quantify lock wait/hold time or holder changes, or establish
statistical significance. Earlier yielding-loop results below remain separate.

The recovery-guest W=1 workload build and all **11 directed tests** pass,
including the 1/24-worker atomic gate, actual default CLI grid, fixed ioctl/clock
call budget, NUMA labels and rejection of mismatched pair placement. Module
imports and disassembly confirm no workload scheduling call. Post-run checks
verify phase counter deltas, affinities, every pair ratio, 112 frozen source
files, four binaries and 140 generated image/assembly hashes. All 70 kdlock
sessions retire with state=2 and zero modules/frames/writers. Final idle and
kernel-baseline checks pass; the ordinary provider artifact is unchanged.

Guest scan: `/tmp/spin-cacheline-continuous-20260914`; precheck and final audit:
`/tmp/spin-cacheline-continuous-precheck-20260914` and
`/tmp/spin-cacheline-continuous-verification-20260914`. Host evidence, readable
`results.md` and CSVs: `/tmp/spin-cacheline-continuous-evidence-20260914`.
Archive `spin-cacheline-continuous-20260914.tar.gz`, SHA256
`175d9da64ab58009acbb0786eb5f112dab9d773a8e6427d99259ed570e97f81b`,
contains the scan, builds/tests, snapshot confirmation, source and binary
copies, generated code and audit scripts. Host offline checks independently
verify all 140 sessions, pair ratios and archived hashes, including 76 source
files present in the current host checkout.

### Single-thread investigation

**2026-09-14, after the continuous scan.** Reanalysis of the archived scan,
not a new performance run: all ten one-thread kdlock sessions published valid
NORMAL entries but measured zero JIT bodies. Each arm has two samples per size;
the following values are median batch-amortized ns/op, not acquisition latency.

| Payload lines | Native wall ns/op | kdlock wall ns/op | kdlock thread CPU ns/op |
| --- | ---: | ---: | ---: |
| 1 | 94.3 | 1584.0 | 1354.0 |
| 2 | 87.4 | 1536.9 | 1536.2 |
| 4 | 88.4 | 1563.1 | 1491.9 |
| 8 | 94.0 | 1610.4 | 1609.7 |
| 16 | 108.1 | 1505.4 | 1390.8 |

The roughly 1.4–1.5 us additional cost changes little with payload size and is
also visible in CPU time. The promoted uncontended source path still registers
the known entry, scans ticket slots, looks up gates and acquires metadata locks.
The [benchmark explanation](../bench/spin_cacheline/README.md#单线程为什么仍有-kdlock-开销)
separates static path counts from measured timing; no per-function cost shares
or isolated causal speedups have been measured. The original scan archive and
its SHA256 above remain unchanged.

A separate attempt to profile selected kdlock functions with ftrace failed:
SSH became unresponsive and serial recorded `BUG: TASK stack guard page was hit`
at guest uptime 695854.205189. The diagnostic intended one 1-line/1-thread batch
after normal preparation; no complete result or per-function statistics were
recovered, and normal request drain/retirement could not be established.
This is a failed diagnostic, not another benchmark sample. Its exact fault
mechanism has not been established; the failing method was not retried.

The old VM was stopped and verified exited before restarting in recovery mode.
By **22:28:45 +08**, SSH, idle checks, the captured 6.1.159 kernel baseline,
241 source hashes, the unchanged ordinary provider artifact and CPU/node mapping
were verified. Tracing is `nop`, function profiling is disabled, filters are
reset, and the new boot log has no kernel fault signatures. The failed session
directory in guest `/tmp` did not survive reboot; the host retained serial,
diagnostic inputs/snapshot proof, the previous one-thread sessions, and recovery
checks at `/tmp/spin-cacheline-single-profile-failure-20260914`.
No production or guest-kernel code was changed for this investigation; no new
performance matrix or function profile passed. Checkout HEAD remains
`43b27c04d4381014ecc8c67138999a2cf0e42295` with the existing uncommitted work.

### Full rescan after workload consolidation

**2026-09-14, 20:41:19–20:47:18 +08.** Reran the complete default grid using
the atomic worker gate and `workload_modules/spin_cacheline/` driver: 1/2/4/8/16
payload lines, 2/4/8/16 threads on guest node-0 CPUs 0–15, 10,000 operations per
thread in one RUN ioctl, two pairs per configuration in native→kdlock then
kdlock→native order. The recovery snapshot was checked through the host monitor;
all 241 current checkout files matched before the run. No benchmark source was
changed and no extra unit, baseline workload or rare-scenario matrix was added.

All **80 sessions / 40 pairs** finish with exact data and normal drain:
**6,000,000 measured operations**, **2,677,776 measured JIT bodies**, 40 native
sessions, 30 kdlock sessions with actual JIT and 10 `NO_JIT` sessions. Every
2-thread kdlock session has zero measured JIT; every 4/8/16-thread kdlock session
has measured JIT, so all five payload sizes have actual-JIT coverage. NO_JIT
retains its performance ratio without being counted as JIT acceptance.

The table shows the median of each configuration's two **kdlock/native
throughput ratios**; values below 1 mean lower kdlock throughput. The 2-thread
column is entirely NO_JIT. These short VM samples do not establish statistical
significance or lock saturation; native still uses the existing hook kernel.

| Payload lines | 2 threads (NO_JIT) | 4 threads | 8 threads | 16 threads |
| --- | --- | --- | --- | --- |
| 1 | 0.2975 | 0.1520 | 0.1415 | 0.1288 |
| 2 | 0.3339 | 0.1574 | 0.1553 | 0.1496 |
| 4 | 0.3252 | 0.1787 | 0.1727 | 0.1620 |
| 8 | 0.3721 | 0.2129 | 0.1995 | 0.1804 |
| 16 | 0.5150 | 0.2097 | 0.2491 | 0.2100 |

The final audit checks all phase-to-phase counter deltas, affinities, pair order
and ratios, publication/body deltas, 112 frozen source/support files, four
binaries and 80 generated image/assembly hashes. All 40 kdlock sessions retire
with state=2 and zero modules/frames/writers. Final idle and source/build/running
kernel baseline checks pass; the ordinary provider artifact is unchanged and
the workload/client have no mutex, condition-variable or libatomic imports.

Guest results: `/tmp/spin-cacheline-rerun-20260914`; verification:
`/tmp/spin-cacheline-rerun-verification-20260914`. Host evidence and readable
`results.md`, `raw.csv`, `pairs.csv`, `summary.csv`:
`/tmp/spin-cacheline-rerun-evidence-20260914`. Archive
`spin-cacheline-rerun-20260914.tar.gz`, SHA256
`57c9206dae1b1cc9305889f2f1a1d64bb80305a2b6b2d119d53f2db2dc212e49`,
contains the complete scan, source/binary copies, topology, snapshot/launch
records, generated code, logs and final verification. Host offline checking
independently confirms every session and archived hash, including 76 source
files present in the host checkout.

### Batch calls and timing documentation

**2026-09-14, 19:34:14–19:34:18 +08.** The guide now shows the unrolled
critical section, client/worker/kernel pseudocode and timing boundaries. The
existing runtime already executes all iterations in one RUN per worker; its
source and binaries are unchanged. A fixture-only API counter checks batches
of 1, 10,000 and 100,000 operations at 1/2 workers: T RUN calls, one layout and
two count queries, T+1 monotonic and 2T thread-CPU clock reads, with exact
payload deltas. These are API counts, not syscall tracing or a measurement of
clock overhead. No observations were added to the performance client.

All **11 directed tests** pass in the recovery guest. Kernel baseline, frozen
inputs, four unchanged binaries and final idle checks pass; no live performance
scan was rerun. Guest evidence: `/tmp/spin-cacheline-batching-verification-20260914`;
host copy: `/tmp/spin-cacheline-batching-evidence-20260914`. The archive
`spin-cacheline-batching-verification-20260914.tar.gz` includes 113 frozen
source/support files and the test log, SHA256
`fb334f62d2a119c13c9db1f62ba9b50b9069106ba75743bc662c0a452ffcd9b7`.

### Atomic worker coordination

**2026-09-14, 19:12:21–19:17:32 +08.** The user's follow-up removes mutexes
from the worker path. `work()` now publishes readiness and waits on C11 atomic
`ready/go/abort` with `pause`; the main thread releases go after starting the
wall clock. The source driver's admission/snapshot state is also atomic, with
a snapshot reserving -1 rather than racing a new writer after checking zero.
Implementation and tests remain under `bench/spin_cacheline/`.

Guest W=1 source-module/client builds and **ten** directed tests pass. New checks
cover delayed readiness at 2/16 workers, partial creation and affinity failure
without entering the device, and actual driver admission helpers with an
in-flight writer and an exclusive snapshot. The built client and source module
have no mutex, condition-variable or libatomic fallback imports.

The focused **4-line, 16-thread, 10,000-iteration, two-pair** rerun passes all four
sessions: **640,000** exact measured operations and **318,627** returned JIT
bodies (159,215 and 159,412). All callers drain, both kdlock sessions retire with
state=2 and zero modules/frames/writers, and modules unload normally. Final idle,
kernel baseline and per-session fault checks pass. The ordinary provider artifact
is unchanged. Evidence verifies 111 source/support files, four binaries and four
generated image/assembly hashes. Existing provider objtool/locale warnings remain.
Earlier scans below use the previous synchronization and are not results for
this version; the full 80-session grid was not rerun. These checks do not measure
contention probability or establish saturated-lock performance.

Guest results: `/tmp/spin-cacheline-atomics-20260914`; host evidence:
`/tmp/spin-cacheline-atomics-evidence-20260914`. Archive
`spin-cacheline-atomics-20260914.tar.gz`, SHA256
`787c890767940dc852fe1468c142eb4967d94cc4121117858edb8b20a6241a31`,
contains source/binary identities, build/unit output, snapshot confirmation,
session data, generated code, CSV/JSON, baseline and final drain checks.

### Benchmark-only build separation

**2026-09-14, 17:55:49–18:00:55 +08.** Following the user's separation request,
all new benchmark code, including its driver and provider observations, lives
under `bench/spin_cacheline/`. The main `include/`, `kernel_module/` and existing
test fixtures have no changes relative to the checkpoint. The benchmark copies
the provider inputs into its own `.build/provider/` and applies the reviewed
`provider/observation.patch` there with fuzzy matching disabled. No production
source or ordinary provider build artifact is overwritten. See the
[build contract](../bench/spin_cacheline/README.md#编译和运行).

Both W=1 builds and all **eight** directed benchmark tests pass in the recovery
guest, including the new isolation/context-mismatch check. The ordinary module
has no `bench_*` parameters or `kd_bench` symbols. All **35** prepared provider
source files match the initial complete scan's instrumented sources byte for
byte. Independent Kbuild outputs have different whole-file hashes; the evidence
records both build identities and verifies the actual loaded binary separately,
without claiming binary reproducibility.

The focused rerun uses **4 lines, 4 threads, 10,000 iterations/thread, two pairs**:
all four sessions pass, with 160,000 exact measured operations and **59,181**
returned JIT bodies (29,318 and 29,863 in the kdlock sessions). Both pairs have
valid ratios; their median is 0.1766. All workers drain, both provider sessions
retire with state=2 and zero modules/frames/writers, modules unload normally, and
the final guest is idle. Kernel baseline and per-session fault checks pass;
existing objtool/locale build warnings remain. Source/binary capture verifies
110 files, four binaries and four generated image/assembly hashes. The ordinary
provider binary remains unchanged by both benchmark builds and the live scan.
The earlier 80-session scan below is historical; it was not rerun for this
directory/build isolation change.

Guest results: `/tmp/spin-cacheline-isolation-20260914`; host evidence:
`/tmp/spin-cacheline-isolation-evidence-20260914`. The archive
`spin-cacheline-isolation-20260914.tar.gz` has SHA256
`9d343867ebed1ff4ce86f7552628eabb6e9f7b3ccfb48abe2db16795a1d6f0cf`.
It includes the actual loaded sources/binaries, unit/build output, both build
identities, the initial postflight hash-assumption failure and corrected identity
check, snapshot confirmation, session logs, CSV/JSON, baseline and drain checks.

### Initial full scan

**2026-09-14, 17:28:12–17:34:11 +08.** The user requested an independent
`bench/spin_cacheline/` implementation and the complete default scan. This is
new work after the checkpoint, based on host commit
`43b27c04d4381014ecc8c67138999a2cf0e42295`, with uncommitted changes. The guest's
older Git metadata is retained separately; actual content hashes identify this
run. No existing benchmark, guest kernel, mutex workload or deferred correctness
feature was changed/added by this experiment. Shared quiet-mode logging and
returned-body accounting are the provider changes.

The final scan uses 73 frozen source/support files, four captured binaries,
Linux 6.1.159 Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`, `nokaslr`,
voluntary preemption, and guest CPUs 0–15 on NUMA node 0 with 64B cachelines.
The four Python dependencies match `disassem/requirements.txt` in the existing
guest interpreter; no package or kernel installation was needed. The host
monitor confirmed snapshot `pre_native_resume_20260905_1110` before live loading.
Both benchmark and SSH had outer timeouts. This does not establish exclusive
host cores or a new hook-reader lifetime guarantee.

| Final scan check | Result |
| --- | --- |
| Default grid | 1/2/4/8/16 lines × 2/4/8/16 threads; 10,000 iterations/thread; native→kdlock and kdlock→native per point |
| Measurement sessions | 80/80 completed: 40 native without kdlock loaded, 30 with actual JIT, 10 NO_JIT |
| Exact data and affinity | All 6,000,000 measured CS operations reconcile; active-line deltas, unchanged unused counters, per-worker binding and CPU/wall aggregation pass |
| Measured body evidence | 2,681,893 matching returned JIT bodies; all five cacheline sizes have evidence; preparation body totals were zero and were still subtracted explicitly |
| NO_JIT | Both kdlock sessions at two threads for each size have zero bodies; performance/ratios retained, no actual-JIT pass claimed for those points |
| Publication and quiet | Every kdlock session has one matching NORMAL entry, valid unchanged image hashes, exited translators, zero measurement writers/frames, and `jit_timing=0`; routine body/delegation/NO_RUN logs are absent |
| Cleanup | All 40 provider sessions retired with state=2, modules=frames=writers=0 before ordinary unload; all 80 sessions drained; final guest idle check passes |
| Kernel observations | No fault/error in the final scan's complete per-session kernel streams; no timeout or log overrun in that scan |

Median paired kdlock/native throughput ratios (two pairs per point):

| Payload lines | 2 threads (NO_JIT) | 4 threads | 8 threads | 16 threads |
| --- | --- | --- | --- | --- |
| 1 | 0.7318 | 0.1598 | 0.1493 | 0.1255 |
| 2 | 0.2887 | 0.1733 | 0.1513 | 0.1479 |
| 4 | 0.6733 | 0.1962 | 0.1722 | 0.1680 |
| 8 | 0.4545 | 0.2098 | 0.1992 | 0.1765 |
| 16 | 0.3891 | 0.2047 | 0.2425 | 0.2074 |

All ratios in these short VM trials are below one. They do not establish
statistical significance, lock-acquisition latency, zero observation cost or
a host-native baseline. Detailed throughput, amortized ns/op, thread CPU time,
per-pair ratios and JIT shares remain in the CSV/JSON results. Usage and the
measurement contract are in the [benchmark README](../bench/spin_cacheline/README.md).

Guest verification ran the new benchmark's seven directed tests (real client
with substituted device, real unrolled payload, data corruption, aggregation,
pair/CSV logic, default-off logging and returned-body counting), plus the seven
affected existing unit programs: `test_jit_body_witness.py`,
`test_jit_entry_scope.py`, `test_spin_outer_progress.py`, `test_remote_outer.py`,
`test_native_after_outer.py`, `test_mutex_outer_progress.py` and
`test_mutex_resources.py`. All pass after fixing the missing diagnostics include
and the logging fixture's unused variable in its disabled-trace mutation.
External modules build with W=1 and the client/daemon with strict warnings;
existing objtool unwind/RETHUNK and guest locale warnings are retained. The final
quiet fix reran the seven new tests and the affected spin outer unit. No basic,
extended or rare live matrix was added.

The initial batch `/tmp/spin-cacheline-20260914-a` stopped at session 6 during
preparation: a routine `KD_EXE_NO_RUN` log was mistakenly left outside quiet,
overwriting unread `/dev/kmsg` records and causing EPIPE. Five sessions had
finished; the sixth did not enter measurement. The runner stopped and preserved
the session. Inspection confirmed correct preparation data, exited callers and
translator, and zero frames; the identified daemon was then stopped, retirement
succeeded and both modules unloaded normally. `manual-drain.json` records this
later cleanup without converting the failed session into a pass. The corrected
routine branch now honors quiet while the real error branch remains visible;
the directed fixture exercises both. The new complete `-b` batch is one fresh
freeze, with no results borrowed from `-a` and no automatic retry of a failed
live session.

Commands and evidence:

```sh
make -C bench/spin_cacheline all test
make -C kernel_module W=1
make -C tests/unit run TESTS= PY_TESTS='test_jit_body_witness.py test_jit_entry_scope.py test_spin_outer_progress.py test_remote_outer.py test_native_after_outer.py test_mutex_outer_progress.py test_mutex_resources.py'
KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=pre_native_resume_20260905_1110 \
  timeout 3600s python3 bench/spin_cacheline/run.py --output /tmp/spin-cacheline-20260914-b
```

Guest full results: `/tmp/spin-cacheline-20260914-b`; host evidence directory:
`/tmp/spin-cacheline-evidence-20260914`. The host retains readable raw/pair/summary
CSV, JSON, synchronization hashes, the pre-report tracked patch and both archives.
Archive validation reconciled the 73 sources, four binaries, 80 session records
and 80 generated image/assembly hashes (237 checks). The source-manifest SHA256
is `2cc1a2f5ce81bfe8fe5b02887c3a1d921133589e0a80b1c7bbedeb01b2a3c5b7`.

| Archive | SHA256 |
| --- | --- |
| `spin-cacheline-20260914-b.tar.gz` (complete) | `177920566f22a3bcbac4ac53bd9283eaefb6524a5754a0d7ca28153924596039` |
| `spin-cacheline-20260914-a.tar.gz` (incomplete, separate) | `0aee4ff9c10ad801bedccf51d182fb8eaf65ce02cc69324dbdea21721f6484bd` |

These external `/tmp` artifacts are not supplied by a fresh checkout. The
post-run documentation adds no runtime result and does not change the captured
runtime inputs. No Git commit was requested or created.

## Repository Checkpoint

**2026-09-14, 16:31:40-16:32:11 +08.** The user requested code cleanup,
documentation and a Git commit after the reading handoff. This checkpoint
collects the accumulated implementation/test consolidation since
`1d5fc7259d96863aa143343d22c79aaf93023c9e`; it is not a new whole-plan acceptance.
The seven new runtime/test files and seven removed obsolete model/header files
belong to those earlier increments, not additional tests introduced here.

The final cleanup changes only five of the **211 runtime/test inputs**:

- `include/exe.h`: separate and format the owner-wait, handoff and queue timing
  contracts, preserving every function declaration.
- `kernel_module/exe.c`: bind the ten log labels explicitly to their timing
  enum entries and align the control-dispatch call. The enum order and label
  mapping are checked against the preceding source archive and are unchanged.
- `daemon/daemon.c`: wrap the usage string without changing its contents.
- `tests/regression.py` / `tests/paired_benchmark.py`: format the opt-in arguments,
  selection and timing table; add a purpose docstring to balanced pairing.
  Parsed execution ASTs, excluding docstrings, match the preceding freeze.

The same recovery guest, boot and isolated CPython 3.10 environment are used.
`test_daemon_policy`, `test_exe_registry.py`, `test_jit_entry_scope.py`,
`test_regression.py` and `test_benchmark.py` pass through the existing unit
Makefile. The external module builds with `KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1`;
daemon builds with `-O2 -Wall -Wextra -Werror`. Existing objtool/locale diagnostics
remain in the logs. No new unit entry, case or suite, no module load, no guest
kernel edit/build/install and no actual kernel-JIT rerun. The earlier 1,252 body
witnesses remain evidence of the previous native-handoff freeze only.

All 211 source hashes remain fixed during verification. Guest idle state and
the captured 18-source/9-build/config/live-ID kernel baseline are checked; the
previous JIT archive still matches its recorded SHA256. Commands, exit statuses,
logs, source archive and binary hashes are retained guest-locally in
`/tmp/kdlock-checkpoint.QPgJPY/`. README, the version overview and TODO now describe
this commit checkpoint rather than an indefinitely uncommitted working tree.
The two-CPU missing-JIT failure and all explicit deferrals remain open.
The final guest-local bundle is `/tmp/kdlock-checkpoint.QPgJPY.tar.gz`; its
adjacent `.archive.json` records SHA256, size and member count. These `/tmp`
artifacts are retained evidence, not files provided by a fresh Git checkout.

## Native Handoff Timing

**2026-09-14, 15:16:02-15:25:34 +08.** The optional native handoff envelope
starts in each backend before `kd_exec_native_begin`, including before spin's
remote-native publication, and finishes after successful owner-wait return,
before frame cleanup. It covers early waiter work that the inner wait omitted.
The two new unload rows are `native_spin_handoff` and `native_mutex_handoff`.
No owner, ACK, queue policy, guest kernel, frame/args layout or deferred flags/
guard/version mechanism changes. All clocks/updates remain default-off.

There are **211 frozen runtime/test inputs**, with nine changed since the
Python-environment freeze: `include/exe.h`, the executor and two backends,
`tests/paired_benchmark.py`, its existing unit driver and three existing
entry/spin/mutex fixtures. No new test method, program, case or suite. Producer
fixtures check start before borrowing and end after native wait but before pop;
the production counter fixture checks both backends, off/on behavior, inner/
outer containment and unchanged execution packets. Existing remote wait,
registry and paired-oracle checks remain selected.

The same recovery guest and CPython 3.10 venv from the previous increment are
used, with its bin first in inherited PATH. Six existing unit programs and an
external kdlock W=1 build pass; known objtool/locale diagnostics remain, not
warning-free acceptance. Default-off mode 4 and 8 then pass. The controller's
next command mistakenly uses `--repeats 1`; the paired CLI rejects it because
balanced ordering requires an even value of at least two. This is exit 1 before
creating its output directory or starting a workload, not a failed JIT session.
`verification.json` and the error log remain intact. After drain/source checks,
`run_remaining.py` runs only the previously unstarted phases with repeats=2;
`remaining-verification.json` records their success. No prior unit/build/live
phase is repeated and no different source freeze is spliced into acceptance.

| Existing scope | Result |
| --- | --- |
| Six guest units | Pass; paired observer has 113 checks, production driver 30 scenarios. |
| Timing off: mode 4/8 | 2/2 pass, 3+10 returned bodies; no timing rows. |
| Timing on: paired mode 2/5 | Eight sessions/four balanced pairs pass, 761 measured and total bodies, 1522 returning services; native comparison groups have no JIT and ten zero timing rows. |
| Timing on: mode 4/5/8 | 3/3 pass, 3+465+10 bodies across six loaded sessions; all original publication/state/service/owner gates retained. |

The pair command uses eight threads, workload 100000, loops16, runs2, CPUs0-7,
repeats2 and `--jit-timing`. Both complex commands use `tests/regression.py`,
explicit `--case` choices and timeout300; the latter adds `--jit-timing`.
Exact commands/environment/phase order are archived, and reusable commands
remain in [the timing guide](JIT_EXECUTION.md#可选的-jit-边界计时). Mutex positives
keep `mutex_jit=1`. No full-unit, basic live, extended, rare-case or two-CPU
missing-JIT rerun is added. Earlier CPU-mask results remain unchanged.

All **1,252** deduplicated returned-body records match saved entry images.
Every enabled session has ten valid rows; ordinary paired bodies retain the
1/3/2/1 dispatcher/wrapper/service/control counts and zero native waits/handoffs.
Complex native-on sessions have these nonzero owner intervals:

| Source case | Backend / owner intervals | Inner wait ns | Handoff ns | Native unlocks |
| --- | --- | --- | --- | --- |
| mode 4 shared native B | mutex / 1 | 58,582,030 | 58,590,898 | 2 |
| mode 5 CALL quota | mutex / 1 | 27,675,061 | 27,679,264 | 1 |
| mode 8 mixed completion | spin / 2 | 9,916,267 | 9,950,780 | 2 |

Each owner interval joins backend/task/outer-lock begin and completion records;
handoff and wait counts match, and handoff contains wait. Two remote spin owners
may cover the same logical suffix, so these four intervals are not four distinct
waiter executions. They include intentional test gates, borrowing/publication,
scheduling, logging, ACK and measurement work. Neither the totals nor their
difference isolate native instruction cost; nested intervals cannot be summed
as disjoint wall time. Full acquisition, observation attribution, parking and
performance/amortization claims remain P2 work.

Guest-local offline-verified archive: **169 members, 22,928,864 bytes**, including
source, both controller journals, original CLI error, units/builds, all selected
captures, independent joins and final default binaries. It was not exported:

```text
/tmp/kdlock-native-handoff.hmcbbC.tar.gz
655cae53edb6ae6f0f3d5469f455f17735428956ac4d61769d247e015f55a9c7
source.tar.gz
30b3cf02396720945b2299e831fb12286f07ca78821d6f91eeeb01a46dfc79dd
review.json
39cc501697f7be9e05633c719e5ddd1519b7c0eed5cd02d79c28f7f36d1bdff0
```

## Isolated Python Runtime

**2026-09-14.** Setup runs at 14:45:43-14:46:31 +08; initial runtime acceptance
at 14:48:39-14:53:01. This is a new Python-environment acceptance, not another
CPU-mask experiment or expanded edge-case matrix. **211 frozen runtime/test
inputs** differ from the queue-timing/oversubscription freeze only in:

- New `disassem/requirements.txt`, pinning miasm 0.1.5, future 1.0.0,
  pyparsing 2.4.7 and pyelftools 0.27 for CPython 3.10.
- `tests/regression.py` retains that recipe in source evidence, without
  collecting arbitrary generated `.txt` files.
- Its existing source-hash unit method checks recipe presence, mutation and
  generated-text exclusion. No new unit method, program, live case or suite.

The recovery guest uses `/usr/bin/python3` 3.10.12. A read-only apt simulation
is checked before adding exactly `python3.10-venv=3.10.12-1~22.04.18`,
`python3-pip-whl=22.0.2+dfsg-1ubuntu0.7` and
`python3-setuptools-whl=59.6.0-1.2ubuntu0.22.04.3`: three new packages, zero
upgrades/removals. No guest-kernel edit/build/install or global runtime pip
upgrade occurs. apt/debconf informational diagnostics remain in the setup log.

The fresh environment is `/tmp/kdlock-python-env.QQhMIk/venv`, with system-site
packages disabled. Its build helper is wheel 0.37.1; seeded pip/setuptools are
22.0.2/59.6.0. The four runtime wheels are prepared from public PyPI without pip
cache or dependency resolution, then installed with `--no-index --no-deps`.
miasm's local native-extension build stays in the guest, not the guest kernel.
`pip check` passes. The reusable commands and PATH/activation flow belong only
to [manual 3.3](PROJECT_GUIDE.md#33-检查依赖与空闲状态), not a parallel setup script.

The controller clears PYTHONHOME/PYTHONPATH, disables user-site imports and
puts this venv's bin first in PATH. Both controller/core environment records
identify its interpreter, prefix and all four package locations inside it;
daemon `execlp("python3")` inherits that same launch environment. No source
changes are needed to select the interpreter. These starting observations do
not attest every imported module or loaded JIT image throughout execution.

| Existing validation | Result |
| --- | --- |
| Guest `make -C tests/unit run` | 40/40 programs, no skipped dependency acceptance; 496 Python methods remain an inventory count, not the total assertion count. |
| Independent admission audit | 25/25; assembly/IR fixtures, not kernel-JIT execution. |
| Core mode 2 | Pass, four returned-body witnesses. |
| Core mode 7 | Pass, two witnesses. |
| Core mode 8, all three existing phases | Pass, ten witnesses. |
| Core mode 4, both existing phases | Pass, three witnesses; `mutex_jit=1`. |
| Core mode 5, normal and quota stages | Pass, 465 witnesses; `mutex_jit=1`. |

The **484** deduplicated timestamped body records all have matching saved
entry images. Original publication, service-return, full-state and physical
owner/ACK checks remain enforced by the existing drivers. Extra `jit_timing`
is off. Default driver builds run as usual; no separate W=1 build, basic live,
native-control, extended or rare-case suite is added. Earlier short-work/two-CPU
missing-JIT results are neither retried nor changed to PASS by this acceptance.

Package observations match before/after testing. All four venv distributions
provide 411 recorded `.py/.so` files (161/197/1/52), whose hashes are unchanged.
Global miasm/future provide 358 such files, also unchanged; distro pyparsing and
pyelftools provide no distribution file lists, so only their metadata was
captured. The first offline review rejects the mistaken assumption that every
global package has a nonempty list. Its script/error are retained; only the
evidence-scope statement is corrected, with no payload retry. Historical setup
fields named `global_unchanged`/`global_packages_unchanged` mean equality of the
captured observations, not retroactive byte coverage of those two packages.
No claim of byte-reproducible wheels, complete toolchain locking or immutable
JIT publication is made.

The guest-local, offline-verified archive has 100 regular members and
13,136,005 bytes, including frozen source, setup/test commands and logs, package
observations, four runtime wheels, all five captured cases, final default
binaries and the initial review error. It deliberately excludes the venv tree
and does not bundle a guest disk, kernel build or every build dependency:

```text
/tmp/kdlock-python-env.QQhMIk.tar.gz
e88f95e2f080118f709fc6dc1aa472f835b98c7e271cd3c40b987f9c68f0a077
source.tar.gz
56d9b3f78a0af71ef54052c4c1d1e3668b8b396e74a6b5208329941e650540c5
review.json
298ba322a9dda1721c0a93d12a680114b85f5c5506e5ec07a58a60400462351a
```

Source identity, drain and the same running baseline/boot remain required;
the archive stays in the guest and was not exported to the host. This closes
the Python install-recipe increment, not all of P1 or broader project acceptance.

## Mutex Oversubscription Assessment

**2026-09-14, 14:11:04-14:18:55 +08.** Existing ordinary mode 5 is measured
with eight workers on two CPU masks, 0-1 and 0-7. Both are on guest socket/node
0; affinity is an inherited allowed set, not a per-worker residency trace or
exclusive CPU reservation. All **210 runtime/test content hashes match the
queue-timing freeze**. No production/test code, new unit entry, live case or
suite is added. No unit, core or extended rerun; existing per-arm default
external-module/daemon/benchmark preparation still builds as usual.

The two planned commands differ only in CPU mask/output. Both retain
`mutex_jit=1`, default-off `jit_timing`, full state and returned-body gates:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/paired_benchmark.py \
  --mode 5 --threads 8 --workload 100000 10000 --loops 16 --runs 2 \
  --repeats 2 --cpus 0-1 --output /tmp/kdlock-mutex-oversub.ooLd7M/cpus-2
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/paired_benchmark.py \
  --mode 5 --threads 8 --workload 100000 10000 --loops 16 --runs 2 \
  --repeats 2 --cpus 0-7 --output /tmp/kdlock-mutex-oversub.ooLd7M/cpus-8
```

These are historical output paths, not destinations for retries. The first
controller exits 1 at 14:12:24 after the two-CPU short-work JIT arm fails.
Its six recorded sessions contain five accepted and one failed outcome; the
last two short-work sessions remain unrun. After inspecting this failure and
confirming drain, `run_remaining.py` runs only the previously unstarted
eight-CPU group at 14:17:10-14:18:55, passing 8/8. Both journals remain intact.
Thus the selected 16 sessions contain **13 accepted, one failed, two unrun**;
the aggregate is incomplete, not 16/16 or a spliced all-PASS matrix.

The failure is `measured JIT lacks matching returned bodies`, not a kernel
crash or corrupt result. Its 1710-byte generated image is published NORMAL and
unchanged before/after measurement, but the dmesg snapshots are identical:
zero body/hostcall/frame execution. Final counters show slowpath=245,
combiner=0, max_waiters=2, multi_slot=0 and no node overflow or context refusal.
All 12257 transitions, clock/scalar results and 2256 native acquire/releases
match; active tasks, waiters and reserved nodes are zero. The measured workload
itself exits 0, but no `arm.json` or successful pair is fabricated. Its
9.41 ms wall / 18.30 ms summed worker CPU record is **not a JIT performance
result**. It was not retried with forced promotion or injected queue pressure.

The six complete pairs retain the following individual-repeat ranges. Each
measurement contains 256 critical sections and 16 completed ioctls; each JIT
body joins its entry/lock to saved images and two successful native services
returning into JIT. Total returned bodies are **829**, with 1658 service returns:

| CPUs / work | Native wall ms | JIT-selected wall ms | Native worker CPU ms | JIT-selected worker CPU ms | JIT bodies per repeat |
| --- | --- | --- | --- | --- | --- |
| 2 / 100000 | 54.71-55.00 | 64.77-66.71 | 103.08-103.55 | 91.73-107.28 | 2, 3 |
| 8 / 100000 | 58.74-59.89 | 54.25-54.72 | 345.58-359.99 | 318.49-376.94 | 192, 220 |
| 8 / 10000 | 12.24-12.33 | 11.64-13.44 | 68.18-71.39 | 72.04-101.58 | 191, 221 |

The two-CPU long-work JIT share is only 0.78%-1.17%, versus roughly 75%-86%
on eight CPUs. One accepted two-CPU long-work session naturally records one
pre-publication node fallback; it completes under the original mutex without
frame/JIT failure or a leaked node. No capacity was reduced or stress role
added. All successful bodies match `jit_success=jit_resume`, original-owner
counts balance, native continuation is zero and extra timing rows are absent.

This evidence does not isolate busy-poll CPU cost, demonstrate consistent CPU
savings, establish parking benefit or prove fairness. The masks are measured
in successive blocks and each point has only two pairs/16 ioctl samples per
arm; scheduling, JIT share, logging and oracle cost remain included. No claim
of a universal speedup, amortization or a complete short-work/two-CPU JIT gate
is made. The short-work failure is a common-configuration participation limit,
not silently classified as a rare correctness exception.

A subsequent read-only review of local TCLock revision
`bbfb9f00a12af51dff6ca291cb9829a82960c2ef` confirms its linked-node
PARKED/PROCESSING handshake, while gate waiting and last-node handoff still
poll/pass onward. The two clean source files inspected have SHA256:

```text
src/kernel/rcuht/locks/komb_mutex.c
d4ae402d81307100ee2c03745643f458d3b42eab13e6e57735eebbd22643dc26
src/kernel/linux-5.14.16/kernel/locking/mutex.c
b7860666f3afe3b68c0b1f8696c9da0888321c34516bdf2fb16f3775ff226dce
```

These external files were not compiled, loaded or copied into the guest bundle.
The [design assessment](DESIGN.md#runnable-polling-and-event-parking) records
the required publication/lifetime handshake; copying only task sleep or enum
values would not be a port. Keep current polling while participation/policy
work remains open; no event parking, owner handoff or guest-kernel change is
claimed. This is a main-path investigation, not a new daily test requirement.

Independent review verifies all recorded byte/outcome archives, the failed
point's raw state and publication, successful body/image joins, pair metadata
and CPU records. It retains the helper's initial duplicate-`scope` report-key
error separately; fixing that helper did not rerun any workload. Evidence is
sealed **inside guest**:

```text
/tmp/kdlock-mutex-oversub.ooLd7M.tar.gz
20,929,798 bytes; 161 members
SHA256: 765b98f82d0b086bb8425abd2610625b74cf2a280c3238611c4d55c9b21292f2
Source archive: 1446536bb63004df77561cf5960eef161d315d79a05b64ef8c108d9524ae91a0
review.json: 433befd711cb483795d010d8e23c630b5e917155c8e43e1158102e92931af009
```

The recovery VM retains boot `e5f08f95-3b68-40f3-bc28-6a7ca42e7941` and the
captured 6.1.159 baseline, live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
No host build/test, VM restart or Git commit occurred. Later documentation
sync and final readback are separate from the immutable experiment archive.

## Private Queue Timing

**2026-09-14, 13:45:01-13:52:06 +08.** Five final verification phases finish
with unchanged **210 runtime/test inputs** and an idle recovery guest. Twelve
inputs differ from the native-owner timing freeze: three headers, `exe.c`,
both queue backends, the paired observer and five unit fixtures/observers.
No new unit entry, live case or suite is added; the inventory remains 40 unit
programs, 496 Python methods, 21 numbered shell drivers and 80 named cases.

Each spin/mutex node gains a 64-bit queue timestamp. Default-off, read-only
`jit_timing` now reports eight phases; native owners, final ACK order, frame
layout, two-word args and the guest kernel are unchanged. This is private
queue residence, not complete Linux lock-acquisition time. Boundaries, node
lifetime and commands are maintained in
[optional timing](JIT_EXECUTION.md#可选的-jit-边界计时).

The first freeze, `/tmp/kdlock-queue-timing.zh6qem`, fails its unit phase at
13:41:28-13:42:15: six programs pass and three fail compilation. The new timer
API uses `uint64_t`, but entry/registry/remote kernel-primitive fixtures provide
`u64` without a stdint dependency. The API and local timing test now use `u64`;
this repairs the compile dependency without changing width or behavior. Make
exits 2 before build/live phases on that predecessor; its six passes are not
combined with the new freeze. It is archived separately inside the final bundle.

| Final phase | Time (+08) | Result |
| --- | --- | --- |
| Nine affected existing units | 13:45:01-13:46:16 | 9/9. Entry/scope 2,842 checks / 18 detected mutants; registry 8,473 / nine; remote 6,941 / 11; benchmark 30 driver scenarios / 109 observer checks. Queue backends, node/resource and frame-capacity fixtures also pass. |
| External kdlock build | 13:46:16-13:46:20 | SELFTEST=0, NUMA=0, W=1, -j8 pass. Existing locale and nonstandard-stack/RETHUNK objtool diagnostics remain; not warning-free or a guest-kernel build. |
| Enabled paired mode 2/5 | 13:46:20-13:48:07 | 8/8 sessions, four balanced pairs; 840 measured/all returned bodies and 1,680 service returns. Native comparison groups have no JIT and eight zero rows. |
| Default-off core | 13:48:07-13:50:28 | 5/5; 481 bodies: mode 2=4, mode 7=2, mode 8=10, mode 4=3, mode 5=462. No timing rows. |
| Enabled nested mode 4/8 | 13:50:28-13:52:06 | 2/2; mode 4 has three bodies in two module sessions, mode 8 has ten in three sessions. Each load confirms Y and each drained session has eight valid rows. |

The paired commands use eight threads, workload 100000, loops 16, runs 2,
CPUs 0-7 and two opposite-order repeats. Every mutex-positive session retains
`mutex_jit=1`. Exact commands, exit codes and phase source checks are in
`verification.json` and `*-control.{json,log}`. There are **1,334 returned-body
witnesses** on this freeze, with matching saved image entries and original
state/owner oracles; this is not full instruction coverage or immutable-version
proof. No kernel fault signature or failed/rejected hostcall appears.

Independent review joins each enabled ordinary body to 1/3/2/1 dispatch/wrapper/
hostcall/control calls; native waits there are zero. Queue sample counts match
the corresponding drained slowpath statistics, with zero remaining waiters and
no pre-publication resource refusal in this selected scope:

| Queue interval | Paired samples | Paired sum ns | Nested samples | Nested sum ns |
| --- | --- | --- | --- | --- |
| spin_queue | 431 | 574353299 | 42 | 62592040 |
| mutex_queue | 431 | 550618412 | 11 | 428245738 |

The 862 paired queue samples include queue owners, not only the 840 delegated
bodies. Nested native waits retain two spin samples (8456971 ns) and one mutex
sample (123216443 ns), matching three begin/complete task/outer/backend identities
and four unlocks. Timestamped copies of the same session are deduplicated.
Elapsed queue/native intervals include deliberate gates and scheduling and may
overlap; do not add them to wall time or subtract queue time from dispatch.

The real timer unit checks both backends, default-off zero clock reads,
exactly-once timestamp consumption and an endpoint saved before simulated body
time. Existing progress fixtures check consumption before native/wake/reuse and
retention after no-body refusal. Those fixture doubles alone do not prove live
queue-head behavior; the live slowpath joins supply separate evidence.

Only these affected units and representative cases were run: no full 40-unit,
admission audit, extended matrix, excluded basic 0/1/3 or new rare-schedule sweep.
Other results remain historical. Complete acquisition/native-suffix accounting,
observation overhead, hardware events, amortization and the native-delegation
comparison remain open performance work. Deferred guards/flags/versioning are
unchanged, and rare-case generalization is not a current delivery gate.

`review.py` validates source/build/protocol archives, body/image publication,
all eight rows, slowpath/native identities and final default binaries. The
immutable bundle is retained **inside guest**, with the initial failed freeze:

```text
/tmp/kdlock-queue-timing.a6C070.tar.gz
26,097,909 bytes; 186 members
SHA256: 1dea3df2723fe98516335d6a2ca93bc96ffe66fa3fa5ba5d8965e638192c141b
Final source archive: 3c6ba5bbcd4b9e83e37cdc4143f1ef4fbac719becd6f96ed9eb77f0718b7c9ab
review.json: 41794c2478a7867f8752288680f85f01998fb5e052b77aa969d4e05f894761fe
```

Pre/post baseline checks match 18 source/interface files, nine build files, two
bundles/config and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`;
boot remains `e5f08f95-3b68-40f3-bc28-6a7ca42e7941`. No host test/build,
guest-kernel edit, VM restart or Git commit was performed for this increment.
Later document sync/readback is separate from the immutable evidence bundle.

## Native Owner Wait Timing

**2026-09-14, 00:03:29-00:12:08 +08.** All five final verification phases
finish with unchanged inputs and an idle recovery guest. The **210-input**
freeze changes `exe.c`, `kd_exec.c`, `exe.h`, the common loader/selection and
paired observer, five unit driver/fixture files, and 16 scripts with mechanical
load-site conversions.
The latter preserve original module arguments and bounded insmod timeouts.
No new unit program, fixed live case or suite is added: 40 programs, **496**
Python methods, 21 shell drivers and 80 named cases. Guest kernel, two-element
args, frame/node layouts, native owners, and deferred guard/flags/version work
are unchanged. Flow and commands live in
[optional timing](JIT_EXECUTION.md#可选的-jit-边界计时).

Two predecessors are retained, not combined into final acceptance:

- `/tmp/kdlock-native-timing.h9MnF4`: 23:49:07-23:50:57 on September 13,
  39/40 units. The new remote fixture exposes a signed/unsigned comparison
  warning under `-Werror`; make exits 2 before module build/live. An explicit
  unsigned cast after the negative-value check preserves the overflow rule.
- `/tmp/kdlock-native-timing.UxrYAe`: 40 units, W=1 build and eight paired
  sessions pass. Review then finds direct script insmod calls bypassing the
  optional selection. The outer controller is stopped, and the current core
  runner drains through mode 8 and observes STOP before mode 4. Controller
  termination/SSH 255 is deliberate, not a guest/JIT failure. Its child PID is
  subsequently absent and idle is checked before any edit. Direct loads are
  rewired before the final freeze; no enabled complex result from this
  incomplete predecessor is claimed.

| Final phase | Time (+08) | Result |
| --- | --- | --- |
| Units | 00:03:29-00:05:26 | 40/40. Remote production wait/packets: 6,797 checks, 11 detected mutants; entry/scope: 2,494 checks, 18 mutants; registry: 8,465 checks, nine mutants; benchmark: 30 driver scenarios / 102 observer checks; regression: 48 methods. |
| External kdlock build | 00:05:26-00:05:28 | SELFTEST=0, NUMA=0, W=1, -j8 pass. Existing locale and non-standard-stack/RETHUNK objtool diagnostics remain; not warning-free. |
| Timing-enabled paired mode 2/5 | 00:05:28-00:07:15 | 8/8 sessions, four balanced pairs, eight threads/workload 100000. 730 measured/all bodies, 1,460 service returns; six exact rows, native comparison rows zero. |
| Default-off core | 00:07:15-00:09:35 | 5/5, 484 bodies: mode 2=4, mode 7=2, mode 8=10, mode 4=3, mode 5=465; no timing rows. |
| Enabled complex native waits | 00:09:35-00:12:08 | 5/5, 479 bodies: mode 4=3, mode 5=464, mode 8=10, registers-1-3=1, registers-4-3=1. Every load confirms Y, including two mode-4 and three mode-8 sessions. |

The final freeze has **1,693 returned bodies**, with saved images matching their
entries, original full-state/owner oracles and drained teardown. Ordinary paired
counts remain 1/3/2/1 per body; both native-wait phases are zero there. The explicit
complex cases instead contain:

| Native interval | Samples | Sum ns | Completed / unlocks |
| --- | --- | --- | --- |
| mode 4 shared native B, mutex owner | 1 | 152990184 | 1 / 2 |
| mode 5 CALL quota, mutex owner | 1 | 31345991 | 1 / 1 |
| mode 8 mixed shared-B relay, spin owners | 2 | 9954444 | 2 / 2 |
| registers-1-3, spin owner | 1 | 15365 | 1 / 2 |
| registers-4-3, mutex owner | 1 | 27710 | 1 / 2 |

Thus three spin and three mutex wait samples match the begin/complete task,
outer-lock and backend multisets: six completions and nine unlock records.
No failed/rejected hostcalls or invalid timing row appears. The synthetic clock
unit exercises two-to-eight nested waits, both backend classifications, unchanged
full software packets, success/error returns and default-off zero clock reads.
It does not restore hardware flags or prove arbitrary concurrent counter behavior.

These intervals include deliberate test gates, scheduling, owner-side unlock and
finish handling. They begin after publication, may miss a native prefix, and
relay intervals overlap; sums are not independent wall/CPU costs or a native
performance baseline. No default-off paired sweep, standalone admission audit,
64-case extended run or excluded basic modes 0/1/3 was rerun on this freeze.
Broader queue/suffix/observation costs, amortization, P1/P2 and C1/C2/C5 remain open.

Independent `review.py` verifies the standard archives and raw per-phase logs,
joins bodies/images and native identities, and deduplicates copied six-row
sessions. It archives the final evidence and both predecessors **inside guest**:

```text
/tmp/kdlock-native-timing.e0ZC5F.tar.gz
47,069,958 bytes; 342 members
SHA256: b8494b5ddcc1196b968bdd8b5912a422d2ecdd804b3e314f6d03707f9037ff5a
Final source archive: 0c567db89f340f810f067ebc75fb1d0a65542b864fdad6eaf12d9c66a6f799e2
review.json: 200643649139fa8817c5ad29a83925bd431e48a364448479469ddc10234d4621
```

Pre/post baseline checks match 18 source/interface files, nine build files, two
bundles/config and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`;
boot remains `e5f08f95-3b68-40f3-bc28-6a7ca42e7941`. No host test/build, guest-kernel
edit, VM restart or Git commit was performed for this increment. Later document
sync/postflight is separate from the immutable archive above.

## JIT Boundary Timing

**2026-09-13, 23:08:09-23:15:58 +08.** All five verification phases finish with
unchanged source and an idle recovery guest. Runtime changes are confined to
`kernel_module/exe.c`: default-off, read-only-after-load `jit_timing`, inclusive
C-boundary observations and drained unload totals. Seven existing driver/fixture
files wire the option and verify its contract; all **210 runtime/test inputs**
are frozen together. No new unit entry, fixed live case or suite, guest-kernel
edit, wrapper argument/layout change, owner handoff, access-time guard or flags
repair is introduced. Flow and interpretation live in
[boundary timing](JIT_EXECUTION.md#可选的-jit-边界计时).

Before these edits, the existing guest `test_exe_registry.py` fails to compile:
the scalar service adapter uses `regs->di` and `int_sqrt`, but its registration
fixture has only `ax` and no scalar primitive declaration. This is a real test
dependency regression after the earlier scalar increment, not a JIT runtime
failure or accepted negative. `registry-baseline-failure.json` preserves the
command, exit 1 and compiler output. The fixture now supplies the typed field
and a primitive that fails if registration unexpectedly invokes it; no copied
sqrt algorithm or weaker service check is added. Service-change instructions
now select this producer/lifecycle unit independently of its imported helpers.

Guest commands, with per-phase command/exit/source records and bounded outer
timeouts, are retained in `verification.json` and `*-control.{json,log}`:

```sh
cd /root/host_fs/kdlock
make -C tests/unit run
make -C kernel_module KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/paired_benchmark.py \
  --mode 2 5 --threads 8 --workload 100000 --loops 16 --runs 2 \
  --cpus 0-7 --repeats 2 --output /tmp/kdlock-jit-timing.d2vPGs/paired-off
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/paired_benchmark.py \
  --mode 2 5 --threads 8 --workload 100000 --loops 16 --runs 2 \
  --cpus 0-7 --repeats 2 --jit-timing --output /tmp/kdlock-jit-timing.d2vPGs/paired-on
KDLOCK_RECOVERY_CONFIRMED=1 python3 tests/regression.py \
  --suite core --timeout 300 --output /tmp/kdlock-jit-timing.d2vPGs/core
```

These are recorded historical destinations; manual repeats require new paths.
The shared dispatcher change justifies the existing full unit inventory and
complex core selection, not a new daily prerequisite or 64-case rerun.

| Phase | Time (+08) | Result |
| --- | --- | --- |
| Units | 23:08:09-23:10:03 | 40/40 existing programs pass. Entry/scope/service/timing consumer: 2,362 checks, 18 detected mutations. Registry: 8,457 checks, nine detected mutations. Benchmark: 30 C-driver scenarios and 97 observer checks. |
| External module build | 23:10:03-23:10:06 | Exit 0 with `W=1`. Existing locale and nonstandard-stack/RETHUNK objtool diagnostics remain in the log; not a warning-free claim or a guest-kernel build. |
| Paired timing off | 23:10:06-23:11:52 | 8/8 sessions, four balanced pairs; 826 measured JIT bodies, no timing rows, no native-arm JIT. |
| Paired timing on | 23:11:52-23:13:37 | 8/8 sessions, four balanced pairs; 773 measured JIT bodies; four validated timing rows per session, native rows all zero. |
| Core, default timing off | 23:13:38-23:15:58 | 5/5: mode 2=4, mode 7=2, mode 8=10, mode 4=3, mode 5=465 distinct returned bodies across saved phases. |

The enabled ordinary sessions have 773 dispatches, 2,319 actual wrapper calls,
1,546 successful hostcalls/returns and 773 control calls, all timing invalid
markers zero. Their body/entry/physical-lock identities match the published
images; preparations happen to have no returned body in this freeze, although
the counter contract covers the entire session. Off/on paired runs together
have **1,599 bodies and 3,198 service returns**. Every arm completes 12,257 exact
state transitions and clock/scalar observations, with no native continuation,
kernel fault or leftover frame/writer/module. Normal JIT admission, witness,
service and full-state checks are not replaced by timings.

The default-off core adds **484 bodies**, for **2,083 in this freeze**. Mode 4
includes its same-CPU and shared-native-B phases; mode 8 includes all three
stages; mode 5 retains normal two-service returns and its separate 17th-clock
native suffix with original-owner ACK. Enabled timing on these nested/quota
kernel paths is not live-certified by this batch. Software fixtures compare
complete frames, registry records and CALL stacks off/on through successful,
refused, progressed-error, quota-native and synthetic-fault exits; they do not
restore hardware flags or prove arbitrary concurrency.

Illustrative enabled per-call means, not pure instruction/service latency:

| Ordinary mode | Body counts in two repeats | Dispatch mean (us) | Wrapper-call mean (us) | Hostcall-dispatch mean (ns) | Control mean (ns) |
| --- | --- | --- | --- | --- | --- |
| 2 | 159 / 211 | 216.076-226.002 | 71.084-74.310 | 135.038-142.336 | 83.957-97.308 |
| 5 | 222 / 181 | 214.472-225.030 | 70.184-73.580 | 136.730-143.180 | 102.284-110.061 |

There are three wrapper samples per body, so its mean cannot be compared as
one complete CS cost. The dispatcher residual contains observations/bookkeeping
and clock overhead. Off/on JIT worker envelopes are mode 2: 57.608-58.527 /
57.657-58.078 ms; mode 5: 56.269-60.203 / 56.253-57.584 ms. JIT participation
differs between repeats; these whole-run differences do not isolate timing
overhead or establish amortization. Nested inclusive intervals may overlap,
and cumulative elapsed is not CPU or experiment wall time. Full queue/native
suffix costs, hardware events, broader sweeps and TCLock's faithful third arm
remain open; earlier profile/small-work/matrix evidence is not merged here.

`review.py` independently reads archived raw phases and four timing rows, joins
body counts to entry/lock/image hashes, checks state/service/native/origin
oracles and verifies exact archive membership. The core phase observer
deduplicates copied timestamped body lines. No archive/source export is made;
all artifacts stay in the recovery guest. The complete guest-local package is:

```text
/tmp/kdlock-jit-timing.d2vPGs.tar.gz
bytes: 31641605; members: 235
SHA256: 89634b20f4758dbcf017be545e7fb2a2046c4d457ecd553951f2fc3c69bcbd35
source archive: ce90a79fe8200061456c9a2a00f35e82f78a86c2de0e758320fcb72b705d2007
review.json: 4c985ab353a613f97a576baf9aa0f415adda95d83d458ea8aaed9961fddcff8d
```

The archive retains the pre-edit failure, current source, units/build logs,
both paired runs, every core phase/image, verification/review scripts and
final default binaries. Loaded paired binaries are checked against each arm's
own build archive; final binaries against the last core build, not assumed
identical across SELFTEST rebuilds. Postflight confirms baseline 18 source /
nine build / two bundle files and running Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`, unchanged boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941` and source hashes. No standalone admission
audit, 64-case extended run or direct excluded mode 0/1/3 was rerun here.
The final x86-64 module's `__param_jit_timing` record is also read directly:
its permission field is `0444`, matching the load-time-only source declaration.

## Context-Symbol Matching

**2026-09-13 +08:** first profile the unchanged translator, then optimize only
`disassem/context_policy.py` and extend the existing symbol-family method in
`tests/unit/test_context_policy.py`. The new **210-input freeze** differs in
exactly these two files. No guest-kernel, native-owner, wrapper/args, access-time
guard, flags or code-version change. No new unit program, fixed live case or
suite is added; the inventory remains 40 programs / 495 Python methods.

The original matcher makes **4,316,572 fnmatchcase calls** for 148,986 kallsyms
names per image. Use stdlib `fnmatch.translate` to compile the unchanged glob
rules into one anchored regex union, retaining each branch's flags/end anchor,
case sensitivity and clone-name stripping. No symbol/address/admission cache
is introduced. Both real guest snapshots classify all names identically and
produce identical maps of **326 sensitive names and interval ends**. The
existing unit adds positive/near-miss/clone/newline/case differential inputs;
it has no timing threshold. Broader dynamic-address safety remains deferred.

The one-off guest observer follows [the profiling flow](JIT_EXECUTION.md#35-翻译器剖析):
prepare/publish ordinary mode 2 or 5, stop the daemon after drain, and translate
the same entry six more times into separate workspaces (three plain and three
profiled, alternating order). Only then run the ordinary 8-thread, 16-loop,
workload-100000, 2-ioctl-per-thread JIT payload. The profile images are never
uploaded. `jit.S`, `jit.bin` and `bin.txt` agree byte-for-byte across all repeats,
both implementations and the published image, at the same source RIP. Module,
daemon and benchmark hashes match across the four profiling sessions.

| Stage (+08) | Command / result |
| --- | --- |
| Original profile 22:09:30-22:11:01 | `/tmp/kdlock-compiler-profile.XJsD3o/profile.py`: 12 standalone translations, 6 raw profiles and 2 JIT payloads; 439 bodies / 878 service returns, original freeze only |
| Units 22:16:10-22:16:25 | `make -C tests/unit run TESTS= 'PY_TESTS=test_context_policy.py test_context_guards.py test_context_memory.py test_jit_diagnostics.py test_text_regions.py'`: 5/5 programs, respectively 100/40/51/13/30 methods |
| Audit 22:16:25-22:16:26 | `python3 -B tests/audit_context_spills.py`: 25/25, 17 expected refusals and 8 accepted assembly cases; not kernel JIT |
| Optimized profile 22:16:27-22:17:32 | `/tmp/kdlock-symbol-union.s7AJib/profile.py`: 12 standalone translations, 6 raw profiles, 2 real symbol-map comparisons, mode 2/5 actual JIT |
| Complex/refusal 22:17:32-22:21:06 | `KDLOCK_RECOVERY_CONFIRMED=1 python3 -B tests/regression.py --suite admission --case mode-4 --case mode-8 --timeout 300 --output /tmp/kdlock-symbol-union.s7AJib/live`: 14/14 accepted |

On the optimized freeze, mode 2/5 return **192/222 bodies** with **828** total
clock/scalar exits, executions and resumptions, no service failures or native
continuation. Each completes all **12,257** state/clock/scalar updates. Mode 4
adds **3 bodies** across both phases; mode 8 adds **10** across all three phases,
including shared-B mixed completion. Thus **427** distinct returned-body records
have matching saved images. Twelve admission cases have no body execution.
Do not merge the original freeze's 439 bodies into this acceptance. No full
core/extended matrix, quota-specific or small-work paired sweep was rerun.

| Mode | Plain CLI wall, original (s) | Plain CLI wall, optimized (s) | Real daemon-child wall, original -> optimized (s) |
| --- | --- | --- | --- |
| 2 | 3.288529-3.311990 | 1.590299-1.597407 | 3.335381 -> 1.602690 |
| 5 | 3.270619-3.311192 | 1.585216-1.616147 | 3.328917 -> 1.594221 |

These are three plain samples per mode/version, plus one independent daemon
child each; not a broad amortization or steady-state speedup claim. The daemon
RSS changes from 50,392 to 50,488 KiB. The separate snapshot-reading observer's
process-tree RSS is not directly comparable to compiler-only memory.
Console settings remain `4 4 1 7`, `ignore_loglevel=N`, with ttyS0.

The raw cProfile runs are much slower (about 7.0 s original, 2.8-2.9 s optimized).
Selected **profiled cumulative** ranges below locate the hotspot; parent/child
rows overlap and must not be added or interpreted as uninstrumented pass costs.
Whole-script profiles also retain translator-import/initialization call records,
not the interpreter startup before profiling begins.

| Function | Original (s) | Optimized (s) |
| --- | --- | --- |
| `load_context_symbols` | 4.866-4.895 | 0.669-0.699 |
| `is_context_symbol`, included above | 4.376-4.398 | 0.209-0.218 |
| `get_kernel_symbol`, 9 calls | 0.492-0.496 | 0.498-0.505 |
| `read_kernel_addr_data`, 7 text/metadata reads | 0.0196-0.0215 | 0.0187-0.0204 |
| `decode_regions` | 0.097-0.106 | 0.096-0.107 |
| `find_segment_policy_error` | 0.913-0.918 | 0.910-0.920 |
| `translation.translate`, 74/81 instructions | 0.0047-0.0052 | 0.0047-0.0052 |
| `build_jit_binary`, including child waits | 0.051-0.056 | 0.046-0.055 |

Initial `review.py` stopped on an overstrict whole-ELF identity assertion after
all tests passed. Mode 8 rebuilds the default external module after SELFTEST;
its final ELF differs only in non-allocated `.BTF` bytes, with every other
section's flags/bytes equal. The profile ELF remains in mode 4's build archive.
`review-final.py` checks both recorded identities and retains the failed observer
and diagnostic; no test rerun, source rollback or existing archive replacement.

The final guest-only archive `/tmp/kdlock-symbol-union.tar.gz` contains both
profile freezes, scripts, raw pstats, symbol snapshots, logs, images, the
14-case evidence and both build identities: **27,913,092 bytes, 482 members**.
Exact-member/hash verification succeeds. Archive SHA256:

```text
1652027f1b1ebb543d0d7cf66ec9aa586bc4c9efe6de2621510d740eed604aaf
```

Optimized source archive SHA256:
`f573e8de01d44657e5313c59a86d4a94ef78d0232c981c61c0105a113b12e4fe`.
Review SHA256: `99cd1735f9a3d9165b12f54236bbd475bb3c2c657e27811e65a00bd751ecef72`.
The /tmp observer scripts are experiment evidence, not new checkout commands;
the reusable CLI flow is documented above. Kernel queueing/hostcall costs,
hardware counters, amortization and a faithful native-delegation arm remain open.

## Translation Resource Accounting

**2026-09-13, units 21:26:02-21:26:07, live 21:30:29-21:37:54 +08:**
add optional daemon `--metrics`, explicit option forwarding in `start_daemon`,
and preparation/translation/console accounting in the existing paired driver.
Extend the existing daemon and benchmark units. These are **six changed inputs**
relative to the severity freeze: `daemon/daemon.c`, `tests/common.sh`,
`tests/benchmark_arm.sh`, `tests/paired_benchmark.py`,
`tests/unit/test_daemon_policy.c`, and `tests/unit/test_benchmark.py`.
All 210 runtime/test hashes match host, units, live and independent review.
Only the daemon binary changes among the four archived experiment binaries;
workload, lock modules, translator, guest kernel, two-word args and all explicitly
deferred features remain unchanged. No fixed case, unit program or suite is added.

Three affected guest unit programs pass: daemon production launch/cache/wire
checks, **30 driver scenarios / 70 paired-observer checks**, and **47 existing
evidence-controller methods**. The daemon tests retain real fork/exec/reaping
with a substituted device, preserve the unmeasured default, and inject EINTR,
before/after clock failures, regressing time and invalid resource values.
Independent JSON inspection finds 11 actual measured child records: three
successes, three deliberate native-only exits and five expected launch/script
errors. These negative fixtures pass their assertions; they are not failed
kernel workloads or JIT evidence. Unit evidence is
`/tmp/kdlock-translation-cost-units.qBkEMg` in the guest.

After baseline, idle and recovery snapshot checks, run:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B -u tests/paired_benchmark.py \
  --mode 2 5 --threads 8 --workload 10000 100000 --loops 16 --runs 2 \
  --cpus 0-7 --repeats 4 --timeout 300 \
  --output /tmp/kdlock-translation-cost-live.qBkEMg
```

The actual kernel log capacity is 524288 bytes; a prior 256-CS mutex arm saves
about 139 KiB of dmesg. Instead of starting the initially considered 2048-CS
arms that risk overwriting logs, this experiment retains 256 CS / 16 ioctl
samples per arm and increases independent balanced repeats to four. This is
a pre-run sizing decision, not a retry or relaxed body/log gate. No printk
setting is changed and no witness/log is disabled. Per-phase, publication,
final and cross-arm console observations agree: `4 4 1 7`, `ignore_loglevel=N`,
ttyS0 present. Discrete observations do not prove continuous sysctl control.

All **32 sessions / 16 pairs pass** with `mutex_jit=1`. Independent inspection
checks exact phase commands and worker completions, identical loaded binaries,
preparation, CPU mask, NORMAL publication, stable images, matching body entry/
physical lock and full state/owner/drain oracles. Native arms contain no JIT
entry, installation, image or body. All **3,250 returned bodies** occur between
the measured dmesg snapshots; **6,500 exits/executed/resumed** match the two
services, with zero rejects/failures/quota exits and no native-continuation
frame. Each arm finishes at 12257 complete state transitions. No per-case
kernel fault is found. These counts do not certify every CS/instruction or
immutable code identity.

Ranges below span four individual opposite-order pairs at each parameter point;
ratios are calculated per pair, not from independent range endpoints or pooled
modes. Every repeat remains in `comparison.json`.

| Mode | Workload | N wall ms | J wall ms | JIT bodies / 256 measured CS | J/N throughput |
| --- | --- | --- | --- | --- | --- |
| 2 | 10000 | 11.612-12.492 | 13.416-15.512 | 189-210 | 0.755-0.865 |
| 2 | 100000 | 121.330-131.468 | 53.537-59.212 | 221 | 2.134-2.266 |
| 5 | 10000 | 10.780-12.629 | 12.858-14.586 | 160-222 | 0.768-0.867 |
| 5 | 100000 | 57.256-59.840 | 55.224-58.738 | 191-222 | 0.975-1.064 |

Each JIT arm has exactly one successful translator-child record, joined to
the published RIP/pid/tgid/kind and bounded by its preparation interval. Raw
daemon records independently reproduce the `costs` summaries. Child wall time
is **3265.824-3398.470 ms**, summed child user/system CPU **3265.504-3398.064 ms**,
and largest-process high-water RSS **50392 KiB** in every record. All have zero
major faults. The record includes launch/imports, analysis, assembly and waited
descendants, but excludes polling/workspace setup/upload and kernel JIT. It is
not pure code-generation time, concurrent tree memory or a hardware counter.
JIT preparation spans **8765.387-9681.484 ms**, versus native
**3332.223-3375.239 ms**; fixed waits and preparation work are included.
Translation can overlap promotion, so these intervals must not be added.

The smaller workload does not benefit in these instrumented pairs; the larger
mode-2 ratio does not establish universal speedup. Compiler-pass profiling,
kernel queue/hostcall/observation costs, hardware events, socket/input coverage,
stable tail estimates, measured amortization and a faithful third arm remain
open. No nested/quota/core/extended or admission gate is rerun; prior evidence
is not spliced into this freeze. Execution/field contracts are in the
[paired flow](JIT_EXECUTION.md#34-原生锁与-jit-配对实验).

The independent review creates and verifies the guest-only outer archive with
exact member/hash checks, including units, raw phase/daemon logs, generated
images, sources, observers and pre-run log-capacity metadata.
`/tmp/kdlock-translation-cost-live.qBkEMg.tar.gz`: **41,135,284 bytes,
308 members**, SHA256:

```text
c9d118eaa8529be09a6fce16267c49a5cde4e18c5a3abdd2df992d195b29aa1b
```

Source archive SHA256:
`fae73383e29f88f2a86d260eb800d3fa76ad984d1f29cb3746429bf3614826bc`.
`translation-review.json` SHA256:
`1e58de2276e08b6603c5ae71d38faba3a10edf7ef20efd57987806d7a6cfd30f`.
`comparison.json` SHA256:
`20ca5e7692fbcc161727c214c9662501e8d018cb8ae96042545a3f85cb4b8a9e`.
No guest archive is exported. Review ends idle on Linux 6.1.159, boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`, with unchanged runtime/test sources.
Before/after baseline checks pass 18 source files, nine build files, two
bundles and config, with running Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. Host static checks pass 11 Markdown
files / 638 local links, the unchanged inventory and 210 source hashes, Python
AST, shell syntax and `git diff --check`. No host build or test executes.
The broader C1/C2/C5 and P1/P2 tasks remain open; this is not whole-plan acceptance.

## Mutex Routine Log Severity

**2026-09-13, unit 20:40:19-20:40:20, paired live 20:42:50-20:44:42,
nested live 20:44:43-20:45:17 +08:** only the routine `mutex_debug` severity
changes from `KERN_ALERT` to `KERN_INFO`, with a purpose comment. Its two
queue/JIT-entry call sites, text, arguments, enabled logging and body witnesses
remain intact. No warning/error branch, locking, JIT translation, owner, guest
kernel, two-word args or deferred feature changes. The existing mutex outer
unit and fixture are extended; these are the only three changed runtime/test
inputs relative to the preceding paired freeze. All 210 hashes agree across
host, units, live runs and the independent drained review.

The diagnosis inspects actual archived module ELF strings: both routine
formats in the prior module use ALERT (level 1), while both new formats use
INFO (level 6). The former ELF SHA256 is
`d4ac1d3916bfacf71874f190da292f9892d9439e0013aea88d6fe4cf4b7b5046`.
The running guest uses a ttyS0 serial console, `/proc/sys/kernel/printk` is
`4 4 1 7`, and `ignore_loglevel=N`; before/after controls for both commands
are identical. On this earlier freeze the outer observer retains these controls;
the paired controller did not yet collect them automatically. No console sysctl
was changed. An exact timestamped old routine line appears in host serial;
an exact new line remains in paired dmesg but is absent from serial at the
follow-up observation. This is a bounded observation, not log authentication.

Read-only source hashes match the guest's printk and serial sources: printk
stores the message before console-level filtering, and a caller can flush
console records synchronously; the serial driver emits characters through its
console callback. Thus native kdlock debug output can delay execution while
the physical mutex is retained. This is not a large `printk` callee being
translated inside the sandbox; these mode-5 JIT services remain clock and
`int_sqrt`. No ftrace, cycle or hardware-event attribution was performed.

The existing guest unit passes **157 checks, five scenarios, zero failures**,
retaining five INFO traces. It compiles the actual production macro against
the guest kernel severity definitions and substitutes only the printk sink.
Both ALERT-regression and disabled-trace mutants compile and then fail the
explicit assertions; compiler failures/crashes are not accepted as detection.
No additional unit program, Python `test_*` method or named live case is added.

With recovery confirmed, the two commands are:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B -u tests/paired_benchmark.py \
  --mode 5 --threads 4 8 --workload 100000 --loops 16 --runs 2 \
  --cpus 0-7 --repeats 2 --timeout 300 \
  --output /tmp/kdlock-mutex-cost-live.EdI0Sf
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B -u tests/regression.py \
  --case mode-4 --timeout 300 --output /tmp/kdlock-mutex-cost-nested.EdI0Sf
```

All **eight paired sessions / four pairs pass** with `mutex_jit=1` in both
arms. The unchanged paired gates independently match phase commands, loaded
binary hashes, preparation, inherited CPU mask, NORMAL entry/physical lock,
stable saved images and complete state/owner/drain oracles. Native arms have
no entry/image/install/body. All **632 returned JIT bodies** occur in the
measured phases, with **1,264 exits/executed/resumed**, zero hostcall failures,
rejects or quota exits, and no native-continuation frame. Full state counts
remain 12129 / 12257 for four/eight threads.

| Threads | Order | N wall ms | J wall ms | JIT bodies / measured CS | J/N throughput |
| --- | --- | --- | --- | --- | --- |
| 4 | N, J | 33.397 | 32.521 | 94 / 128 | 1.027 |
| 4 | J, N | 35.247 | 31.978 | 94 / 128 | 1.102 |
| 8 | N, J | 59.366 | 56.856 | 222 / 256 | 1.044 |
| 8 | J, N | 60.468 | 64.926 | 222 / 256 | 0.931 |

Each JIT arm retains 189/189/445/445 routine lines respectively, with one
combiner, no handoff and no not-ready/frame/node/context failures. JIT success
and service-resume counts equal its body count; physical origin acquisitions
and releases balance. The prior 8-thread envelope was about 2.1 seconds and
the prior 4-thread participation 2/128. These controls and the limited change
support serial logging as a major contributor to that anomaly, including
changed queue timing; they do not isolate every remaining cost or prove a
general speedup. More verbose console settings can emit INFO again. Logging,
body witnesses, full oracles, scheduling and services still affect the results.

Mode 4 also passes both existing phases: seven roles/two CPUs produce one JIT
body without a native frame; the fresh shared-B session produces two JIT
bodies, one native frame and two owner ACKs. Independent phase-archive reading
joins all three returned-body entries to saved images. Total scoped evidence
is **635 returned bodies**, not a count of fully translated instructions or
an immutable-version proof. No per-case kernel fault is found. No other mode,
quota/OOO phase, unit program, core/extended matrix or admission audit is rerun;
their earlier results are not combined into this freeze.

The guest-local outer archive contains the paired run, nested run, units,
observers, console/ELF audit metadata and control logs. Independent verification
checks exact membership/hashes and confirms the preceding paired archive is
unchanged. `/tmp/kdlock-mutex-cost-live.EdI0Sf.tar.gz`: **13,273,362 bytes,
110 members**, SHA256:

```text
794d5390d3b0057ef97093884ed16b76370f2219735f2b62984a1003e059ec39
```

Source archive SHA256:
`112ee1795b4486e20aee19a70edf2f0f6d637811b692a9f4f946b647a872f76d`.
`cost-review.json` SHA256:
`cb47ba8050da0a244897931af9c69e165704f1c6650f5ed2366988e894bde580`.
`comparison.json` SHA256:
`b284eaf3889a4089069a6b4861065f61c2ae1bcbc8f21a8279e3baf33c83d35d`.
No guest archive is exported. The review confirms idle state, Linux 6.1.159,
boot `e5f08f95-3b68-40f3-bc28-6a7ca42e7941` and unchanged runtime inputs.
The separate post-review baseline check passes 18 source files, nine build
files, two bundles and config, with running Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. Host static checks pass all 11
Markdown files / 630 local links, unchanged inventory and 210 runtime/test
hashes, Python AST, shell syntax and `git diff --check`; no host test executes.
The broader C1/C2/C5, reproducibility/cost decomposition and third-arm work
remain open; access-time guards, flags and immutable versions remain deferred.

## Paired Native-JIT Experiments

**2026-09-13, unit 20:08:03-20:08:07, live 20:11:06-20:14:52 +08:**
add an explicit paired controller and one-session shell driver, extending the
existing benchmark unit only. All **210 runtime/test inputs** agree between
host, units, live run and postflight. Relative to the 208-input measurement
freeze, only `tests/paired_benchmark.py`, `tests/benchmark_arm.sh` and
`tests/unit/test_benchmark.py` differ. No production workload, lock/module,
guest-kernel, two-word ABI, owner, deferred guard/flags/version change occurs.

Affected guest units pass **2/2**: 30 production-driver scenarios, 49 paired
observer checks and 47 evidence-controller methods. Unit source/log/result
evidence is `/tmp/kdlock-paired-units.aEjAK5`. The synthetic observer tests do
not execute kernel JIT; the independent live experiment below supplies that
evidence. The fixed inventory remains 40 unit entries, 495 Python `test_*`
methods, 21 numbered shell drivers, 80 cases and 15 suites. The new experimental
driver is not added to that fixed regression catalog or any daily scope.

Guest command, with the existing recovery snapshot confirmed:

```sh
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B -u tests/paired_benchmark.py \
  --mode 2 5 --threads 4 8 --workload 100000 --loops 16 --runs 2 \
  --cpus 0-7 --repeats 2 --timeout 300 \
  --output /tmp/kdlock-paired-live.aEjAK5
```

All **16 sessions / eight pairs pass**. Both arms retain `mutex_jit=1` and
identical loaded binary hashes, ordinary workload/module parameters, inherited
CPU mask 0-7 and preparation: one warmup operation, then 12000 promotion
operations after a one-second gap. Native selects `kd_unused`; JIT selects
`klock_test`. Every arm rebuilds a drained provider/source session. Translators
are stopped before the payload; NORMAL publication, code address and image
hashes are checked before/after. Detailed execution/evidence contracts are in
the [paired flow](JIT_EXECUTION.md#34-原生锁与-jit-配对实验).

Independent archive inspection checks every command/phase, exact worker and
state counts, unchanged snapshot prefixes, entry/physical-lock matching bodies,
saved images and owner/drain/service logs. The eight native arms contain no
entry/image/install/body. The eight JIT arms contain **1,044 returned bodies**,
all inside their measured phases, with **2,088 exits/executed/resumed** and zero
hostcall rejects/failures/quota exits. No native-continuation frame starts.
Four-thread arms finish at 12129 state transitions, eight-thread arms at 12257;
full replay, completion, clock and scalar oracles pass. Mutex JIT success/resume
counts match bodies, origin acquire/release counts balance, and no kernel fault
is detected. These are not claims that every CS or instruction used JIT.

Each row is one paired repeat, not an average. N is native-with-existing-hooks,
J is JIT; ratios use the driver's instrumented ioctl throughput:

| Mode | Threads | Order | N wall ms | J wall ms | JIT bodies / measured CS | J/N throughput |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 4 | N, J | 33.854 | 34.462 | 93 / 128 | 0.982 |
| 2 | 4 | J, N | 33.878 | 33.877 | 93 / 128 | 1.000 |
| 2 | 8 | N, J | 117.187 | 59.275 | 221 / 256 | 1.977 |
| 2 | 8 | J, N | 128.149 | 58.170 | 208 / 256 | 2.203 |
| 5 | 4 | N, J | 32.513 | 51.418 | 2 / 128 | 0.632 |
| 5 | 4 | J, N | 33.886 | 43.143 | 2 / 128 | 0.785 |
| 5 | 8 | N, J | 58.956 | 2149.490 | 213 / 256 | 0.0274 |
| 5 | 8 | J, N | 58.725 | 2088.644 | 212 / 256 | 0.0281 |

`comparison.json` preserves all per-repeat p50/p99, worker CPU time, completed
counts and ratios; per-arm archives also retain preparation records. With only
8/16 ioctl samples per payload, these p99s are not stable tail estimates.
Mode 2's eight-thread ratio is not a general speedup claim. Mode 5's eight-thread
worker envelope is about 35x slower on this earlier ALERT-logging freeze; its
four-thread JIT participation is only 2/128. The later
[severity follow-up](#mutex-routine-log-severity) retains these results and
investigates their console cost; it does not rewrite this historical table.
Logging, witness, oracle, scheduling and services remain included, cache/thermal
conditions are not equalized, and workers are not individually pinned or given
exclusive CPUs. No third arm, hardware events, nested-role measurement or
preparation amortization has been validated. C1/C2/C5 and P1/P2 remain open.

The temporary `review.py` completed per-arm inspection and generated/verified
the archive, then exited 1 by comparing the verifier's integer member count
with its hash map. Keep that script and archive unchanged. The independent
`/tmp/kdlock-paired-finalize.aEjAK5.py` reconstructs the expected file map and
verifies the **original** archive; it does not rerun workloads or recreate the
archive. Its final metadata is `/tmp/kdlock-paired-finalization.aEjAK5.json`.
This observer error is not a failed kernel workload and is not silently erased.

Guest-only evidence: `/tmp/kdlock-paired-live.aEjAK5.tar.gz`, **21,172,928 bytes,
163 members**, SHA256:

```text
d9a992e5185eafc4ec42c146976a3a2c9140aeffba428970e061d6d7afb455af
```

Source archive SHA256:
`65d602136791913e5b7775c96879c4de3478a836117d159d45f6a774120a0908`.
`paired-review.json` SHA256:
`67a86dab4964bb3f0bed20bb644066608cbcfd39d983ed4c0ffaa013492d1993`.
`comparison.json` SHA256:
`8a538492adf444e402929225f80178ad107dab63e756c493d79ee133412bb6d5`.
The archive stays guest-local; no denied export is retried. Kernel baseline
checks pass before/after (18 source, nine build and two bundle files); Linux
6.1.159, Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`, boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941` and final idle state are unchanged.
No core/extended, other unit programs, admission negatives or kernel probes are
rerun by this increment; their older evidence is not spliced into this freeze.

## TCLock Comparator Feasibility

**2026-09-13, completed 19:42 +08:** inspect the clean local TCLock checkout at
`~/TCLocks`, revision `bbfb9f00a12af51dff6ca291cb9829a82960c2ef`, and compile only
external objects against `/root/linux-6.1.159` in the recovery guest.
`KERNEL_SYNCSTRESS` selects the upstream nano-benchmark headers. Four upstream
files were copied individually without edits; no upstream build/run script,
kernel rebuild, new VM, module link/load or JIT workload was executed.

The normal `control.o` build succeeded and its x86-64 relocatable ELF was
verified. The unchanged `komb_mutex.o` build failed; diagnostics and the actual
guest `sched.h` agree on nine missing task members: `komb_stack_curr_ptr`,
`komb_mutex_node`, `komb_local_queue_head`, `komb_local_queue_tail`,
`komb_curr_waiter_task`, `komb_prev_waiter_task`, `komb_next_waiter_task`,
`komb_lock_addr`, and `counter_val`. The original source object's SHA256 is
`d4ae402d81307100ee2c03745643f458d3b42eab13e6e57735eebbd22643dc26`.
The positive control distinguishes this dependency failure from unavailable
compiler/build infrastructure; it does not certify any TCLock port or runtime.

The initial temporary observer exited 1 after compilation because its regex
did not accept GCC's typographic quotes. Keep that observer and both compiler
logs unchanged. `finish.py` independently reads the saved logs/object, checks
the actual task header and packages them; it does **not** recompile or turn the
compiler failure into a passing delegation test. No `.ko` was produced.

The guest exposes a `cpu` PMU (`type=4`), but no `perf` executable is found on
PATH, so hardware event counting was not executed. This is a tooling gap, not
evidence that the PMU or all cache-transfer events are unsupported.
The later [paired increment](#paired-native-jit-experiments) supplies the first
same-kernel native-with-hooks/JIT experiment; the separate third-arm capability
assessment remains in [TODO](TODO.md#comparator-feasibility-and-matched-experiments).

Guest-local evidence: `/tmp/kdlock-comparator-guest.rm7uIs`.
Its 17-member, 711,506-byte archive is
`/tmp/kdlock-comparator-guest.rm7uIs.tar.gz`, SHA256
`610349bb6f9bd28c198c952075b24eae0b191359bf77aad17d936253f97417b8`;
`audit.json` SHA256 is
`f2162ab373b4c46fa1eebc4498d95785b3094bacae2d82a669f2efbf48fd058e`.
The archive includes frozen kdlock sources, upstream inputs, control object,
logs and both observers; member hashes pass. It remains guest-local.
All 208 kdlock runtime/test hashes, boot and idle state are unchanged. This
documentation/compatibility increment adds no unit entry or named live case;
the measurement run below was then the latest actual-JIT evidence, before the
separate paired increment above.

## Instrumented Benchmark Measurements

**2026-09-13, unit 19:21:23-19:21:26, live 19:22:19-19:25:21 +08:**
add `KD_TEST_METRICS=1` to the existing benchmark without changing the ioctl,
two-word wrapper, native owners, guest kernel or deferred guards/flags/versions.
Measure the post-barrier worker envelope and per-ioctl monotonic latency,
sum worker CPU time and preserve exact successful counts on partial failure.
Bound storage to 1048576 samples; invalid input is refused before device open.
Existing `test_04` payloads and mode-5 continuous stress retain structured
records and both kernel-log snapshots through the ordinary evidence collector.
Execution boundaries and field definitions live in
[usage 3.3](JIT_EXECUTION.md#33-带观测的负载测量).

On the same **208 runtime/test inputs**, the guest standalone benchmark builds
with `cc -O2 -Wall -Wextra -Werror -pthread`. The new production-driver fixture
passes **30 scenarios**: real pthreads, controlled clock/IO primitives, exact
envelope/nearest-rank quantiles, a real guest-clock path, mixed roles and setup,
IO/timer/argument failures. The existing evidence controller passes 47 methods;
`make ... run` reports **2 passed, 0 failed**. These units do not run a kernel CS.
The earlier unit-only pass before the two snapshot additions remains separate
in `/tmp/kdlock-benchmark-units.KMqFzu`; it is not the final source identity.

The unchanged `core` selection passes **5/5 actual-JIT cases** with `mutex_jit=1`
for mutex positives. Distinct returned-body records with saved entry images:
mode 2 = 4, mode 7 = 2, mode 8 = 10 across three phases, mode 4 = 3 across two
phases, mode 5 = 462 (461 normal JIT returns plus one quota/native suffix).
All **481** records are phase-deduplicated. Full workload oracles pass, including
mode-5 scalar count 12587 with zero failures, service exits/executed/resumed
939/938/938, one quota exit and one real-owner unlock ACK.

Four recorded payloads are independently joined to the *new* witness lines
between intact before/after snapshots. They contain **451** returned bodies:

| Measured payload | Completed ioctls | Loops/ioctl | Worker envelope (ms) | Ioctl p50 / p99 (ms) | New returned bodies |
| --- | --- | --- | --- | --- | --- |
| mode 2 | 8/8 | 1 | 23.280183 | 15.487023 / 23.149292 | 4 |
| mode 7 | 8/8 | 1 | 23.242952 | 14.318951 / 23.159649 | 2 |
| mode 8, original phase | 9/9 | 1 | 2.541042 | 1.799060 / 2.452807 | 2 |
| mode 5, continuous stress | 8/8 | 64 | 4541.236616 | 4508.671886 / 4541.222288 | 443 |

These values only verify the measurement pipeline for these executions. Modes
have different workloads/roles, samples are few, and native paths, kernel
logging, witnesses, state checks and instrumentation remain included. They
are not comparable speedups, pure JIT/lock latency or stable p99 estimates.
Mode 4 has actual-JIT evidence but no structured measurement in this increment.
No baseline/native-controls, additional parallel case, complete 40-unit run
or full live matrix is added; old freezes cannot certify this one.

Guest commands:

```sh
make -C tests/unit run TESTS= PY_TESTS='test_benchmark.py test_regression.py'
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B tests/regression.py --suite core \
  --timeout 300 --output /tmp/kdlock-benchmark-final-live.m7GxAl
```

Final guest units: `/tmp/kdlock-benchmark-final-units.m7GxAl`.
The guest-only archive `/tmp/kdlock-benchmark-final-live.m7GxAl.tar.gz` has
8,779,545 bytes and 63 regular members, SHA256
`b14b9e8a94359cc63fd8793d7d03621e78d389e1f7b3e1edd17fe99b07c9afe5`.
Its source archive SHA256 is
`659b77eaaaea8bcb1711949c3e22162393404a0548145ce995664d61bf52da12`;
`benchmark-review.json` SHA256 is
`bfe7a81cebf49e7103f42b820be4fe9599b52590d000d2c97b199e8982fc9c4a`.
The repository verifier, measured-payload joins and outer member hashes pass;
source hashes, boot and running kernel notes are unchanged, callers/modules
are drained, and no kernel fault is detected. No guest archive was exported.
Broader P1/P2 comparisons, repeatability, cost separation and the recorded
C1/C2/C5 capability limits remain open. Access-time checking remains deferred.

## Hotlock Promotion Ordering

**2026-09-13, final unit 18:46:56-18:46:58, live 18:47:41-18:51:14 +08:**
remove cross-lock shrinking of the existing 2.5-billion-cycle sample window,
and read the sample-update TSC under the table lock. Preserve the module-wide
warmup, 10000-sample quota, strict deadline, sticky decisions, table capacity
and JIT admission. Only `kd_hotlock.c` changes production behavior; two existing
unit files add checks, and three workload/driver files only update comments.
No guest-kernel, two-word ABI, ownership or deferred guard/flags/version change.

The existing guest production sampler unit establishes two distinct failures
before their fixes, using real `kd_hotlock_record()` calls with substituted
TSC/lock primitives, never fabricated table states:

| Attempt | Evidence and outcome |
| --- | --- |
| Cross-lock counterexample | Fast-first/slow-first samples expose 11 failed checks in the old global-window implementation; it compiles and the fixture exits 1, not a build failure |
| Window-only increment | 211140 checks and three mutants pass; six complex cases pass with 429 returned bodies on their own freeze |
| Timestamp counterexample | One caller reads TSC first but another calls the production updater before it acquires the table lock; two assertions show false IGNORE and an old end timestamp |
| Final combined fix | 211150 checks, zero failures; four compiled mutants report checked failures: stale TSC, narrowed window, deadline equality, shortened quota |

The final runner selects `--suite core --case parallel-drain-0 --timeout 300`.
**6/6 actual-JIT cases pass on the same 206 runtime/test inputs as the final
unit**, with the following returned-body counts. Mutex positives use
`mutex_jit=1`; prefixes followed by native completion are not full-JIT CS claims.

| Case | Bodies | Preserved contract |
| --- | --- | --- |
| `mode-2` | 4 | Natural root promotion, eight clock/scalar executions and resumes, 12009 correct scalar results |
| `mode-7` | 2 | Non-LIFO nested spin execution and exact complete state |
| `mode-8` | 10 (2+4+4) | All three complex/shared-B phases, including quota/native and waiter exit |
| `mode-4` | 3 (1+2) | Same-CPU B-holder scheduling and two A roots sharing native B |
| `mode-5` | 447 | 446 normal JIT completions, one quota-native frame, 908 service executions/resumes and 12587 correct scalar results |
| `parallel-drain-0` | 2 | Two concurrent native frames, four owner ACKs, peer cancellation, resource pressure, rename and retirement/reload |

All **468 distinct timestamped body records** have matching saved entry images.
An independent join also checks mode 2/5 and both parallel root body locks
against their natural `begin delegate` records. Existing SELFTEST resource
promotion remains separately labelled, not evidence of natural frequency.
All cases drained with complete evidence, unchanged source hashes and no
detected kernel fault. Pre/post baseline checks match 18 source files, nine
build files, two bundles/config and Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`; boot remains
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`, kernel 6.1.159. No VM restart occurs.

Guest evidence directories are `/tmp/kdlock-hotlock-before-units.4aUxnP`,
`/tmp/kdlock-hotlock-units.I2k5mA`, `/tmp/kdlock-hotlock-live.I2k5mA`,
`/tmp/kdlock-hotlock-clock-before-units.qymr88`,
`/tmp/kdlock-hotlock-final-units.sk1fHz` and
`/tmp/kdlock-hotlock-final-live.sk1fHz`. The verified, **guest-local** outer
archive contains 78 members and 23,241,590 bytes, preserving earlier attempts
as distinct nested archives, not additional accepted final cases:
`/tmp/kdlock-hotlock-final-live.sk1fHz.tar.gz`, SHA256:

```text
802a6b7fa3f19a7662c838a5d6211835811e0c2ef472776c0e5e6a823a3d85bc
```

Final source archive SHA256:
`c7d5d317b454fd202c3747b525837399d651a457754040c6a033c1c778f01d3d`;
`hotlock-review.json` SHA256:
`97717e978ea55ac0fe5577e14aed607df982ed977e2d32396eecbbf47051a5a8`.
Host final source/static metadata is `/tmp/kdlock-hotlock-order-final.sk1fHz`.
No archive is exported. No new routine test or full-matrix rerun is added;
39 unit programs, 495 Python methods and 80 named cases remain unchanged.
This bounded improvement does not prove TSC synchronization, deterministic OS
scheduling, actual contention, speedup, resampling or broader C1/C2/C5/P1/P2
completion. Policy and operation are in [usage 3.2](JIT_EXECUTION.md#32-热锁晋升与翻译准备).

## Typed Scalar Service

**2026-09-13, 18:12:11-18:15:09 +08:** add manifest ID 3, `int_sqrt`, using
the native kernel helper with saved unsigned 64-bit RDI input and RAX output.
Other saved GPRs, two-word wrapper arguments and the existing CALL-return
protocol remain unchanged. This helper has no pointer argument, sleeping,
allocation or task/per-CPU dependency in the inspected baseline implementation.
The service contract and mode 2/5 flows are maintained in
[DESIGN 8.4](DESIGN.md#84-native-hostcalls) and
[JIT_EXECUTION 6.13](JIT_EXECUTION.md#613-call-次数额度与原生后缀).

Ten runtime/test files change from the preceding audit; all **206 input hashes**
match between host, unit run, live run and idle postflight. The recovery guest
builds the external modules and runs the four affected existing units:
`test_hostcall_codegen.py`, `test_jit_entry_scope.py`,
`test_mutex_signal_protocol.py`, `test_jit_diagnostics.py`. All pass, including
**1,837 production-consumer checks**, 14 detected mutations and 34/13 protocol/
diagnostic methods. Each mutant must compile and report a checked failure, not
crash or time out. The three scalar mutants truncate input, select RSI instead
of RDI, or sign-extend a 32-bit result. Native primitives in that fixture remain
test doubles; actual numerical correctness is established separately below.

The existing runner selects only `mode-2`, `mode-5`, `mode-8`, with a 300-second
per-case timeout and confirmed recovery. **3/3 pass**, with these observations:

| Case | Returned bodies | Service and completion evidence |
| --- | --- | --- |
| `mode-2` | 4 | Four JIT completions; hostcall exits/executed/resumed 8/8/8, no rejection/failure/limit; all 12,009 CS scalar calls correct |
| `mode-5`, `mutex_jit=1` | 430 | 429 normal JIT completions plus one quota-native frame; exits/executed/resumed 875/874/874, limit 1, rejection/failure 0; native begin/complete/unlock 1/1/1 |
| `mode-8` | 10 (2+4+4) | All three existing complex/remote phases pass; mixed child quota remains clock-only, 17/16/16 exits/executed/resumed, first waiter exits before the next root on B |

Mode 5 checks 12,587 complete critical sections, 12,667 clock returns and
12,587 scalar calls with zero failures. The five final callers each run 17 clocks;
one delegated request exits before clock 17, then its original waiter executes
that clock and the scalar suffix before owner ACK. Normal requests each return
from two services. Both modes consume high-bit scalar arguments/results and
retain the independent complex-state oracle; total CS counts include native
warmup/owners and are not JIT counts.

Saved mode 2/5 assembly contains exactly the distinct ID 1 `ktime_get` and
ID 3 `int_sqrt` stubs at live symbols `ffffffff81193700` and
`ffffffff816b2e90`. All **444 distinct timestamped returned-body records** have
matching saved entry images. Independent offline checks validate source/archive
membership, hashes and recorded outcomes; all cases drained, and no kernel
fault was detected. The boot remains `e5f08f95-3b68-40f3-bc28-6a7ca42e7941`,
kernel 6.1.159, Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
Pre/post baseline checks pass for 18 source files, nine build files, two bundles
and config. No VM restart or guest-kernel edit/build occurs.

Evidence remains **guest-local**: units in `/tmp/kdlock-scalar-units.lzyYlP`,
live results in `/tmp/kdlock-scalar-live.lzyYlP`. The verified outer archive
`/tmp/kdlock-scalar-live.lzyYlP.tar.gz` contains 44 members, 6,177,040 bytes,
including frozen source, logs, images, build captures, unit records and the
read-only math-source/inspection material. SHA256:

```text
72cce3a7a5448f28b3634e054b2c962e16cb4212e61681195920fafa745b5771
```

The shared source archive SHA256 is
`14e03fd5955a1a5b140bad6e62778973faf2f3db78e38e0a392751432375aabd`;
`scalar-review.json` is
`bc0a7c5931eae8d818a54da93e8bf2b60add9b7f2a9d5fa402bdc2bfa533234a`.
Host static/source metadata is in `/tmp/kdlock-scalar-service.lzyYlP`;
no guest archive is exported. The current inventory is unchanged: 39 programs,
495 Python methods, 80 named cases. The older 64-case audit is not a run of
this new scalar freeze. C1/C2/C5 and broader P1/P2 remain open; access-time guards,
flags, immutable JIT versions, pointer/variadic/side-effecting services and
performance claims are not added or certified by this increment.

## Main-Plan Acceptance Audit

**2026-09-13, 16:56:08-17:23:17 +08:** the existing **64-case `extended`
selection passes on one freeze of 206 runtime/test inputs**. No runtime or test
source changed during this audit, and no new routine entry was added. This
checks the currently implemented contracts together instead of combining older
scoped PASS results. The inspected requirements and remaining boundaries are in
[the task audit](TODO.md#main-plan-acceptance-audit).

| Acceptance category | Result | Evidence boundary |
| --- | --- | --- |
| Actual kernel JIT | 50/50 | Returned generated-body witnesses, matching saved entry images and each driver's workload/protocol oracle |
| Context admission refusal | 12/12 | Expected native-only refusal and correct native state, zero returned JIT body |
| Kernel task/RCU protocol | 2/2 | Real reader/task/ACK probes, zero returned JIT body; not JIT positives |
| Existing unit programs | 39/39 | Recovery-guest `make -C tests/unit run`; not a forced `make -B` rebuild |
| Independent admission audit | 25/25 | 17 expected refusals and eight accepted assembly cases; concrete miasm IR and mocked text, no native/JIT machine-code execution |

The first three rows are the 64 live cases. The last two are separate programs,
not additional live cases. Baseline, `native-controls` and eleven covered
diagnostics were not selected. In particular, ordinary mode 0/1/3 diagnostics
retain their mode 2/8/5 replacements; the eight independent register gates still
run. This is not a new direct run of every mode or the historical 67-case scope.

After the runner exits 0, the existing offline verifier validates all 64 result
records and source/protocol/generated/post-case-build archive memberships and
hashes. A temporary read-only reviewer also inspects saved phase archives and
joins **1,538 distinct timestamped returned-body records** to generated entries;
no observed body entry lacks a saved image. Copied log records are counted once
per case. Neither this join nor a body witness identifies an immutable loaded
code version or proves every generated instruction/path executed.

Representative multi-phase checks remain independently visible:

| Existing case | Observed result |
| --- | --- |
| `mode-4` | Seven-role/two-CPU phase: one JIT body, no native frame. Shared-B phase: two JIT bodies, one native frame, two real-owner ACKs and a native peer. No mutex owner handoff |
| `mode-5` | 450 normal JIT completions plus one quota/native continuation; 466 service executions and 466 returns to JIT, with the excess callee's original-waiter completion checked |
| `mode-8` | Original, two-root pure JIT and mixed quota/exit phases: 2 + 4 + 4 bodies. The first waiter TID detaches before the same B combiner runs the second root |
| Resource/lifetime/register scopes | Real gate and node pressure, local and physical capacities, cross-module learned calls, changed-stack continuation, physical/native peers, waiter signals and source retirement pass their existing individual oracles |

All mutex JIT positives use `mutex_jit=1`. Spin-only drivers with
`mutex_jit=0` still execute spin JIT; the two task/RCU probes deliberately do not
execute JIT. Every case records `drained=true`, `source_unchanged=true`,
`evidence_complete=true`, `kernel_fault=false` and no acceptance errors. The
final read-only idle/source check also passes. This only establishes the
documented experimental drain, not arbitrary hook-reader quiescence or safe
provider hot unload.

Recorded guest commands, with stdout/stderr retained in the evidence paths
below, were equivalent to:

```sh
cd /root/host_fs/kdlock
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 make -C tests/unit run
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 python3 -B tests/audit_context_spills.py
env LC_ALL=C KDLOCK_RECOVERY_CONFIRMED=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 -B tests/regression.py --suite extended --timeout 300 \
  --output /tmp/kdlock-acceptance-audit-live.sRPnuo
```

These are recorded invocations, not instructions to reuse the existing output
directory. Exact SSH/outer-timeout commands and preflight hashes are retained in
`audit-context.json`. The live runner had a 7,200-second outer SSH timeout and
300 seconds per case; it completed without a timeout or retry.

The checkout still has uncommitted changes relative to
`1d5fc7259d96863aa143343d22c79aaf93023c9e`. Host, unit and live source maps all
match on the 206 inputs. Guest Linux 6.1.159 retains boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941` and Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`; before/after baseline checks match
18 source/interface files, nine build files, two captured bundles and config.
The existing 40-vCPU, 28-GiB, two-NUMA recovery guest and
`pre_native_resume_20260905_1110` snapshot were confirmed; no guest-kernel edit,
kernel rebuild, restart or snapshot restore occurred.

Evidence directories remain **guest-local**:

- `/tmp/kdlock-acceptance-audit-units.sRPnuo`: unit/admission logs, source
  snapshot, recorded context and the temporary read-only reviewer.
- `/tmp/kdlock-acceptance-audit-live.sRPnuo`: selection, source/environment,
  all 64 per-case records/archives and `acceptance-review.json`.

The live `source.tar.gz` SHA256 is
`9422265f6369665bd57d9c1e1e6ea7e1f7289e876557aa62a4095d236db66970`;
`acceptance-review.json` SHA256 is
`5028d23f5b8b7dd2ba07d9e934852c9a3d89a8792059995b8151ce6c74443f0f`.
Source/artifact archives were not exported to the host. Earlier failed attempts
in other increments remain separate records, not retries silently folded into
this run.

The complete guest-local archive is
`/tmp/kdlock-acceptance-audit-live.sRPnuo.tar.gz`, **98,060,721 bytes**, SHA256:

```text
34961d0a85096da252844026f83f6095c1a78b6f1d5de9454dc0b3e730cc081c
```

Its companion `.archive.json` lists all **592 members**. The live run keeps its
directory prefix; unit/admission inputs, logs, reviewer and context/closeout
metadata use `unit-` prefixes at archive root. Independent outer-archive
verification passes, followed by another idle/source/boot check at
**17:35:50 +08**. The package contains frozen execution evidence, not a copy of
the subsequently edited progress documents. Host inventory/link/syntax checks
retain 39 unit entries, 495 distinct Python methods, 21 shell drivers and the
unchanged 80-case/15-suite catalog; they do not execute host test payloads.

This completes the finite same-freeze acceptance audit, not the whole project.
Broader C1/C2/C5 contracts and P1/P2 work remain open. Access-time checks, the new
pre-instruction exit, local/general flags repair and immutable JIT versions
remain explicitly deferred. No new safety capability follows from this PASS.

## Shared B Waiter Exit

**2026-09-13, 16:24:05-16:26:23 +08:** **2/2 selected complex spin JIT cases
pass**, with `mutex_jit=1` and **206 frozen runtime/test inputs**. The existing
mode-8 quota phase now observes the first native waiter's normal TID detachment
before B pops its old frame and executes the next independent root. Only a
SELFTEST pop observation point, the existing observer/driver/oracle and units
change; no production owner/queue protocol, workload or new routine case.
The execution flow and commands are in [usage 6.14](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner).

| Case / phase | Returned bodies | Native begin / complete / ACK | Scope |
| --- | --- | --- | --- |
| `mode-8`, original | 2 | 0 / 0 / 0 | Original complex single-root remote JIT |
| `mode-8`, multi | 4 | 0 / 0 / 0 | Two independent pure-JIT roots on one B |
| `mode-8`, multi quota | 4 | 2 / 2 / 2 | First waiter exit before the same B runs its second root |
| `remote-late-3` | 4 | 4 / 4 / 1 | Existing no-lock root finish, cross-NUMA/rename/native-owner schedule |

All **14 body witnesses** are linked to their separately retained generated
images; final dmesg is not double-counted as another mode-8 phase. The mixed
image at `ffffffffc0b4e17a` is **3,417 bytes**, SHA256
`d17c19f8b17a016bfb1e017585d67ecaa48c5156a3e9b3dae23c9b957dd804e5`.
Waiter **2405928** runs its supported quota suffix from callee
`ffffffff81193700`, CALL SP `ffffc90008ac7c00`. Its B owner stays
`ffff8883c1d4a080` on CPU **12**. After B and A0's actual ACKs and role 0's
return, `kd_child_exit release` reports **detached=packet=context=valid=1**;
only then does that same owner start waiter **2405927**'s child JIT.
Both root records are `before=after=2`, values **`6cf80006` / `6cf8060c`**,
shared sequence **12006 / 12007**; all 14 callers return with clean IRQ/preempt.
Each multi phase retains **36,023** complex transitions. The quota phase has
17/16/16 service exits/executions/resumes, one limit and no failed/rejected
service; all three publication identities remain unchanged.

Three focused guest units pass on the same corrected freeze. The production
frame/observer fixture has **10,912 checks**, **20 assertion-detected mutants**
and the unchanged **168-byte regs / 656-byte frame / 5,264-byte context** layout.
It tests both observer boundaries, one-shot PID refs, already-detached/normal/
timeout outcomes, packet/context corruption and ACK-before-pop ordering using
substituted PID/RCU/time primitives, not a model of Linux task exit. The two
protocol units retain **16 + 17 methods**, including missing/duplicate/wrong
identity and reordered exit/second-JIT evidence. The first attempt passed the
production fixture and both oracles, but a skip-observer mutant failed to
compile under unused-function `-Werror`; that was not a detected behavior
mutation. Keeping a non-calling function reference fixed the test, after which
all three programs passed before any live run. Both freezes/logs are retained.

At **16:30:08 +08**, the guest is idle and all 206 host/guest/source-freeze
hashes agree. Boot `e5f08f95-3b68-40f3-bc28-6a7ca42e7941` and live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` are unchanged; the 18-source/nine-build
baseline check passes. Both cases drain without kernel faults. Default and
SELFTEST external-module build logs retain objtool stack/RETHUNK and locale
warnings, so these are not warning-free builds. No VM restart or guest-kernel
edit/build/install. Host freezes: `/tmp/kdlock-child-exit.Yr7QkG/` and corrected
`/tmp/kdlock-child-exit-fixed.Yr7QkG/`.

Guest-local source/log/image/unit archive:
`/tmp/kdlock-child-exit-live.Yr7QkG.tar.gz`, SHA256:

```text
19b6fc9bef999cd0efdb92d6111b8124416d3014603c874b3e05311672e0c4fa
```

Frozen source archive SHA256:
`762b6256eba9a2389fec5afa61e9335713593688b86aed5808cbc9f87779a7c5`.
Guest-local offline verification returns 0, covering source plus **18/30**
artifact, **61/37** protocol and **five** build members per case; no unrecorded
selections. Initial failed and corrected passing units each retain their own
source archive. Source/artifact export remains unapproved; the archive stays
in the guest and only metrics/log excerpts/hashes were read back.

This is TID detachment, not completed task-memory RCU reclamation, arbitrary
cancellation or a production all-owner exit barrier. Broader C1/C2/C5 remain
open; two-word args, access-time checks, local/general flags, immutable versions
and guest hooks are unchanged. No new unit program/method or live case, no
unselected live rerun, no Git commit. Host static/document checks are separate
from the guest execution results above: all **11 Markdown files / 580 local
links and anchors**, Python AST, shell syntax and `git diff --check` pass;
all 206 runtime/test hashes remain equal to the accepted freeze. Inventory
stays at **39 unit programs / 495 Python methods / 21 drivers / 80 cases**.

## Progressed Spin Gate Refusal

**2026-09-13, 15:39:17-15:41:27 +08:** **2/2 selected complex JIT cases pass**
on **206 frozen runtime/test inputs**. The existing real ticket/gate-pressure
case now adds A2/C while the original A/B native suffix is paused. This tests
the existing production gate-ENOMEM/PENDING continuation, not a new recovery
boundary. Only the workload, its selector, driver/oracle and two existing unit
programs change; production lock code, capacities, guest kernel and two-word
ABI do not change in this increment. Flow is in
[usage 6.3](JIT_EXECUTION.md#63-spin-虚拟请求取消与续跑).

| Case | Returned bodies | Native begin / complete / ACK | Scope |
| --- | --- | --- | --- |
| `virtual-ticket-refusal` | 2 | 2 / 2 / 2 | Old real ticket E2BIG plus new progressed gate ENOMEM; Linux C contention and two live frames |
| `virtual-node-refusal` | 1 | 1 / 1 / 1 | Existing injected count refusal and cancellation; gate-pressure extension disabled |

Both cases execute the original **16,369-byte** image at
`ffffffffc0b549e4`. The ticket case also executes the **738-byte** A2 image at
`ffffffffc0b593d8`, SHA256
`f6d01488452916d5d3188e3b862f7e4441e4d2b7bbc83b6616c91212205527c7`.
These are returned-body witnesses linked to the archived images, not merely
translation or installation logs. Seven/six generated images are not seven/six
executed bodies. The original **12,003 requests / 12,011 protected transitions**
remain checked independently of the new A2 record.

Gate occupancy is **4 / 66 / 1024 / 1024 / 1024**, and source frame counts are
**0 / 1 / 1 / 2 / 1** at prepare/held/filled/progress/drained. The filler acquires
1,025 distinct locks, adds 958 gates and gets 67 genuine refusals; the cold
target adds one, and the progressed combiner adds one: **69 total**. Cold
native records remain separate from JIT evidence. The A2 NORMAL/code fields
and all three image-file hashes remain unchanged across the snapshots.

The old logical waiter **2395295**, executor CPU **4**, retains A while the
new logical waiter **2395327** on CPU **16** receives the new callee packet.
Its executor **2395330** on CPU **14** keeps A2's physical owner
`ffff888107db8000`. Native C holder **2395324** on CPU **18** observes Linux
word `0x440101`, committed prefix `before=2 inner=0 after=1`, and unchanged
value `0x26ae8201a`. New PENDING errno is **-12**, target
`ffffffff81e90a20`, CALL SP `ffffc9000b20fdc8`, return
`ffffffffc0b59436`; the staged SP is exactly eight bytes higher. After C
releases, the original waiter sees that prefix, completes `before=2 inner=1
after=2`, value **`0x24e802029`**, and receives A2's final ACK. All six new
roles join before the old B releases; old A/B owner observations stay equal.

Two focused guest unit programs pass. The gate map/owner fixture retains
**3,131 checks** and the three protocol methods now reject missing/incorrect
JIT, errno, callee/stack, owner, effects, frame snapshots and ACKs. The outer
production fixture passes **12,597 / 27,192 checks** with NUMA off/on, including
actual API-filled gate ENOMEM, **168-byte pt_regs / 656-byte frame / 5,264-byte
context** preservation, and PENDING callee/SP restoration. It detects 12
temporary source mutants, including failed-map sequence consumption and pin
leakage; a BUG-only control is not counted as an assertion detection. Its CPU,
physical-lock and JIT primitives remain substitutes, not live concurrency.

The initial unit attempt failed on a new fixture API-signature error and a
WARN-row parser that expected a colon. Neither was a production failure or
kernel-JIT run; corrected units passed before live execution. Initial and
passing logs are retained. Initial host source freeze remains at
`/tmp/kdlock-gate-progress.wOuGfL/`; the corrected host freeze is
`/tmp/kdlock-gate-progress-fixed.wOuGfL/`. Default/SELFTEST external-module
builds retain recorded objtool stack/RETHUNK and locale warnings; this is
not a warning-free build. Both cases drain without kernel faults. At
**15:46:26 +08**, all 206 host/guest/runtime-source hashes still agree, boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941` is unchanged, and the 18-file source,
nine-file build and live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`
baseline still matches. No VM restart or guest-kernel build/edit/install.

Guest-local source/log/image/unit archive:
`/tmp/kdlock-gate-progress-live.wOuGfL.tar.gz`, SHA256:

```text
5b338e189845d6c869c39d475699475620132759716f998db86f93d790654988
```

Frozen source archive SHA256:
`b86c1c81f20e0c1cb9d8c4363145f0dbe374d02632af6318b8c9a1f8e22dd663`.
Guest-local offline verification returns 0 for both recorded cases with no
unrecorded selections. It checks source plus 42/36 artifact, 38/22 protocol
and five build members per case. An initial auxiliary-directory layout was
rejected by that verifier; only the auxiliary notes were moved to flat files,
without changing case evidence. Source/artifact export to the host remains
unapproved, so this archive stays in the guest; only metrics/log excerpts and
hashes were read back. The test catalog is still 39 unit programs, 495 Python
methods, 21 shell drivers and 80 cases. Broader C1/C2/C5, access-time guards,
local/general flags, immutable versions and arbitrary cancellation are not
completed by this bounded increment. Unselected live cases were not rerun;
no Git commit was requested or made.

Host static checks cover all 11 Markdown files and 572 local links/anchors,
Python AST, shell syntax and `git diff --check`; all 206 runtime/test input
hashes still match the accepted live freeze. No host build or test payload ran.

## Shared Native Mutex B

**2026-09-13, 14:50:32-14:51:45 +08:** ordinary mode 4 now preserves its
seven-role/two-CPU phase, then starts a separate shared-B module session.
A0's original waiter completes an ordinary CALL-miss suffix while its real
combiner retains A0/B; A1's combiner and a non-target peer both wait on that
same Linux B. A1 subsequently completes JIT and the peer acquires as itself.
This adds workload/oracle coverage, not production owner handoff, remote-B
mutex delegation or new recovery boundaries. Flow and commands live in
[usage 6.15](JIT_EXECUTION.md#615-两个-a-combiner-共享原生-mutex-b).

The 206 runtime/test inputs in host
`/tmp/kdlock-mutex-shared-fixed.6WnQZz/source.json` match the guest freeze and
postflight. Guest evidence is
`/tmp/kdlock-mutex-shared-fixed-live.6WnQZz`; its complete archive remains **in
the guest**, not a host copy:
`/tmp/kdlock-mutex-shared-fixed-live.6WnQZz.tar.gz`, SHA256
`739ce1a01c247d599b08b63cc1fc90bd52e870cfe36da1b39ef28ec35f440723`.
The archive's frozen-source SHA256 is
`8854796d786c29173d49f17fa12aca422dcbc8a1f510908564fca2451075ed09`.
Export of the initial source/artifact archive to host `/tmp` was denied by
the approval layer; permission was requested and no alternate export attempted.
Both runs remain available and verified in the guest. Host-side metadata and
the locally created source freeze do not imply that the guest archive was copied.

| Case / phase | Returned JIT bodies | Native start / complete / ACK |
| --- | --- | --- |
| mode 4, original two-CPU phase | 1 | 0 / 0 / 0 |
| mode 4, shared native B phase | 2 | 1 / 1 / 2 |
| mode 5, normal returns plus CALL quota | 409 | 1 / 1 / 1 |
| registers-4-3 | 1 | 1 / 1 / 2 |

All three selected cases pass with `mutex_jit=1`: **413 body witnesses**, no
kernel faults and no remaining modules/callers/frames. Mode 4's final case
dmesg contains only its last two bodies; its first phase retains its own
`final.log`, protocol result and single-image archive. The shared phase
preserves three images, both selected A publications, source objdump/CALL
returns, unchanged image hashes and all nine role/CPU/exit records. The extra
B image is not counted as a separately executed remote-B body.

Shared-B evidence records original waiter **2388174** on CPU 2, not physical
owner `ffff888132cfc100` on CPU 1. A0 entry is `ffffffffc0b3fc65`; the native
packet resumes callee `ffffffffc0b3f910` with CALL SP `ffffc90005a33c78`,
`held=remaining=2`. At both retained-state observations, A1 executor **2388172**
and native peer **2388181** are in B's real wait list, B/A0 keep the first
owner, and A1 has `before=12002 held=after=12001`. B remains at sequence 24003.
B then A0 receive owner ACKs; A1 completes B transition 24004 and the native
peer completes 24005 as its own owner. Both root records finish with
`before=held=after=12002`, 12005 A visits, exact recomputed values and zero
owners. The independent B state-machine replay verifies all 24005 transitions.
All nine original tasks return with IRQ/preempt zero. No global ordering is
inferred from ACK logs, which occur after physical unlock.

Guest validation commands:

```sh
make -C klock_module -j8
make -C tests/unit run TESTS= PY_TESTS='test_mutex_signal_protocol.py test_mutex_stack_protocol.py'
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B tests/regression.py \
  --case mode-4 --case mode-5 --case registers-4-3 --timeout 240 \
  --output /tmp/kdlock-mutex-shared-fixed-live.6WnQZz
python3 -B tests/verify_evidence.py /tmp/kdlock-mutex-shared-fixed-live.6WnQZz
```

The two existing units pass **34 + 8 methods**, extending existing methods
with shared-B packet/identity/ordering mutations and checked source-symbol
relocation. No new unit program, Python method, shell driver or named live case
is added. The default external test-module build succeeds with its two existing
redundant-CLD objtool warnings. Core kdlock, guest kernel, two-word args,
access-time guards, local/general flags and immutable versions are unchanged.
Postflight at **14:54:45 +08** is idle on boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`, kernel 6.1.159. Baseline remains
18 source files, nine build files, two bundles and running Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`; the existing recovery snapshot was
confirmed before loading. No VM restart or Git commit is performed.
The guest offline verifier reports all three recorded acceptances and no
unrecorded case; this is evidence consistency, not another JIT execution.

**Initial rejected candidate, 14:43:20-14:43:53 +08:** the original phase
passes, but the new preparation asserts exactly two artifacts. Serial warmup
also promotes B, producing a third valid entry, so that assertion fails before
arming any shared-B workload. No shared-B JIT or native frame runs; all state
drains without a kernel fault. The remaining two cases are NOT RUN. Correction
keeps all artifacts, reuses the checked E8/`mutex_lock` relocation parser to
identify each A's first CALL return, and verifies both selected publications;
it does not delete B or weaken body/owner/effect requirements. First evidence
and its distinct source freeze remain at guest
`/tmp/kdlock-mutex-shared-live.600WVz.tar.gz`, SHA256
`280ac3101ed0a4885b7c28a6a7117c927aa3fdc9d8f900ca1485a29695b99e71`.
The initial build/34-method unit result is not substituted for the corrected
two-unit run. This bounded shared-lock schedule does not close C1/C2/C5,
arbitrary cancellation/fairness, task/lock lifetime or deferred features.

## Shared B Mixed Completion

**2026-09-13, 14:10:10-14:13:17 +08:** the existing mode-8 driver now retains
its original complex phase and pure dual-root phase, then adds quota/native
completion before a different root's JIT on the same B combiner. This extends
the workload and oracles, not production ownership or guest-kernel code.
The full execution/evidence contract is in
[usage 6.14](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner).

The first candidate, **14:03:23-14:04:44 +08**, failed its mode-8 oracle; the
other three selected cases were not run. Its two native observations expected
`preempt_count=2` merely because two locks were borrowed. Source review of
`kd_spin_entry_begin/borrow_get/end`, native ACK routing and the existing
origin-ticket probe confirms one retained root pin on the waiter. Actual
borrowing adds references, not one waiter pin per remote frame. The corrected
test requires exactly **1** during native execution and **0** after the final
ACK. Both candidate observations had otherwise correct owners, task, blocked
successor state and service count; all callers drained without a kernel fault.
This is a fixture-premise correction, not a runtime crash fix or full native
context reconstruction. The failed source and logs remain separate.

On the corrected freeze, the external workload module builds with the same
two redundant-CLD fixture warnings. Two focused guest unit programs pass:
`test_remote_outer_protocol.py` has 16 methods; `test_jit_entry_scope.py`
checks **1718 assertions** and rejects **11 mutants**. Its actual consumer now
tests remote quota packets while verifying that the waiting parent's full
software frame remains untouched. No new unit method/program or named live
case is added; the inventory stays 39 programs, 495 Python methods and 80 cases.

```sh
# Guest only; snapshot and idle/source identity checks precede these commands.
make -C klock_module
make -C tests/unit run TESTS= PY_TESTS='test_remote_outer_protocol.py test_jit_entry_scope.py'
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B tests/regression.py \
  --case mode-8 --case mode-2 --case remote-late-3 --case registers-8-3 \
  --timeout 240 --output /tmp/kdlock-multi-quota-fixed-live.c1oHro
```

| Accepted case / phase | Returned-body witnesses | Native started / completed / unlocks |
| --- | --- | --- |
| `mode-8`, original complex | 2 | 0 / 0 / 0 |
| `mode-8`, pure dual-root | 4 | 0 / 0 / 0 |
| `mode-8`, quota/native plus JIT successor | 4 | 2 / 2 / 2 |
| `mode-2` | 4 | 0 / 0 / 0 |
| `remote-late-3` | 4 | 4 / 4 / 1 |
| `registers-8-3` | 2 | 2 / 2 / 2 |

All **4/4** cases pass with unchanged inputs and final drain, **20** body
witnesses in total. The mixed phase's waiters **2377453 / 2377456** share
entry `0xffffffffc0b3501a` (3417-byte image). CPU-11 B executor
`ffff888121c94100` retains ownership while the first waiter completes its
pending `ktime_get` CALL at `0xffffffff81193700`, then executes the second
child's JIT after B-local native completion. Two native frames retain the same
CALL RIP/RSP and different physical owners. The three publication records stay
NORMAL with identical entry/TGID/code; no callee-learning miss substitutes for
the quota. Service counts are **17 exits / 16 executed / 16 resumed / 1 limit**,
no rejected/failed dispatches. Each dual-root phase separately checks **36023**
state transitions, exact root values, 14 clean caller returns and correct B
sequence numbers. This is neither a mutex rerun nor arbitrary scheduling proof.

Postflight **14:14:29 +08** is idle on the same recovery boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`, kernel 6.1.159, with all **205**
host/frozen/guest runtime/test hashes matching. Baseline verifies 18 source
files, nine build files, config and two bundles against live Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`. QEMU PID 2900511 remains alive;
monitor confirms `pre_native_resume_20260905_1110`, no restart was needed.

Host evidence directories are `/tmp/kdlock-multi-quota.L8vwaR/` (first) and
`/tmp/kdlock-multi-quota-fixed.c1oHro/` (corrected). Both guest live archives are
also retained on the host, with identical SHA256 values across copies:

| Archive | Recorded outcome | SHA256 |
| --- | --- | --- |
| `/tmp/kdlock-multi-quota-live.L8vwaR.tar.gz` | Initial fixture failure, other cases not run | `a0225c2c39cb5bcf73e301d8c7a9aee475207c68c59d708c6612d1807d276d98` |
| `/tmp/kdlock-multi-quota-fixed-live.c1oHro.tar.gz` | Four accepted cases | `08470a5424a5b2954723ef48e53b804c1420816441ddfddb2aadf98983aed185` |

Offline verification preserves the first archive's failure (exit 1) and accepts
all four corrected records (exit 0). Each mode-8 phase's nested logs/images
remain captured; final dmesg alone is not the three-phase evidence. C1/C2/C5
remain open; no access-time guard, local/general flags protection, immutable
version, owner handoff or Git commit is added.
Host static checks pass for 11 Markdown files / 554 local links, unchanged
205 runtime inputs, all Python/shell syntax and the unchanged test inventory.
These read-only checks execute no test or JIT payload.

## Shared B Combiner

**2026-09-13, 13:33:26-13:36:01 +08:** extend the existing mode-8 driver
without changing production lock ownership. Two independent A roots send
virtual B requests to one physical combiner, retaining separate logical tasks,
outer owners and exact prefix/suffix state. The old complex phase remains;
[usage 6.14](JIT_EXECUTION.md#614-两个独立-root-共享-b-combiner) owns the role map,
gates and evidence contract. No access-time check, flags protection, immutable
code version or guest-kernel change is added.

In the recovery guest, the external workload module builds with the existing
two context-fixture redundant-CLD warnings. The focused unit invocation passes
**2/2 programs**: `test_remote_outer_protocol.py` has 16 methods and
`test_regression.py` 47. Two new methods in the existing oracle reject missing,
duplicate or corrupted root/JIT/owner/state/publication/status evidence;
synthetic ordering checks do not prove kernel concurrency. Inventory remains
39 programs, 21 shell drivers and 80 named cases, with 495 Python test methods.

```sh
# Guest only; recovery snapshot confirmed before loading modules.
make -C klock_module
make -C tests/unit run TESTS= PY_TESTS='test_remote_outer_protocol.py test_regression.py'
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B tests/regression.py \
  --case mode-8 --case remote-late-3 --case registers-8-3 --timeout 240 \
  --output /tmp/kdlock-multi-roots-live.o62dXC
```

| Accepted case / phase | Returned-body witnesses | Native started / completed / unlocks |
| --- | --- | --- |
| `mode-8`, retained complex phase | 2 | 0 / 0 / 0 |
| `mode-8`, two independent roots | 4 | 0 / 0 / 0 |
| `remote-late-3` | 4 | 4 / 4 / 1 |
| `registers-8-3` | 2 | 2 / 2 / 2 |

All **3/3 cases** pass, with **12** body witnesses across four phases. Both
mode-8 sessions retain their own artifacts and protocol logs; the final case
dmesg alone contains only its second phase. That phase publishes three images;
entry `0xffffffffc0b30294` is 2769 bytes. Waiters **2362665 / 2362668** run their
B children on the same CPU-12 executor `ffff8883cc064100`, with distinct A owners.
All 14 callers return successfully with matching task/CPU and clean IRQ/preempt.
The three complex states total **36023** transitions; both root before/after
counters equal two, values match, and shared B sequences are **12006 / 12007**.
No native suffix, retry or state failure substitutes for actual JIT.

Postflight at **13:37:49 +08** is idle on boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`, kernel 6.1.159. All **205** host/frozen/guest
runtime/test hashes match; baseline verifies 18 source and nine build files,
config and two bundles, with live Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
QEMU PID 2900511 remains alive; monitor confirms `pre_native_resume_20260905_1110`.
All cases are drained, source-unchanged and fault-free under the runner's checks.

Host source/build/unit/closeout evidence is `/tmp/kdlock-multi-roots.o62dXC/`.
The complete guest live archive is also retained on the host as
`/tmp/kdlock-multi-roots-live.o62dXC.tar.gz`; both copies have SHA256
`ccf87fce5ae369a8e622d1e1b89575d37ed8f74e8ca0287b90d79b16bb98e8a4`.
Offline verification accepts all three recorded cases with no missing cases;
the nested first-phase archive still has its six generated images and two body
witnesses. This is bounded spin multi-request evidence, not a mutex rerun,
general C1/C2 completion or any of the explicitly deferred features. No Git
commit is made for this increment.
Host static checks pass for 11 Markdown files / 548 local links, the current
inventory, all runtime Python/shell syntax and unchanged frozen input hashes;
they do not execute tests or generated code.

## CALL Quota Continuation

**2026-09-13, 12:56:19-12:59:25 +08:** the excess, not-yet-dispatched CALL
can finish on the original waiter using the existing native/owner-ACK path.
Previously the quota branches returned RUN_ERROR after progress; that is a
source-review finding, not a reproduced live crash. Validated quota packets
retain callee RIP, pushed CALL RSP, GPRs and physical owners without replay,
service invocation or callee learning. Packet/policy/source failures still
fail-stop. This does not implement access-time guards, instruction-budget
recovery, flags preservation, version isolation or guest-kernel changes.
Contracts and counter equations are in [usage 6.13](JIT_EXECUTION.md#613-call-次数额度与原生后缀).

The two external modules build in the recovery guest. Four existing focused
unit programs pass on the frozen inputs:

| Program | Result / boundary |
| --- | --- |
| `test_jit_entry_scope.py` | 1328 assertions; 11 assertion-detected mutants. Actual policy/consumer/CALL save code; wrapper, clocks, stack reads and pins use substitutes |
| `test_mutex_signal_protocol.py` | 34 methods; new quota history checks reject lost/duplicate events, wrong packets, service counts or changed publication |
| `test_mutex_outer_progress.py` | 136 assertions, five scenarios; existing backend packet/owner continuation contract |
| `test_spin_outer_progress.py` | NUMA-off/on 10487/25082 assertions and ten mutants; shared backend regression, not additional live quota coverage |

Commands, executed only in the guest (live runner outer timeout 1500 seconds):

```sh
make -C kernel_module KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8
make -C klock_module W=1 -j8
make -C tests/unit run TESTS= \
  PY_TESTS='test_jit_entry_scope.py test_mutex_signal_protocol.py test_mutex_outer_progress.py test_spin_outer_progress.py'
KDLOCK_RECOVERY_CONFIRMED=1 python3 -B tests/regression.py \
  --case mode-5 --case mode-2 --case mode-4 --case registers-4-3 \
  --case registers-8-3 --case native-mutex-depth --timeout 180 \
  --output /tmp/kdlock-call-quota-live.AbY5N9
```

All **6/6** cases are accepted with unchanged inputs and final drain. Four
mutex cases require `mutex_jit=1`; the other two exercise actual spin JIT.

| Case | Returned-body witnesses | Native started / completed / unlocks |
| --- | --- | --- |
| `mode-5` | 431 | 1 / 1 / 1 |
| `mode-2` | 4 | 0 / 0 / 0 |
| `mode-4` | 1 | 0 / 0 / 0 |
| `registers-4-3` | 1 | 1 / 1 / 2 |
| `registers-8-3` | 2 | 2 / 2 / 2 |
| `native-mutex-depth` | 5 | 5 / 5 / 26 |

Mode 5 retains **430** ordinary JIT completions and adds one quota native
frame among five callers. Its hostcall counts are **447 exits, 446 executed,
446 resumed, one limit, zero rejected/failed**. The extra pending clock CALL
runs on the original waiter, not the adapter. Entry `0xffffffffc0b41d54`, the
1459-byte generated image, service `ktime_get` at `0xffffffff81193700`, saved
CALL packet, completion/ACK and original-task return all match. Registration
remains NORMAL without new installs/translation requests. Complex state records
**12587** transitions, API observations **12587**, API calls **12667**, no
state failures. Ordinary mixed-control quota and corrupted-packet checks remain
unit coverage; none of this certifies arbitrary hardware GPR/flags exits.

Recovery QEMU PID 2900511 remained alive; monitor listed
`pre_native_resume_20260905_1110`. Before/after baseline verification reports
18 source files, nine build files, config and two bundle files matching live
Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`. Postflight at
**13:00:33 +08** is idle on boot `e5f08f95-3b68-40f3-bc28-6a7ca42e7941`,
kernel 6.1.159; all **204** host/frozen/guest runtime/test hashes match.
No per-case kernel fault pattern or retained workload/module is reported.
Existing locale/objtool RETHUNK/frame and fixture CLD warnings remain; these
builds are not warning-free. No old quota crash, full basic matrix, arbitrary
instruction recovery or access-time guard test was run.

Host source/unit/build/closeout evidence: `/tmp/kdlock-call-quota.AbY5N9/`.
Its `source.tar.gz` SHA256 is
`0a60bff6e9467027322fa4c3dd0c44221279e0dcf04616973a34255ce1215843`.
Guest run above is transferred to `/tmp/kdlock-call-quota-live.AbY5N9.tar.gz`;
both sides have SHA256
`9742f73a6093df1458ba8f218573fea24e4cd8a4b272a5d6a119a4596d5453e8`.
The offline verifier exits zero, with six accepted records and no unrecorded
cases. Host static checks pass for 11 Markdown files / 539 local links, all
Python and shell syntax, archive member hashes and the unchanged 39-program
inventory (493 distinct Python method bodies). These checks execute no test
or JIT payload. This increment adds no routine case or unit program and does not close
C1/C2/C5. No Git commit is made for this increment.

## Native Frame Retirement

**2026-09-13, 12:03:49-12:08:03 +08:** harden the common frame retirement
predicate, not the native owner/ACK protocol. Initialize an empty native routing
head on frame allocation; pop returns EBUSY for a pending native request or linked
registration even in ERROR/COMPLETE state. Refusal changes no output packet,
context bytes or source lease. Existing callers still finish native waiting
before pop. This is not access-time checking, new native-exit authorization,
flags repair, an ABI change or a guest-kernel modification. Flow is in
[Frame retirement](JIT_EXECUTION.md#frame-回收门禁).

First extend only the existing frame fixture against old production code:
guest unit `test_exec_capacity.py` exits through four failed assertions, and
`make` exits **2**. Old pop accepts the constructed pending-native ERROR frame,
changes output/context and drops its source lease. This is a deterministic
API-contract counterexample, not a reached live UAF; no module/JIT runs against
that negative freeze. Its log and inputs remain separate from the correction.

With the fix, run `make -C tests/unit run TESTS=` with
`PY_TESTS='test_exec_capacity.py test_spin_outer_progress.py'` in the guest,
under 240-second command / 255-second SSH limits: exit **0**, **2/2 programs**.
Frame tests pass **10,362 assertions** and **14 assertion-detected mutants**,
including separate missing-native-request and missing-native-route predicates.
They cover two backend tags, ERROR/COMPLETE, full software packets and retained
leases; list/CPU/source primitives are substitutes. Spin outer tests pass
**10,487 / 25,082 checks** with NUMA off/on and **10 mutants**. No unit entry,
Python test method or routine case is added; inventory remains 39 programs,
491 distinct Python methods and 80 named live cases.

Guest `make -C kernel_module KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8` exits **0**.
Existing assembly/RETHUNK/frame objtool and locale-fallback warnings remain
recorded. After checking the live recovery monitor's snapshots, run only:

```sh
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 1800s python3 -B tests/regression.py \
  --case mode-4 --case mode-5 --case registers-4-3 \
  --case parallel-drain-0 --case parallel-drain-1 --case registers-8-3 \
  --case remote-late-3 --case node-physical-8-1 \
  --timeout 180 --output /tmp/kdlock-frame-native-live.OkcyAB
```

SSH also has an 1830-second timeout. Exit **0**, **8/8 accepted**, with generated
images, matched returned-body evidence and their exact workload/owner oracles:

| Case | `body=1` | Native started/completed/unlocks | Retained boundary |
| --- | --- | --- | --- |
| `mode-4` | 1 | 0/0/0 | Two-CPU nested mutex, ordinary JIT completion |
| `mode-5` | 444 | 0/0/0 | 444 hostcall exits/executions/resumes and JIT completions |
| `registers-4-3` | 1 | 1/1/2 | Local mutex GPR/native suffix and owner ACKs |
| `parallel-drain-0` | 2 | 2/2/4 | Two live native frames, task exit, resources and first drain order |
| `parallel-drain-1` | 2 | 2/2/4 | Opposite drain order with independent owners |
| `registers-8-3` | 2 | 2/2/2 | Spin remote GPR/native continuation |
| `remote-late-3` | 4 | 4/4/1 | No-lock ancestor survives original-waiter exit |
| `node-physical-8-1` | 8 | 1/1/1 | Eight physical frames, real held-record capacity and NUMA-aware path |

The five mutex cases use `mutex_jit=1`. The physical-spin case uses
`mutex_jit=0` but executes spin JIT; it is not a mutex-JIT or no-JIT result.
All **464** bodies belong to this freeze, not earlier runs. Every case reports
zero invariants/kernel faults, unchanged inputs, complete evidence and drained
callers/modules. Basic, unselected and full-matrix cases are **NOT RUN**. These
normal live completions do not reproduce the deliberately invalid unit state
or establish arbitrary task exit, cancellation or hardware flags semantics.

Only four runtime/test files change and are synchronized. All **204 inputs**
match host, synchronized guest and the **12:09:59 +08** idle postflight.
Source/build/config/running baseline checks pass before and after: kernel
6.1.159, Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`, unchanged boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`; no VM restart or guest-kernel build/install.
Offline verification exits **0**, with eight accepted and no unrecorded cases;
it executes no payload. C1/C2/C5 remain open beyond these bounded contracts.

| Host evidence directory | Scope | Source archive SHA256 |
| --- | --- | --- |
| `/tmp/kdlock-frame-native-before.72hPz3/` | Old-code negative unit, four assertions; no live run | `46fd9ffc265dc39a0eabaff18154039d11445400d3792d0cce24617c7bd19c7f` |
| `/tmp/kdlock-frame-native.OkcyAB/` | Fixed units/build, commands, monitor, baselines, manifests and final results | `682cdc3476dfc1fb05a2356c8cb54ad22068336da64d5762000e94067b5df477` |

Complete live source/log/artifact/protocol archive:
`/tmp/kdlock-frame-native-live.OkcyAB.tar.gz`, matching host and guest SHA256:

```text
5faa10bfcb424e4bdac4688ded583744e4e2a65f1fcd435d4cd43678307cca89
```

Host close-out verifies 11 Markdown files / 527 local links and anchors, the
unchanged test inventory, Python/shell syntax and `git diff --check`. All 204
current/frozen/guest/archive inputs, eight results and 464 body counts match.
The retained `static-check.py` and `static.log` execute no test or JIT payload.

## Mutex Nested Scheduling

**2026-09-13, 11:30:37-11:31:46 +08:** strengthen existing mode 4 placement and
its observer/oracle, not production mutex scheduling. Seven roles use CPUs 0/1;
B's native holder observes A's physical executor in its real Linux wait list on
the same CPU before releasing B. The original nested waiter then completes JIT,
not an original-waiter native suffix. Ordinary and OOO variants retain exact
complex A/B state and all seven task identities/clean return contexts.
[Usage 6.12](JIT_EXECUTION.md#612-同-cpu-的嵌套-mutex-jit) owns the role map,
execution order, commands and independent coverage boundaries.

Only four runtime/test inputs change: the test module, `test_08` driver, existing
mutex protocol controller and its unit. No guest-kernel, production lock/owner,
two-word ABI, translator, flags or access-time guard changes are made. No new
routine entry is added: **39 unit programs**, now **491 distinct Python methods**;
the source catalog remains **80 cases** with the same suite selection.

Focused guest verification, each with an outer 195-second SSH timeout:

```sh
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 timeout --kill-after=5s 180s \
  make -C /root/host_fs/kdlock/tests/unit run TESTS= PY_TESTS=test_mutex_signal_protocol.py
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 timeout --kill-after=5s 180s \
  make -C /root/host_fs/kdlock/klock_module W=1 -j8
```

Unit exit **0**, **32 methods / one program pass**, including three added
scheduling methods and corrupted/missing/duplicate/wrong-order witnesses.
External-module build exits **0**; the two pre-existing redundant-CLD objtool
warnings and locale fallback remain recorded, not silently treated as fixed.
There is no guest-kernel build/install.

After a read-only monitor snapshot check, run three selected cases through the
existing runner. The OOO variant uses an in-memory case registration solely to
retain normal preflight, drain and evidence gates; it is not added to `CASES`
or daily suites. Exact guest invocation follows; SSH also has a 750-second timeout:

```sh
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 720s python3 -B - <<'PY'
import sys
sys.path.insert(0, '/root/host_fs/kdlock/tests')
import regression as r
r.add('mode-4-ooo', 'test_08_mutex_jit_modes.sh', 4, KD_MUTEX_OOO=1)
sys.exit(r.main([
    '--case', 'mode-4', '--case', 'mode-4-ooo', '--case', 'mode-5',
    '--timeout', '180', '--output', '/tmp/kdlock-mutex-schedule-live.XZriH1',
]))
PY
```

The recorded command uses equivalent `python3 -c` quoting rather than this
readable heredoc. Exit **0**, **3/3 accepted**, all with `mutex_jit=1` and valid
images, matched entry/lock returned-body witnesses and exact workload oracles:

| Run | `body=1` | Key observations |
| --- | --- | --- |
| `mode-4` | 1 | Holder PID 2326146 and executor 2326164 on CPU 0; queued/valid=1; nested_queued/nested_jit/jit_resume=1; counter 12008 |
| `mode-4-ooo` | 1 | Holder PID 2327215 and executor 2327234 on CPU 0; same scheduling/JIT checks; OOO counter 12009 |
| `mode-5` | 430 | JIT success/resume and hostcall exit/executed/resumed all 430; max_waiters=8; counter 12582 |

Both mode 4 protocol records report seven roles, two CPUs, one body and zero
native frames. All runs have native started/completed/unlocks=0, no kernel fault,
unchanged inputs, complete evidence and drained callers/modules; hostcall
rejected/failed/limit=0. Unselected, basic and extended cases are **NOT RUN**.
These **432** body observations are not complete instruction coverage, immutable
version identity or evidence for the explicitly deferred access-time guard.

Only the four changed files are synchronized to recovery ext4. All **204 inputs**
match the 11:26:35 synchronized freeze and 11:34:48 idle postflight. Source/build/
config/running checks pass before and after with kernel 6.1.159, Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5` and unchanged boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`; no VM restart occurs. Offline verification
exits **0**, records three accepted cases and no unrecorded cases, without
executing workloads. C1/C2/C5 remain open beyond these bounded observations.

Host `/tmp/kdlock-mutex-schedule.XZriH1/` retains commands, unit/build logs,
monitor output, baseline checks, manifests and result records. Its source archive
SHA256 is `7af6818dc36704661466857e86b7dc2f15decb8fbdcc4db1efc93573597a78c3`.
The full live archive `/tmp/kdlock-mutex-schedule-live.XZriH1.tar.gz` matches
host and guest SHA256:

```text
fd636bb9dd9eefc0eeff66fef51f7e8bb50f7bc46537bff34cc53f57deea8ce3
```

Documentation close-out verifies 11 Markdown files and 519 local links/anchors,
the 39-entry inventory, 491 distinct method bodies and unchanged live selection.
Python/shell syntax, documented shell blocks, `git diff --check`, both archived
source manifests and all 204 current input hashes pass. The retained
`static-check.py` / `static.log` execute no unit, module or JIT payload.

## Remote Packet Unit

**2026-09-13, 00:22 +08:** strengthen only `test_remote_outer.py` and its existing
fixture. Replace the hand-written IP/SP/DI-only struct with the actual guest
x86-64 `pt_regs` definition, asserting its 168-byte layout and RIP/RSP offsets.
Compare distinct full packets across ancestor RPC, cancellation and native ACK;
check the normal return's IP/SP advance and the terminal OOO CALL packet.
Observe child detachment before DONE and immediately poison an all-unlocked
parent after publication to expose late publisher writes. No production change,
extra task reference, wrapper argument or new unit/live entry is introduced.
Flow, selection and limits are in [usage 2.1](JIT_EXECUTION.md#21-waiter-发布边界).

Only the following guest unit command runs, with an outer 195-second SSH timeout:

```sh
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 timeout --kill-after=5s 180s \
  make -C /root/host_fs/kdlock/tests/unit run TESTS= PY_TESTS=test_remote_outer.py
```

Exit **0**, **1/1 program passes**, **4,637 assertions**, **2,439 full-packet
comparisons** and **88 DONE observations**. All eight temporary-code mutants
exit through explicit assertions: poll/cancel/native-begin/native-ACK register
clobbers, partial normal/terminal copies, DONE-before-detach and write-after-DONE.
The BUG-only control exits 2 with no assertion marker and is not accepted as
mutation detection. These are deterministic substitute CPU/release observations,
not a hardware memory-order test, architectural flags restoration or arbitrary
concurrent lifetime proof. The inventory stays **39 programs**; no module build,
load, daemon, workload or live JIT runs in this increment. The preceding nine-case
spin gate remains historical, not re-certified with this unit's source freeze.

The 00:21 preflight and 00:23 postflight find the guest idle, kernel 6.1.159 and
unchanged boot `e5f08f95-3b68-40f3-bc28-6a7ca42e7941`. All **204 inputs** match
host and guest after synchronizing only the two changed test files, and remain
unchanged through the run. No VM restart or guest-kernel modification occurs.
Host evidence directory `/tmp/kdlock-remote-packet.TKf6Z2/` retains the command,
unit log, pre/sync/postflight manifests, result and source archive. Its
`source.tar.gz` SHA256 is:

```text
b7ff02fd5668df3bf8a70b986d1103cef9b31e1481bcf84670ee5ccaf372ae55
```

Host static review confirms all 39 inventory rows, 488 distinct Python method
bodies, 21 shell drivers and 508 local links/anchors across 11 Markdown files.
Python syntax, `git diff --check` and all archived input hashes pass; these checks
execute no unit or JIT payload. The checker and output are retained with evidence.

## Spin Waiter Publication

**2026-09-12, 23:53:39-23:59:21 +08; postflight on 2026-09-13:** replace three
spin publication writes with `smp_store_release`: the combined completion word,
the lone/IRQ-native handoff and the final batch-successor handoff. The existing
early-handoff full barrier is retained. Final register copying and queue splicing
precede publication; physical owners, node layout, two-word wrapper inputs,
flags and guest-kernel code do not change. Flow and test interpretation are in
[usage 2.1](JIT_EXECUTION.md#21-waiter-发布边界).

The existing production combiner fixture now observes five release/packet/reuse
boundaries and supplies a changed output register to catch premature publication.
The simulated awakened node immediately loses its old packet, task and successor;
the publisher must preserve those reused bytes and use its saved successor.
This is a deterministic API/packet test, not a hardware memory-order litmus,
observed CPU-reordering failure or proof of every possible post-wake read.
No unit entry or routine live case is added; the inventory stays **39 programs**.

Three frozen unit phases are kept separate:

1. Against the old production stores, the new outer fixture reports **15 failed
   assertions across five publication paths**. `make` exits **2** on its first
   NUMA-off variant; later variants and mutants do not run. This establishes
   detection of the missing explicit release contract, not a live kernel fault.
2. With the production fix and five new mutants, only
   `test_spin_outer_progress.py` runs: exit **0**, **10,487 / 25,082 assertions**
   for NUMA off/on, and **10 assertion-detected mutants**. A separate affected
   `test_spin_shadow.py --mutations` run then exits **1** before its mutants:
   its old generic-release counter misclassifies ordinary batch publication as
   capacity handoff, causing 16 queue-head and 441 nested-list failures. The
   retained terminal failure log is explicitly partial/truncated.
3. Only `spin_shadow_fixture.c` changes: capacity accounting identifies the
   actual queue-head caller, retaining the owner and capacity assertions.
   Rerun only `test_spin_shadow.py --mutations`: exit **0**, both NUMA variants
   pass their 48 queue-head, 441 nested-list and producer/recursive/observer
   checks; all **nine mutants** are rejected. The earlier outer pass is not
   relabeled as a new two-program frozen run. Observer-allocation diagnostics
   belong to deliberate substituted failures, not a kernel module load.

Guest default `make -C kernel_module KDLOCK_SELFTEST=0 KDLOCK_NUMA=0 W=1 -j8`
passes. Existing assembly/RETHUNK/frame objtool and locale-fallback warnings are
retained in the log. After confirming snapshots through the live host monitor,
run only the affected complex spin cases:

```sh
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 1800s python3 -B tests/regression.py \
  --case mode-2 --case mode-6 --case mode-7 --case mode-8 \
  --case registers-1-3 --case registers-8-3 --case remote-multi-b \
  --case virtual-ticket-refusal --case remote-late-3 \
  --timeout 180 --output /tmp/kdlock-spin-publish-live.z7khuH
```

An outer SSH timeout is 1830 seconds. Exit **0**, **9/9 accepted**; unselected
cases, mutex and covered basic diagnostics are **NOT RUN**. Every case has valid
generated images, entry/lock-matched returned-body evidence and its workload
oracle. All report unchanged source, complete capture, no kernel fault and drained
callers/modules. Body counts are observations, not complete instruction coverage
or immutable code-generation identity:

| Case | Returned `body=1` witnesses | Retained contract |
| --- | --- | --- |
| `mode-2` | 4 | Single-lock JIT and four completed/resumed allowlisted hostcalls |
| `mode-6` | 4 | Three locks in one frame |
| `mode-7` | 2 | Non-LIFO outer unlock |
| `mode-8` | 2 | Nested contended/remote queues |
| `registers-1-3` | 1 | Local native suffix with original registers and owner ACKs |
| `registers-8-3` | 2 | Remote native suffix and register packet |
| `remote-multi-b` | 8 | Cross-NUMA eight-frame, multi-request/deferred progress |
| `virtual-ticket-refusal` | 1 | Real ticket/gate saturation and checked PENDING/native completion |
| `remote-late-3` | 4 | Waiter exit while a no-lock ancestor still retires |

All **204 inputs** match the corrected freeze and the 2026-09-13 **00:00:36 +08**
idle postflight. Source/build/config/running baseline checks pass before and after
with kernel 6.1.159, Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5` and
unchanged boot `e5f08f95-3b68-40f3-bc28-6a7ca42e7941`. No VM restart or guest-kernel
change occurs. Offline verification exits **0**, with nine recorded accepted
results and no unrecorded cases; it performs no payload execution or new JIT
certification. C1/C2/C5 remain open broadly. At this freeze, local guard-flags
scope was still pending, not implicitly authorized by the publication fix.

| Host evidence | Scope | `source.tar.gz` SHA256 |
| --- | --- | --- |
| `/tmp/kdlock-spin-publish-before.brR2sT/` | Old stores rejected by the new fixture | `991735dfd65faad6725c6a3b526a49ec1daa653cf037c8cf39906630d311fe7d` |
| `/tmp/kdlock-spin-publish.3wVVhI/` | Outer unit pass, separate node-counter failure | `287ddd1b1d1e9ee6c1dc406c261a7b3e61a307edb2c6bb6abd386a6bb2a0fcad` |
| `/tmp/kdlock-spin-publish-corrected.z7khuH/` | Node-unit correction, build, commands, monitor, postflight and live summary | `47e707a39625e0675999d40f64b4187b5d73c6af71460d13b07ecfa0584cea7f` |

The complete live source/log/artifact archive is
`/tmp/kdlock-spin-publish-live.z7khuH.tar.gz`; host and guest SHA256 match:

```text
91087ab8cbe924ecff385bb87c25c6c18e268757807d69e06fdd99c3fff34e04
```

## Original Waiter Exit

**2026-09-12, 23:16-23:18 +08:** extend the existing `parallel-drain-0/1`
cases with signals to their original borrowed waiters. No routine case or unit
entry is added: the inventory remains **39 programs**, with 488 distinct Python
test-method bodies after three methods are added to the existing protocol unit.
Only test workload/client/controller/oracle code changes; production lock,
translator, two-word ABI and guest-kernel code remain unchanged. Execution order,
incremental commands and limits are maintained in
[usage 6.6](JIT_EXECUTION.md#66-独立队列的并行-native-frame).

In the recovery guest, run only:

```sh
env LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 \
  timeout --kill-after=10s 1000s python3 -B tests/regression.py \
  --case parallel-drain-0 --case parallel-drain-1 \
  --case parallel-node-pressure --case native-peer-1 --case native-peer-3 \
  --timeout 180 --output /tmp/kdlock-waiter-exit-live.2gA3XC
```

The outer SSH command also has a 1030-second timeout. Exit **0**, elapsed
**120.61 seconds**, **5/5 accepted**. All five read back `mutex_jit=1`, have
valid generated images, matching post-wrapper body witnesses and correct
workload records. Per-case results report no kernel fault, unchanged source,
complete evidence and drained callers/modules; unselected cases are **NOT RUN**.

| Case | Actual JIT bodies / owner ACKs | Additional evidence |
| --- | --- | --- |
| `parallel-drain-0` | 2 / 4 | First lane 0 exits; lane 1 retains its frame and then returns after SIGUSR1 |
| `parallel-drain-1` | 2 / 4 | Reverse drain order and the same retained-owner/exit checks |
| `parallel-node-pressure` | 1 / 2 | Independent context, real node-pool and injected task refusals; a prepared second image does not execute |
| `native-peer-1` | 1 / 1 | Shared client's native interruptible cancellation regression |
| `native-peer-3` | 1 / 1 | Shared client's native killable cancellation regression |

Each dual-frame case retains the real 64-block code-pool and 1024-slot shadow
pressure, renamed waiter/native C routing, native-peer cancellation and requeue,
six exact records with 24008 transitions, and terminal retirement/reload checks.
The original waiters are single-process, single-ioctl clients. Identity-checked
pidfds send SIGKILL to the first-draining waiter and SIGUSR1 to the survivor.
Both real B/A owner ACKs and the first record complete before fatal syscall
exit. Its retained pidfd then proves exit while source reports
`DRAINING/modules=1/frames=1/writers=1` and the survivor remains alive. A bounded
test gate holds that second frame until this observation; its unchanged owners,
exact suffix/ACKs and one userspace signal return are then required. Only the
first waiter's supervisor exits 137; the other seven exit 0. The saved dmesg
prefix/hash links the intermediate observation to the final protocol log.

This proves pending-signal completion in two bounded schedules, not `do_exit`
inside a native suffix, abandoned delegated work, RCU reclamation or general
hook-reader lifetime safety. No test task reference or owner handoff is added.
C1/C2 remain open broadly; at this freeze the C5 access-time guard was awaiting
agreement on local flags preservation, and was not implemented by this test.

Before live execution, the first focused guest unit command selects
`test_mutex_parallel_protocol.py test_mutex_signal_protocol.py`. It exits **2**:
the parallel unit has four failed subtests, while the independent signal unit
passes **29 methods**. The failures are fixture issues: `Path.touch()` reaches a
mocked source-FD close counter, and a broad mutation changes an earlier native
peer log instead of the original waiter's resume log. Only the protocol unit
driver changes afterward. The corrected run selects only
`test_mutex_parallel_protocol.py`: exit **0**, **38 methods pass**, including the
actual C client's 24 fixture rounds and invalid-target checks. The earlier 29
passes are not relabeled as a new two-program frozen run. The guest workload
build `make -C klock_module W=1 -j8` also passes; existing redundant-CLD objtool
warnings and locale fallback messages remain in its log.

All **204 runtime/test inputs** match the corrected host freeze, guest postflight
and live source archive. Baseline source/build/config/running-ID checks pass
before and after: kernel 6.1.159, Build ID
`6f9f2e9fec382e97f620553793aa90b527a30af5`, unchanged boot
`e5f08f95-3b68-40f3-bc28-6a7ca42e7941`. Recovery snapshots are confirmed through
the host monitor before loading. The 23:22 +08 postflight is idle; there is no
VM restart or guest-kernel modification. Offline evidence verification exits 0
with all five recorded accepted results and no unrecorded cases; this is stored
evidence consistency, not another JIT run.

| Host evidence | Scope | `source.tar.gz` SHA256 |
| --- | --- | --- |
| `/tmp/kdlock-waiter-exit.HoHFta/` | Failed first unit selection, including the separate signal-unit pass | `b1d03d5b1deed704f803bacb7dbfd422bfe69a8a4ace97a048b7719409d7c9a8` |
| `/tmp/kdlock-waiter-exit-corrected.2gA3XC/` | Corrected unit, build, monitor, live summary and postflight | `05f02935dc2dff5d3a7accd4397cc9b93c7975be9f5fae6f8904989bbc8f9342` |

The two unit source archives differ only in `test_mutex_parallel_protocol.py`.
The corrected directory also retains `commands-results.json`, `static-check.py`
and `static.log`: the 39-entry inventory, 488 distinct method bodies, all 21
shell drivers, Python syntax, 499 local links/anchors across 11 Markdown files
and `git diff --check` pass. Host checks only inspect stored bytes and syntax;
they do not execute unit or JIT payloads.
The complete live source/log/artifact archive is
`/tmp/kdlock-waiter-exit-live.2gA3XC.tar.gz`; its SHA256 matches on host and guest:

```text
0fa0fff3cda6a7f22eda75a3a70d1eafdb288d0a58e3974b7bcab61ff8277ddf
```

## Test Inventory Review

**2026-09-12:** the initial [test inventory review](TEST_EXAMPLES.md) covers
44 unit entries (7 C and 37 Python programs), 21 shell drivers and 80 named
cases. It distinguishes the 64-case `extended` scope, 11 already excluded
diagnostics, script dispatch, production fixtures and evidence-oracle tests.
Five models are removed below after covering their retained contracts in
production tests; 39 programs remain, with distinct verification layers retained.

Before removal, host-side static checks find no missing or duplicated inventory
rows, 485 distinct Python test-method AST bodies, and 211 unchanged runtime/test
input hashes. Distinct method bodies do not prove
semantic independence. `run_all.sh --list` and the combined
`--suite mutex --suite hostcall --case mode-5 --dry-run` confirm the documented
selection, with mode 5 appearing only once. Local links/anchors, the catalog's
shell-block syntax and `git diff --check` pass.

The review corrects the former host/guest unit-test instruction, merges
duplicate script/case descriptions, and links the existing manual instead of
maintaining another full setup sequence. That static phase runs no unit or live
workloads; its evidence is separate from the subsequent production-unit check.

### Redundant Node Model Removal

**2026-09-12:** remove `tests/unit/test_spin_node_count.c`, its Makefile target
and generated-binary ignore entry. The three hand-written model checks already
have production producer/count/return coverage in `test_spin_shadow.py` and
`spin_node_pool_fixture.c`. After this first deletion, the inventory was **43
programs: 6 C and 37 Python**. No production source or live-case selection changes
in this removal.

In the recovery guest, run only:

```sh
python3 -B tests/unit/test_spin_shadow.py --mutations
```

Exit status is **0**. The production queue-head, nested-list, producer,
recursive-return and observer checks pass with NUMA off and on. All **nine
mutants** are rejected by assertions, including native/virtual full-count leaks,
cancel/native/complete/common-return leaks, double release and wrong logical
origin/task. Mutations run in the final NUMA-on temporary build; production
source is never mutated. The allocation-refusal diagnostic in the log belongs
to the deliberate fixture failure check, not a kernel module load.

Eight stale guest inputs match historical host versions and are synchronized
before testing. All **210 remaining runtime/test inputs** match the host,
frozen source archive and guest postflight. The running kernel baseline check
passes; modules and callers are idle before and after. Guest `make -n run`
confirms the removed target is absent without executing other unit programs.
This is guest-userspace production C with substituted primitives, not kernel
JIT, Linux concurrency or a full unit acceptance. No live modes are rerun.

Host evidence: `/tmp/kdlock-node-model-prune.wdFYvh/` contains `unit.log`,
`command.txt`, `timing.log`, `postflight.json`, `make-preview.txt`, the removal
patch and the 210-input `source.json` / `source.tar.gz`. Archive members and
their SHA256 hashes match the manifest. `source.tar.gz` SHA256:

```text
a8efd1fa2e015768bf2da3afcffcc39c246286b55c94f3020c03868369acc387
```

### Redundant Mutex Model Removal

**2026-09-12:** remove `tests/unit/test_mutex_transition.c`, its Makefile target
and generated-binary ignore entry after extending the existing
`test_mutex_resources.py` / `mutex_resources_fixture.c`. After this second
deletion, the inventory was **42 programs: 5 C and 37 Python**. No production
source or live-case selection changes in this removal.

The fixture now extracts the real `kd_main.c` target/selector functions, checks
cold-lock promotion with an intervening native owner, and checks routing after
rename and source closure. Borrowed A remains owned by the peer; the waiter
owns only its unrelated C, and unlocking A must use the notification path.
The retained-task route ends only after the final substituted reference is
released. The four old model contracts and their production-test replacements
are mapped in [the inventory](TEST_EXAMPLES.md#52-单元精简进展与顺序).

In the recovery guest, run only:

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_mutex_resources.py test_mutex_outer_progress.py'
```

Exit status is **0**: **2 programs pass**, with **15,953 resource checks** and
**136 outer-progress checks across five scenarios**. All **11 resource
mutants** fail assertions, including the three added selector/admission/unlock
mutants. Mutations affect only temporary extracted copies. Physical locks,
task membership, scheduling and the owner/ACK boundary are substituted; this
does not prove Linux wait-list behavior, RCU safety or actual kernel JIT. The
existing live and task-lifecycle cases are retained and are not rerun here.

All **209 remaining runtime/test inputs** match the host, frozen archive and
guest postflight. Only the two changed fixture/driver files and scoped removal
patch are synchronized. The previously verified guest boot is unchanged;
modules and callers remain idle before and after. Guest `make -n run` confirms
five C and 37 Python entries, with both removed targets and binaries absent.
No other unit programs or live modes are rerun.

Host evidence: `/tmp/kdlock-mutex-model-prune.aEMOhb/` contains `unit.log`,
`command.txt`, `timing.log`, `postflight.json`, `make-preview.txt`, the removal
patch and the 209-input `source.json` / `source.tar.gz`. Archive members and
their SHA256 hashes match the manifest. `source.tar.gz` SHA256:

```text
69ac16a756ebaa057496baa12ddd27e27ff5fd765bee4f2d808b83ad1a719b2e
```

### Frame Model Consolidation

**2026-09-12:** remove `tests/unit/test_exec_frame.c`, its Makefile target and
binary ignore entry. Extend the existing `test_exec_capacity.py` fixture with
production ledger/event functions and both backend cleanup helpers. After this
third deletion, the inventory was **41 programs: 4 C and 37 Python**. No production
code changes.

The [11-contract map](TEST_EXAMPLES.md#52-单元精简进展与顺序) records replacements
and the obsolete model behavior: early A release retains its record rather than
removing it while B/C remain. Full-context and output-packet checks cover foreign
owners and pending remote links; ledger checks cover metadata shifts, malformed
inputs and capacity. Completion waits for nested releases and remote progress.
Eight direct cleanup configurations check reverse order, already-released locks
and retained A with substituted physical operations. They do not authorize
cleanup or replay after JIT execution. The unchanged node producer's earlier GS
inheritance evidence remains earlier evidence, not a new run.

Only three guest unit programs run:

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_exec_capacity.py test_jit_entry_scope.py test_segment_codegen.py'
```

Exit status **0**: **8,010 frame checks**, **146 entry-scope checks** and segment
codegen pass. All **12 frame mutants** compile and fail explicit assertions,
including duplicate/missing-outer ledgers, shifted kind loss, repeated unlock,
premature completion, a lost logical-parent dependency and double mutex cleanup
unlock.
The entry test checks actual high-level two-word argument setup using a wrapper
substitute; the segment test checks lowering/layout. This is not a kernel-JIT,
Linux scheduling or full unit acceptance. No other units or live modes rerun.

All **208 runtime/test inputs** match host, frozen archive and guest postflight.
Only the two changed test files and checked model-removal patch are synchronized;
the old generated model binary is removed. The previously verified boot remains
unchanged, callers/modules are idle, and guest `make -n run` confirms 4 C plus 37
Python entries with all three removed model sources/binaries absent.

Host evidence: `/tmp/kdlock-frame-model-prune.bZLz1e/` contains `unit.log`,
`command.txt`, `timing.log`, `postflight.json`, `make-preview.txt`, the removal
patch and 208-input `source.json` / `source.tar.gz`. Archive SHA256:

```text
f06384211ce22b6f9914eaa7f887deb57ffbff6cd90a47c0f6b4a9f124687990
```

### Call Model Consolidation

**2026-09-12:** remove `test_jit_call_policy.c`, its target and binary ignore
entry. After this fourth deletion, the inventory was **40 programs: 3 C and 37 Python**. Existing
entry-scope and native-after-outer fixtures now compile the real service
manifest/typed adapters, dispatch/advance and nested mutex lock producer.
Clock, wrapper and physical-lock primitives are substitutes. The old remote
mutex B assumption is replaced with current same-executor native acquisition;
the [seven-contract map](TEST_EXAMPLES.md#52-单元精简进展与顺序) records the boundary.

The first guest command selects three programs:

```sh
make -C tests/unit run TESTS= \
  PY_TESTS='test_jit_entry_scope.py test_native_after_outer.py test_hostcall_codegen.py'
```

It exits **2**, with **2 programs passing and 1 failing**. Native-after-outer
passes **3,297 production checks plus four Python methods**, and hostcall
codegen passes. Entry-scope reports seven failed assertions: its test set SP to
zero before admission, so the existing scope check correctly refused before
the intended service-return failure. This is a fixture error, not a production
fix. The six entry mutants do not run on that failed attempt.

Only `jit_entry_scope_fixture.c` changes afterward: the valid root now produces
the bad SP in its substituted wrapper exit packet. Rerun only:

```sh
make -C tests/unit run TESTS= PY_TESTS=test_jit_entry_scope.py
```

Exit **0**, **823 checks and six assertion-detected mutants**. Coverage includes
all manifest flag combinations, unresolved/unknown services, typed returns,
service/control shared budgets, intact excess-CALL packets, invoke/return errors
without replay, and ordinary CALL_MISS to an allowlisted address without service
execution. The earlier two passes are not relabeled as a new three-program
frozen run. No production code, kernel baseline, live selection or JIT semantics
changes; no modules or live JIT run in either attempt.

The final **207 inputs** match host, source archive and guest postflight, with
only that one fixture differing from the failed freeze. The boot remains the
previously verified recovery boot; callers/modules are idle. Guest `make -n run`
lists 3 C plus 37 Python entries, with all four removed sources/binaries absent.

Evidence directories contain commands, logs, timings and frozen input manifests
and archives; the corrected directory also has full postflight hashes and the
Makefile preview. The removal patch is in the first directory.

| Host evidence | Scope | `source.tar.gz` SHA256 |
| --- | --- | --- |
| `/tmp/kdlock-call-model-prune.LmBbOs/` | Failed first selection, including the two separate passes | `90f444251b5f7328909771c547827127497dbec790dec2fa2560e10da25c5966` |
| `/tmp/kdlock-call-model-corrected.9XIibs/` | Corrected entry-only run | `e2dda4ff5668306ded7614078bd503cb1b3ce2015aa0ce57ae56849dfca885bd` |

### Tail Model Consolidation

**2026-09-12:** remove `test_tail_encoding.c`, its target and binary ignore
entry after moving its five checks into the existing mutex resource fixture.
The current inventory is **39 programs: 2 C and 37 Python**. The decoder is now
extracted from `kd_mutex.c` alongside the encoder; only per-CPU storage is
substituted. Fixed wire words, all 160 CPU/slot pairs and real slowpath node
identity replace the copied field arithmetic. Zero is an empty-queue sentinel,
not a valid decoder input. These are finite mutex codec checks, not spin codec
coverage or Linux per-CPU concurrency validation.

The old `mock_kernel.h` and `test_harness.h` have no remaining consumers. Remove
them and the pattern rule's unused dependencies, plus stale hash/hotlock-model
binary ignore entries. No production source or live-case selection changes.
To verify that dependency cleanup, force a rebuild of both retained C programs
and select only the affected Python fixture in the recovery guest:

```sh
make -B -C tests/unit run TESTS='test_control_call test_daemon_policy' \
  PY_TESTS=test_mutex_resources.py
```

The command is issued at **22:45:49 +08**, finishes with exit **0** in **9.34 s**,
and reports **3/3 programs passing**. The mutex fixture passes **16,768 checks**
and all **16 assertion-detected mutants**, including five new CPU/slot/sentinel
faults. Each mutant must compile and exit through a failed assertion; crashes,
compiler errors and timeouts do not qualify. The control-CALL program covers
56 phase/error combinations and post-CALL bounds; daemon error messages are
expected fault-injection branches, followed by its explicit PASS. No live JIT,
module loading or unrelated Python unit run occurs.

All **204 runtime/test input hashes** match host, archive and guest postflight.
Only two changed test files and the checked incremental removal/Makefile patch
are synchronized; obsolete model binaries are absent. The guest baseline
still matches 18 source files, nine build files, config and two bundle files,
with running Build ID `6f9f2e9fec382e97f620553793aa90b527a30af5`.
Final postflight at **22:47:19 +08** confirms unchanged boot ID and dmesg bytes,
no test callers/modules/compiler processes, and the 2 C / 37 Python inventory.
The 80-case live catalog and its selection rules remain unchanged.

Host evidence: `/tmp/kdlock-tail-model-prune.5SW8ZX/` contains `unit.log`,
pre/postflight JSON (including the command), `make-preview.log`, the checked
patch and 204-input `source.json` / `source.tar.gz`. Archive SHA256:

```text
ea76ed212bc924d85df0cb4873e4fec40dbd837c6819ba79da4d3399c69c781c
```

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
The [future packet contract](JIT_REGISTER_ABI.md#31-访问时续跑的前置契约待实现)
defines prerequisites only. At the time of this audit, local flags changes had
not received a scope decision; the later explicit deferral is recorded above.

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
