# First ordinary rwsem writer admission

This is a later source candidate layered on `204466eb`. That earlier commit
and its frozen handoff remain the current bench target. This change needs its
own build, live checks and measurements after that target; no performance gain
or executed regression result is established by source review.

## Change and ordering

`kernel/rw.c:kd_rw_writer_enter()` can grant the first immediately admissible
ordinary writer before registering a wait entry. It retains the existing MCS
turn, `writer_pending` publication and owner-progress callback. Under the same
family guard, the shortcut requires all of these conditions:

- Sleepable ordinary `TASK_UNINTERRUPTIBLE` acquisition.
- No cohort candidate, so candidate signal handling remains on its old path.
- Pending admission, unblocked owner progress and zero active readers.
- No wait entry has ever been registered by this invocation.

Success writes the same exact batch pointer, GRANTED admission, zero
`cancel_users` and cleared `writer_pending` under the guard, then returns.
It creates no wait entry or temporary cancel-task reference. Each failed
probe follows the original register-then-recheck protocol. The local
`wait_prepared` flag is set after the first `prepare_to_wait()` and never reset,
so subsequent iterations always reach `finish_wait()`, even if no scheduling
occurred. A last reader leaving between the first probe and registration is
observed by the original guarded recheck, without depending on a remembered
wakeup.

The shortcut does not compete for an MCS turn or alter queue links. The
selected turn already closed reader admission; queued writers retain their
order and cohort selection. Killable requests, canceled admission, cohort
candidates and atomic writers use the existing checks. In particular, actual
readiness still wins over a pending signal before commitment. The source
assumes the existing stable wait-state/request metadata contract; it adds no
new authority or object-lifetime rule.

The request, frame, image/source users, auxiliary-stack entry and GS capture
are unchanged. Nested requests retain their distinct acquisitions and same
canonical state. Grant publication, real/retained downgrade, physical release,
source ACK and final retirement are unchanged. No source instruction or
operation is replayed. Object and task-root layouts, wrapper ABI and evidence
ABI3 are unchanged. The optimization removes wait registration/cleanup on this
one path; it is not a bypass of delegation preparation or a measured cost share.

## Focused VM checks

Only the existing bench session runs builds and tests. Set
`KDLOCK_RWSEM_WRITER_ADMISSION_TEST_CONFIG` to a JSON file containing the exact
running VM `expected_release`, an existing absolute `scratch_parent`, and
absolute `compiler` path. The shape matches the existing reader/fast-owner
configurations. From the separately staged candidate source:

```sh
python3 -B -m unittest discover -s "$nano_source/tests" -p test_rwsem_writer_admission.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_rwsem_fast.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_mutex_fast.py -v
python3 -B -m unittest discover -s "$nano_source/tests" -p test_nano_recording.py -v
```

The eleven new cases extract the actual writer enter/grant/exit and reader
credit/gate/release functions. Wait registration, scheduler, task references,
spin guards and owner progress are controlled endpoints. The runner retains
input hashes, compiler output and per-case receipts, and refuses a missing
configuration or mismatched running release.

| Case | Required observation |
|---|---|
| `immediate` | Owner progress runs with reader admission closed; the exact writer is granted without wait registration or cleanup. |
| `drain_before_wait` | An exact reader releases before wait publication; the guarded recheck admits without sleeping and removes the registered entry. |
| `drain_after_wait` | A reader drains while waiting; the next loop still registers and performs one final cleanup. |
| `queued` | The supplied successor stays pending and its links/tail remain intact; reader admission stays closed during the writer and across its remaining queue tail. |
| `blocked` | Zero readers cannot override blocked owner progress; a ready retry still cleans up its existing wait entry. |
| `cancel` | Killable readiness wins over a fatal signal, a blocked killable request cancels without consuming its reader, and canceled admission cannot gain a writer. |
| `cohort` | An ordinary served writer still registers when a candidate exists; candidate signal cancellation prevents its subsequent grant. |
| `nested` | Distinct inner/outer writers retain separate batch identities and the same source pointer; inner release leaves the outer owner intact. |
| `downgrade` | The real conversion creates the exact shared credit before writer exit, admits a concurrent reader and releases the converted credit once. |
| `atomic` | A reader-blocked atomic writer uses relaxation and its existing admission path without sleep-wait setup. |
| `final` | After admission, family writer exit makes no object access after its final guard release; the fixture makes the object inaccessible at that point. |

These are boundary mechanism checks, not a real scheduler, queue handoff,
source-continuation or full retirement proof. The queue turns and downgrade
conversion record are explicit fixture inputs. The final-access case covers
the family hook, not the enclosing MCS release function's later queue accesses.
The four focused files define 36 units total; they remain unrun for this
candidate until the bench supplies receipts.

## Later live and measurement handoff

Use a distinct kernel release/build/boot and matching modules because `rw.c`
is built in. Keep the established recovery, idle, 40 GiB headroom, exact
source/config/ELF/Build ID/boot, fresh GS/ITS identity and ordinary drain gates.
Preserve `204466eb`, prior images, recovery data, frozen inputs and receipts.

Run the existing mutex, rwsem reader/mode and managed-killable live fixtures.
Retain their `contended-local`, `nested`, `out-of-order`, concurrent-reader,
writer-first-reader, local-real-downgrade and retained/nested-downgrade checks.
The killable runner retains readiness-before-signal, reader-drain cancellation,
queued exit before predecessor release, foreign waiter wakeup and current-borrow
drain checks. Their exact grant, physical ACK and final retirement observations
remain required; the controlled C cases cannot replace them.

After correctness, use the unchanged `native-current` harness/workloads and
the existing four functional receipts and twelve two-second timings, keeping
same-boot Native and separately identified prior KD results. Report the whole
workload separately from selected peaks. No new production observation is
added, so nano event counts cannot directly attribute time or successful entry
to this shortcut. All compilation, execution and performance work belongs to
the existing bench session; this handoff creates no second active VM campaign.
