# Native rwsem reader fast path

This source candidate accelerates ordinary enrolled native rwsem reads. It
preserves the mutex fast path from `a1ad50e5` and leaves writer acquisition on
the existing MCS/cohort path. The current nano rwsem mix is 80% reads, so this
is a focused first step. A writer shortcut would also need to represent cohort
ownership, cancellation and real downgrade conversion; this change does not
infer those duties from the mutex algorithm. Compilation, runtime behavior and
performance require new receipts from the bench session.

## Admission and storage

The ordinary wrapper retains exact root/native binding, typed target, family,
source admission and shared native validation. Fast entry additionally requires
TASK_RUNNING in sleepable task context with IRQs enabled, no auxiliary entry,
fast mutex/read owner, logical source grants, physical batches, native grants
or pending exit, and an IDLE/RESUMABLE source operation. Unprepared Linux
bindings and callable acquisitions retain their existing compatibility path.
Signal, trylock and nonowner acquisitions are not accelerated.

Each attached root preallocates one `kd_rw_read_credit`. Its state points to the
same canonical S_W; its acquisition/user identity is that retained credit. It
contains no register packet or image use. Attachment retains task/storage and
the existing native source lease. Normal detach, unpublished-child cleanup and
canceled-root revocation refuse a held credit. Native progress includes it in
pending metadata. Completed pool records retaining a current native endpoint
stay retained; fast entry neither collects nor reuses them.

Under the existing family guard, fast admission requires no writer_pending,
writer or observed queue tail. Success adds the exact credit to active_reads
and increments the physical reader count in the same protected transaction.
Other readers can hold distinct simultaneous credits. A writer racing this
transaction must take the same guard before admission and sees the new credit.
An observed queued writer declines the shortcut; fallback uses the original
admission/wait path before any source operation completes. No failed fast
attempt changes a credit, count, queue or continuation. No writer selection,
cohort order or fairness policy is replaced; this is not a general progress
or fairness proof.

## Release, nesting and mode changes

Fast reads have a distinct `KD_RW_READ_FAST` kind in the existing acquisition
order index. Object equality is insufficient for up_read: a later managed or
callable read on the same object must release first. Both source Linux aliases
and callable up_read route through the exact latest owned credit. Nonowner
credits remain separately selected by their existing API.

The common `kd_rw_read_release()` removes the exact active link, decrements the
count and wakes waiters under the family guard. The fast release clears its
held pointer only after that function completes its final object access. It
then emits FAST_READ_DONE using scalar object identity and retained task-root
metadata. No object dereference follows that physical release. Repeated
completion fails from private metadata without dereferencing a former object.
The next own invocation may reuse the record only after this call returns.

While a fast read is held, nested source requests use the existing persistent
path with proxy readiness disabled and local service limit zero. Thus no
unrepresented read owner follows a borrowed continuation or serves another
origin. A repeated read keeps a distinct managed inner credit. An inner write
on another object retains its exact ordinary writer/cancellation record. Same-
object read-to-write upgrade receives no new success or deadlock exception.
Real downgrade, retained proxy downgrade and concurrent reader placement remain
on their existing paths. Selected generated boundaries, canonical state, GS
lowering, source leases and exact handback remain unchanged.

## Focused VM checks

Set `KDLOCK_RWSEM_FAST_TEST_CONFIG` to a JSON file with the exact running VM
`expected_release`, an existing absolute `scratch_parent`, and absolute
`compiler` path. The same shape is used by `KDLOCK_MUTEX_FAST_TEST_CONFIG`.
Only the bench session executes these checks:

```sh
python3 -B -m unittest discover -s "$nano_source/tests" -p test_rwsem_fast.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_mutex_fast.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_recording.py -v
```

The five new C cases extract actual reader and Linux release-dispatch functions:

| Case | Required observation |
|---|---|
| `credits` | Distinct concurrent reader credits, exact release/reuse, no wait setup on fast success. |
| `fallback` | Writer-held, writer-pending and queued-writer states decline without effects; the actual managed reader function subsequently waits/acquires/releases. |
| `writer` | A controlled arriving writer cannot admit until the existing exact fast reader leaves. |
| `routing` | Managed and callable inner reads take precedence over the fast outer credit; source/callable releases select the same latest owner and leave nonowner credits intact. |
| `final` | The object can become inaccessible at final family-guard release before DONE; repeated release reads only retained credit metadata. |

Writer/wait and compatibility endpoints are controlled stand-ins. These cases
do not prove actual kernel scheduling, LKMM equivalence or complete native
compatibility. The seven existing fast-owner checks additionally exercise the
shared eligibility predicate and all detach guards with the new reader record.
The twelve recorder tests cover ABI3 offsets, exact accounting, incomplete
release rejection and family separation; they retain recorder-off unavailability.

Rebuild/run the existing mutex, rwsem reader/mode and managed killable fixtures.
The reader oracle preserves pool proofs for managed credits and requires
original-task READ_ACQUIRE/READ_RELEASE/FAST_READ_DONE for fast storage. It
rejects borrowing/serving while a fast read is held. Existing concurrent-reader,
queued-writer, downgrade, repeated-read, cancellation and exact retirement
checks remain. The warm reader checks now also run a single original task with
a fast outer read and managed inner write while an image is available. A
passed source-only inspection is not any of these live results.

## Evidence and measurement

READ_ACQUIRE/READ_RELEASE retain their physical meaning. Flag FAST_READ names
task-root storage; FAST_READ_DONE follows final object access and ends that
record lifetime. No synthetic SLOT_RESERVE/FREE or JIT completion is emitted.
Nano ABI3 adds fast_read_acquired/released counts and uses distinct ioctl
`0x420c`, refusing old smaller buffers before copying. Recorded totals require
pool reservations plus fast mutex pairs plus fast reader pairs to equal actual
completed operations. All reads still require physical credit pairs. Mutex
and rwsem fast counts must match their respective families.

The [bench handoff](../../bench/nano/RWSEM_FAST.md) preserves kernel11 and older
receipts and requires a new kernel, dependent modules, current Native comparison
and separate comparisons against earlier KD versions. No performance result is
claimed for this reader candidate.
