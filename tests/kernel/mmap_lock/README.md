# Actual-mm API fixture queue observations

This fixture calls the mmap lock APIs on retained real mm objects. It is
mechanism and lifetime evidence, separate from unchanged applications invoking
their actual system calls. Native and KD modes retain the same API, signal,
downgrade, reader, IRQ-release, deferred-reference and destruction checks.

The scope3 API attempt using diagnostic harness `9d10ae77` failed its old
`phase_wait` assertion for a writer blocked behind another writer. All workers
joined and the object became idle, but the probe reported one error and stopped
before completing its checks. Preserve that failed receipt. The unprepared
scope3 writer now queues at the physical gate before reserving its phase;
killable readers still use `phase_wait`, and a writer that owns the gate and
phase waits for existing readers on `reader_drain`. One Boolean selecting
between two wait queues no longer describes these three intervals.

The correction names the waiting kind and exact worker at every call site.
A gate observation checks the retained holder's physical ownership,
closed admission, zero readers, WAITERS flag and the singleton ring's exact
worker under `gate.wait_lock`. It requires empty phase/drain queues, no
OSQ membership and no delegation. Reader-phase and reader-drain observations
retain their own exact queue, owner, phase and reader-count checks. Timed reader
drain can unlink and requeue, so a bounded observation waits for its actual
parked publication; deadline expiry remains a failed check. The controlled cases
have only the one specified acquisition waiter when sampled.
The Native branch retains its existing contention and parked-worker checks;
it does not pretend to have the KD queue topology.

The gate waiter type is private. A test-only header completes its exact
captured `list_head` plus `task` layout and flag definitions. Before building,
the runner derives the same declaration from the named harness's
`kernel_module/kd_mutex_local.c`, applies the maintained generated prefix, and
requires byte equality with that header. It retains this source hash and
copy. No unlocked waiter-pointer dereference, new kernel export or production
instrumentation is introduced. The task reference and object remain retained
until the existing ordinary joins complete.

Pending nonfatal signals must still leave killable acquisitions waiting. Fatal
cancellation must still return `-EINTR`. Before releasing the original holder,
the fixture checks exact queue removal and unchanged holder state, or the
writer's exact gate/phase rollback when draining readers. Downgrade still moves
a blocked writer from the gate to reader drainage before allowing it to enter.
Timeouts remain failures and do not establish drain or authorize forced unload.

Only this README, the API runner, payload module and test-only layout header
change. The kernel, provider, application binaries, timing runner and eligibility
policy remain frozen. Earlier classifier checks and baseline replay keep their
original `9d10ae77` identities; a fresh API result must identify this successor.
This correction is initially source-reviewed only. Compilation and live checks
run in the VM and supply their own results.
