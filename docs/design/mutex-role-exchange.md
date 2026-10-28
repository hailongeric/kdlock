# Mutex queued role exchange candidate

This source adds a scoped queued role exchange to the owner handoff introduced
at `ee7ace6684b5257ae08d82648e9e2dcb4ceb8986`. It starts from
`40353f4f00d8ce571e8de7e57edac930e369e3f7`. Initial source review and fixtures
were implementation work only. Subsequent live work exposed the native-mutex
accounting failure recorded below; the source correction requires its own
validation. Earlier owner-handoff passes do not validate queued role exchange.

The case is a delegated ABI2 mutex body executing on combiner C for waiter W.
A recognized ordinary spin acquisition makes one CAS. If it fails while the
frame owns only its root mutex A, the candidate can make W the physical owner
and requeue C's original request. Multi-owner/remote frames retain the existing
borrowing protocol. A source-lease or custody-reservation refusal occurs before
queue edits and retains the existing owner-handoff/native fallback.

## Queue and storage lifetime

The implementation uses existing preallocated slots and preserves the two-word
wrapper ABI. A node's 168-byte `regs` packet becomes a custody record only after
W copies FULL to its original stack. Existing node identity, task, lock, count
generation and CPU-slot reservation remain live; static layout assertions still
require the 320-byte node and packet offset 128. A task record gains one exact
custody-node pointer. No frame or shadow stack moves between CPUs.

1. C obtains an independent source/provider lease and reserves W's existing
   task route before any irreversible queue or owner change.
2. C appends its same unstarted MINIMAL node at the current tail. Its original
   counted membership remains live; it is neither counted again nor replaced
   by a captured runtime continuation. Only then does C retire W's publication,
   finish any delayed predecessor link, and rejoin the deferred prefix.
3. C transfers A's nonzero physical owner word to W with PICKUP, preserving
   native waiter/handoff flags. The gate stays occupied. C publishes W's FULL
   native packet and transfer offer without waking the retained successor.
4. W ends its counted waiting interval, copies FULL, consumes PICKUP, installs
   the queued head/source lease/generation in its retained node and clears its
   old-frame pointer. Its release ACK is the last access to C's frame.
5. C validates that ACK against the task route, node generation, queue head,
   its own still-published request and W's physical ownership. The distinct
   `KD_EXEC_EVENT_OWNER_TRANSFER` / `KD_EXEC_FRAME_TRANSFERRED` transition allows
   frame retirement. It does not record OUTER_UNLOCK, mark any lock released or
   count a completed JIT/native body.
6. After popping its own frame and dropping its old batch lease, C release-stores
   READY into W's node as its final access to that node. C returns to the normal
   result wait on its original node. It does not reacquire A through a node-less
   gate path. W waits for READY before executing its native suffix.

These operations are in
[`combiner.inc`](../../kernel_module/mutex/combiner.inc),
[`custody.inc`](../../kernel_module/mutex/custody.inc),
[`clobber.inc`](../../kernel_module/mutex/clobber.inc),
[`native.inc`](../../kernel_module/execution/native.inc) and
[`frame_lifecycle.inc`](../../kernel_module/execution/frame_lifecycle.inc).
W retains migration exclusion, its node's `lock` identity and the reservation
through final custody cleanup. A same-CPU task therefore cannot publish a pinned
A waiter that prevents W from resuming. Public spin acquisition also remains
local while that migration exclusion is active.

## Combining at W's logical unlock

W first finishes its own source suffix. Its ordinary public or callable A unlock
then finds the exact custody route before ordinary release routing. In a safe
context, the combiner runs with `after_body=true`: W's own body is already done.
The same translated C entry can contain the supported nested controls and
native exits. There is no new image classifier or trusted-source rejection.

If C reaches a native boundary, the ordinary continuation protocol retains a
new frame on W's CPU. C is now able to resume because its old frame was already
retired before READY. C's unlock ACK returns to this new W frame, so there is no
dependency on the former C frame. If C unlocks A while a nested B remains held,
the existing release hook detaches A's queue; W finishes B/native ACKs and returns
without reacquiring A. Otherwise the final after-body boundary releases A once
and wakes the retained queue head. Another queued role exchange is disabled in
this after-body batch; the established native borrowing/owner-handoff paths remain.

W's task route, source lease, slot and migration exclusion survive until that
release and all newly retained C frame/ACK obligations have ended. Cleanup clears
the exact task route, retires the custody record, drops its lease, releases the
reserved node and drops W's original acquisition reference. Post-unlock code
must observe none of those custody resources still live.

## Native nesting boundary

W may unlock A before releasing a native spin B or a native KD mutex X. Running
C under that unrelated held lock can introduce a wait that did not exist in the
source. The candidate therefore releases A and wakes the queue head for normal
acquisition instead of combining when IRQs/preemption remain disabled, W's CPU
already has an execution frame, or its native KD mutex ledger is nonempty.

The exact bounded ledger records successful KD mutex acquisitions during W's
native suffix: ordinary DIRECT fast/slow paths, callable/local operations,
successful signal/try/I/O paths and the legacy OUTER inline CAS. Matching local
releases remove the exact address. Overflow conservatively disables combining
for this custody interval without rejecting native acquisitions. The ledger is
inactive during W's after-body combining, where the execution frame already owns
the exact nested-lock records. A per-CPU presence hint avoids task-record lookup
when no custody exists; it never authorizes ownership. The legacy inline pair
needs the exported hint and cold acquire-note symbol. Their ordinary-path cost
requires measurement.

**Untracked Linux Native sleeping locks, KD rwsem reads/downgrade, and locks held
before the root acquisition remain unsupported contexts for this exchange.**
For example, W can acquire `kd_down_read(R)` in its native suffix, release spin B,
and reach `kd_mutex_unlock(A)` while still holding R. Without a reader ownership
record, C's `kd_down_write(R)` could wait for W, while W is executing C and cannot
reach `kd_up_read(R)`. A zero preemption count does not rule out this cycle.
Native Linux mutex ownership has the same observation gap. No rwsem-read guard
is added here; its API and generated-MM dependencies require a separate change.
These are runtime context limitations, not a change to trusted translation.
The candidate does not establish arbitrary nesting or whole-kernel replacement.

## Observed native-mutex accounting failure

The live `w-early-mutex` case at `2d4ee3df` reached the duplicate-lock BUG in
`kd_mutex_custody_native_acquire`. W stopped while holding A and its native inner
mutex M, and C remained waiting. This is a failed, undrained execution, not a
timeout-based cleanup opportunity or a completed correctness checkpoint.

The composed source path explains the failure:
`kd_mutex_lock_entry` calls `kd_mutex_trylock_fast`, which calls
`kd_mutex_outer_trylock`. The successful inline CAS already records M through
`kd_mutex_note_native_acquire`; the public-entry layer then recorded that same
acquisition again. The correction removes only the second note. The inline
OUTER pair still records its successful CAS, and the exact duplicate-entry BUG
remains. Local/signal/I/O success is recorded by `kd_local_lock_state`; trylock
records its own success. Failed acquisition and continuation pickup through
`kd_mutex_transfer_pickup` add no acquisition event.

The earlier resource fixture substituted the fast helper, while the custody
fixture called its ledger directly. Neither composed these layers. The new
`mutex/test_mutex_custody_acquire.py` compiles the actual aliases, fast helper,
inline CAS, note hooks and exact ledger together. It also exercises local and
trylock success, failed acquisition and no-custody cases, and reinserts the
duplicate note as a negative mutation. This source-only correction does not
establish guest recovery, successful retest or performance parity.

## Validation gates

All builds and execution belong in the maintained VM after the recovery and
idle checks. The accounting correction and its new fixture remain unexecuted
until a new frozen-source validation record establishes otherwise.

- `mutex/test_mutex_custody.py` compiles the actual queue exchange, pickup,
  native ledger, custody unlock, transferred event and frame pop. Two threads
  substitute for pinned CPUs; terminal, linked, delayed-link and deferred chains,
  ACK/READY order, stale generations, source refusal, retained native locks and
  exact resource disposal have explicit checks and negative mutations. Its
  after-body combiner is a substitute, so it does not prove C JIT execution.
- `mutex/test_mutex_outer_progress.py` compiles the actual after-body loop and
  event path with modeled bodies, including C native continuation and early A
  release with retained B. Task-cache, terminal, resource, policy and diagnostic
  fixtures cover the changed records and signatures. Basic and directly affected
  execution/spin fixtures remain required; none has been run for this candidate.
- Live evidence must show a failed CAS, uninterrupted C-to-W physical exclusion,
  C's original node becoming delegatable, C's returned JIT body on W, and exact
  final source/frame/task/node/pin drain. Separate cases must exercise C native
  escape, C early A unlock with retained B, W early A unlock while native spin/KD
  mutex B remains, source closure and node reuse after the final ACK.
- Compare frozen baseline/candidate nano points with identical workload bodies,
  placement and instrumentation. The presence hint and after-body service change
  code paths; no performance-neutrality claim follows from source review.

The offer log `kd_mutex role exchange:` records the committed physical transfer
before pickup ACK. It alone proves neither accepted custody nor C execution.
Optional batch diagnostics record ownership transfers separately from refusals
and completed JIT/native bodies; those measurement schemas must not be pooled.
