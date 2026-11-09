# Stage (c): retained killable writers and exact retirement

This is an isolated functional candidate on `codex/unified-lock-queue-c`, not a
master promotion or a general Native replacement claim. The Stage (c) design
was committed before implementation at `7527bf2f`; the parent infrastructure
checkpoint is `28d576ba4bbba8d8539018de36bfbac854dd9996`. The implementation
checkpoint after the final reader-release correction is
`9370ae4e635bef487d16be475e37a5a1f9e27d7b`. Its focused validation is recorded
in `results.json`. Earlier source versions and unsuccessful attempts are
retained separately; their observations are not combined into one run.

The supported slice captures an integer-returning writer, arbitrates actual
readiness against the origin's signal, and executes a successful body on an
independent worker. Nested mutex/rwsem writer controls retain their own exact
request and result. Broader helper/context services remain incomplete: a
reached unsupported continuation diagnoses and calls `BUG()` rather than
silently continuing on the origin. That boundary prevents claiming unchanged
Native semantics for arbitrary callers. No mmap1 run or performance gate was
performed in this stage.

## Source and execution identity

| Item | Identity |
| --- | --- |
| Source inspection, editing and Git | `380G10` |
| Builds, compiled fixtures and live execution | VM `10.176.26.71` only |
| Kernel | `7.0.0-38-kdlock1` |
| Running kernel Build ID | `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62` |
| Boot ID | `b4c42511-d2fd-4ac7-b6b5-48650aae48b7` |
| Kernel source/output | `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source`, `/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build` |
| Schema-2 bundle | `/root/kdlock-kernel-baselines/linux70-kdlock1-20261027` |
| Recovery snapshot verified | `kdlock-builddisk-clean-20261031` |
| Topology | 64 vCPUs, two NUMA nodes: CPUs 0–31 / 32–63; 24 GiB; fixed 2 GHz, turbo off |
| Runtime preemption | `full (lazy)` |
| Focused origins | CPUs 0–3; local fixture/controller on CPU 63 |
| MM backend | Disabled in the ordinary development kernel |

The maintained `master` and unrelated work in the main checkout were not
modified. Every synchronized source tree was frozen, and synchronization and
archive creation required an idle guest. Final receipt/source hash comparisons
are recorded in `source-verification.json`, including private `.inc` inputs.
Build logs retain the existing objtool return-stack/thunk warnings; a completed
build is not a claim that all return configurations are supported.

## Preserved behaviors and their mechanisms

| Behavior | Mechanism and code evidence |
| --- | --- |
| Successful acquisition takes priority over a pending signal | `kd_wait_decide_locked` calls the actual-readiness callback before testing the logical origin's signal: `kernel_module/kd_wait_queue.c:301`. Merely selecting a request or putting a gate in PICKUP is insufficient. |
| rwsem writer readiness includes fresh reader drainage | `kd_admission_ready` requires the exact physical owner, exact selected phase identity/generation, and a fresh zero-reader observation: `kernel_module/kd_admission.c:111`. All writer entry forms use selected `-1`, without overwriting a live positive cohort. Preparation grants capture capability, not another admission encoding. |
| Failure returns `-EINTR` without executing the body | Integer capture has distinct Native-result and captured-success paths; success explicitly supplies EAX zero. Cancellation resolves before capture execution. See `include/kd_mutex_direct.h`, `include/kd_rwsem.h`, `kernel_module/kd_service_api.c`. |
| Signals refer to origin O, not executor E | The canonical node retains `logical_origin`; wait state is killable or interruptible as requested. Local nested admission on E observes O's signals. Nonfatal signals do not cancel a killable request. |
| Return while the holder/readers remain locked | Cancellation unlinks all memberships under the object guard, joins selection/cleanup custody, moves to retained guard state, completes actual tentative-owner and phase release ACKs, and only then publishes CANCEL_ACK. See `kd_wait_queue.c:250`, `kd_admission.c:273`, `kd_service.c:187`. No wait for the unrelated holder to unlock is required. |
| No error reported after committed effects | Committed roots are continuously dispatchable. A later signal cannot reverse a successful acquisition. Independent workers have no uncommitted public writer body that could strand cancellation behind someone else's body. |
| Reuse cannot consume an older invocation | Request namespace/generation, memberships, acquisition, selection, cleanup, child CALL identity and return ACK are exact obligations. Final retirement precedes reuse. Namespace is not a storage-address measurement. |
| Nondelegable requests remain on their submitter | `may_delegate` is fixed before publication. Selection refuses another physical submitter for a false node. A false nested request runs locally on its already executing E; it does not migrate to another worker. |
| Allowed nesting and early/out-of-order releases | Each child has its own request, depth, parent identity snapshot and owner record. The active continuation is unbound before a blocking child wait and rebound on the same E afterward. Returned AX and the CALL word are consumed once; released records stay retained until referenced operations retire. See `kd_service.c:339`, `execution/continuation.inc:434`. |
| Atomic-compatible final read release | Retained `kd_admission_finish_read` and ordinary `kd_up_read` end object access at the fully ordered final decrement. Writers poll or use one-tick timed rechecks. Phase reopening notifications remain distinct. No scheduler lock or deferred object pointer is added to read release. |
| Downgrade remains continuous protection | The read credit is published before writer release. The delegated read tail keeps that credit until matching `up_read`; a following writer freshly drains readers. Public `up_read` does not hide another write acquisition. |

Queued roots are migration-pinned but preemptible before the selected service
interval. The dispatcher selects committed roots by default. Origin transfers
that exact grant through physical PICKUP/ACK; its body executes only on E. The
worker reserves a CPU not hosting a captured origin. This avoids the reciprocal
pin wait within the tested nonoversubscribed scope, but requires spare executor
CPU capacity. Nested pending requests do not consume another root slot/worker.

The image keeps its exact source/image/task/stack leases through returned-body
and unlock acknowledgment. Deep or changing writer nesting uses explicit image
requirement bit 8 (value 256) plus budget-resume bit 7 (value 128), protocol
3/header 64; ordinary images retain protocol 2/header 48. Legacy execution
refuses the extra bit.
There is no new public depth-eight or allocation-error return. The tested depth
is nine; arbitrary stack/allocation pressure remains unvalidated.

## Focused checks and retained attempts

All fixtures below ran on the VM. Each attempt directory and its exact source
are retained in the archives listed in `archives.json`.

| Attempt | Source | Outcome and correction |
| --- | --- | --- |
| `stage-c-first-20261102` | `1ace3622` | Common queue: 14 deterministic topology checks pass. Compiled mutex API and generated local-MM dependencies pass. Admission exposes a callback-to-schedule delay; fixed by readiness/signal recheck before scheduling. rwsem decoder oracle and missing selector declaration fail; corrected. Initial build fails, not counted as a pass. |
| `stage-c-second-20261102` | `44b8a006` | Build passes. Admission oracle incorrectly treats WAITERS-only owner bits as a task owner; corrected. Integer rwsem image uses a normal FULL CALL for GCC's shared failure return; oracle now checks the actual CALL/return/exit contract. |
| `stage-c-local-20261102-a` | `44b8a006` | Existing local mutex kernel probe passes: 32-byte/alignment-8 layout, eight workers/160,000 operations/2,048 objects; cancellation, nesting, address reuse, exact drain and normal unload. |
| `stage-c-third-20261102` | `2adbda80` | Build, compiled rwsem facade and immutable image/upload checks pass. Production admission eight cases pass; a negative-control compile fails on an unused fake helper. Three new decoder fixtures lack required fake ABI2 symbols. Fixture setup corrected; failures preserved. |
| `stage-c-rwsem-20261102-a` | `2adbda80` | Existing local rwsem probe passes: 17 API checks, 10 cancellation checks, downgrade/publication checks, same-CPU/atomic/try/sleep cases and guarded signals; zero errors, exact retirement and unload. |
| `stage-c-fourth-20261102` | `5c4a7ee0` | Three targeted decoder methods pass. Admission passes production and first two negative controls; third control's text mutation matches twice after the scheduling recheck. Target corrected without changing production. |
| `stage-c-fifth-20261102` | `a2511373` | Admission eight cases and all three negative controls pass. Provider/observer/workload builds pass. Live publication fails because a child Python lacks the pinned environment in PATH. No API client/body starts. Modules/daemon are preserved on timeout, then independently shown idle and normally retired/unloaded after exact process checks. |
| `stage-c-sixth-20261102` | `a2511373` | Correct PATH; all 11 live phases pass and drain. Production equals `5c4a7ee0`; `a2511373` changes only fixture mutation targeting/order. |
| `stage-c-seventh-20261102` | `af28dfc1` | All 11 live phases pass after keeping committed requests continuously dispatchable and removing an extra terminal packet copy. |
| `stage-c-basic-20261102` | `af28dfc1` | One functional point each: mutex c01 and rwsem c16, four workers × 1,000 measured operations; both correct and drained. Returned JIT bodies: 1 and 4,000 respectively. Each has 48,000 warmup operations per worker. This is not timing acceptance. |
| `stage-c-eighth-20261102` | `9370ae4e` | Final build passes. Production final-access fixture and its negative control pass; local rwsem probe passes with 17 API/10 cancellation checks; all 11 retained-killable phases pass and drain. |

The earlier production bug allowed a signal published by an owner service to
reach `schedule_timeout(1)` before re-arbitration. The final-access review found
that ordinary `up_read` could inspect the object after its final credit
decrement; the optional drain wake was removed because all writer drainage
consumers already retry. The actual production reader-release function is
compiled with a fixture that makes the object inaccessible at its last credit;
an added post-final notification is a negative control. These are correctness
checks, not performance measurements.

## Meaning of the live observations

The matrix covers actual other-task killable completion; queued head/middle/tail
cancellation before holder release; selected reader-drain cancellation before
reader release; a nested LOCAL cancellation using O's signal while E retains
the parent; committed success with pending signals; mixed permission/depth nine;
early outer release and out-of-order child release; 128 repeated child calls;
and a true-permission child control. Exact counts and task identities are in
`results.json`; full events and images remain in the archives.

An `enter` alone is insufficient. The receipt pairs origin, executor, request
namespace/generation and returned completion, requires E to differ from O for
the selected root, and checks empty queues, zero phase/read credits, source
retirement and normal unload. Canceled roots never execute their bodies. The
root cancellation events are executed by O under the default committed-only
dispatch policy; the live run does not prove E-driven pending-root rollback.
The deterministic production fixture exercises that arbitration separately.

The trace's `identity` is the permanent per-CPU UID namespace from
`kd_wait_local_identity`, not the owner-record address. Distinct generations
prove distinct invocations. The 128-call loop exercises bounded record reuse;
the actual storage-reuse mechanism is source-verified at `kd_service.c:453`.
It is not physically identified by the trace field. True child permission is
exercised on the existing E, not a third task.

The final `9370ae4e` matrix records 14 other-task root enter/returned pairs,
four root cancellations and one nested cancellation. It records 145 child
grants (80 false-permission and 65 true-permission), depth nine, 128 distinct
child invocations in the repeated loop, and one downgrade/read-release pair.
Every phase ends with zero errors, no queued requests and an idle object. The
source/image and module retirement checks finish with an idle guest.

In this final run, O `45691`'s downgraded tail and O `45692`'s successor writer
both run on E `45657`. They have separate request namespace/generation pairs;
the read release and returned completion precede the successor's entry. This
is an observed fresh phase for different origin work. It does not prove the
executor's own pending writer work, and same-executor scheduling is not a
guarantee of this worker policy. The successor O wins its canonical
gate/phase/zero-reader grant before E consumes the exact transfer/PICKUP;
this is not E independently selecting and draining its own pending writer.

The `af28dfc1` read-tail phase uses O `39696` / E `39661`; the successor writer
uses O `39697` / E `39622`. It proves read-credit drainage before the next
writer, not that the same E freshly acquires its own pending writer phase. The
older `a2511373` observation used the same worker `37328` for two different
origins; that scheduling coincidence is not a protocol guarantee or a merged
result. The final checkpoint's exact identities are retained separately.

## Remaining acceptance gates

1. General retained execution lacks read acquisition, try/non-owner controls,
   spin/rwlock/IRQ/BH controls, indirect CALL service and task/context-dependent
   helper service. See `kernel_module/execution/service_control.inc`,
   `include/kd_native_terminals.def`, the retained block in `exe.c:507`, and
   the diagnosed unsupported status in `kd_service.c:474`. A reached missing
   service currently calls `BUG()`. Broad Native equivalence is incomplete;
   this candidate must remain isolated and cannot replace arbitrary kernel
   locks or mmap_lock on this evidence.
2. A missing/incompatible entry image is explicitly nondelegable before
   publication and uses local admission. That is an initial eligibility
   distinction, not instruction-level service of a reached branch. Published
   service execution has no silent origin-suffix route.
3. Source-close/replacement races, all-CPU/oversubscribed operation, arbitrary
   nesting/stack headroom, private spill allocation pressure and a blocking
   holder colocated with a pinned origin are unvalidated. A 512-byte restore
   margin assertion is not a general stack-pressure proof. Publication of
   requirements 384 does not prove an actual instruction-budget exhaustion,
   yield and resume; this matrix records no explicit budget-yield witness.
4. The killable live root is rwsem. Mutex signal variants are compiled and
   nested controls are exercised, but this receipt is not top-level live
   interruptible-mutex service coverage. Ordinary mutex has only the reduced
   functional point described above. Legacy rwlock adapter migration remains
   outside this Stage (c) receipt.
5. Explicit downgrade/read-tail execution is exercised, but same-executor
   pending-writer reacquisition, an intervening reader cohort and enabled-MM
   continuation entry remain further work. Builtin MM dependencies compile as
   general local wrappers; no mmap1-specific helper was introduced and no
   actual-MM delegation is claimed.
6. No Nano grid, baseline throughput comparison, real syscall performance,
   mmap1 throughput, fairness change or promotion was performed. Independent
   worker dispatch/wake costs and delegation batching require measurement.
   Full suites were not run. Stale extraction fixtures depending on removed
   positive-cohort helpers were not counted as passes.

Next work remains the unimplemented general continuation services and the
writer/read-tail integration gate, followed by focused MM proxy proof and
separately identified performance comparisons.
