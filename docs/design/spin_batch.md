# Bounded ordinary spin batches: pending source candidate

Base: `2592ce0b64b00e8bc0d1eda2ab766b20f5d740ec`. This source candidate
changes atomic spin only. The kernel candidate is uncompiled and unbenchmarked; focused excerpt and checker
tests have passed in the VM, as recorded below. Live batching remains unverified. Existing
rwsem diagnostics and node-wait work remain separate and pending.

## Contention admission and queue opportunity

The selected policy uses eight direct-mapped entries per physical CPU, keyed by
lock address and a nonzero object-lifetime epoch. Each first plain-spin MCS
exchange counts one acquisition; a non-NULL predecessor is a genuine contended
entry. Combiner requeues (`wait_started`) do not count again. Mutex and rwlock
entries do not contribute. The supported pinned task/IRQ-enabled context prevents
migration or concurrent task writers to this CPU-local state; no new IRQ/NMI lane
is supplied. No clocks, allocation or shared hot sampling counter are added.

Compile-time defaults in `kernel/spin_policy.h` are 100 acquisitions per window,
99 contended entries for heavy contention, and one opportunity probe per 16 heavy
acquisitions. Cold/incomplete windows stay local. A complete window classifies
the next partial window; the acquisition completing it sees the new decision.
This is a bounded window estimate, not instantaneous contention. The first heavy
observation probes immediately, then every sixteenth. Permission is captured at
the original enqueue and is not refreshed by requeue.

Only heavy, probe-due acquisition attempts inspect queue opportunity. The sample
reads at most the immediate successor and its next link once: zero/one queued
successor is insufficient. These two requests need not both be JIT ready. No
waiting, retry-to-fill, or repeated lookahead is used. After authorization, serve
available eligible requests in order, stop at the first hole or handback, and
obey the configured `proxy_limit`. Consequently races/ineligibility after the
sample can yield fewer than two foreign executions; the sample is not a promised
batch size or a contention metric. Light and probe-not-due cases remain local
even with several synthetic eligible queue entries.

`kd_spin_init` assigns a fresh lifetime epoch through a cold-only saturating
sequence. Reinitialization requires complete prior-user quiescence. No ID is
reused on sequence exhaustion; epoch zero disables sampling/delegation. Static
initializer-only objects still work locally, but require cold `kd_spin_init`
before publication to participate in batching. A changed address/epoch or cache
collision resets that slot's history rather than combining different locks.
Other CPUs have independent caches. This keeps metadata bounded; colliding locks
may repeatedly stay cold, an intentional conservative performance limitation.

## Implemented ownership and source behavior

`spin_serve_batch` requires heavy/probe-due admission, a successful two-link
queue opportunity sample and `proxy_limit` at least two. Source eligibility is
then checked per immediate request, without skipping holes. Only root spin
offers with an admitted image and no already-open logical grant can be served.
The existing configured limit bounds attempts, not a measured completed-body
count; no new default cap replaces it.

C withdraws once while retaining its own ungranted request. W1 becomes the fixed
physical MCS head; C owns one `release_owner` throughout the admitted batch.
Later W records detach from that head's queue. `detach_proxy` can redirect a
last successor's tail to the retained W1 head, so a third unconsumed successor
is not required. Each W binds a distinct acquisition/release record. The head,
owner control and active driver remain retained until all actual users end.

A successful generated body handles its logical unlock through OWNER, closes
that logical grant and returns the exact post-unlock continuation to its origin.
It does not label this physical release. The original source and return users,
release record and backing storage remain retained through actual physical ACK;
`kd_state_unlink_grant` and `kd_mutex_reap_batch` retain their existing ACK/user
checks. A same-object reacquisition reserves a new pool slot under the existing
preallocated-capacity contract. It does not reuse or wait to reuse the old slot.

A miss, required native context or nested acquisition closes admission before
exact native transfer. A nested source lock is handed back before its operation
is executed. Earlier successful origins have already been allowed to resume.
The current native suffix retains its logical grant; its SYNC unlock requests
physical release and waits for the true ACK while C pumps owner duties. There is
no replay and no copying or mixing of different origins' canonical state.

The active spin driver temporarily suppresses its own terminal-owner progress
block while it continues serving or explicitly drains that batch. The existing
`cohort_active` actor prevents reaping across individual source exports. On limit,
hole, exhaustion or handback, admission closes and C drains physical release.
Only then does C drop the driver, drain any other physical duties and rejoin once
for its own ordinary local turn. This preserves the existing off-queue ordering
needed by native suffix reacquisition. Continuous ownership ends once per batch;
queue-head status does not itself grant logical ownership to C.

The ordinary x86-64 non-RT task/IRQ/preemption contract remains. No IRQ/NMI lane,
backend lowering, rwsem/rwlock policy or mutex release protocol is added.

## Prepared checks and minimum VM handoff

`tests/test_spin_batch.py` is VM-only and requires
`KDLOCK_SPIN_BATCH_TEST_CONFIG` with exact `expected_release` and existing absolute
`scratch_parent` and `compiler` paths. It compiles production batch, release and
reaping excerpts against controlled source/queue endpoints. Eighteen prepared
cases cover zero/one/two successors, limit and local-only operation, initial and
later holes, one eligible body after a sufficient raw queue sample, handback/nesting, same-origin distinct-record reacquisition, and
independent source/return/result users through ACK and retirement. Policy cases
cover cold windows, 98 versus 99, probe cadence, lock/CPU isolation, epoch reuse,
collision reset, saturation, light queues, probe-not-due queues and no requeue
resampling. The witness
checks two foreign callback bodies, one unchanged physical owner, no intervening
release/rejoin, one final backend release and remaining-queue handoff. Counters
alone do not satisfy the witness. The extractor regression and all eighteen cases compiled and passed in the VM on
`7.0.0-38-kdrebuild16`. Their native callbacks do not establish generated-body or
weak-memory behavior. The extractor now excludes the `detach_proxy` forward
declaration and requires exactly one function definition.

The benchmark session must pin the exact spin-only candidate, source/config/compiler and modules, check
idle/recovery/space, build the affected core/fixture and run only focused tests.
Then a real spin fixture must establish complete heavy windows on its participating
CPUs for the exact lock incarnation and select a probe-due acquisition. Keep
source/image readiness separate from this policy preparation. Stage two eligible
foreign JIT bodies and join
SELECT_PROXY, GRANT, logical unlock, origin continuation, PHYSICAL_BEGIN/END,
queue/result/source/return drops and NODE_RETIRE_READY by exact owner/acquisition.
Both foreign body completions must precede one actual physical release, with no
intervening acquire/release or combiner requeue. Include zero/one successor,
policy-light/strong, cap, eligibility hole, miss, nested handback, same-lock
reacquisition and proxy-off cases. Preserve failure and incomplete evidence.
No matched performance or TCLock parity claim is available.

Source inspection and preservation checks are separate from this unrun VM work.
Live core validation requires a separate exact candidate build and boot. A
spin-only candidate commit may be prepared with a separate index and branch ref;
main, its original index and the pending rwsem working tree must remain unchanged.
Integration into main requires successful focused validation of that exact candidate.

## Focused continuous-ownership JIT test

Run `tests/kernel/spin/run_spin_batch_fixture.py` in the designated VM with the
same explicit identity, immutable-text, auxiliary-stack, source limits, event
capacity and six distinct CPU arguments as `run_spin_runtime_fixture.py`. The
module must be rebuilt from these fixture sources against a kernel containing
the spin candidate. A successful run on an older core is not accepted evidence.
Use the existing exact kernel ELF/configuration/GS receipts and recovery checks;
do not modify a frozen benchmark kernel or infer recovery from a timeout.

This entry point runs only the focused spin scene and required publication and
shutdown plumbing. Scene zero is enabled only for the spin fixture. H holds A;
C, W1 and W2 enqueue in observed order on A before H releases it. The independent
B holder supplies no protected source effect. Each round checks all five tasks,
three exactly-once A effects and ordinary callee effects, original contexts and
complete lock drain. The same lock incarnation and C CPU persist across rounds.
The runner permits at most 164 rounds, observes every genuine contended C entry,
and allows source learning at the policy's 16-acquisition probe intervals after
the initial 100-acquisition window. It never sets policy counters or shortens the
production window. Every round and all failed/incomplete evidence are retained.

Acceptance requires two distinct foreign origins, canonical states and acquisition
records, generated entry/normal exits and exactly one typed unlock each, followed
by their proxy returns before one physical release callback. Both grants must name
one owner on the same object. No intervening other owner, release or C requeue is
allowed. Existing exact source-drop, ACK, record retirement and slot-free checks
apply to both requests; the image stays fixed throughout the accepted round.
Empty feedback and ordinary archival/destroy/unload complete the successful run.
A selection count, image publication, native callback or handed-back suffix cannot
satisfy this witness.

Eight focused checker regressions passed in the VM, including negative examples
for separate owners, absent JIT entry, native execution, handback, intervening
release, different objects and C requeue. These synthetic records test rejection logic only. The
live scene has not run: the inspected VM remains on `7.0.0-38-kdrebuild16`, not a
kernel built from this spin candidate. No two-foreign-JIT-body runtime result or
performance improvement is claimed. Keep the candidate unmerged until that exact
kernel/module/image run succeeds.

[Focused VM receipts](../../tests/evidence/spin-batch-focused-20261113/README.md).
