# Mutex producer preemption

The production-extraction unit driver is `mutex/test_mutex_proxy_pin.py`.
The READY candidate's initial pinned spin budget is 65,536 loop iterations and
its rolling ready window has eight slots. This live runner records those
provider metadata values. The unit driver separately forces expiry, claim and
wake interleavings; no real-time duration is inferred from the iteration count.

The live payload first performs 400,000 lock acquisitions under contention on CPUs 0–3
with the matching `target_process=kd_proxy`. It then holds a KD mutex on CPU 0,
lets CPU 2 reserve the delegation gate, publishes a head on CPU 1 and a second
producer on CPU 3, and schedules a witness on CPU 3. The witness must eventually
run before the owner releases, permitting the initial pinned grace period.
The owner has a five-second release deadline, every created
thread is joined and all four protected effects plus final lock drain are
checked. Four worker tasks record preemption, migration-disable and IRQ state
before warmup, after warmup and after their final lock pair. The witness records
entry and exit. The runner requires exactly fourteen joined-task receipts with
zero context counts/flags and the assigned CPUs. Negative receipt checks live
in `infrastructure/test_mutex_proxy_runner.py`.

Exact published waiter counts prevent a local sleeping path from passing as
delegation waiting. This proves eventual queued scheduling and restored task
state, not the precise instant at which the spin budget expires. Withdrawal
leaves a runnable preemptible waiter; it adds no parked-producer sleep/wake
protocol and does not establish general oversubscription support. The fraction
remaining in the initial pinned spin state is measured by separate optional
diagnostics, not inferred from this witness or from all lock acquisitions.

Run only in the verified recovery VM through `run.py --output <new-external-path>`.
It freezes inputs, builds provider and payload, checks the exact kernel result
and retires sources before unloading. The payload deliberately prepares no JIT
image. Proxy execution and retirement require the separate affected basic/JIT
checks; this scheduling probe alone cannot establish them.

The earlier request/ACK probe was restored from archived
`658b918a05cb930d52ccf7307b8d44d54c6d6265`. Its historical results remain
separate. These READY-policy and context-receipt changes still require their
own VM run; proxy/JIT, claim cancellation and role-exchange checks remain
separate gates.
