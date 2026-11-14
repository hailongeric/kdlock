# Temporary ordinary rwsem wait diagnostic

Source base: `7338197a587fd84110fe710be63abafde270c02b`. The working tree
contains the temporary diagnostic and an independently selected ordinary-writer
wait candidate. Both remain uncommitted, unbuilt and unrun. The diagnostic's
configuration and task opt-in do not select the algorithm. Scene 7 remains
failed or incomplete, with foreign generated execution unverified. The probe
pilot's 41.65% slowdown makes its frequency ratios unsuitable as estimates of
normal-run behavior. Existing kernel16 KD OFF throughput was 87.55% of Native
at one worker and 13.29% at eight; no result exists for this candidate.

## Exact target helper review

Before implementation, the local kernel16 archive at
`/home/eric/vm/vm-shared/kdlock-evidence/rwsem-writer-waits-kernel16-20261113-01/`
was read. These files match its `diagnostic-manifest.json`; the core scheduler
also matches its separately stored `source-and-types.json` export.

| Target file | SHA-256 |
| --- | --- |
| `include/linux/wait.h` | `26f762288b8a5992eb895f00427f02eebf275081cb7f869889b789e597b76971` |
| `kernel/sched/wait.c` | `53061f82571cd55f20dfde25156a4347cbe9a8326416814d0cae58201252e514` |
| `kernel/sched/core.c` | `7d6a2601752ebd0424be5936db9b2705cae17389b51a4c16e6dc846b2cfd4e3f` |

The target `prepare_to_wait` (wait.c:249) clears EXCLUSIVE, takes the existing
IRQ-saving queue lock, conditionally inserts, sets task state with its barrier,
and unlocks. The diagnostic preserves that sequence and classifies insertion
under that same lock. `autoremove_wake_function` (402) removes only after an
accepted default wake; `finish_wait` (376) restores running state and completes
removal. `__wake_up_common` (92) invokes callbacks synchronously under the queue
lock. `default_wake_function` (core.c:7229) ignores its key and returns the
`try_to_wake_up` result. This result is not proof of a previously descheduled task.

## Source implementation and counter scope

`CONFIG_KDLOCK_RW_WAIT_DIAG` defaults off. When built, a cold provider can attach
one preallocated row to the physical task header for one target rwsem and a
proxy-limit-zero runtime. Nano uses separate 128-byte-aligned rows; no callback
writes the waiting task's row. No row is linked from an MCS record or borrowed
S_W. Task-root teardown removes current-task lookup through its existing route.
The provider retains rows until every worker, callback and queue user drains.

Snapshot ABI2 retains the same 41 counters; declarations are in `include/kd_rw_wait_diag.h` and the
matching decoder is `bench/nano/wait_diag.py`. Reader and writer preparation
categories are separate. Read counters distinguish direct slow admission,
reserved phase credits, successful slow-helper return and reserved-credit
rollback. These returns are not critical-section completions. Fast reads and
fast writes retain their original code; existing nano totals cover completions.
Writer reasons distinguish lack of turn, startup, cached WAKE and refused probe
READ/WRITE/WAKE bits. Reasons can overlap; only the preparation categories form
a partition. Scheduling calls and release-side WAKE retries are separate.

Broadcast requests are categorized by READ/WRITE/QUEUE/WAIT release or native
writer cancellation. A broadcaster owns a four-word stack summary passed as
the synchronous wake key. Read/write callbacks copy that pointer before calling
the existing autoremove function and touch only the summary/scalars afterward.
An uninstrumented NULL-key wake keeps its behavior and supplies no callback
count. The complete-count scope is the closed ordinary nano KD OFF lane, where
all target actors attach before entering the workload. Mixed or managed actors
are not covered by that completeness claim. JIT and reader-phase policy are not
changed. Direct MCS turn wake requests/accepted calls are separate from broadcasts;
their sink is captured before condition publication, with no subsequent node read.

The original WAKE clear remains the final lock-object access. Release counters
use already observed values, and remaining completion accounting uses only
independently retained rows. Signal/grant order, the second reader probe, cached
guarded WAKE observation, source records and canceled-node lifetimes are intact.
There are no new shared counter atomics, hot-path allocations, event records,
clock reads or actual scheduler-activation counters. Non-waking releases do not
look up a diagnostic row; release-side lookup is delayed until a WAKE duty exists.

Nano command 14 sets counter mode while its existing ioctl gate excludes workers;
command 16 returns snapshot ABI2, including `node_wait` even when counters are
off. The header is nine 64-bit words followed by the unchanged counter rows.
Command 15 is refused rather than copying a larger result into an ABI1 buffer.
CONFIG resets rows only after the same gate, exact task leaves, empty target state/wait queue and any native
pool drain. A mode change invalidates the old phase until CONFIG. Each worker
marks completion after its existing exact leave. Snapshot refuses active or
retained users; no timeout authorizes collection. Both row and temporary wake
summary storage stay valid across wake return and cancellation. Native is a
negative control with zero KD counters; unsupported builds reject ON.

## Source checks performed

`git diff --check`, Python AST parsing and source consistency checks are recorded
in `/tmp/kd-rwsem-node-wait-source-review.json`. They do not import project code,
compile C or execute helpers. The C enum and Python decoder retain all 41 ordered
counters. With both options disabled, the five affected C source units match the
base tokens after comments, whitespace and redundant grouping braces are removed.
This is source agreement, not compiled-code equivalence. The writer candidate
changes only `write_lock_common`; its selection, startup, departure and control
retirement functions retain the base source. The MCS direct-wake code is unchanged
from the preceding diagnostic change.

Static review covers no waiter access after autoremove, no node access after
turn publication, no object access after the final WAKE clear, and the pinned
target-helper hashes. The local reader/fast paths, managed rwsem/JIT/episode code,
nano body and scene-7 fixture/reader sources remain byte-identical to the base.
The earlier diagnostic receipt `/tmp/kd-rw-wait-diag-static-review.json` remains
unchanged; it identifies the preceding 19-file state rather than this candidate.

Five diagnostic helper cases remain unrun. The new VM-only
`tests/test_rwsem_node_wait.py` prepares 17 controlled boundary cases across all
four node-wait/diagnostic configurations, plus a snapshot/decoder check. It uses
actual writer-loop, turn-publication and native control-retirement excerpts;
queue/admission/scheduler endpoints are controlled. These are not real scheduler,
weak-memory, full MCS or live-kernel proofs. The helper source is uncompiled.

No host helper execution, C compilation, unit-test execution, kernel/module build,
VM command, installation, boot or benchmark occurred. The repository expressly
requires all builds, modules, tests and timing to run in the development VM
([BUILDING.md](../../kernel/integration/BUILDING.md),
lines 51-52). Its rwsem guide also confines compilation, project parsing and
execution to the VM. No relevant host-side helper exception was found.

## Narrow verification handoff

Testing belongs to the existing `bench new version kdlock` session. No VM use,
compilation, installation, reboot or benchmark occurred for this source work.
At November 13, 2026, 21:11:07 PST (November 14, 05:11:07 UTC), build2
available space was 46,665,125,888 bytes, exceeding the unchanged 40 GiB gate by
3,715,452,928 bytes. The later old-data batch left build2 unchanged. These are
external observations, not a current guarantee; recheck before future build work.
The [retention guide](../operations/build_retention.md) records the exact completed
deletions and preserved paths. No build started as part of those actions.
Do not stage running inputs, perform cleanup, or infer that this source change
has passed kernel compilation. Pin this base plus the entire uncommitted diff,
new private `.inc` files, config, target helpers and module/build identities.

After the external build gate is satisfied:

1. Pin both independent Kconfig settings from the table below. Build the target
   and Native/KD nano modules. Review changed compiled frames and callbacks; no
   whole-kernel stack bound is claimed. Keep a clean reference and verify the
   diagnostic-disabled configurations separately.
2. Run the five VM-only helper excerpt cases in `tests/test_rwsem_wait_diag.py`.
   Configuration uses `KDLOCK_RWSEM_WAIT_DIAG_TEST_CONFIG`, with the exact
   `expected_release`, existing absolute `scratch_parent`, and absolute `compiler`.
   Cases cover registration, accepted/rejected callbacks, immediate loss of waiter
   access after removal, disabled helpers and temporary-entry cancellation cleanup.
   Controlled endpoints do not establish real scheduler or MCS cancellation behavior.
   Also run `tests/test_rwsem_node_wait.py` with
   `KDLOCK_RWSEM_NODE_WAIT_TEST_CONFIG` and the same three explicit configuration
   fields. It builds four focused excerpt variants and checks turn wake before
   state publication, after publication, after the guarded check and at scheduling;
   selection preceding turn publication; head admission; reader drain and release
   before registration; cached WAKE; callable/non-atomic/unmarked exclusions;
   queued/selected cancellation; grant before signal; startup error; and try miss.
   The decoder check requires A to register every slow writer, permits B's absent
   writer registrations, rejects excess registrations, and checks both identities
   with counters off. No host execution of either helper is authorized.
3. Run directly affected existing admission (8), writer admission (12), ordinary
   native/cancellation and teardown checks, including readiness versus signal,
   canceled queue users, last-reader wake and the guarded WAKE interval. No scene-7
   retry or full suite is part of this handoff. Retain all errors/skips as unpassed.
4. Use the existing client spec with the optional boolean `wait_diagnostic` field.
   Explicit false/true select OFF/ON before CONFIG; omission preserves the old
   client interface. Collection occurs after joined workers and before runtime
   destruction. The client retains raw counters and validates complete lifetimes,
   registration partition, accepted wakes versus visits, reinsertion versus counted
   removal and global `read_direct + read_reserved = read_return + read_rollback`.
   Native/OFF must have zero KD counters. Record `node_wait` and match it to the
   expected kernel config for every A/B result, including diagnostic-OFF runs.
   Existing data/mix/completion checks remain.
5. First run fixed-work Native and KD OFF checks at 1 then 8 workers. For timings,
   turn the observation recorder and perf off; use 80% reads, one cacheline,
   post-work 256, original affinities, matched warmup and two-second duration.
   In each of the four cells run at most three OFF-ON-ON-OFF blocks on the same
   instrumented image. Separately compare instrumented-OFF to the clean reference.

Instrumentation acceptance proposal, not a measured result: median absolute
throughput shift at most 3%, every bracket-normalized block within +/-5%, and
the OFF controls within each block within 3%. Normalize a block by
`sqrt(ON1 * ON2) / sqrt(OFF1 * OFF2)`. Reject/invalidate noisy or over-budget
observations rather than extrapolating uninstrumented frequencies. Compare
each backend/worker cell separately; never pool source/config/instrumentation
identities. No algorithm performance A/B is combined with this overhead check.

## Implemented ordinary-writer wait candidate

`CONFIG_KDLOCK_RWSEM_NODE_WAIT` defaults off and depends only on the core option.
It is independent of `CONFIG_KDLOCK_RW_WAIT_DIAG` and the per-task counter opt-in.
Only `write_lock_common` uses it; no lock, record or task layout changes belong to
this algorithm candidate. The existing diagnostic task field remains separate.

| Algorithm | `KDLOCK_RWSEM_NODE_WAIT` | `KDLOCK_RW_WAIT_DIAG` | Counter opt-in |
| --- | --- | --- | --- |
| A, existing writer wait | n | n or y | independent |
| B, ordinary writers wait on their node until selected | y | n or y | independent |

Algorithm performance comparison must use matched diagnostic-OFF settings and
separate exact kernel/config/module receipts. The intended short comparison is
Native and KD OFF at one and eight workers, after affected correctness and drain
checks. No new performance measurement is available. Diagnostic overhead is a
separate comparison within each image, as described above. A matching kernel16
TCLock module/workload and its context, functional and drain receipts are missing;
this work supplies no TCLock parity conclusion.

Eligibility requires a reserved, ordinary queued writer record from the task-owned
pool, atomic rwsem admission and an uninterruptible wait. Callable/killable writers,
trylocks, managed/JIT paths and other record forms retain A. Readers, fast paths,
reader-phase policy, nested ownership, mmap and scene 7 are untouched.

The source ordering argument is:

1. Before turn, `set_current_state(wait_state)` supplies the state-publication
   barrier before the same guarded turn check. The existing predecessor selects
   under the pool guard and calls `publish_condition(next, &next->turn)`, which
   retains the task, release-publishes turn and unconditionally calls
   `wake_up_process`. No wait-queue membership is required for that wake. A turn
   already published is observed; a later publication wakes the task whose sleep
   state was already set. The first queue head publishes its own turn before this
   wait begins. The existing `native_start` still waits for final turn publication
   if the predecessor's earlier guarded selection is observed first.
2. A selected, initialized writer which cannot acquire marks the need for shared
   registration under the same guards. After unlocking it restores RUNNING and
   continues, then prepares its existing autoremove entry and repeats the complete
   guarded WAKE, turn, admission and signal checks before any reader-drain sleep.
   A release before registration is therefore rechecked. Once registered, the
   original reinsert and cached-WAKE behavior continues. A guarded WAKE observation
   still prevents sleeping even if the actor clears WAKE after guard unlock.
3. Startup, acquisition-before-signal and cancellation blocks are unchanged.
   Cancelable callable records always register as before. No new operation drops
   a queue user, task reference or grant. Canceled nodes remain retained through
   exact departure. Successful writers retain their queue/grant controls through
   the existing unlock path; unexpected startup errors retain controls as before.
4. Both existing `finish_wait` calls remain unconditional. The pinned target's
   implementation restores RUNNING and, for an empty `DEFINE_WAIT`, returns
   without taking or touching the shared queue. This covers B success or startup
   error without registration. It also preserves registered-entry cleanup.

These are source arguments, not executed progress results. No shared broadcast
was removed and no reader batching or wake-one policy was added. An accepted
low-overhead diagnostic could help decide whether turn waits plus shared scans
are material; the perturbed pilot does not establish that. Another proposed
persistent non-autoremoving entry remains unimplemented and may increase scans.

## Exact source change list

The implementation remains uncommitted. This inventory records the 21-path
source-work state before the subsequent documentation-only commit:

- `Kbuild`, `Kconfig`
- `kernel/exports.c`, `kernel/mutex.c`, `kernel/rw_admission.c`, `kernel/rw_native.c`
- `kernel/task_state.c`, `kernel/task_state.h`
- `kernel/rw_wait_diag.c`, `kernel/rw_wait_diag.h`, `include/kd_rw_wait_diag.h`
- `workload_modules/nano/api.h`, `workload_modules/nano/module.c`,
  `workload_modules/nano/wait_diag.inc`
- `bench/nano/client.py`, `bench/nano/wait_diag.py`
- `tests/test_rwsem_wait_diag.py`, `tests/rwsem_wait_diag/diag_check.c`
- `tests/test_rwsem_node_wait.py`, `tests/rwsem_node_wait/node_wait_check.c`
- `docs/design/rwsem_wait_diagnostic.md`

The candidate extends seven paths in the preceding 19-file diagnostic state:
`Kconfig`, `kernel/rw_native.c`, `include/kd_rw_wait_diag.h`,
`workload_modules/nano/api.h`, `workload_modules/nano/wait_diag.inc`,
`bench/nano/wait_diag.py` and this guide. The two new node-wait test files bring
the total to 21. The other twelve diagnostic paths retain their prior hashes.
The source implementation phase made no commit, push or VM operation. A later
documentation-only commit records current status and separately authorized cleanup;
it includes no implementation, and leaves the earlier source receipts unchanged.
