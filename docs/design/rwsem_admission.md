# Atomic rwsem admission candidate

This is a source implementation and review record. It has no candidate build,
runtime, stack-bound or performance result. Kernel14 remains the historical
baseline; its validation does not cover this layout or protocol.

The selected change separates ordinary native admission from optional writer
delegation. It applies to sleepable rwsems. The rwlock guard and context lane
remain separate. Ordinary source boundaries retain the two-word wrapper ABI,
and reached generated operations retain the existing canonical S_W, original
JIT, recursive driver and exact continuation routes.

## References and chosen scope

[Linux v7.0 rwsem.c](https://github.com/torvalds/linux/blob/v7.0/kernel/locking/rwsem.c)
uses atomic admission and serialized waiting/wakeup handling.
[Its OSQ implementation](https://github.com/torvalds/linux/blob/v7.0/kernel/locking/osq_lock.c)
is an optimistic-spin queue whose per-CPU nodes require a nonpreemptible spin
lifetime. It is not a sleeping waiter queue.
[TCLock section 3.5 and Listing 2](https://www.usenix.org/system/files/osdi23-gupta.pdf)
use shared reader/writer/waiter state and reader/writer phases. This candidate
keeps KD's persistent MCS writer queue and execution engine. It introduces no
per-CPU reader counters or CPU scratch that survives a critical section.

## Admission and ordering

`kd_rw.admission` is the sole physical admission state for rwsems:

| Field | Meaning | Limit |
| --- | --- | --- |
| bit 0 | Physical writer | One |
| bit 1 | Wake actor completing final object access | One |
| bits 2–31 | Admitted physical reads | 1,073,741,823 |
| bits 32–47 | Exact writer queue reservations | 65,535 |
| bits 48–63 | Registered reader waits | 65,535 |

Checked increments reject a violated field bound before a carry can change
another field. Reader-phase conversion also checks the resulting read count.
These are representation limits, independent of the finite caller-provisioned
record capacity and its existing availability premise. There is no allocation,
storage refill or public void-lock failure policy on ordinary admission.

A reader uses an acquire CAS only when neither a writer, wake actor nor writer
reservation exists. Failed admission changes nothing. A waiting writer charges
the same word before publishing its MCS link; this closes new reader admission
while existing readers drain. An ordinary writer claims an entirely empty word.
Only the exact MCS turn holder can use queued writer admission. A withdrawn
cohort candidate keeps its one reservation through its existing off-queue duties
and rejoin; it does not charge again. Final queue departure drops it once.

Registered readers form a phase at physical writer release. Under the slow
family guard, the wake actor removes the current reader-wait list and converts
those exact waits into reserved reads. New readers cannot extend that phase
while a writer reservation remains. The next writer waits for the phase to
drain. Removing the last canceled writer reservation also reopens waiting
readers when no writer holds the gate. This is phase alternation at physical
batch boundaries, not a claim of Linux's precise waiter order, time bounds or
general nested progress.

The release CAS sets the wake bit when wakeup is needed. It blocks admission
while wakeup and the final family-guard unlock finish. Clearing the bit with
release ordering is the wake actor's last object access. Woken tasks observing
that bit retry instead of sleeping again. Without a wake duty, the release CAS
itself is the final object access. The remaining completion observations use
only scalar object addresses and independently retained task/control storage.

Reader wait publication includes a second admission probe while holding the
slow guard. This closes the specific race where a writer releases after the
first failed probe, before the reader publishes its wait. Either the release
observes the wait or the second probe observes the release. A canceled wait
retains its atomic charge through `finish_wait`; an admitted reader retains its
read through that cleanup. Phase grants are rolled back on a progress error.

Acquire/release CAS operations order critical-section effects. The slow guard
also publishes phase-grant metadata. Queue reservations and reader counts are
admission state, not substitutes for the existing exact queue, source, image,
cancel-actor and release-user lifetimes. Existing API/object retention contracts
still cover live callers and canceled queue actors.

## Ordinary call paths and release routing

For a native original task with no unresolved managed duties:

```text
ordinary down_read -> task-owned native record -> atomic read CAS
    contended -> registered reader phase wait -> same native body
ordinary up_read -> exact task-owned acquisition -> atomic read release

ordinary down_write -> atomic empty-word CAS -> same native body
    contended, delegation disabled or no admitted image -> native MCS record
    contended, eligible and image retained -> existing source/JIT preparation
ordinary up_write -> exact ordinary, native MCS, or managed release route
```

Uncontended ordinary reader paths do not call `prepare_current`, construct or
look up a delegation credit, or take `kd_rw.guard`. A contended reader uses the
guard for wait publication and phase completion. A final reader that must wake
a writer uses the release wake path. Uncontended writers also avoid source
preparation. Only eligible ordinary contended writers obtain an image use and
then enter capture. That small temporary image use is extended into the exact
persistent frame and dropped before stack switching.

Each resource frame contains a cold sibling native record with no source packet.
Its small identity and link fields serve ordinary reads; its queue fields are
initialized only for a contended local writer. Native records use a task-owned
free list independently of managed request-slot reservation. Their finite count
is the existing explicit resource capacity. This enlarges cold resource storage;
no memory or execution-cost improvement is claimed without a matching build.

All owned rwsem read kinds also join a source-ordered task list. Ordinary release
looks up its native acquisition there, without the shared active-credit guard.
Managed, callable, repeated-read and downgrade acquisitions remain distinct.
The logical source owner serializes that list, including while a proxy executes
the stopped origin's source. Nonowner reads retain their separate transferable
object-owned records. Diagnostic reader-task values remain speculative hints,
never acquisition authority or retained task references.

Older physical owners or managed grants are progressed before ordinary admission.
If they remain live, their existing common nested/retained route handles the
operation. The integer killable source route retains its existing capture,
cancellation and deferred-exit storage protocol; it is not converted into a
cancelable task-native ordinary record. Callable signal/try/nonowner operations
retain their existing object-owned records and now use the same atomic gate.
Actual readiness precedes pending-signal cancellation. Native downgrade converts
WRITE to a real READ continuously; delegated retained-read downgrade keeps the
existing physical writer and exact typed final-release route.

## Delegation control and evidence

### Single ordinary read at an inner writer boundary

The first read bridge covers one already-held ordinary rwsem read of A when its
original task attempts an eligible contended ordinary writer on distinct B.
Uncontended writers, disabled delegation and absent images keep their local
routes. Repeated reads, callable/nonowner reads, native downgrade credits and
other simultaneous owned grants are outside this bridge. It changes neither
ordinary read acquisition/release function nor the atomic admission algorithm.

After retaining an image, private preparation transfers the existing read's
metadata into a generic source grant in that same record's unused local-writer
storage. The original task and acquisition identity stay unchanged. A's atomic
read count remains continuously charged; no read operation, source prefix or
side effect is replayed. Only the guarded credit index gains a managed entry.
The single canonical S_W remains the inner writer's execution state.

Frame/image or auxiliary-entry refusal cancels private writer preparation and
restores the ordinary read metadata before local waiting. Commit requires an
actually offerable writer and records READ_PROMOTE, distinct from READ_ACQUIRE.
Local selection or a generated miss after commitment retains a complete read
grant with the existing exact native continuation. The held outer grant keeps
local service of unrelated borrowers disabled through the common service rule.

This first bridge keeps A's release on original W. A generated outer up_read
hands its exact unexecuted operation back through the existing terminal route;
it never treats the read as an episode frame. Native up_read uses the existing
credit release, source-grant close and final unlink. The atomic read is dropped
once, all object access ends before ORDINARY_RWSEM_DONE, and only then does the
original record return to its task-owned free list. An open grant and owned-read
index prevent task detach; no new lifetime counter or physical owner is added.

Focused excerpt and evidence-oracle tests distinguish private rollback,
original-owner release, exact promotion and final reuse. They do not establish
live generated execution. Scene 7 still requires its managed B enqueue, foreign
generated entry, original outer-read owner, source effects and exact retirement;
the retained kernel15 local-only result remains a failed scene.

The nano module's read-only load parameter `delegation` selects immutable runtime
`proxy_limit=16` or `0`. Zero also disables request offer eligibility; another
enabled combiner cannot select such a request. It is independent of `RB_RECORDING`.
Recorder-off means observations are unavailable, not that delegation is off.

Evidence ABI4 uses ioctl 13, 26 counters and the unchanged six 20-word generated
proof records. Old smaller snapshot commands are refused before copying. Ordinary
read/write acquisition, release and final completion observations pair exact
record/object/origin identities. A queued local writer's final completion also
requires queue completion and node retirement. These events do not fabricate
managed slot lifetimes or generated execution. Reader admission/release totals
still must match actual workload reads; ordinary and managed operation totals
must cover every completed body exactly once.

`bench/nano/run.py --scope rwsem-split --family rwsem` covers 1 and 8 workers.
KD runs select `--delegation off` or `on`; Native is the third arm. Functional
checks retain recorder-on and recorder-off cases. Timings use recording off.
The disabled mode must show a completed contended local queue witness and zero
proxy selections/generated entries/completions. The enabled mode must show an
exact foreign generated completion in a contended recorded functional case.
All three matching functional receipts precede timing. No mode is yet validated.

## Review findings and outstanding checks

Source review found and corrected the failed-probe/wait-publication lost wake
described above. It also found post-unlock reads of the admission-lane marker on
the retained guard path; releases now cache that marker before their final
object access. Counter increments and phase conversion enforce field bounds.
Both writer wait loops also retain their guarded observation of the wake bit
through the sleep decision. Re-reading it after dropping the guard could miss
the actor's final clear after an earlier wake, leaving a newly registered writer
asleep. A controlled writer excerpt case covers that exact decision interval.

The VM-only `tests/test_rwsem_admission.py` fixture compiles actual admission
functions with controlled atomic/scheduler endpoints. It includes the exact
lost-wake interleaving, fast exclusion without guard calls, reader phases,
reader/queue cancellation, downgrade, final-access invalidation and field bounds.
The existing reader-credit and writer-control excerpt fixtures retain their
guard-lane coverage, plus that controlled writer wake interval; they do not
establish the new atomic lane's integration.
The mutex-entry fixture also follows the revised preparation interface and
checks ordinary rwsem root eligibility separately from retained source capture.

Before acceptance, the benchmark session still needs a candidate build, focused
checks, actual MCS/native/managed integration and nested release tests, killable
and nonowner compatibility, final retirement, compiled stack-frame review, and
the three-arm functional/performance campaign. The full-build disk gate remains
40 GiB. The benchmark coordinator reports 54.877 GiB free after its separately
approved kernel9–11 cleanup; this source session performed no storage operation.
Kernel14 remains preserved.
