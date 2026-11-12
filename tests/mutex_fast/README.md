# Task-owned mutex fast path

The fixed mutex checkpoint is `a1ad50e5`; its kernel11 report is referenced by
the [subsequent rwsem reader handoff](../../bench/nano/RWSEM_FAST.md). The original
scope and ABI2 discussion below describe that checkpoint. The shared eligibility
and lifecycle excerpt checks now also cover the separate fast reader record.

This candidate separates a successful ordinary native mutex acquisition from
delegation preparation. Source review is complete only when recorded with the
frozen commit; compilation, execution and performance require separate VM
receipts. The measured baseline remains `0d3fc6fb` on kernel10.

## Eligibility and ownership

`prepare_current()` retains the existing attached-root, exact native binding,
family, source admission and typed-target checks. Fast acquisition additionally
requires ordinary mutex lock, TASK_RUNNING in sleepable task context with IRQs
enabled, no auxiliary entry, no active fast owner, no logical grants, no tracked
physical batches, no native compatibility grants, no pending exit users and an
IDLE or RESUMABLE operation. Finished pool storage may still retain the current
native endpoint; fast entry neither collects nor reuses that storage.
Fast acquire and release call the same native validation as the progress path,
including exact pool/state/resource and physical-owner-task consistency. Only
the progress work is skipped. Pending metadata includes a held fast record.

Each attached root has one `kd_mutex_fast` record. Its embedded queue head has
no source grant, release batch or second packet. Cold attachment initializes
the only fields used by this lane. The root retains both storage and its exact
task until matching unlock completes; every root detach route refuses a held
record. The existing task enrollment retains the native source lease. A native
fast body needs no image use or per-operation source capture.

A compare/exchange from NULL to that head in the existing `lock->tail` is the
unique execution selection and actual physical acquisition. A failed compare
publishes nothing and falls through to the ordinary persistent-request path
before any source operation completes. A fast head is never queued behind a
predecessor, offered, combined, canceled or selected as another head's successor.
Only a later producer's final `head.next` store exposes the fast record to
another task. The mutex object remains the same two-pointer layout; the task
root layout changes and requires rebuilding the kernel and dependent modules.

Matching native unlock checks the exact record/object/task. It either removes
that head from tail or waits for the producer's final predecessor-link store,
selects the normal mutex successor locally and publishes its MCS turn. It uses
the existing condition publisher, which retains the successor task before
publication and does not read its node afterward. No lock-object access follows
tail removal or turn publication. Only then can this root reuse its fast record.
The lock's batch owner pointer remains NULL during this local grant; tail is
the physical queue authority. All users must use this same mutex protocol.

## Nested and excluded paths

A fast owner stays on its original task. While it is held, nested acquisitions
use the existing persistent local queue path with proxy readiness disabled and
local service limit zero. Thus the owner neither lends its own continuation
nor serves another origin while holding this untransferred record. Distinct
nested grants retain their ordinary records and exact source state. Non-LIFO
fast A unlock physically releases A while local B remains held. Reacquiring A
while B is held uses the ordinary path; sequential A unlock/reacquire can reuse
the fast record only after the first handoff's final access.

Rwsem/read grants, spin/rwlock, mode changes, killable/cancelable operations,
compatibility APIs and existing delegated/deferred duties are not accelerated.
Their queue, cancellation, downgrade and retirement protocols remain in place.
This candidate adds no transfer of fast owners, mixed-family support, arbitrary
nesting/progress result, or general kernel replacement claim. Existing typed
pre-operation boundaries, UB-derived JIT/GS lowering and exact native handback
remain unchanged. Recursive locking of an already-held nonrecursive mutex is
not given a new success path.

## Focused checks for the VM session

`test_mutex_fast.py` extracts the actual fast helpers, native eligibility and
three root detach functions and the shared native validation. The C fixture
supplies controlled surrounding task/queue interfaces, records input hashes
and runs seven bounded cases:

| Case | Required result |
|---|---|
| `reuse` | Empty-tail success, complete release, same-record reacquisition; object can become inaccessible immediately at tail removal. |
| `failed` | Existing tail, successor selection and source operation remain untouched by failed fast claim. |
| `linked` | An offered successor receives local selection/turn; its node and object can become inaccessible immediately at publication. |
| `delayed` | Producer pauses after exchange; unlock waits for the final predecessor link, then preserves the already-local selection. |
| `eligibility` | Nested owners, pending source/physical/native duties, other families/modes/cancellation and unsupported contexts decline fast entry. |
| `lifetime` | Normal detach, unpublished-child detach and canceled-root revoke retain a held record; ordinary cleanup succeeds after release. |
| `native_checks` | Source/context, exact binding, pool/state/resources and physical-task consistency checks remain required. |

The C stand-ins do not establish LKMM equivalence, actual kernel scheduling or
full lifecycle integration. Run them only in the VM. Supply an existing scratch
directory, compiler and the exact running VM release in a JSON file:

```json
{
  "expected_release": "REPLACE_WITH_VERIFIED_VM_RELEASE",
  "scratch_parent": "/REPLACE_WITH_VM_SCRATCH",
  "compiler": "/usr/bin/gcc"
}
```

Set `KDLOCK_MUTEX_FAST_TEST_CONFIG` to that JSON's absolute path, then run:

```sh
python3 -B -m unittest discover -s "$nano_source/tests" -p test_mutex_fast.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_recording.py -v
```

The existing mutex runtime fixture now checks exact fast pairs in each completed
case, single-task fast success without a pool request, and nested/non-LIFO native
execution with an admitted image. Its controlled five-task scenes require the
two fast holders to hand off to actual queued successors before the unchanged
recursive JIT and retirement proofs. A fast owner may neither appear as borrowed
origin nor serve another origin. Existing rwsem mode/reader and killable fixtures
remain the directly affected shared-root regression checks.

FAST_ACQUIRE/FAST_RELEASE are separate from SLOT_RESERVE/SLOT_FREE. Nano evidence
ABI2 adds two counts and exact pair checks. It uses a distinct evidence ioctl
so a stale smaller buffer is refused before any copy. The workload ABI, body,
postwork, proxy limit, trace subscription and recording selection are unchanged. For each
worker, pool reserved equals freed, fast acquired equals released, and reserved
plus fast acquired equals completed operations. Read credits and JIT witnesses
retain their existing checks. Rwsem phases reject fast mutex counts.
Recorder-off evidence stays unavailable.

The [bench handoff](../../bench/nano/FAST_MUTEX.md) pins the baseline, rebuild
requirements and unchanged small measurement scope. No test in this guide is
reported as run merely because its source exists.
