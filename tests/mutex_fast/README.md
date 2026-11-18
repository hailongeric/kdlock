# Ordinary mutex acquisition and optional delegation

The subsequent [rwsem eligibility recheck](../../bench/nano/RWSEM_READ_RECHECK.md)
adds one controlled case using the actual native wrapper and operation
predicates. It checks that completed owner progress can enable a read before
frame preparation, while retained duties and failed physical admission keep
the ordinary path. Its progress/gate endpoints are stand-ins, not a runtime
owner-retirement proof. The focused runner also exercises typed local mutex entry with the recorder enabled and disabled.

The fixed mutex checkpoint is `a1ad50e5`; its kernel11 report is referenced by
the [subsequent rwsem reader handoff](../../bench/nano/RWSEM_FAST.md). The original
scope and ABI2 discussion below describe that checkpoint. The shared eligibility
and lifecycle excerpt checks now also cover the separate fast reader record.

This candidate separates a successful ordinary native mutex acquisition from
delegation preparation. Source review is complete only when recorded with the
frozen commit; compilation, execution and performance require separate VM
receipts. The measured baseline remains `0d3fc6fb` on kernel10.

## Ordinary acquisition and contention sampling

The native typed mutex pair requires a task enrolled before entry. A new source
call checks that admission is open. It first tries to replace the empty MCS tail
with the ordinary head tag. Success gives the caller physical ownership. Each
lock has its own successor link and owner. A task may hold several such mutexes
and release them in any order. Its ordinary ownership count prevents lending
its continuation or detaching the root until all its local grants are released.

Only a failed empty-tail claim advances the task's sampling counter. Every
fourth miss reads this lock's count of ordinary waiters. With at least two
already waiting, and delegation enabled, the sampled caller can check its
native binding, execution context and retained duties and prepare a managed
request. Unsampled or shallow misses enqueue a local-only waiter on the same
MCS queue. A predecessor can select this waiter only for local execution.
While blocked, a physical owner continues to service its existing duties.

The local waiter stays on the caller's stack until it receives its turn and
moves the physical head to the lock's permanent link. If another producer
has exchanged the tail, the caller acquires that producer's final link store
before returning. Unlock either clears an empty tail or publishes the next
waiter's turn. The releasing task accesses only its own root and scalar
identities after either publication. Managed source operations and handback
continue to use the persistent request, image and release protocol.

## Focused checks for the VM session

`test_mutex_fast.py` extracts the actual fast helpers, native eligibility and
three root detach functions and the shared native validation. The C fixture
supplies controlled surrounding task/queue interfaces, records input hashes
and exercises the following bounded cases:

| Case | Required result |
|---|---|
| `reuse` | Empty-tail success, complete release, same-record reacquisition; object can become inaccessible immediately at tail removal. |
| `failed` | Existing tail, successor selection and source operation remain untouched by failed fast claim. |
| `linked` | An offered successor receives local selection/turn; its node and object can become inaccessible immediately at publication. |
| `delayed` | Producer pauses after exchange; unlock waits for the final predecessor link, then preserves the already-local selection. |
| `eligibility` | A hot sample declines a proxy offer with nested owners, pending duties, unsupported modes or an invalid native binding. |
| `typed_mutex` | Empty and nested claims, non-LIFO release, shallow and unsampled deep waits bypass native eligibility and capture. A hot sample reaches preparation. |
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

On the local 380G10 guest, the original source and original checks passed all
nine cases. Applying the idle-link assertion to that source failed the linked
and delayed handoffs. With the release-side link clear, all nine passed.
[Source test receipt](../evidence/380g10-original-main-mutex-20261117/result.json)
